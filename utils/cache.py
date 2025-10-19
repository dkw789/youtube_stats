from __future__ import annotations

import json
import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union


class CacheTTL(Enum):
    """Predefined cache durations."""

    HOUR = timedelta(hours=1)
    DAY = timedelta(days=1)
    WEEK = timedelta(weeks=1)
    MONTH = timedelta(days=30)


@dataclass(frozen=True)
class CacheEntry:
    """Metadata stored alongside cached payloads."""

    timestamp: datetime
    payload: Any

    @classmethod
    def load(cls, content: dict) -> "CacheEntry":
        return cls(
            timestamp=datetime.fromisoformat(content["timestamp"]),
            payload=content["data"],
        )

    def dump(self) -> dict:
        return {
            "timestamp": self.timestamp.astimezone(timezone.utc).isoformat(),
            "data": self.payload,
        }


def _normalize_ttl(ttl: Optional[Union[CacheTTL, timedelta, int, float]]) -> Optional[timedelta]:
    if ttl is None:
        return None
    if isinstance(ttl, CacheTTL):
        return ttl.value
    if isinstance(ttl, timedelta):
        return ttl
    if isinstance(ttl, (int, float)):
        return timedelta(seconds=float(ttl))
    raise TypeError(f"Unsupported TTL type: {type(ttl)!r}")


class CacheManager:
    """Filesystem-backed cache for JSON-serialisable payloads."""

    def __init__(self, root: Union[str, os.PathLike[str]]):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _hash_key(self, key_material: str, prefix: str = "") -> str:
        digest = hashlib.md5(key_material.encode("utf-8"))
        return f"{prefix}{digest.hexdigest()}"

    def _path(self, namespace: str, key_material: str, prefix: str = "") -> Path:
        hashed = self._hash_key(key_material, prefix=prefix)
        return self.root / namespace / f"{hashed}.json"

    def load(self, namespace: str, key_material: str, ttl: Optional[Union[CacheTTL, timedelta, int, float]] = CacheTTL.DAY, prefix: str = "") -> Optional[Any]:
        path = self._path(namespace, key_material, prefix)
        if not path.exists():
            return None

        try:
            with path.open("r", encoding="utf-8") as fh:
                raw = json.load(fh)
            entry = CacheEntry.load(raw)
        except (json.JSONDecodeError, KeyError, ValueError):
            return None

        ttl_delta = _normalize_ttl(ttl)
        if ttl_delta is not None:
            now = datetime.now(timezone.utc)
            if now - entry.timestamp > ttl_delta:
                return None

        return entry.payload

    def save(self, namespace: str, key_material: str, payload: Any, prefix: str = "") -> Path:
        path = self._path(namespace, key_material, prefix)
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = CacheEntry(timestamp=datetime.now(timezone.utc), payload=payload)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(entry.dump(), fh, ensure_ascii=False, indent=2)
        return path

    def invalidate(self, namespace: str, key_material: str, prefix: str = "") -> None:
        path = self._path(namespace, key_material, prefix)
        if path.exists():
            path.unlink()

    def clear_namespace(self, namespace: str) -> None:
        target = self.root / namespace
        if not target.exists():
            return
        for file in target.glob("*.json"):
            file.unlink()

    def clear_all(self) -> None:
        for entry in self.root.glob("**/*.json"):
            entry.unlink()
