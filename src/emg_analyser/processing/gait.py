from __future__ import annotations
import numpy as np
from scipy import signal as sp_signal

from ..model.trial import Trial
from ..model.cycles import CycleSet, GAIT_PHASE_N
from ..model.pipeline import PipelineConfig, SegConfig
from .filters import apply_pipeline, apply_display, highpass, rectify, lowpass


def _envelope(x: np.ndarray, fs: float) -> np.ndarray:
    return lowpass(rectify(highpass(x, fs, 20.0)), fs, 6.0)


def _find_period_autocorr(
    env: np.ndarray, fs: float, min_s: float, max_s: float
) -> int:
    """Return dominant period in samples via autocorrelation."""
    env_zm = env - env.mean()

    min_lag = max(1, int(min_s * fs))
    max_lag = min(int(max_s * fs), len(env_zm) - 1)
    if min_lag >= max_lag:
        return int(fs)  # fallback: 1 s

    # FFT autocorrelation: O(N log N), much faster than np.correlate O(N^2)
    n = len(env_zm)
    n_fft = 1 << (2 * n - 1).bit_length()
    spectrum = np.fft.rfft(env_zm, n=n_fft)
    corr = np.fft.irfft(spectrum * np.conjugate(spectrum), n=n_fft)[:n]
    c0 = float(corr[0]) if len(corr) else 0.0
    if c0 <= 1e-12:
        return int(fs)
    corr /= c0

    search = corr[min_lag : max_lag + 1]
    if len(search) == 0:
        return int(fs)
    best = int(np.argmax(search))
    return min_lag + best


def _select_boundaries(
    all_peaks: np.ndarray, period_samples: int, max_gap_factor: float = 3.0
) -> list[int]:
    """Return sorted boundary list from height/distance-filtered peaks.

    Peaks are already spaced >= 70 % of the period by find_peaks(), so we use
    them directly as boundaries.  Consecutive pairs whose gap exceeds
    max_gap_factor × period are dropped (the long cycle is discarded later in
    _extract_cycles via the min-length check rather than here, so we keep all
    boundaries — this comment is just for clarity).
    """
    if len(all_peaks) == 0:
        return []
    return [int(p) for p in sorted(all_peaks)]


def _extract_cycles(
    trial: Trial,
    pipeline_cfg: PipelineConfig,
    boundaries: list[int],
    min_duration_s: float = 0.2,
    max_duration_s: float = 10.0,
) -> CycleSet:
    """Given boundary sample indices, extract and interpolate per-channel cycles."""
    if len(boundaries) < 2:
        return CycleSet({}, np.array([]), 0)

    ch_names = list(trial.channels.keys())
    # Process each channel through the full pipeline
    processed = {
        ch: apply_pipeline(trial.channels[ch], trial.fs, pipeline_cfg)
        for ch in ch_names
    }

    cycles: dict[str, list[np.ndarray]] = {ch: [] for ch in ch_names}
    durations: list[float] = []
    cycle_starts: list[float] = []

    for i in range(len(boundaries) - 1):
        start, end = boundaries[i], boundaries[i + 1]
        n = end - start
        if n <= 1:
            continue
        dur_s = n / trial.fs
        if dur_s < min_duration_s or dur_s > max_duration_s:
            continue
        for ch in ch_names:
            seg = processed[ch][start:end]
            interp = np.interp(
                np.linspace(0, 1, GAIT_PHASE_N),
                np.linspace(0, 1, len(seg)),
                seg,
            )
            cycles[ch].append(interp)
        durations.append(dur_s)
        cycle_starts.append(float(trial.t[start]))

    if not durations:
        return CycleSet({}, np.array([]), 0)

    stacked = {ch: np.stack(cycles[ch]) for ch in ch_names}
    return CycleSet(
        cycles=stacked,
        durations=np.array(durations),
        n_cycles=len(durations),
        start_times=np.array(cycle_starts, dtype=float),
    )


def _event_times_to_sample_indices(
    trial: Trial, event_times: np.ndarray | list[float]
) -> list[int]:
    """Map event times (s) to sample indices on trial.t, handling non-zero t0."""
    if trial.n_samples <= 1:
        return []

    ev = np.asarray(event_times, dtype=float).ravel()
    ev = ev[np.isfinite(ev)]
    if ev.size == 0:
        return []

    t0 = float(trial.t[0])
    t1 = float(trial.t[-1])
    ev = ev[(ev >= t0) & (ev <= t1)]
    if ev.size == 0:
        return []

    idx = np.searchsorted(trial.t, ev, side="left")
    idx = np.clip(idx, 0, trial.n_samples - 1).astype(int)
    return [int(i) for i in np.unique(idx)]


