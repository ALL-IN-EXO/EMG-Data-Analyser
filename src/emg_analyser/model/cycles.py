from __future__ import annotations
from dataclasses import dataclass
import numpy as np

GAIT_PHASE_N = 101  # 0 % … 100 %


@dataclass
class CycleSet:
    cycles: dict[str, np.ndarray]  # channel -> (N_cycles, GAIT_PHASE_N)
    durations: np.ndarray          # (N_cycles,) seconds
    n_cycles: int

    def mean(self, channel: str) -> np.ndarray:
        return self.cycles[channel].mean(axis=0)

    def std(self, channel: str) -> np.ndarray:
        return self.cycles[channel].std(axis=0)

    @property
    def phase_axis(self) -> np.ndarray:
        return np.linspace(0, 100, GAIT_PHASE_N)

    @property
    def mean_duration(self) -> float:
        return float(self.durations.mean()) if self.n_cycles > 0 else 0.0

    @property
    def std_duration(self) -> float:
        return float(self.durations.std()) if self.n_cycles > 0 else 0.0
