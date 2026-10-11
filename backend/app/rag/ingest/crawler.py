"""Knowledge base corpus builder: crawl public SZU procurement policies + regulations.

语料分层（来源可追溯，全部为公开页面）：
- institution: 深圳大学采购合同管理制度（官网公开文本）
- regulation: 国家法律法规（民法典合同编等，人工整理的条款语料）
- template: 样例合同条款模板（自建演示语料）
"""
import re
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

# 深大公开制度页面（来源标注：深圳大学审计室 / 招投标管理中心官网）
SZU_PAGES = [
    {
        "title": "深圳大学采购管理办法实施细则",
        "url": "https://sjs.szu.edu.cn/info/1014/1087.htm",
    },
    {
        "title": "深圳大学网上竞价采购管理办法实施细则",
        "url": "https://sjs.szu.edu.cn/info/1014/1088.htm",
    },
    {
        "title": "深圳大学网上竞价采购管理办法",
        "url": "https://sjs.szu.edu.cn/info/1014/1086.htm",
    },
    {
        "title": "集中采购合同签订注意事项",
        "url": "https://bidding.szu.edu.cn/info/1029/24696.htm",
    },
    {
        "title": "深圳大学自行采购项目合同备案办事指南",
        "url": "https://bidding.szu.edu.cn/info/1029/26472.htm",
    },
]

# 外部法规（人工整理的条款级语料，源自公开法规原文）
REGULATION_SAMPLES = {
    "民法典合同编·合同订立与效力要点": """第四百六十九条 当事人订立合同，可以采用书面形式、口头形式或者其他形式。书面形式是合同书、信件、电报、电传、传真等可以有形地表现所载内容的形式。
第五百零二条 依法成立的合同，自成立时生效，但是法律另有规定或者当事人另有约定的除外。
第五百零三条 无权代理人以被代理人的名义订立合同，被代理人已经开始履行合同义务或者接受相对人履行的，视为对合同的追认。
第五百零七条 当事人超越经营范围订立合同的效力，依照本法第一编第六章第三节和本编的有关规定确定，不得仅以超越经营范围确认合同无效。""",
    "政府采购需求管理办法·合同必备条款": """第二十三条 合同文本应当包含法定必备条款和采购需求的所有内容，包括但不限于标的名称，采购标的质量、数量（规模），履行时间（期限）、地点和方式，包装方式，价款或者报酬、付款进度安排、资金支付方式，验收、交付标准和方法，质量保修范围和保修期，违约责任与解决争议的方法等。
采购项目涉及采购标的的知识产权归属、处理的，如订购、设计、定制开发的信息化产品等，应当在合同中明确知识产权归属。""",
}

# 样例合同模板（演示用，标注为自建样例）
TEMPLATE_SAMPLES = {
    "服务类合同模板·验收与质保条款样例": """服务验收标准：乙方完成服务后，应向甲方提交验收申请及完整交付材料。甲方应在收到申请后 10 个工作日内组织验收。验收合格的，出具验收合格证明；验收不合格的，乙方应在 10 个工作日内整改并重新申请验收。
质量保证期：自验收合格之日起 12 个月。质保期内发生质量问题的，乙方应在接到通知后 48 小时内响应并免费修复。""",
    "货物类合同模板·付款条款样例": """付款方式：合同签订后 7 个工作日内支付合同总金额的 30% 作为预付款；货物验收合格后支付 60%；剩余 10% 作为质保金，质保期满且无质量问题后 30 日内无息支付。
乙方应在收款前向甲方开具合法有效的发票，否则甲方有权顺延付款且不承担违约责任。""",
}


def _clean_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


async def crawl_szu_pages(timeout: float = 30.0) -> list[dict]:
    """采集深大公开制度页面 → [{"title", "source", "text"}]。失败页面跳过并记录。"""
    results: list[dict] = []
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers={
        "User-Agent": "Mozilla/5.0 (contract-review knowledge base crawler; edu research)"
    }) as client:
        for page in SZU_PAGES:
            try:
                resp = await client.get(page["url"])
                resp.raise_for_status()
                text = _clean_text(resp.text)
                if len(text) > 200:
                    results.append({"title": page["title"], "source": page["url"], "text": text})
            except Exception as exc:  # noqa: BLE001
                print(f"[crawler] skip {page['url']}: {exc}")
    return results


def load_corpus(data_dir: str | Path) -> list[dict]:
    """从 data/kb 目录加载语料 JSON/纯文本（ingest 脚本用）。"""
    data_dir = Path(data_dir)
    docs: list[dict] = []
    for layer, folder in [("institution", "institution"), ("regulation", "regulation"), ("template", "templates")]:
        for path in sorted((data_dir / folder).glob("*")):
            if path.suffix == ".txt":
                docs.append({"title": path.stem, "source": str(path), "doc_type": layer, "text": path.read_text(encoding="utf-8")})
    return docs
