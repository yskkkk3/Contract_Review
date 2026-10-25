"""多引擎文档解析：格式回退链 + 可选 OCR + 结构抽取。

引擎链（有序，失败/空文本自动降级下一引擎）：
  1. pdfplumber  —— PDF 文本层（基线，轻量）
  2. pymupdf     —— PDF 文本层（更强版面抽取）
  3. pypdf       —— PDF 纯文本兜底
  4. python-docx —— .docx 段落+表格
  5. LibreOffice —— .doc/.docx 转换兜底（系统依赖，可选）
  6. OCR(pdf2image+pytesseract) —— 扫描件 OCR（可选，需 poppler+tesseract）
  7. Cloud OCR    —— 千问视觉 OCR（显式启用后复用百炼 Key）
  8. Docling / MinerU —— 复杂版面深度解析（可选，extra: docling / mineru）

设计要点：每个引擎独立 try/except；仅接受非空文本；OCR 等重型引擎做成特性开关，
未安装依赖/未配置时静默跳过——保证 Docker 镜像默认体积可控。
"""
import json
import logging
import shutil
import subprocess
from pathlib import Path

from app.agent.prompts import load_prompt
from app.core.config import get_settings

logger = logging.getLogger("document.parse")
settings = get_settings()


def _read_text_file(path: str | Path) -> str:
    """Read common UTF-8/GB18030 text files without corrupting Chinese text."""
    data = Path(path).read_bytes()
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _clean(text: str) -> str:
    return "\n".join(line.strip() for line in text.splitlines() if line.strip()).strip()


def _parse_pdfplumber(path: str) -> str:
    import pdfplumber

    parts = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            parts.append(t)
            for table in page.extract_tables() or []:
                for row in table:
                    parts.append(" | ".join(c or "" for c in row))
    return "\n".join(parts)


def _parse_pymupdf(path: str) -> str:
    import fitz  # PyMuPDF

    doc = fitz.open(path)
    return "\n".join(page.get_text("text") for page in doc)


def _parse_pypdf(path: str) -> str:
    from pypdf import PdfReader

    return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)


def _parse_docx(path: str) -> str:
    import docx

    d = docx.Document(path)
    parts = [p.text for p in d.paragraphs if p.text.strip()]
    for table in d.tables:
        for row in table.rows:
            parts.append(" | ".join(c.text.strip() for c in row.cells))
    return "\n".join(parts)


def _parse_libreoffice(path: str, out_dir: Path) -> str:
    """.doc 等旧格式：LibreOffice 转 txt。"""
    if shutil.which("soffice") is None and shutil.which("libreoffice") is None:
        raise RuntimeError("LibreOffice not installed")
    bin_ = shutil.which("soffice") or shutil.which("libreoffice")
    subprocess.run([bin_, "--headless", "--convert-to", "txt:Text", "--outdir", str(out_dir), path],
                   check=True, capture_output=True, timeout=120)
    txt = out_dir / (Path(path).stem + ".txt")
    if not txt.exists():
        raise RuntimeError("LibreOffice convert failed")
    return _read_text_file(txt)


def _parse_ocr(path: str, out_dir: Path) -> str:
    """扫描件 OCR：pdf2image + pytesseract。需系统 poppler-utils 与 tesseract。"""
    if shutil.which("pdftoppm") is None or shutil.which("tesseract") is None:
        raise RuntimeError("OCR system deps missing (poppler/tesseract)")
    import pytesseract
    from pdf2image import convert_from_path

    parts = []
    for i, img in enumerate(convert_from_path(path, dpi=200)):
        parts.append(pytesseract.image_to_string(img, lang=settings.ocr_lang or "chi_sim"))
        if i >= 9:  # 上限 10 页，防长文档超时
            break
    return "\n".join(parts)


def _parse_cloud_ocr(path: str) -> str:
    """千问视觉 OCR：PDF 逐页转 PNG 后调用百炼 OpenAI-compatible API。"""
    import base64

    import fitz
    from openai import OpenAI

    if not settings.effective_ocr_api_key:
        raise RuntimeError("cloud OCR not configured")

    client = OpenAI(
        base_url=settings.effective_ocr_base_url,
        api_key=settings.effective_ocr_api_key,
        timeout=120,
    )
    parts: list[str] = []
    with fitz.open(path) as document:
        page_count = min(len(document), settings.ocr_max_pages)
        for index in range(page_count):
            page = document[index]
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            image = base64.b64encode(pixmap.tobytes("png")).decode()
            response = client.chat.completions.create(
                model=settings.ocr_model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{image}"},
                            },
                            {
                                "type": "text",
                                "text": (
                                    f"这是合同第 {index + 1} 页。请识别全部文字，"
                                    "保留段落和表格结构，只输出识别结果。"
                                ),
                            },
                        ],
                    }
                ],
                max_tokens=4096,
            )
            text = response.choices[0].message.content or ""
            if text.strip():
                parts.append(text)
    return "\n\n".join(parts)


