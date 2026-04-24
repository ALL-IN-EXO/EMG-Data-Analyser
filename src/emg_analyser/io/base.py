from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from ..model.trial import Trial


@dataclass
class TrialHandle:
    subject: str
    trial_id: str
    paths: dict = field(default_factory=dict)
    est_duration_s: float = 0.0

    def __str__(self) -> str:
        return f"{self.subject} / {self.trial_id}"


class DatasetAdapter(Protocol):
    name: str
    display_name: str

    def scan(self, root: Path) -> list[TrialHandle]: ...

    def load_trial(self, handle: TrialHandle) -> Trial: ...

    def channel_taxonomy(self) -> dict[str, str]:
        """Map raw channel name → canonical name."""
        ...
