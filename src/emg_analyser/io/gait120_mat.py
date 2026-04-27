"""
Low-level reader for the Gait120 dataset ProcessedData.mat files.

Each subject folder contains EMG/ProcessedData.mat which stores normalised EMG
envelopes for 7 locomotion modes. Signals are pre-segmented into individual gait
steps and interpolated to 101 points (0–100 % of the cycle). The MCOS table
objects are unpacked using the same __function_workspace__ technique as
camargo_mat.py.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

import numpy as np
import scipy.io as sio
from scipy.io.matlab._mio5 import MatFile5Reader

# Channel order matches the MATLAB table variable order in the dataset.
# Note: "GastrocnemuisMedialis" preserves the original (misspelled) dataset name.
CHANNEL_NAMES: list[str] = [
    "VastusLateralis",
    "RectusFemoris",
    "VastusMedialis",
    "TibialisAnterior",
    "BicepsFemoris",
    "Semitendinosus",
    "GastrocnemuisMedialis",
    "GastrocnemiusLateralis",
    "SoleusMedialis",
    "SoleusLateralis",
    "PeroneusLongus",
    "PeroneusBrevis",
]

MODES: list[str] = [
    "LevelWalking",
    "StairAscent",
    "StairDescent",
    "SlopeAscent",
    "SlopeDescent",
    "SitToStand",
    "StandToSit",
]


def _parse_workspace(mat_raw: dict) -> np.ndarray:
    """Decode __function_workspace__ and return the MCOS data array."""
    fw = mat_raw["__function_workspace__"].tobytes()
    header = (b"MATLAB 5.0 MAT-file" + b" " * (116 - 19))[:116]
    header += b"\x00" * 8 + b"\x00\x01" + b"IM"
    fake = header + fw[8:]
    bio = BytesIO(fake)
    rdr = MatFile5Reader(bio, struct_as_record=False, squeeze_me=True)
    rdr.initialize_read()
    bio.seek(128)
    vhdr, _ = rdr.read_var_header()
    top = rdr.read_var_array(vhdr, process=True)
    return top.MCOS[0]["arr"]


def _decode_mcos(opaque, ws_arr: np.ndarray) -> dict[str, np.ndarray]:
    """
    Decode a single MCOS table opaque reference into a channel dict.

    The 5th element of the opaque arr (idx4) encodes the table slot within the
    FileWrapper__ workspace. Data sits at workspace position 2 + (idx4-1)*7.
    """
    inst = opaque[0]
    idx4 = int(inst["arr"].ravel()[4])
    ws_pos = 2 + (idx4 - 1) * 7
    data_arrays = np.asarray(ws_arr[ws_pos]).ravel()
    return {
        name: np.asarray(data_arrays[i], dtype=float).ravel()
        for i, name in enumerate(CHANNEL_NAMES)
    }


def load_mode_steps(
    path: Path,
    mode: str,
) -> dict[str, np.ndarray]:
    """
    Load the EMGs_interpolated data for every step of *mode* from ProcessedData.mat.

    Returns
    -------
    dict[channel_name, np.ndarray(n_steps, 101)]
        Each column is one 0–100 % gait-cycle profile, normalised to MVC.
        The matrix may be empty (shape (0, 101)) if no steps were found.
    """
    mat = sio.loadmat(str(path))
    ws_arr = _parse_workspace(mat)

    mode_struct = mat[mode][0, 0]
    avail = mode_struct["AvailableTrialIdx"].ravel().astype(int)

    accumulator: dict[str, list[np.ndarray]] = {ch: [] for ch in CHANNEL_NAMES}

    for trial_idx in avail:
        trial_name = f"Trial{trial_idx:02d}"
        trial_struct = mode_struct[trial_name][0, 0]
        n_steps = int(trial_struct["nSteps"].ravel()[0])
        for s in range(1, n_steps + 1):
            step_name = f"Step{s:02d}"
            if step_name not in trial_struct.dtype.names:
                continue
            step = trial_struct[step_name][0, 0]
            channels = _decode_mcos(step["EMGs_interpolated"], ws_arr)
            for ch, arr in channels.items():
                accumulator[ch].append(arr)

    return {
        ch: np.vstack(arrs) if arrs else np.empty((0, 101), dtype=float)
        for ch, arrs in accumulator.items()
    }


def list_subjects(root: Path) -> list[str]:
    """Return sorted subject IDs (e.g. ['S001', 'S002', ...]) present in *root*."""
    subjects: list[str] = []
    for d in sorted(Path(root).iterdir()):
        if d.is_dir() and d.name.startswith("S"):
            if (d / "EMG" / "ProcessedData.mat").exists():
                subjects.append(d.name)
    return subjects


def processed_data_path(root: Path, subject: str) -> Path:
    return Path(root) / subject / "EMG" / "ProcessedData.mat"
