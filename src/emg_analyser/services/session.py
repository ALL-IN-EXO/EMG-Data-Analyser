from __future__ import annotations
from PyQt5.QtCore import QObject, pyqtSignal

from ..model.trial import Trial, TimeRange
from ..model.cycles import CycleSet
from ..model.pipeline import PipelineConfig, SegConfig


class SessionManager(QObject):
    trialLoaded = pyqtSignal(object)   # Trial
    cyclesReady = pyqtSignal(object)   # CycleSet
    logMessage = pyqtSignal(str)       # info string

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.trial: Trial | None = None
        self.time_range: TimeRange | None = None
        self.pipeline_cfg = PipelineConfig()
        self.seg_cfg = SegConfig()

    def set_trial(self, trial: Trial) -> None:
        self.trial = trial
        # Default region = full trial
        self.time_range = TimeRange(float(trial.t[0]), float(trial.t[-1]))
        self.trialLoaded.emit(trial)
        self.logMessage.emit(
            f"Loaded {trial.subject}/{trial.trial_id}  "
            f"({trial.duration:.1f} s, {len(trial.channels)} ch, {trial.fs:.0f} Hz)"
        )

    def set_time_range(self, t_start: float, t_end: float) -> None:
        self.time_range = TimeRange(t_start, t_end)

    def set_pipeline(self, cfg: PipelineConfig) -> None:
        self.pipeline_cfg = cfg

    def set_seg_config(self, cfg: SegConfig) -> None:
        self.seg_cfg = cfg

    def set_cycles(self, cycles: CycleSet) -> None:
        self.cyclesReady.emit(cycles)
        self.logMessage.emit(
            f"Segmentation done — {cycles.n_cycles} cycles  "
            f"({cycles.mean_duration:.3f} ± {cycles.std_duration:.3f} s)"
        )
