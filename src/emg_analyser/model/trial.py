from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np


@dataclass
class TimeRange:
    t_start: float
    t_end: float

    @property
    def duration(self) -> float:
        return self.t_end - self.t_start


@dataclass
class Trial:
    source: str
    subject: str
    trial_id: str
    fs: float
    t: np.ndarray
    channels: dict[str, np.ndarray]
    units: str
    meta: dict = field(default_factory=dict)
    events: dict[str, np.ndarray] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return float(self.t[-1] - self.t[0]) if len(self.t) > 1 else 0.0

    @property
    def n_samples(self) -> int:
        return len(self.t)

    def slice(self, t_start: float, t_end: float) -> Trial:
        mask = (self.t >= t_start) & (self.t <= t_end)
        sliced_events: dict[str, np.ndarray] = {}
        for key, arr in self.events.items():
            sliced_events[key] = arr[(arr >= t_start) & (arr <= t_end)]
        return Trial(
            source=self.source,
            subject=self.subject,
            trial_id=self.trial_id,
            fs=self.fs,
            t=self.t[mask],
            channels={ch: arr[mask] for ch, arr in self.channels.items()},
            units=self.units,
            meta=self.meta,
            events=sliced_events,
        )
