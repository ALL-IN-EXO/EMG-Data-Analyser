from __future__ import annotations
import numpy as np
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


def _merge_cycle_sets(cycle_sets: list[CycleSet]) -> CycleSet:
    """Vertically stack CycleSets from multiple trials into one."""
    valid = [cs for cs in cycle_sets if cs.n_cycles > 0]
    if not valid:
        return CycleSet({}, np.array([]), 0)
    channels = list(valid[0].cycles.keys())
    merged: dict[str, np.ndarray] = {}
    for ch in channels:
        parts = [cs.cycles[ch] for cs in valid if ch in cs.cycles]
        if parts:
            merged[ch] = np.vstack(parts)
    durations = np.concatenate([cs.durations for cs in valid])
    starts = np.concatenate([cs.start_times for cs in valid])
    return CycleSet(
        cycles=merged,
        durations=durations,
        n_cycles=int(durations.shape[0]),
        start_times=starts,
    )


class CamargoThread(QThread):
    """Load and segment Camargo trials grouped by subject.

    Emits done({'by_subject': dict[subject, CycleSet], 'channels': list[str]}).
    Normalization is applied after merging all trials for a subject so that the
    reference is computed from the full combined distribution.
    """
    progress = pyqtSignal(int, int)   # (done, total)
    done = pyqtSignal(dict)
    error = pyqtSignal(str)
    logMessage = pyqtSignal(str)

    def __init__(
        self,
        adapter,
        handles: list[TrialHandle],
        pipeline_cfg: PipelineConfig,
        seg_cfg: SegConfig,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._adapter = adapter
        self._handles = handles
        self._pipeline_cfg = pipeline_cfg
        self._seg_cfg = seg_cfg

    def run(self) -> None:
        try:
            self._run()
        except Exception as exc:
            self.error.emit(str(exc))

    def _run(self) -> None:
        # Group handles by subject
        grouped: dict[str, list[TrialHandle]] = {}
        for h in self._handles:
            grouped.setdefault(h.subject, []).append(h)

        # Segment with normalize=off; apply normalization after merging
        internal_cfg = SegConfig(
            method=self._seg_cfg.method,
            ref_muscle=self._seg_cfg.ref_muscle,
            period_min_s=self._seg_cfg.period_min_s,
            period_max_s=self._seg_cfg.period_max_s,
            normalize="off",
        )

        by_subject: dict[str, CycleSet] = {}
        channels: list[str] | None = None
        total = len(self._handles)
        done = 0

        for subj, subj_handles in grouped.items():
            per_trial: list[CycleSet] = []
            for handle in subj_handles:
                try:
                    trial = self._adapter.load_trial(handle)
                    if channels is None:
                        channels = list(trial.channels.keys())
                    cs = gait_mod.segment(trial, self._pipeline_cfg, internal_cfg)
                    if cs.n_cycles > 0:
                        per_trial.append(cs)
                    self.logMessage.emit(
                        f"[INFO] {subj}/{handle.trial_id} — {cs.n_cycles} cycles"
                    )
                except Exception as exc:
                    self.logMessage.emit(
                        f"[WARN] {subj}/{handle.trial_id}: {exc}"
                    )
                done += 1
                self.progress.emit(done, total)

            if per_trial:
                merged = _merge_cycle_sets(per_trial)
                merged = gait_mod.normalize_cycle_set(
                    merged, self._seg_cfg.normalize
                )
                if merged.n_cycles > 0:
                    by_subject[subj] = merged

        self.done.emit({
            "by_subject": by_subject,
            "channels": channels or [],
        })
