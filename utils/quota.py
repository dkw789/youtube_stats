from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


class QuotaLimitError(RuntimeError):
    """Raised when a quota limit would be exceeded."""


@dataclass
class QuotaTracker:
    """Simple quota accounting helper."""

    daily_limit: int
    safety_buffer: int = 0
    used: int = 0
    saved: int = 0
    counters: Dict[str, int] = field(default_factory=dict)

    def _max_allowed(self) -> int:
        return max(0, self.daily_limit - self.safety_buffer)

    def can_spend(self, units: int) -> bool:
        return self.used + units <= self._max_allowed()

    def ensure_within_limit(self, units: int) -> None:
        if not self.can_spend(units):
            raise QuotaLimitError(
                f"Quota exceeded: used {self.used}, request {units}, limit {self._max_allowed()}"
            )

    def spend(self, action: str, units: int) -> None:
        self.ensure_within_limit(units)
        self.used += units
        self.counters[action] = self.counters.get(action, 0) + units

    def record_saved(self, units: int = 1) -> None:
        self.saved += units

    def reset(self) -> None:
        self.used = 0
        self.saved = 0
        self.counters.clear()
