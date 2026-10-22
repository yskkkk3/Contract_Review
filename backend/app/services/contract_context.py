"""Bounded, version-aware cache for contract excerpts used by chat."""
import time
from collections import OrderedDict
from concurrent.futures import Future
from pathlib import Path
from threading import Lock

from app.core.config import get_settings
from app.core.storage import get_storage

settings = get_settings()


class ContractTextCache:
    def __init__(self) -> None:
        self._lock = Lock()
        self._entries: OrderedDict[tuple, tuple[float, str]] = OrderedDict()
        self._pending: dict[tuple, Future] = {}

    def read(self, user_id: int, file_id: int, location: str) -> str:
        # Uploaded OSS objects have unique names; local edits also invalidate immediately.
        version = None
        if not location.startswith("oss://"):
            stat = Path(location).stat()
            version = (stat.st_mtime_ns, stat.st_size)
        key = (user_id, file_id, location, version)
        ttl = settings.chat_contract_cache_ttl
        limit = settings.chat_contract_cache_entries
        if ttl <= 0 or limit <= 0:
            return get_storage().read_text(location)[:8000]
        with self._lock:
            cached = self._entries.get(key)
            if cached and cached[0] > time.monotonic():
                self._entries.move_to_end(key)
                return cached[1]
            self._entries.pop(key, None)
            pending = self._pending.get(key)
            owner = pending is None
            if owner:
                pending = Future()
                self._pending[key] = pending
        if not owner:
            return pending.result()
        try:
            text = get_storage().read_text(location)[:8000]
            with self._lock:
                self._entries[key] = (time.monotonic() + ttl, text)
                self._entries.move_to_end(key)
                while len(self._entries) > limit:
                    self._entries.popitem(last=False)
            pending.set_result(text)
            return text
        except BaseException as exc:
            pending.set_exception(exc)
            raise
        finally:
            with self._lock:
                self._pending.pop(key, None)


contract_text_cache = ContractTextCache()
