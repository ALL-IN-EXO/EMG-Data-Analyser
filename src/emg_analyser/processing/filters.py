from __future__ import annotations
import numpy as np
from scipy import signal as sp_signal
from ..model.pipeline import PipelineConfig


def highpass(x: np.ndarray, fs: float, cutoff_hz: float) -> np.ndarray:
    if cutoff_hz <= 0 or cutoff_hz >= fs / 2:
        return x
    sos = sp_signal.iirfilter(
        4, cutoff_hz / (fs / 2), btype="high", ftype="butter", output="sos"
    )
    return sp_signal.sosfiltfilt(sos, x)


def lowpass(x: np.ndarray, fs: float, cutoff_hz: float) -> np.ndarray:
    if cutoff_hz <= 0 or cutoff_hz >= fs / 2:
        return x
    sos = sp_signal.iirfilter(
        4, cutoff_hz / (fs / 2), btype="low", ftype="butter", output="sos"
    )
    return sp_signal.sosfiltfilt(sos, x)


def rectify(x: np.ndarray) -> np.ndarray:
    return np.abs(x)


def moving_average(x: np.ndarray, fs: float, window_ms: float) -> np.ndarray:
    n = max(1, int(fs * window_ms / 1000))
    kernel = np.ones(n) / n
    return np.convolve(x, kernel, mode="same")


def sliding_rms(x: np.ndarray, fs: float, window_ms: float) -> np.ndarray:
    n = max(1, int(fs * window_ms / 1000))
    x2 = x ** 2
    kernel = np.ones(n) / n
    return np.sqrt(np.maximum(np.convolve(x2, kernel, mode="same"), 0.0))


def apply_display(x: np.ndarray, fs: float, cfg: PipelineConfig) -> np.ndarray:
    """Display preview pipeline for Page 1."""
    return apply_pipeline(x, fs, cfg)


def apply_pipeline(x: np.ndarray, fs: float, cfg: PipelineConfig) -> np.ndarray:
    """Full pipeline: highpass → rectify → smooth. Used before segmentation."""
    out = highpass(x, fs, cfg.highpass_hz)
    if cfg.rectify:
        out = rectify(out)
    if cfg.smoothing == "lowpass":
        out = lowpass(out, fs, cfg.smoothing_cutoff_hz)
    elif cfg.smoothing == "movavg":
        out = moving_average(out, fs, cfg.smoothing_window_ms)
    elif cfg.smoothing == "rms":
        out = sliding_rms(out, fs, cfg.smoothing_window_ms)
    return out
