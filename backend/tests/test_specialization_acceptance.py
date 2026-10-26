"""The live acceptance runner must not turn incomplete material/outages into passes."""
import argparse
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.runtime_config import RuntimeConfig


@pytest.fixture
def runner():
    path = Path(__file__).resolve().parents[1] / "scripts/eval_specializations.py"
    spec = importlib.util.spec_from_file_location("specialization_acceptance", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ocr_page_limit_rejects_partial_material(runner, monkeypatch, tmp_path):
    import pymupdf

    class Document(list):
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

    monkeypatch.setattr(pymupdf, "open", lambda _: Document([
        SimpleNamespace(get_text=lambda: "") for _ in range(11)
    ]))
    monkeypatch.setattr(runner, "get_settings", lambda: SimpleNamespace(ocr_max_pages=10))
    monkeypatch.setattr(runner, "_parse_cloud_ocr", lambda _: pytest.fail("Must not truncate"))
    pdf = tmp_path / "public.pdf"
    pdf.write_bytes(b"public sample")
    with pytest.raises(ValueError, match="truncate"):
        runner.extract_sample(pdf, tmp_path / "lease")
    assert not (tmp_path / "lease.text.json").exists()


def test_changed_sample_cannot_reuse_old_text(runner, tmp_path):
    pdf = tmp_path / "public.pdf"
    pdf.write_bytes(b"changed public sample")
    (tmp_path / "goods.text.json").write_text(json.dumps({"pdf_sha256": "old"}))
    with pytest.raises(ValueError, match="changed"):
        runner.extract_sample(pdf, tmp_path / "goods")


def test_long_coordinate_output_is_not_valid_contract_material(runner):
    with pytest.raises(ValueError, match="coordinates"):
        runner.validate_material("合同正文" * 30 + "\n26,3004,27,35,90" * 15)


def test_table_only_ocr_cannot_pass_source_fidelity_acceptance(runner):
    with pytest.raises(ValueError, match="warranty/payment"):
        runner.validate_business_material("goods", "沙发、饮水机、碎纸机，合计3969元。" * 10)


async def test_unknown_type_does_not_start_paid_calls(runner, tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "runtime_snapshot", lambda: pytest.fail("Unexpected DB read"))
    args = argparse.Namespace(directory=tmp_path, extract_only=False, types="unknown")
    with pytest.raises(ValueError, match="Unknown"):
        await runner.run(args)


async def test_provider_outage_stops_before_business_batch(runner, tmp_path, monkeypatch):
    class Unavailable(Exception):
        status_code = 502

    class Client:
        closed = False

        async def _complete(self, *_args, **_kwargs):
            raise Unavailable()

        async def chat_with_tools(self, *_args, **_kwargs):
            raise Unavailable()

        async def aclose(self):
            self.closed = True

    class Rag:
        closed = False

        async def close(self):
            self.closed = True

    client, rag = Client(), Rag()

    async def prepare(_):
        return rag

    monkeypatch.setattr(runner, "runtime_snapshot", lambda: (RuntimeConfig(), {}))
    monkeypatch.setattr(runner, "get_sf_client", lambda: client)
    monkeypatch.setattr(runner, "prepare_rag", prepare)
    monkeypatch.setattr(runner, "build_graph", lambda _: pytest.fail("Do not start the batch"))
    args = argparse.Namespace(directory=tmp_path, extract_only=False, types="technology",
                              run_id="outage", prepare_only=False)
    assert await runner.run(args) == 2
    report = json.loads((tmp_path / "preflight.outage.json").read_text())
    assert report["passed"] is False
    assert report["provider_status"] == 502
    assert client.closed and rag.closed
    assert not list(tmp_path.glob("technology.*.json"))
