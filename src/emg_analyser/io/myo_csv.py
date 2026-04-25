from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

from ..model.trial import Trial
from ..processing.filters import highpass, rectify, lowpass
from .base import TrialHandle

# Map raw channel name (as extracted from filename) → canonical name
CHANNEL_MAP: dict[str, str] = {
    "BICEPS_FEM._RT":  "biceps_femoris",
    "GLUT._MED._RT":   "gluteus_medius",
    "RECTUS_FEM._RT":  "rectus_femoris",
}

CLIP_THRESHOLD = 3276.0  # µV — MyoMetrics amplifier saturation

# Prefix that identifies per-channel raw data files
_CURVE_PREFIX = "Channel_Curves-"

# Substring that marks a session as MVC
_MVC_MARKER = "mvc"


class MyoMetricsAdapter:
    """
    Handles the MyoMetrics session-folder layout exported by the device software.

    Expected structure (user selects the *parent* folder or a *session* folder):

        <parent>/                          ← user selects this
          <session>/                       ← e.g. "EMG-with Electrode"
            Channel_Curves-*-BICEPS_FEM._RT.csv
            Channel_Curves-*-GLUT._MED._RT.csv
            Channel_Curves-*-RECTUS_FEM._RT.csv
            Record_info.csv
            ...
          <MVC session>/                   ← e.g. "EMG-Electrode Max MVC"
            Channel_Curves-*-BICEPS_FEM._RT.csv
            ...

    Each Channel_Curves CSV has a 3-line preamble:
        line 0: metadata header  ("type","name","time_units","begin_time","frequency","count","units")
        line 1: metadata values  ("signal","","s",0.0,2000.36,146960,"uV")
        line 2: blank
    followed by data lines with header  "time","value".
    """

    name = "myometrics"
    display_name = "MyoMetrics (Self-collected)"

    # ------------------------------------------------------------------
    # DatasetAdapter protocol
    # ------------------------------------------------------------------
    def scan(self, root: Path) -> list[TrialHandle]:
        root = Path(root)

        # Case 1: root is itself a session folder (contains Channel_Curves CSVs)
        if self._is_session_dir(root):
            if not self._is_mvc_session(root.name):
                return [self._make_handle(root.parent, root)]
            return []

        # Case 2: root is a parent folder containing session subfolders
        handles: list[TrialHandle] = []
        for sub in sorted(root.iterdir()):
            if sub.is_dir() and self._is_session_dir(sub) and not self._is_mvc_session(sub.name):
                handles.append(self._make_handle(root, sub))
        return handles

    def load_trial(self, handle: TrialHandle) -> Trial:
        session_dir = Path(handle.paths["session_dir"])
        parent_dir  = Path(handle.paths["parent_dir"])
        selected_mvc = handle.paths.get("mvc_dir")

        # Discover all channel CSV files in this session
        ch_files = sorted(session_dir.glob(f"{_CURVE_PREFIX}*.csv"))
        if not ch_files:
            raise FileNotFoundError(f"No Channel_Curves CSVs in {session_dir}")

        channels: dict[str, np.ndarray] = {}
        t_ref: np.ndarray | None = None
        fs: float = 2000.0
        units: str = "uV"

        for cf in ch_files:
            ch_name = self._channel_name_from_path(cf)
            if ch_name is None or ch_name.lower() == "events":
                continue
            meta, t, values = self._load_channel_csv(cf)
            channels[ch_name] = values
            if t_ref is None:
                t_ref = t
                fs    = meta["frequency"]
                units = meta["units"]

        if t_ref is None or not channels:
            raise ValueError(f"No valid channel data found in {session_dir}")

        # MVC peaks and clip fractions
        mvc_peaks: dict[str, float] = {}
        clip_fractions: dict[str, float] = {}
        mvc_dir = self._resolve_mvc_dir(selected_mvc, parent_dir)

        for ch_name, arr in channels.items():
            clip_fractions[ch_name] = float((np.abs(arr) >= CLIP_THRESHOLD).mean())
            if mvc_dir:
                mvc_val = self._load_mvc_peak(mvc_dir, ch_name)
                if mvc_val is not None:
                    mvc_peaks[ch_name] = mvc_val

        return Trial(
            source="myometrics",
            subject=handle.subject,
            trial_id=handle.trial_id,
            fs=fs,
            t=t_ref,
            channels=channels,
            units=units,
            meta={
                "mvc_peak_abs":  mvc_peaks,
                "clip_fraction": clip_fractions,
            },
            events={},
        )

    def channel_taxonomy(self) -> dict[str, str]:
        return CHANNEL_MAP

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _is_session_dir(path: Path) -> bool:
        return any(path.glob(f"{_CURVE_PREFIX}*.csv"))

    @staticmethod
    def _is_mvc_session(name: str) -> bool:
        return _MVC_MARKER in name.lower()

    @staticmethod
    def _make_handle(parent_dir: Path, session_dir: Path) -> TrialHandle:
        return TrialHandle(
            subject=parent_dir.name,
            trial_id=session_dir.name,
            paths={
                "session_dir": session_dir,
                "parent_dir":  parent_dir,
            },
        )

    @staticmethod
    def _channel_name_from_path(path: Path) -> str | None:
        """
        Extract channel name from filename.
        e.g. "Channel_Curves-Analyzed_Work_Activities-BICEPS_FEM._RT.csv"
             → "BICEPS_FEM._RT"
        """
        stem = path.stem  # drop .csv
        # Channel name is everything after the last '-'
        parts = stem.rsplit("-", maxsplit=1)
        if len(parts) == 2:
            return parts[1]
        return None

    @staticmethod
    def _load_channel_csv(path: Path) -> tuple[dict, np.ndarray, np.ndarray]:
        """
        Parse a Channel_Curves CSV.

        Returns (meta_dict, t_array, values_array).
        meta_dict keys include 'frequency' (float) and 'units' (str).
        """
        # -- metadata section (rows 0-1) --
        meta_df = pd.read_csv(path, nrows=1, encoding="utf-8-sig")
        frequency = float(meta_df["frequency"].iloc[0])
        units_raw = str(meta_df["units"].iloc[0]).strip('"').strip()

        # -- data section (skip meta header + meta values + blank = 3 rows) --
        data_df = pd.read_csv(path, skiprows=3, encoding="utf-8-sig")
        t      = data_df["time"].to_numpy(dtype=float)
        values = data_df["value"].to_numpy(dtype=float)

        return {"frequency": frequency, "units": units_raw}, t, values

    @staticmethod
    def _find_mvc_dir(parent_dir: Path) -> Path | None:
        """Return the MVC session subfolder if it exists."""
        for sub in parent_dir.iterdir():
            if sub.is_dir() and _MVC_MARKER in sub.name.lower():
                return sub
        return None

    @classmethod
    def _resolve_mvc_dir(
        cls,
        selected_mvc: Path | str | None,
        parent_dir: Path,
    ) -> Path | None:
        """Resolve MVC folder from explicit selection, otherwise from parent."""
        if selected_mvc:
            root = Path(selected_mvc)
            if root.is_dir():
                if cls._is_session_dir(root):
                    return root
                sub_sessions = [
                    sub for sub in sorted(root.iterdir())
                    if sub.is_dir() and cls._is_session_dir(sub)
                ]
                named_mvc = [sub for sub in sub_sessions if cls._is_mvc_session(sub.name)]
                if named_mvc:
                    return named_mvc[0]
                if len(sub_sessions) == 1:
                    return sub_sessions[0]
            return None
        return cls._find_mvc_dir(parent_dir)

    @classmethod
    def _load_mvc_peak(cls, mvc_dir: Path, ch_name: str) -> float | None:
        """95th-percentile of the absolute rectified MVC envelope for ch_name."""
        for cf in mvc_dir.glob(f"{_CURVE_PREFIX}*.csv"):
            if cls._channel_name_from_path(cf) == ch_name:
                try:
                    meta, _, values = cls._load_channel_csv(cf)
                    fs = float(meta["frequency"])
                    env = lowpass(rectify(highpass(values, fs, 20.0)), fs, 6.0)
                    return float(np.percentile(env, 95))
                except Exception:
                    return None
        return None
