from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class PipelineConfig:
    highpass_hz: float = 20.0
    smoothing: Literal["lowpass", "movavg", "rms", "none"] = "lowpass"
    smoothing_cutoff_hz: float = 6.0
    smoothing_window_ms: float = 50.0


@dataclass
class SegConfig:
    method: Literal["autocorr", "heelstrike"] = "autocorr"
    ref_muscle: str = ""
    period_min_s: float = 0.4
    period_max_s: float = 2.5
    normalize: Literal["off", "task_env95"] = "task_env95"
    show_individuals: bool = False
