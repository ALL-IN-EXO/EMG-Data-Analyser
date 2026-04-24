from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

from ..model.trial import Trial
from .base import TrialHandle

CHANNEL_MAP: dict[str, str] = {
    "BICEPS_FEM._RT": "biceps_femoris",
    "GLUT_MED._RT":   "gluteus_medius",
    "RECTUS_FEM._RT": "rectus_femoris",
}

_MVC_KEYWORDS: dict[str, list[str]] = {
    "BICEPS_FEM._RT": ["biceps", "bicep"],
    "GLUT_MED._RT":   ["glut", "gluteus"],
    "RECTUS_FEM._RT": ["rectus"],
}

CLIP_THRESHOLD = 3276.0  # µV — MyoMetrics amplifier saturation


class MyoMetricsAdapter:
    name = "myometrics"
    display_name = "MyoMetrics (Self-collected)"

    def scan(self, root: Path) -> list[TrialHandle]:
        root = Path(root)
        handles: list[TrialHandle] = []
        for csv_file in sorted(root.glob("*.csv")):
            if self._is_mvc(csv_file.name):
                continue
            handles.append(
                TrialHandle(
                    subject=root.name,
                    trial_id=csv_file.stem,
                    paths={"csv": csv_file, "session_dir": root},
                )
            )
        return handles

    def load_trial(self, handle: TrialHandle) -> Trial:
        csv_path = Path(handle.paths["csv"])
        session_dir = Path(handle.paths["session_dir"])

        df = pd.read_csv(csv_path)
        time_col = df.columns[0]
        t = df[time_col].to_numpy(dtype=float)
        dt = float(t[1] - t[0]) if len(t) > 1 else 1e-3
        fs = round(1.0 / dt)

        channels: dict[str, np.ndarray] = {}
        for col in df.columns[1:]:
            channels[col] = df[col].to_numpy(dtype=float)

        mvc_peaks: dict[str, float] = {}
        clip_fractions: dict[str, float] = {}
        for ch_name, arr in channels.items():
            clip_fractions[ch_name] = float((np.abs(arr) >= CLIP_THRESHOLD).mean())
            mvc_file = self._find_mvc(session_dir, ch_name)
            if mvc_file is not None:
                mvc_df = pd.read_csv(mvc_file)
                mvc_sig = mvc_df.iloc[:, 1].to_numpy(dtype=float)
                mvc_peaks[ch_name] = float(np.percentile(np.abs(mvc_sig), 95))

        return Trial(
            source="myometrics",
            subject=handle.subject,
            trial_id=handle.trial_id,
            fs=float(fs),
            t=t,
            channels=channels,
            units="uV",
            meta={
                "mvc_peak_abs": mvc_peaks,
                "clip_fraction": clip_fractions,
            },
            events={},
        )

    def channel_taxonomy(self) -> dict[str, str]:
        return CHANNEL_MAP

    # ------------------------------------------------------------------
    def _is_mvc(self, filename: str) -> bool:
        return "mvc" in filename.lower()

    def _find_mvc(self, session_dir: Path, raw_name: str) -> Path | None:
        keywords = _MVC_KEYWORDS.get(raw_name, [])
        for f in session_dir.glob("*.csv"):
            if not self._is_mvc(f.name):
                continue
            fname_lower = f.name.lower()
            if any(kw in fname_lower for kw in keywords):
                return f
        return None
