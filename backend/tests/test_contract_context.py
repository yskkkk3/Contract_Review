"""Contract cache invalidation, isolation and nonblocking chat preparation."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace

import pytest

from app.services import contract_context
from app.services.contract_context import ContractTextCache


def test_cache_reuses_excerpt_but_isolates_users_and_versions(monkeypatch, tmp_path):
    calls = []
    path = tmp_path / "contract.txt"
    path.write_text("first", encoding="utf-8")

    def read(location):
        calls.append(location)
        return path.read_text(encoding="utf-8")

    monkeypatch.setattr(contract_context, "get_storage", lambda: SimpleNamespace(read_text=read))
    cache = ContractTextCache()
    assert cache.read(1, 1, str(path)) == "first"
    assert cache.read(1, 1, str(path)) == "first"
    assert len(calls) == 1
    cache.read(2, 1, str(path))
    assert len(calls) == 2
    path.write_text("updated contract", encoding="utf-8")
    assert cache.read(1, 1, str(path)) == "updated contract"
    assert len(calls) == 3


def test_cache_expires_and_evicts_oldest_entry(monkeypatch):
    clock = [0.0]
    calls = []
    monkeypatch.setattr(contract_context.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(contract_context.settings, "chat_contract_cache_ttl", 5)
    monkeypatch.setattr(contract_context.settings, "chat_contract_cache_entries", 1)
    monkeypatch.setattr(contract_context, "get_storage", lambda: SimpleNamespace(
        read_text=lambda path: calls.append(path) or "a" * 9000,
    ))
    cache = ContractTextCache()
    assert len(cache.read(1, 1, "oss://bucket/a")) == 8000
    cache.read(1, 1, "oss://bucket/a")
    clock[0] = 6
    cache.read(1, 1, "oss://bucket/a")
    cache.read(1, 2, "oss://bucket/b")
    cache.read(1, 1, "oss://bucket/a")
    assert len(calls) == 4


def test_failed_read_is_not_cached(monkeypatch):
    attempts = []

    def read(path):
        attempts.append(path)
        if len(attempts) == 1:
            raise OSError("temporary storage failure")
        return "recovered"

    monkeypatch.setattr(contract_context, "get_storage", lambda: SimpleNamespace(read_text=read))
    cache = ContractTextCache()
    with pytest.raises(OSError):
        cache.read(1, 1, "oss://bucket/a")
    assert cache.read(1, 1, "oss://bucket/a") == "recovered"


def test_concurrent_cache_misses_share_one_download(monkeypatch):
    entered, release = Event(), Event()
    calls = []

    def read(path):
        calls.append(path)
        entered.set()
        assert release.wait(3)
        return "contract"

    monkeypatch.setattr(contract_context, "get_storage", lambda: SimpleNamespace(read_text=read))
    cache = ContractTextCache()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(cache.read, 1, 1, "oss://bucket/a")
        assert entered.wait(3)
        second = pool.submit(cache.read, 1, 1, "oss://bucket/a")
        release.set()
        assert first.result(3) == second.result(3) == "contract"
    assert len(calls) == 1


async def test_contract_read_does_not_block_event_loop(monkeypatch):
    from app.services import chat_service

    monkeypatch.setattr(chat_service, "get_sf_client", lambda: SimpleNamespace())
    entered, release = Event(), Event()

    def load(*args):
        entered.set()
        assert release.wait(3)
        return ""

    class DB:
        def query(self, *args):
            return self

        def filter(self, *args):
            return self

        def order_by(self, *args):
            return self

        def all(self):
            return []

        def add(self, *args):
            pass

        def commit(self):
            pass

    monkeypatch.setattr(chat_service, "_load_contract_text", load)
    task = asyncio.create_task(chat_service.stream_chat(
        SimpleNamespace(content="test", parent_id=None), SimpleNamespace(id=1, file_id=None), None, DB(),
    ))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        # This coroutine runs while the storage worker is still blocked.
        assert not task.done()
    finally:
        release.set()
        await task
