# Dataset Reference

This document describes the structure, field conventions, sampling rates, and channel mappings for every dataset supported by EMG-Data-Analyser.  
See [`DOCS/WORKFLOW.md`](WORKFLOW.md) for how each dataset plugs into the adapter layer.

---

## Table of Contents

1. [Self-Collected Dataset — MyoMetrics CSV](#1-self-collected-dataset--myometrics-csv)
2. [Public Dataset — Camargo 2021](#2-public-dataset--camargo-2021)
3. [Public Dataset — Gait120](#3-public-dataset--gait120)
4. [Cross-Dataset Channel Mapping](#4-cross-dataset-channel-mapping)
5. [Unified `Trial` Representation](#5-unified-trial-representation)

---

## 1. Self-Collected Dataset — MyoMetrics CSV

### 1.1 Overview

| Property | Value |
|----------|-------|
| Device | MyoMetrics wireless surface EMG |
| Channels | 3 (right leg) |
| Sampling rate | 2 000 Hz (downsampled to 1 000 Hz for analysis) |
| Signal unit | µV (microvolts) |
| File format | CSV (comma-separated, UTF-8) |
| MVC sessions | Separate session files for each muscle |
| Gait events | None embedded; derived by autocorrelation segmentation |

### 1.2 Directory Layout

```
Dataset/MyoMetrics/
├── <session_date>/                  # e.g. 2026-04-13/
│   ├── EMG-with Electrode.csv       # main walking trial
│   ├── MVC-BicepsFem.csv            # MVC contraction, biceps femoris
│   ├── MVC-GlutMed.csv              # MVC contraction, gluteus medius
│   └── MVC-RectusFem.csv            # MVC contraction, rectus femoris
└── <session_date>/
    └── ...
```

### 1.3 CSV Structure

Each file shares the same header layout:

```
Time(s), BICEPS_FEM._RT, GLUT_MED._RT, RECTUS_FEM._RT
0.0000,  12.34,          -5.67,          8.90
0.0005,  ...
```

| Column | Description |
|--------|-------------|
| `Time(s)` | Timestamp in seconds; uniform 0.5 ms step (2 kHz) |
| `BICEPS_FEM._RT` | Biceps femoris, right, µV |
| `GLUT_MED._RT` | Gluteus medius, right, µV |
| `RECTUS_FEM._RT` | Rectus femoris, right, µV |

### 1.4 Signal Quality Notes

- **Saturation / clipping** — the MyoMetrics amplifier clips at ±3 276.7 µV. The loader (`myo_csv.py`) flags clipped samples and exposes `meta["clip_fraction"]` per channel. Trials with clip fraction > 5 % should be treated with caution.
- **MVC peak** — `myo_csv.py` reads the paired MVC file and stores the rectified envelope 95th-percentile in `meta["mvc_peak_abs"]` (µV). This enables `mvc_peak` and `mvc_env95` normalisation modes.
- **DC offset** — a baseline offset is common; the default processing pipeline applies a 20 Hz high-pass filter before rectification.

### 1.5 Loader Output (`MyoMetricsAdapter.load_trial`)

```python
Trial(
    source    = "myometrics",
    subject   = "self-2026.4.13",           # session folder name
    trial_id  = "EMG-with Electrode",
    fs        = 2000.0,                      # original; pipeline downsamples to 1000
    t         = np.ndarray,                  # (N,) seconds
    channels  = {
        "BICEPS_FEM._RT":  np.ndarray,       # (N,) µV, raw
        "GLUT_MED._RT":    np.ndarray,
        "RECTUS_FEM._RT":  np.ndarray,
    },
    units     = "uV",
    meta      = {
        "mvc_peak_abs":    {"BICEPS_FEM._RT": float, ...},  # µV
        "clip_fraction":   {"BICEPS_FEM._RT": float, ...},  # 0–1
    },
    events    = {},   # filled later by AutocorrSegmenter
)
```

---

## 2. Public Dataset — Camargo 2021

### 2.1 Overview

| Property | Value |
|----------|-------|
| Reference | Camargo et al. 2021, *Scientific Data* |
| Lab | Aaron Young Lab, Georgia Tech |
| DOI (Part 1) | [10.17632/fcgm3chfff.1](http://dx.doi.org/10.17632/fcgm3chfff.1) |
| DOI (Part 2) | [10.17632/k9kvm5tn3f.1](http://dx.doi.org/10.17632/k9kvm5tn3f.1) |
| DOI (Part 3) | [10.17632/jj3r5f9pnf.1](http://dx.doi.org/10.17632/jj3r5f9pnf.1) |
| Subjects | 22 able-bodied adults (AB06–AB30; AB22, AB26, AB29 absent from release) |
| Channels | 11 lower-limb surface EMG |
| Sampling rate | 1 000 Hz |
| Signal unit | mV (millivolts) |
| File format | MATLAB `.mat` (HDF5-backed MCOS table objects) |
| Gait events | Heel strikes and toe-offs in paired `gcRight/*.mat` |

### 2.2 Directory Layout

```
Dataset/Camargo2021/
├── SubjectInfo.mat             # demographics (age, mass, height, leg length)
├── README.txt                  # original Part 1 documentation
├── README_part2.txt
├── README_part3.txt
├── scripts_part1/              # MATLAB analysis scripts from the authors
│
├── AB06/
│   └── 10_09_18/               # collection date (MM_DD_YY)
│       ├── treadmill/
│       │   ├── emg/            # treadmill_01_01.mat, treadmill_01_02.mat …
│       │   ├── gcRight/        # gait cycle events (same trial names)
│       │   ├── gon/            # goniometer joint angles
│       │   ├── id/             # inverse dynamics (joint moments)
│       │   └── fp/             # force plate
│       ├── levelground/
│       │   ├── emg/
│       │   ├── gcRight/
│       │   └── ...
│       ├── ramp/
│       │   ├── emg/
│       │   ├── gcRight/
│       │   └── ...
│       └── stair/
│           ├── emg/
│           ├── gcRight/
│           └── ...
│
├── AB07/ … AB14/               # Part 1
├── AB15/ … AB25/               # Part 2  (AB22 missing)
└── AB27/ AB28/ AB30/           # Part 3  (AB26, AB29 missing)
```

### 2.3 Locomotion Modes and Trial Naming

| Mode folder | Description | Typical trial count |
|-------------|-------------|-------------------|
| `treadmill` | Treadmill walking at multiple speeds | 6–12 trials |
| `levelground` | Overground walking, straight path | 4–8 trials |
| `ramp` | Inclined ramp, ascent and descent | 4–8 trials |
| `stair` | Stair ascent and descent | 4–8 trials |

Trial files follow the pattern `<mode>_<speed_or_condition>_<repetition>.mat`, e.g.:
- `treadmill_01_01.mat` — treadmill, condition 01, repetition 01
- `levelground_01_03.mat` — level ground, condition 01, repetition 03

### 2.4 EMG `.mat` File Contents

Each `emg/*.mat` stores a MATLAB `table` with one row per sample (≈ 143 s × 1 000 Hz ≈ 143 000 rows):

| Variable / Column | Type | Description |
|-------------------|------|-------------|
| `Header` | string | Trial identifier |
| `time` | double (N×1) | Timestamp, seconds |
| `LNormF` | double (N×1) | Left normalised force (from force plate) |
| `RNormF` | double (N×1) | Right normalised force |
| `gastrocnemius_l` | double (N×1) | Gastrocnemius lateralis (mV) |
| `gastrocnemius_m` | double (N×1) | Gastrocnemius medialis (mV) |
| `soleus` | double (N×1) | Soleus (mV) |
| `tibialis_anterior` | double (N×1) | Tibialis anterior (mV) |
| `vastus_medialis` | double (N×1) | Vastus medialis (mV) |
| `vastus_lateralis` | double (N×1) | Vastus lateralis (mV) |
| `rectus_femoris` | double (N×1) | Rectus femoris (mV) |
| `biceps_femoris` | double (N×1) | Biceps femoris (mV) |
| `semitendinosus` | double (N×1) | Semitendinosus (mV) |
| `gluteus_medius` | double (N×1) | Gluteus medius (mV) |
| `gluteus_maximus` | double (N×1) | Gluteus maximus (mV) |

> The loader (`camargo_mat.py`) uses MCOS reverse-engineering to unpack these MATLAB table objects — standard `scipy.io.loadmat` is insufficient for this format.

### 2.5 Gait Event `.mat` File Contents (`gcRight/`)

Paired `gcRight/<trial_name>.mat` is also a MATLAB `table`, but there are two observed formats:

1. Event-list format (each row is one cycle event), e.g. `HeelStrike/ToeOff` already in seconds.
2. Phase-trajectory format (common in downloaded Camargo release), where:
   - `Header` is time (s),
   - `HeelStrike` / `ToeOff` are 0–100 gait-phase trajectories that wrap around at events.

The loader handles both formats. For phase trajectories, it detects phase wrap points and converts them into event times in seconds, then stores:

- `trial.events["heel_strike"]`
- `trial.events["toe_off"]`

### 2.6 Subject Demographics (`SubjectInfo.mat`)

| Field | Description |
|-------|-------------|
| `subject` | Subject ID string (e.g. `"AB06"`) |
| `age` | Age (years) |
| `mass` | Body mass (kg) |
| `height` | Standing height (m) |
| `leg_length` | Leg length, greater trochanter to lateral malleolus (m) |
| `sex` | `'M'` / `'F'` |

### 2.7 Loader Output (`CamargoAdapter.load_trial`)

```python
Trial(
    source    = "camargo",
    subject   = "AB06",
    trial_id  = "treadmill_01_01",
    fs        = 1000.0,
    t         = np.ndarray,                   # (N,) seconds
    channels  = {
        "gastrocnemius_l":   np.ndarray,      # (N,) mV
        "gastrocnemius_m":   np.ndarray,
        "soleus":            np.ndarray,
        "tibialis_anterior": np.ndarray,
        "vastus_medialis":   np.ndarray,
        "vastus_lateralis":  np.ndarray,
        "rectus_femoris":    np.ndarray,
        "biceps_femoris":    np.ndarray,
        "semitendinosus":    np.ndarray,
        "gluteus_medius":    np.ndarray,
        "gluteus_maximus":   np.ndarray,
    },
    units     = "mV",
    meta      = {
        "mode":     "treadmill",              # locomotion mode
        "date":     "10_09_18",               # collection date
        "subject_mass_kg": float,             # from SubjectInfo.mat
    },
    events    = {
        "heel_strike": np.ndarray,            # (M,) seconds, from gcRight
        "toe_off":     np.ndarray,            # (M,) seconds
    },
)
```

---

## 3. Public Dataset — Gait120

### 3.1 Overview

| Property | Value |
|----------|-------|
| Subjects | 10 able-bodied adults (S001–S010) |
| Channels | 12 right-leg surface EMG |
| Sampling rate | 2 000 Hz (raw); pre-interpolated to 101 points (0–100 % gait cycle) |
| Signal unit | MVC fraction (0–1, normalised inside the dataset) |
| File format | MATLAB `.mat` (MCOS-backed table objects, v5) |
| Locomotion modes | 7 (see §3.3) |
| Gait events | Embedded as `TargetFrame` indices in the motion-capture reference frame |

### 3.2 Directory Layout

```
Gait120_001_to_010/
├── S001/
│   ├── EMG/
│   │   ├── RawData.mat          # raw 2 kHz signals, per-trial MCOS tables
│   │   └── ProcessedData.mat    # envelope, filtered, normalised, and
│   │                            # gait-cycle-interpolated (101 pt) data
│   ├── JointAngle/              # OpenSim .mot files (joint angles)
│   │   ├── LevelWalking/Trial01/step01.mot …
│   │   └── …
│   └── MotionCapture/           # marker trajectories (.trc files, 100 Hz)
│       ├── LevelWalking/TRC/Trial01/Step01.trc …
│       └── …
├── S002/ … S010/
```

### 3.3 Locomotion Modes

| Key in `.mat` | Description | Steps per trial |
|---------------|-------------|-----------------|
| `LevelWalking` | Overground level walking | 2 |
| `StairAscent` | Stair climbing, ascent | 2 |
| `StairDescent` | Stair climbing, descent | 2 |
| `SlopeAscent` | Inclined ramp, ascent | 2 |
| `SlopeDescent` | Inclined ramp, descent | 2 |
| `SitToStand` | Sit-to-stand transition | 1 |
| `StandToSit` | Stand-to-sit transition | 1 |

Each mode contains up to 5 trials. `AvailableTrialIdx` (inside the struct) lists which trial indices are actually present for a given subject.

### 3.4 EMG Channel Names (fixed order, right leg)

| Index | Key in `.mat` | Muscle |
|-------|--------------|--------|
| 0 | `VastusLateralis` | Vastus lateralis |
| 1 | `RectusFemoris` | Rectus femoris |
| 2 | `VastusMedialis` | Vastus medialis |
| 3 | `TibialisAnterior` | Tibialis anterior |
| 4 | `BicepsFemoris` | Biceps femoris |
| 5 | `Semitendinosus` | Semitendinosus |
| 6 | `GastrocnemuisMedialis` | Gastrocnemius medialis *(typo preserved from source)* |
| 7 | `GastrocnemiusLateralis` | Gastrocnemius lateralis |
| 8 | `SoleusMedialis` | Soleus medialis |
| 9 | `SoleusLateralis` | Soleus lateralis |
| 10 | `PeroneusLongus` | Peroneus longus |
| 11 | `PeroneusBrevis` | Peroneus brevis |

### 3.5 `RawData.mat` Structure

| Field path | Type | Description |
|------------|------|-------------|
| `EMGs_info.fs` | double | EMG sampling rate (2 000 Hz) |
| `Markers_info.fs` | double | Motion-capture sampling rate (100 Hz) |
| `<Mode>.nTrials` | uint8 | Total number of trials for this mode |
| `<Mode>.AvailableTrialIdx` | uint array | 1-based indices of existing trials |
| `<Mode>.Trial<N>.EMGs_raw` | MCOS table | Raw 2 kHz signal, 12 channels |
| `<Mode>.Trial<N>.TotalFrame` | uint16 (1×2) | [start, end] motion-capture frame of the full trial |
| `<Mode>.Trial<N>.nSteps` | uint8 | Number of gait steps segmented in the trial |
| `<Mode>.Trial<N>.Step<S>.TargetFrame` | uint16 (1×2) | [start, end] motion-capture frame of gait step S |
| `<Mode>.MVC_raw` | struct | MVC contraction recordings (5 × 1 trials), same table format |

### 3.6 `ProcessedData.mat` Structure

| Field path | Type | Description |
|------------|------|-------------|
| `<Mode>.Trial<N>.MVCs` | double (1×12) | MVC peak values per channel (Volts) |
| `<Mode>.Trial<N>.Step<S>.EMGs_env` | MCOS table | Linear envelope (2 000 Hz), normalised to MVC |
| `<Mode>.Trial<N>.Step<S>.EMGs_filt` | MCOS table | Band-pass filtered signal (2 000 Hz), normalised |
| `<Mode>.Trial<N>.Step<S>.EMGs_norm` | MCOS table | Normalised envelope at native 2 000 Hz duration |
| `<Mode>.Trial<N>.Step<S>.EMGs_interpolated` | MCOS table | Normalised envelope resampled to **101 points** (0–100 % gait cycle) |

### 3.7 MCOS Decoding

Both `.mat` files store EMG tables as MCOS objects (same internal format as the Camargo dataset). The loader (`gait120_mat.py`) decodes them via the `__function_workspace__` subsystem:

```python
opaque = step["EMGs_interpolated"][0]   # MatlabOpaque element
idx4   = int(opaque["arr"].ravel()[4])  # table slot index (1-based)
ws_pos = 2 + (idx4 - 1) * 7            # position in workspace arr
data   = workspace_arr[ws_pos]          # object array of 12 channel arrays
```

### 3.8 Loader Output (`gait120_mat.load_mode_steps`)

```python
load_mode_steps(path: Path, mode: str) -> dict[str, np.ndarray]
# Returns {channel_name: np.ndarray(n_steps, 101)}
# n_steps = nTrials * nSteps_per_trial (typically 10 for locomotion, 5 for transitions)
# Values are MVC fraction (0–1 range)
```

---

## 4. Cross-Dataset Channel Mapping

The **Compare View** aligns channels from different datasets using a shared **canonical name**. Canonical names follow Camargo's lowercase column names (underscores, no spaces).

| Canonical Name | Camargo Column | MyoMetrics Column | Muscle (plain English) |
|----------------|---------------|-------------------|------------------------|
| `biceps_femoris` | `biceps_femoris` | `BICEPS_FEM._RT` | Biceps femoris (hamstring) |
| `gluteus_medius` | `gluteus_medius` | `GLUT_MED._RT` | Gluteus medius (hip abductor) |
| `rectus_femoris` | `rectus_femoris` | `RECTUS_FEM._RT` | Rectus femoris (quad head) |
| `gastrocnemius_l` | `gastrocnemius_l` | — | Gastrocnemius lateralis |
| `gastrocnemius_m` | `gastrocnemius_m` | — | Gastrocnemius medialis |
| `soleus` | `soleus` | — | Soleus |
| `tibialis_anterior` | `tibialis_anterior` | — | Tibialis anterior |
| `vastus_medialis` | `vastus_medialis` | — | Vastus medialis |
| `vastus_lateralis` | `vastus_lateralis` | — | Vastus lateralis |
| `semitendinosus` | `semitendinosus` | — | Semitendinosus (hamstring) |
| `gluteus_maximus` | `gluteus_maximus` | — | Gluteus maximus |

The Compare View only plots canonical channels present in **all** selected trials. With the current 3-channel MyoMetrics setup, comparisons are limited to `biceps_femoris`, `gluteus_medius`, and `rectus_femoris`.

---

## 5. Unified `Trial` Representation

Both adapters produce the same `Trial` dataclass, which is the only type the GUI, processing layer, and export services ever consume:

```python
@dataclass
class Trial:
    source:   str                        # "camargo" | "myometrics"
    subject:  str                        # "AB06"  |  "self-2026.4.13"
    trial_id: str                        # "treadmill_01_01" | "EMG-with Electrode"
    fs:       float                      # samples per second
    t:        np.ndarray                 # (N,) time axis, seconds
    channels: dict[str, np.ndarray]      # raw channel name → (N,) array
    units:    str                        # "mV" | "uV"
    meta:     dict                       # adapter-specific key-value metadata
    events:   dict[str, np.ndarray]      # "heel_strike" / "toe_off" → (M,) seconds
```

### Unit Normalisation

The processing pipeline does **not** automatically convert units between datasets. Normalisation options handle the scale difference instead:

| Mode | Formula | Applicable to |
|------|---------|---------------|
| `off` | raw signal | both |
| `mvc_peak` | `signal / mvc_peak_abs` | MyoMetrics only |
| `mvc_env95` | `signal / 95th-pct of MVC envelope` | MyoMetrics only |
| `task_env95` | `signal / 95th-pct of trial envelope` | both |

For cross-dataset comparison, `task_env95` is the recommended normalisation because it requires no separate MVC session and produces dimensionless 0–1 amplitude on both datasets.

---

*Last updated: 2026-04-27*
