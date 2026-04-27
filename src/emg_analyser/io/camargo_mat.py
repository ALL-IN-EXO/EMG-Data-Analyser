"""
Low-level loader for Camargo 2021 MATLAB table .mat files.

Camargo .mat files store MATLAB `table` values as MCOS objects.  Standard
`scipy.io.loadmat()` only exposes an opaque placeholder and does not decode the
table columns directly.  This module parses `__function_workspace__` to recover
table variable names and column arrays.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

import numpy as np
import scipy.io as sio
from scipy.io.matlab._mio5 import MatFile5Reader

# Supported EMG channel labels seen in Camargo releases (different exports use
# different naming styles: with/without underscores, abbreviated names, etc.).
EMG_CHANNELS = [
    # Compact style seen in the downloaded dataset
    "gastrocmed",
    "tibialisanterior",
    "soleus",
    "vastusmedialis",
    "vastuslateralis",
    "rectusfemoris",
    "bicepsfemoris",
    "semitendinosus",
    "gracilis",
    "gluteusmedius",
    "rightexternaloblique",
    # Alternate style from some docs/exports
    "gastrocnemius_l",
    "gastrocnemius_m",
    "tibialis_anterior",
    "vastus_medialis",
    "vastus_lateralis",
    "rectus_femoris",
    "biceps_femoris",
    "gluteus_medius",
    "gluteus_maximus",
]


def load_emg_table(path: Path) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """
    Load an EMG .mat file.

    Returns
    -------
    t : (N,) float64 — time in seconds
    channels : dict[channel_name, (N,) float64] — signal in mV
    """
    names, data = load_table(path)

    time_key = None
    for key in ("time", "Time", "Header"):
        if key in data:
            time_key = key
            break
    if time_key is None:
        raise KeyError(
            f"No 'time' column found in {path}. Available keys: {names}"
        )
    t = np.asarray(data[time_key], dtype=float).ravel()

    channels: dict[str, np.ndarray] = {}
    for ch in EMG_CHANNELS:
        if ch in data:
            channels[ch] = np.asarray(data[ch], dtype=float).ravel()

    if not channels:
        # Fallback: keep numeric columns except known non-EMG metadata.
        skip = {
            time_key.lower(),
            "lnormf",
            "rnormf",
            "cycletime",
            "heelstrike",
            "heelstrike2",
            "toeoff",
        }
        for key, col in data.items():
            k = key.lower()
            if k in skip:
                continue
            arr = np.asarray(col)
            if np.issubdtype(arr.dtype, np.number):
                channels[key] = np.asarray(arr, dtype=float).ravel()

    if not channels:
        raise ValueError(
            f"No EMG channel columns found in {path}. "
            f"Available keys: {list(data.keys())}"
        )
    return t, channels


def load_gc_table(path: Path) -> dict[str, np.ndarray]:
    """
    Load a gcRight .mat table into standard event keys.

    Returns dict with optional keys:
        HeelStrike, ToeOff, HeelStrike2, CycleTime
    """
    _, data = load_table(path)
    out: dict[str, np.ndarray] = {}
    lower_to_key = {k.lower(): k for k in data.keys()}
    time_key = next(
        (k for k in ("time", "Time", "Header") if k in data),
        lower_to_key.get("time") or lower_to_key.get("header"),
    )
    time_s = (
        np.asarray(data[time_key], dtype=float).ravel()
        if time_key is not None else np.array([])
    )

    for canonical in ("HeelStrike", "ToeOff", "HeelStrike2", "CycleTime"):
        key = canonical if canonical in data else lower_to_key.get(canonical.lower())
        if key is not None:
            raw = np.asarray(data[key], dtype=float).ravel()
            if canonical in ("HeelStrike", "ToeOff"):
                phase_events = _phase_wrap_events(raw, time_s)
                if phase_events.size >= 2:
                    out[canonical] = phase_events
                    continue
            out[canonical] = _sanitize_event_array(raw)
    return out


def load_table(path: str | Path) -> tuple[list[str], dict[str, np.ndarray]]:
    """
    Decode a Camargo MATLAB table .mat file into (column_names, column_data).
    """
    path = Path(path)
    raw = sio.loadmat(str(path), struct_as_record=False, squeeze_me=False)
    if "__function_workspace__" not in raw:
        raise ValueError(f"{path} does not contain a MATLAB table subsystem")

    fw = raw["__function_workspace__"].tobytes()
    top = _read_subsystem(fw)

    opaque = top.MCOS[0]    # structured void with fields (s0, s1, s2, arr)
    arr = opaque["arr"]     # object array with table internals

    # Camargo table layout: names and data columns are stored in fixed slots.
    data_cells = np.asarray(arr[2]).ravel()
    name_cells = np.asarray(arr[7]).ravel()

    names: list[str] = []
    data: dict[str, np.ndarray] = {}
    for raw_name, raw_col in zip(name_cells, data_cells):
        name = _to_str(raw_name)
        col = np.asarray(raw_col).ravel()
        names.append(name)
        data[name] = col
    return names, data


def _read_subsystem(fw_bytes: bytes):
    """
    Parse MATLAB __function_workspace__ payload with scipy's MAT reader.
    """
    header = (b"MATLAB 5.0 MAT-file" + b" " * (116 - 19))[:116]
    header += b"\x00" * 8
    header += b"\x00\x01"
    header += b"IM"
    fake = header + fw_bytes[8:]  # skip original 8-byte subsystem endian header

    bio = BytesIO(fake)
    rdr = MatFile5Reader(bio, struct_as_record=False, squeeze_me=True)
    rdr.initialize_read()
    bio.seek(128)
    vhdr, _ = rdr.read_var_header()
    return rdr.read_var_array(vhdr, process=True)


def _to_str(v) -> str:
    if isinstance(v, bytes):
        return v.decode("ascii", errors="replace")
    if isinstance(v, str):
        return v
    if isinstance(v, np.ndarray):
        if v.dtype.kind in ("U", "S"):
            return str(v.item()) if v.size == 1 else str(v)
        if v.dtype == object and v.size == 1:
            return _to_str(v.item())
    return str(v)


def _sanitize_event_array(arr: np.ndarray) -> np.ndarray:
    out = np.asarray(arr, dtype=float).ravel()
    out = out[np.isfinite(out)]
    if out.size == 0:
        return out
    out = np.sort(out)
    if out.size > 1:
        keep = np.r_[True, np.diff(out) > 1e-9]
        out = out[keep]
    return out


def _phase_wrap_events(phase: np.ndarray, time_s: np.ndarray) -> np.ndarray:
    """Extract event times from a 0..100 phase trajectory by wrap detection."""
    ph = np.asarray(phase, dtype=float).ravel()
    tt = np.asarray(time_s, dtype=float).ravel()
    if ph.size < 10 or tt.size != ph.size:
        return np.array([])

    valid = np.isfinite(ph) & np.isfinite(tt)
    if valid.sum() < 10:
        return np.array([])
    ph = ph[valid]
    tt = tt[valid]

    lo, hi = float(np.min(ph)), float(np.max(ph))
    if lo < -5.0 or hi > 105.0:
        return np.array([])

    d = np.diff(ph)
    # phase wrap: either a strong negative jump, or near-100 -> near-0 transition
    wrap_idx = np.where((d <= -30.0) | ((ph[:-1] >= 80.0) & (ph[1:] <= 20.0)))[0] + 1
    if wrap_idx.size < 2:
        return np.array([])

    events = np.sort(tt[wrap_idx])
    if events.size <= 1:
        return events

    # Suppress duplicate wraps from jitter: keep events at least 150 ms apart.
    keep = [events[0]]
    for t in events[1:]:
        if t - keep[-1] >= 0.15:
            keep.append(t)
    return np.asarray(keep, dtype=float)
