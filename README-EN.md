# EMG-Data-Analyser

A PyQt desktop application for analysing and comparing self-collected EMG datasets against public benchmarks.  
Architecture design: [`DOCS/WORKFLOW.md`](DOCS/WORKFLOW.md) | Dataset reference: [`DOCS/DATASET.md`](DOCS/DATASET.md)

---

## 1. Software Usage (GUI)

### 1.1 Setup and Launch

```bash
# Optional: create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install runtime dependencies
pip install -U pip
pip install PyQt5 pyqtgraph numpy scipy pandas

# Launch GUI
python3 run.py
# or
PYTHONPATH=src python3 -m emg_analyser
```

### 1.2 Page 1: Raw Timeline (Self-Collected Data)

1. Click `Data Folder` and select your data directory.
2. Click `MVC Folder` and select an MVC directory (must contain `Channel_Curves-*.csv`).
3. Tune `Display Pipeline` (`Highpass / Smoothing / Cutoff / Window`) for live updates.
4. Drag the blue selection region on the plots to define the segmentation window.
5. Click `→ Gait Cycle Segmentation` to enter Page 2.

### 1.3 Page 2: Gait Cycle Segmentation

1. In `Segmentation`, configure `Method` (`autocorr` or `heelstrike`), `Ref. muscle`, and `Period min/max`.
2. In `Display`, select normalization (`mvc_env95 / task_env95 / off`) and optional individual-cycle overlay.
3. Parameter changes trigger automatic re-segmentation and redraw.
4. `Cycle Stats` and the bottom status bar show summary metrics; use `Export PNG` to save the figure.

### 1.4 Page 3: Camargo Dataset

1. Click the folder button in `Dataset` and choose the Camargo root (e.g., `.../Camargo2021`).
2. Click `Scan Dataset`.
3. Select `Activity`, `Subject`, and configure `Segmentation` + `Filter Chain`.
4. Click `Run Analysis`.
5. Re-analysis runs only when `Run Analysis` is clicked (parameter edits alone do not trigger analysis).
6. `Display` and `Muscles` checkboxes only change what is drawn; they do not re-run analysis.

### 1.5 Common Paths and Warnings

- MyoMetrics:
  - `Data Folder`: session parent directory or a single session directory.
  - `MVC Folder`: MVC session directory or its parent.
- Camargo:
  - In Page 3, choose the `Camargo2021` root, not a nested `ABxx/.../emg` folder.
- Common warnings:
  - `No recognised dataset found`: selected data path does not match a supported folder structure.
  - `Selected MVC folder has no Channel_Curves CSV`: wrong MVC folder was selected.

---

## 2. Dataset Download

### Dataset Overview

**Camargo 2021 Lower-Limb Biomechanics Dataset** (Aaron Young Lab, Georgia Tech)  
22 able-bodied adult subjects performing treadmill walking, level-ground walking, ramp ascent/descent, and stair ascent/descent. Includes 11-channel lower-limb surface EMG (1 kHz) plus joint kinematics and kinetics.

| Part | DOI | Subjects | Size |
|------|-----|----------|------|
| Part 1/3 | [10.17632/fcgm3chfff.1](http://dx.doi.org/10.17632/fcgm3chfff.1) | AB06 – AB14 | ~9.5 GB |
| Part 2/3 | [10.17632/k9kvm5tn3f.1](http://dx.doi.org/10.17632/k9kvm5tn3f.1) | AB15 – AB25 | ~10.1 GB |
| Part 3/3 | [10.17632/jj3r5f9pnf.1](http://dx.doi.org/10.17632/jj3r5f9pnf.1) | AB27, AB28, AB30 | ~3.2 GB |

> Total compressed download: **~22.6 GB**; extracted footprint: **~45 GB** (including temporary ZIPs).  
> Ensure the target disk has **≥ 50 GB** free space (or **≥ 70 GB** with `--keep-zips`).

---

### Prerequisites

| Tool | Ubuntu | macOS | Windows (Git Bash / WSL) |
|------|--------|-------|--------------------------|
| `bash` ≥ 3.2 | system default | system default | Git Bash / WSL built-in |
| `curl` or `wget` | `sudo apt install curl` | `brew install curl` | Git Bash ships with curl |
| `unzip` | `sudo apt install unzip` | `brew install unzip` | `pacman -S unzip` (MSYS2) |
| `python3` | system default | system default | bundled with Python installer |

`python3` is only used to parse Mendeley's JSON file listings — no additional pip packages required.

---

### Quick Start

```bash
# 1. Enter the tools directory
cd EMG-Data-Analyser/TOOLS

# 2. Grant execute permission (Linux / macOS)
chmod +x download_dataset.sh

# 3. Preview the file list without downloading
./download_dataset.sh --list-only

# 4. Download and merge all parts (default destination: ../Dataset/Camargo2021)
./download_dataset.sh
```

After completion, `Dataset/Camargo2021/` will be laid out as follows:

```
Dataset/Camargo2021/
├── AB06/
│   ├── 10_09_18/
│   │   ├── treadmill/
│   │   │   ├── emg/          # treadmill_01_01.mat ...
│   │   │   ├── gcRight/      # gait cycle events (heel strikes, toe-offs)
│   │   │   ├── gon/          # goniometer (joint angles)
│   │   │   └── ...
│   │   ├── levelground/
│   │   ├── ramp/
│   │   └── stair/
├── AB07/ ... AB30/
├── README.txt                 # original dataset documentation
├── README_part2.txt
├── README_part3.txt
├── SubjectInfo.mat
└── scripts_part1/             # MATLAB scripts shipped with the dataset
```

---

### CLI Options

| Flag | Description | Example |
|------|-------------|---------|
| `--dest DIR` | Override the destination directory | `--dest /data/Camargo` |
| `--parts N[,N]` | Download only the specified parts (default: all) | `--parts 1,3` |
| `--keep-zips` | Retain raw `ABxx.zip` files after extraction | `--keep-zips` |
| `--list-only` | Print the file manifest without downloading | `--list-only` |

```bash
# Part 1 only, keep ZIPs
./download_dataset.sh --parts 1 --keep-zips

# Custom destination
./download_dataset.sh --dest /mnt/data/Camargo2021

# Resume Part 3 (Parts 1 and 2 already downloaded will be skipped)
./download_dataset.sh --parts 3
```

---

### Resumable Downloads

The script is **idempotent** and can be interrupted and re-run at any time:

- **Download phase** — `curl -C -` / `wget -c` resumes partial ZIPs automatically.
- **Extraction phase** — any non-empty `ABxx/` directory is skipped.
- **File manifest** — the per-part `_downloads/*_files.json` is cached locally; re-runs skip the Mendeley API call.

---

### Known Dataset Gaps

- Part 2 is missing **AB22**; Part 3 is missing **AB26** and **AB29**.  
  These are upstream omissions in the published dataset, not download errors.
- Mendeley Data download URLs are fetched in real-time from the official API; they remain valid until 2126 and require no manual updates.
- Windows users are recommended to use **WSL** or **Git Bash**; WSL requires `unzip` to be installed separately (`sudo apt install unzip`).

---

## 3. Project Structure

```
EMG-Data-Analyser/
├── Dataset/                   # local datasets (git-ignored)
│   └── Camargo2021/
├── DOCS/
│   ├── WORKFLOW.md            # overall architecture design
│   └── DATASET.md             # dataset field conventions, sampling rates, units
├── TOOLS/
│   └── download_dataset.sh    # dataset download script
├── README.md                  # Chinese README
└── README-EN.md               # this file
```