def _normalize_cycles_task_env95(cycle_set: CycleSet) -> CycleSet:
    """Divide each channel's (N, 101) matrix by the 95th-percentile of its mean."""
    new_cycles: dict[str, np.ndarray] = {}
    for ch, mat in cycle_set.cycles.items():
        peak = float(np.percentile(mat.mean(axis=0), 95))
        new_cycles[ch] = mat / (peak + 1e-12)
    return CycleSet(
        cycles=new_cycles,
        durations=cycle_set.durations,
        n_cycles=cycle_set.n_cycles,
        start_times=cycle_set.start_times,
    )


def _normalize_cycles_mvc_env95(cycle_set: CycleSet, trial: Trial) -> CycleSet:
    """Divide each channel by MVC 95th-percentile stored in trial.meta."""
    mvc_peak_abs = trial.meta.get("mvc_peak_abs", {})
    new_cycles: dict[str, np.ndarray] = {}
    for ch, mat in cycle_set.cycles.items():
        peak = float(mvc_peak_abs.get(ch, 0.0))
        if peak <= 0:
            new_cycles[ch] = mat
            continue
        new_cycles[ch] = mat / peak
    return CycleSet(
        cycles=new_cycles,
        durations=cycle_set.durations,
        n_cycles=cycle_set.n_cycles,
        start_times=cycle_set.start_times,
    )


class AutocorrSegmenter:
    def segment(
        self, trial: Trial, pipeline_cfg: PipelineConfig, seg_cfg: SegConfig
    ) -> CycleSet:
        ref = seg_cfg.ref_muscle or list(trial.channels.keys())[0]
        if ref not in trial.channels:
            ref = list(trial.channels.keys())[0]

        env = _envelope(trial.channels[ref], trial.fs)
        period = _find_period_autocorr(
            env, trial.fs, seg_cfg.period_min_s, seg_cfg.period_max_s
        )
        min_dist = int(period * 0.70)
        # height threshold: ignore noise peaks below 20 % of max envelope
        height_thresh = float(env.max() * 0.20)
        peaks, _ = sp_signal.find_peaks(
            env, distance=min_dist, height=height_thresh
        )
        boundaries = _select_boundaries(peaks, period)

        cs = _extract_cycles(
            trial,
            pipeline_cfg,
            boundaries,
            min_duration_s=seg_cfg.period_min_s,
            max_duration_s=seg_cfg.period_max_s,
        )
        if seg_cfg.normalize == "task_env95" and cs.n_cycles > 0:
            cs = _normalize_cycles_task_env95(cs)
        elif seg_cfg.normalize == "mvc_env95" and cs.n_cycles > 0:
            cs = _normalize_cycles_mvc_env95(cs, trial)
        return cs


class HeelStrikeSegmenter:
    def segment(
        self, trial: Trial, pipeline_cfg: PipelineConfig, seg_cfg: SegConfig
    ) -> CycleSet:
        hs = trial.events.get("heel_strike", np.array([]))
        if len(hs) < 2:
            return AutocorrSegmenter().segment(trial, pipeline_cfg, seg_cfg)

        boundaries = _event_times_to_sample_indices(trial, hs)
        if len(boundaries) < 2:
            return AutocorrSegmenter().segment(trial, pipeline_cfg, seg_cfg)
        cs = _extract_cycles(
            trial,
            pipeline_cfg,
            boundaries,
            min_duration_s=seg_cfg.period_min_s,
            max_duration_s=seg_cfg.period_max_s,
        )
        if seg_cfg.normalize == "task_env95" and cs.n_cycles > 0:
            cs = _normalize_cycles_task_env95(cs)
        elif seg_cfg.normalize == "mvc_env95" and cs.n_cycles > 0:
            cs = _normalize_cycles_mvc_env95(cs, trial)
        return cs


def segment(
    trial: Trial, pipeline_cfg: PipelineConfig, seg_cfg: SegConfig
) -> CycleSet:
    if (
        seg_cfg.method == "heelstrike"
        and len(trial.events.get("heel_strike", [])) >= 2
    ):
        return HeelStrikeSegmenter().segment(trial, pipeline_cfg, seg_cfg)
    return AutocorrSegmenter().segment(trial, pipeline_cfg, seg_cfg)


def normalize_cycle_set(
    cs: CycleSet,
    normalize: str,
    trial: Trial | None = None,
) -> CycleSet:
    """Apply post-extraction normalization to a CycleSet."""
    if normalize == "task_env95" and cs.n_cycles > 0:
        return _normalize_cycles_task_env95(cs)
    if normalize == "mvc_env95" and cs.n_cycles > 0 and trial is not None:
        return _normalize_cycles_mvc_env95(cs, trial)
    return cs
