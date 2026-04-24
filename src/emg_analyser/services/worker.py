from __future__ import annotations
from PyQt5.QtCore import QThread, pyqtSignal

from ..model.trial import Trial, TimeRange
from ..model.cycles import CycleSet
from ..model.pipeline import PipelineConfig, SegConfig
from ..io.base import DatasetAdapter, TrialHandle
from ..processing.filters import apply_display
from ..processing import gait as gait_mod


class LoadThread(QThread):
    loaded = pyqtSignal(object)   # Trial
    error = pyqtSignal(str)

    def __init__(
        self,
        adapter: DatasetAdapter,
        handle: TrialHandle,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._adapter = adapter
        self._handle = handle

    def run(self) -> None:
        try:
            trial = self._adapter.load_trial(self._handle)
            self.loaded.emit(trial)
        except Exception as exc:
            self.error.emit(str(exc))


class ReprocessThread(QThread):
    """Apply highpass-only display pipeline to every channel."""
    done = pyqtSignal(dict)   # {channel: np.ndarray}

    def __init__(self, trial: Trial, cfg: PipelineConfig, parent=None) -> None:
        super().__init__(parent)
        self._trial = trial
        self._cfg = cfg
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        result: dict = {}
        for ch, raw in self._trial.channels.items():
            if self._cancelled:
                return
            result[ch] = apply_display(raw, self._trial.fs, self._cfg)
        if not self._cancelled:
            self.done.emit(result)


class SegmentThread(QThread):
    done = pyqtSignal(object)   # CycleSet
    error = pyqtSignal(str)

    def __init__(
        self,
        trial: Trial,
        time_range: TimeRange,
        pipeline_cfg: PipelineConfig,
        seg_cfg: SegConfig,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._trial = trial
        self._time_range = time_range
        self._pipeline_cfg = pipeline_cfg
        self._seg_cfg = seg_cfg

    def run(self) -> None:
        try:
            sliced = self._trial.slice(
                self._time_range.t_start, self._time_range.t_end
            )
            cs = gait_mod.segment(sliced, self._pipeline_cfg, self._seg_cfg)
            self.done.emit(cs)
        except Exception as exc:
            self.error.emit(str(exc))