# 兼容旧引擎名，现统一使用百炼千问 OCR。
_parse_deepseek_ocr = _parse_cloud_ocr


def _parse_docling(path: str) -> str:
    """Docling：复杂版面/表格结构化（重型，需 pip install docling）。"""
    from docling.document_converter import DocumentConverter

    result = DocumentConverter().convert(path)
    return result.document.export_to_markdown()


def _parse_mineru(path: str) -> str:
    """MinerU：PDF 深度解析（重型，需 pip install mineru / magic-pdf）。"""
    from magic_pdf.data.data_reader_writer import FileBasedDataReader
    from magic_pdf.data.dataset import PymuDocDataset

    ds = PymuDocDataset(FileBasedDataReader("").read(path), path)
    result = ds.apply(ds.pipe_txt_mode if hasattr(ds, "pipe_txt_mode") else ds.pipe_ocr_mode)
    return "\n".join(result.get_content_list() or [])


# 引擎注册表：名称 -> 可调用（返回文本）
def _registry():
    enabled = [e.strip() for e in settings.doc_parser_engines.split(",") if e.strip()]
    eng = {
        "pdfplumber": _parse_pdfplumber,
        "pymupdf": _parse_pymupdf,
        "pypdf": _parse_pypdf,
        "docx": _parse_docx,
        "libreoffice": _parse_libreoffice,
        "ocr": _parse_ocr,
        "cloud_ocr": _parse_cloud_ocr,
        "deepseek_ocr": _parse_deepseek_ocr,
        "docling": _parse_docling,
        "mineru": _parse_mineru,
    }
    return {k: v for k, v in eng.items() if k in enabled}


def extract_text_from_file(path: str, suffix: str | None = None) -> str:
    """按文件后缀选择引擎子链，逐级降级直到得到非空文本。"""
    suffix = (suffix or Path(path).suffix).lower().lstrip(".")
    out_dir = Path(settings.oss_bucket_dir) / "libreoffice"
    out_dir.mkdir(parents=True, exist_ok=True)
    registry = _registry()

    if suffix == "pdf":
        chain = [
            "pdfplumber",
            "pymupdf",
            "pypdf",
            "docling",
            "mineru",
            "ocr",
            "cloud_ocr",
            "deepseek_ocr",
        ]
    elif suffix in ("docx", "doc"):
        chain = ["docx", "libreoffice", "docling"]
    elif suffix in ("txt", "md"):
        return _clean(_read_text_file(path))
    else:
        chain = ["docx", "libreoffice"]

    for name in chain:
        fn = registry.get(name)
        if fn is None:
            continue
        try:
            text = fn(path, out_dir) if name == "libreoffice" or name == "ocr" else fn(path)
            text = _clean(text)
            if len(text) >= 30:
                logger.info("parse ok: engine=%s suffix=%s len=%d", name, suffix, len(text))
                return text
        except Exception as exc:  # noqa: BLE001
            logger.warning("parse engine %s failed for %s: %s", name, suffix, exc)
    raise ValueError(f"所有解析引擎均失败或文本为空: {path}")


def extract_text_from_pdf(path: str) -> str:
    """兼容旧调用。"""
    return extract_text_from_file(path, "pdf")


async def extract_contract_meta(text: str) -> dict:
    """LLM 结构化抽取甲乙方与金额（async；无凭据/超时等失败时返回空，不影响上传）。"""
    from app.rag.client import get_sf_client

    try:
        sf = get_sf_client()
        raw = await sf.chat(messages=[{"role": "system", "content": load_prompt("contract_extract")},
                                      {"role": "user", "content": text[:6000]}],
                            model=settings.llm_chat_model, model_type="chat", temperature=0, max_tokens=256)
        data = json.loads(raw)
        return {"party_a": data.get("party_a", ""), "party_b": data.get("party_b", ""), "amount": data.get("amount", "")}
    except Exception:  # noqa: BLE001
        return {"party_a": "", "party_b": "", "amount": ""}


# ===== 兼容层：保持旧接口（contracts.py 等调用方） =====
def parse_document(path: str, file_type: str) -> str:
    """解析文档为纯文本：file_type 可为 'pdf'/'docx'/'doc'/'txt'/'md'。"""
    suffix = file_type.lower().lstrip(".")
    return extract_text_from_file(path, suffix)


def extract_text_from_docx(path: str) -> str:
    return extract_text_from_file(path, "docx")


def extract_text_from_doc(path: str) -> str:
    return extract_text_from_file(path, "doc")


async def extract_contract_info(text: str) -> dict:
    """LLM 结构化抽取甲乙方与金额（async 包装）。"""
    return await extract_contract_meta(text)


def _parse_json(raw: str) -> dict:
    import json
    import re

    m = re.search(r"\{[^{}]*\}", raw)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return {}


def _clean(val: str) -> str:
    return (val or "").strip()
