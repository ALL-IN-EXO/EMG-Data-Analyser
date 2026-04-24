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
    corr = np.correlate(env_zm, env_zm, mode="full")
    corr = corr[len(corr) // 2 :]
    corr /= corr[0] + 1e-12

    min_lag = max(1, int(min_s * fs))
    max_lag = min(int(max_s * fs), len(corr) - 1)
    if min_lag >= max_lag:
        return int(fs)  # fallback: 1 s

    search = corr[min_lag : max_lag + 1]
    best = int(np.argmax(search))
    return min_lag + best


def _greedy_boundaries(
    env: np.ndarray, all_peaks: np.ndarray, period_samples: int
) -> list[int]:
    """Starting from the first peak, step forward by ~period and snap to nearest peak."""
    if len(all_peaks) == 0:
        return []

    boundaries = [int(all_peaks[0])]
    current = boundaries[0]
    half_period = period_samples // 2

    while True:
        expected = current + period_samples
        window = int(period_samples * 0.25)
        lo, hi = expected - window, expected + window

        candidates = all_peaks[(all_peaks >= lo) & (all_peaks <= hi)]
        if len(candidates) == 0:
            break

        next_peak = int(candidates[np.argmin(np.abs(candidates - expected))])
        if next_peak <= current:
            break
        boundaries.append(next_peak)
        current = next_peak

        if current >= len(env) - half_period:
            break

    return boundaries


def _extract_cycles(
    trial: Trial, pipeline_cfg: PipelineConfig, boundaries: list[int]
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

    for i in range(len(boundaries) - 1):
        start, end = boundaries[i], boundaries[i + 1]
        n = end - start
        if n < int(trial.fs * 0.2):  # skip fragments < 0.2 s
            continue
        for ch in ch_names:
            seg = processed[ch][start:end]
            interp = np.interp(
                np.linspace(0, 1, GAIT_PHASE_N),
                np.linspace(0, 1, len(seg)),
                seg,
            )
            cycles[ch].append(interp)
        durations.append(n / trial.fs)

    if not durations:
        return CycleSet({}, np.array([]), 0)

    stacked = {ch: np.stack(cycles[ch]) for ch in ch_names}
    return CycleSet(cycles=stacked, durations=np.array(durations), n_cycles=len(durations))


def _normalize_cycles(cycle_set: CycleSet) -> CycleSet:
    """Divide each channel's (N, 101) matrix by the 95th-percentile of its mean."""
    new_cycles: dict[str, np.ndarray] = {}
    for ch, mat in cycle_set.cycles.items():
        peak = float(np.percentile(mat.mean(axis=0), 95))
        new_cycles[ch] = mat / (peak + 1e-12)
    return CycleSet(
        cycles=new_cycles,
        durations=cycle_set.durations,
        n_cycles=cycle_set.n_cycles,
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
        boundaries = _greedy_boundaries(env, peaks, period)

        cs = _extract_cycles(trial, pipeline_cfg, boundaries)
        if seg_cfg.normalize == "task_env95" and cs.n_cycles > 0:
            cs = _normalize_cycles(cs)
        return cs


class HeelStrikeSegmenter:
    def segment(
        self, trial: Trial, pipeline_cfg: PipelineConfig, seg_cfg: SegConfig
    ) -> CycleSet:
        hs = trial.events.get("heel_strike", np.array([]))
        if len(hs) < 2:
            return AutocorrSegmenter().segment(trial, pipeline_cfg, seg_cfg)

        boundaries = sorted(
            [int(t * trial.fs) for t in hs
             if 0 <= int(t * trial.fs) < trial.n_samples]
        )
        cs = _extract_cycles(trial, pipeline_cfg, boundaries)
        if seg_cfg.normalize == "task_env95" and cs.n_cycles > 0:
            cs = _normalize_cycles(cs)
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
