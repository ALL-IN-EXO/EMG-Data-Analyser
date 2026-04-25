"""
CamargoAdapter — scans and loads the Camargo 2021 lower-limb biomechanics dataset.

Expected directory layout (after running download_dataset.sh):

    <root>/
      AB06/
        <date>/
          treadmill/
            emg/        ← emg .mat files: treadmill_01_01.mat …
            gcRight/    ← gait-cycle .mat files: same names as emg/
          levelground/
          ramp/
          stair/
      AB07/ … AB30/
"""
from __future__ import annotations
from pathlib import Path

import numpy as np

from ..model.trial import Trial
from .base import DatasetAdapter, TrialHandle
from .camargo_mat import load_emg_table, load_gc_table, EMG_CHANNELS

CHANNEL_MAP: dict[str, str] = {ch: ch for ch in EMG_CHANNELS}  # canonical = raw

MODES = ("treadmill", "levelground", "ramp", "stair")


class CamargoAdapter:
    name = "camargo"
    display_name = "Camargo 2021 (Aaron Young Lab)"

    # ------------------------------------------------------------------
    def scan(self, root: Path) -> list[TrialHandle]:
        root = Path(root)
        handles: list[TrialHandle] = []

        for subject_dir in sorted(root.iterdir()):
            if not subject_dir.is_dir() or not subject_dir.name.startswith("AB"):
                continue
            subject = subject_dir.name

            # There may be one or more date sub-directories
            for date_dir in sorted(subject_dir.iterdir()):
                if not date_dir.is_dir():
                    continue
                for mode in MODES:
                    emg_dir = date_dir / mode / "emg"
                    gc_dir  = date_dir / mode / "gcRight"
                    if not emg_dir.is_dir():
                        continue
                    for mat_file in sorted(emg_dir.glob("*.mat")):
                        gc_file = gc_dir / mat_file.name if gc_dir.is_dir() else None
                        handles.append(TrialHandle(
                            subject=subject,
                            trial_id=mat_file.stem,
                            paths={
                                "emg":  mat_file,
                                "gc":   gc_file,
                                "mode": mode,
                            },
                            est_duration_s=143.0,
                        ))
        return handles

    def load_trial(self, handle: TrialHandle) -> Trial:
        emg_path = Path(handle.paths["emg"])
        gc_path  = handle.paths.get("gc")

        t, channels = load_emg_table(emg_path)
        fs = round(1.0 / float(t[1] - t[0])) if len(t) > 1 else 1000.0

        events: dict[str, np.ndarray] = {}
        if gc_path and Path(gc_path).exists():
            try:
                gc = load_gc_table(Path(gc_path))
                if "HeelStrike" in gc:
                    events["heel_strike"] = gc["HeelStrike"]
                if "ToeOff" in gc:
                    events["toe_off"] = gc["ToeOff"]
            except Exception:
                pass  # missing gcRight → segmenter will fall back to autocorr

        return Trial(
            source="camargo",
            subject=handle.subject,
            trial_id=handle.trial_id,
            fs=float(fs),
            t=t,
            channels=channels,
            units="mV",
            meta={"mode": handle.paths.get("mode", "")},
            events=events,
        )

    def channel_taxonomy(self) -> dict[str, str]:
        return CHANNEL_MAP

    # ------------------------------------------------------------------
    # Convenience: return all unique (subject, mode) combinations present
    # ------------------------------------------------------------------
    @staticmethod
    def available_modes(root: Path) -> list[str]:
        found: set[str] = set()
        for ab in Path(root).iterdir():
            if not ab.is_dir() or not ab.name.startswith("AB"):
                continue
            for date in ab.iterdir():
                if not date.is_dir():
                    continue
                for mode in MODES:
                    if (date / mode / "emg").is_dir():
                        found.add(mode)
        return [m for m in MODES if m in found]

    @staticmethod
    def available_subjects(root: Path, mode: str) -> list[str]:
        subjects: list[str] = []
        for ab in sorted(Path(root).iterdir()):
            if not ab.is_dir() or not ab.name.startswith("AB"):
                continue
            for date in ab.iterdir():
                if not date.is_dir():
                    continue
                if (date / mode / "emg").is_dir():
                    subjects.append(ab.name)
                    break
        return subjects
