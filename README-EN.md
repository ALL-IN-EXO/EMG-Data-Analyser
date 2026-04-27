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

---

### 1.2 Page 1: Raw Timeline (Self-Collected Data)

1. Click `Data Folder` and select your MyoMetrics session directory.
2. Click `MVC Folder` and select an MVC directory (must contain `Channel_Curves-*.csv`).
3. Tune `Display Pipeline` (`Highpass / Smoothing / Cutoff / Window`) — plots update live.
4. Drag the blue selection region on the plots to define the segmentation window.
5. Click `→ Gait Cycle Segmentation` to enter Page 2.

---

### 1.3 Page 2: Gait Cycle Segmentation

1. In `Segmentation`, configure `Method` (`autocorr` or `heelstrike`), `Ref. muscle`, and `Period min/max`.
2. In `Display`, select normalisation (`mvc_env95 / task_env95 / off`) and optional individual-cycle overlay.
3. Parameter changes trigger automatic re-segmentation and redraw.
4. `Cycle Stats` and the bottom status bar show summary metrics; use `Export PNG` to save the figure.

---

### 1.4 Page 3: Camargo Dataset

1. Click the folder button in `Dataset` and choose the Camargo root (e.g., `.../Camargo2021`).
2. Click `Scan Dataset`.
3. Select `Activity`, `Subject`, and configure `Segmentation` + `Filter Chain`.
4. Click `Run Analysis`.
5. Re-analysis runs only when `Run Analysis` is clicked — parameter edits alone do not trigger it.
6. `Display` and `Muscles` checkboxes only control what is drawn; they do not re-run analysis.

---

### 1.5 Page 4: Gait120 Dataset

Gait120 is a public EMG dataset covering 100 subjects and 7 locomotion modes. EMG signals are pre-segmented and MVC-normalised, then linearly interpolated to 101 points (0–100 % gait cycle). **No manual segmentation is required** — load and plot immediately.

1. Click the folder button in `Dataset` and choose the Gait120 root (the directory containing `S001/`, `S002/`, … subfolders).
2. Click `Scan Dataset` — subjects are detected automatically.
3. In `Activity Mode`, choose one of the 7 locomotion modes (see table below).
4. In `Subject`, select a single subject or `All subjects`.  
   - Single subject: mean ± std fill across all steps.  
   - All subjects: one thin mean line per subject + bold global mean.
5. In `Muscles`, tick the channels to display (12 available).
6. Click `Run Analysis` to load data and render plots.
7. `Normalize per channel` rescales each panel to 0–1; `Show individual steps` overlays each individual gait step.

| Activity Mode | Description | Steps / trial |
|---------------|-------------|---------------|
| LevelWalking | Overground level walking | 2 |
| StairAscent | Stair climbing, ascent | 2 |
| StairDescent | Stair climbing, descent | 2 |
| SlopeAscent | Inclined ramp, ascent | 2 |
| SlopeDescent | Inclined ramp, descent | 2 |
| SitToStand | Sit-to-stand transition | 1 |
| StandToSit | Stand-to-sit transition | 1 |

> Y-axis unit: **MVC fraction** (0–1). Normalisation is baked into the dataset; no external MVC files are needed.

---

### 1.6 Common Paths and Warnings

| Scenario | Recommendation |
|----------|----------------|
| MyoMetrics | `Data Folder`: session parent dir; `MVC Folder`: dir containing `Channel_Curves-*.csv` |
| Camargo | In Page 3, choose `Camargo2021/` root — not a nested `ABxx/.../emg` folder |
| Gait120 | In Page 4, choose the directory that directly contains `S001/`, `S002/`, … |
| `No recognised dataset found` | Selected path does not match any supported folder structure |
| `Selected MVC folder has no Channel_Curves CSV` | Wrong MVC folder was selected |

---

## 2. Dataset Download

### 2.1 Camargo 2021 Lower-Limb Biomechanics Dataset

22 able-bodied adult subjects performing treadmill walking, level-ground walking, ramp ascent/descent, and stair ascent/descent. Includes 11-channel lower-limb surface EMG at 1 kHz plus joint kinematics and kinetics (Aaron Young Lab, Georgia Tech).

| Part | DOI | Subjects | Compressed size |
|------|-----|----------|-----------------|
| Part 1/3 | [10.17632/fcgm3chfff.1](http://dx.doi.org/10.17632/fcgm3chfff.1) | AB06–AB14 | ~9.5 GB |
| Part 2/3 | [10.17632/k9kvm5tn3f.1](http://dx.doi.org/10.17632/k9kvm5tn3f.1) | AB15–AB25 | ~10.1 GB |
| Part 3/3 | [10.17632/jj3r5f9pnf.1](http://dx.doi.org/10.17632/jj3r5f9pnf.1) | AB27, AB28, AB30 | ~3.2 GB |

> Total compressed: **~22.6 GB**; extracted footprint: **~45 GB** (including temporary ZIPs).  
> Ensure the target disk has **≥ 50 GB** free (or **≥ 70 GB** with `--keep-zips`).

#### Prerequisites

| Tool | Ubuntu | macOS | Windows (Git Bash / WSL) |
|------|--------|-------|--------------------------|
| `bash` ≥ 3.2 | system default | system default | Git Bash / WSL built-in |
| `curl` or `wget` | `sudo apt install curl` | `brew install curl` | Git Bash ships with curl |
| `unzip` | `sudo apt install unzip` | `brew install unzip` | `pacman -S unzip` (MSYS2) |
| `python3` | system default | system default | bundled with Python installer |

`python3` is only used to parse JSON file listings — no additional pip packages required.

#### Quick Start

```bash
cd EMG-Data-Analyser/TOOLS
chmod +x download_dataset.sh

./download_dataset.sh --list-only          # preview file list, no download
./download_dataset.sh                      # download all parts (→ ../Dataset/Camargo2021)
./download_dataset.sh --dest /data/Camargo # custom destination
./download_dataset.sh --parts 1 --keep-zips
```

| Flag | Description |
|------|-------------|
| `--dest DIR` | Override the destination directory |
| `--parts N[,N]` | Download only specified parts (default: all) |
| `--keep-zips` | Retain raw `ABxx.zip` files after extraction |
| `--list-only` | Print the file manifest without downloading |

After completion, `Dataset/Camargo2021/` is laid out as:

```
Dataset/Camargo2021/
├── AB06/
│   └── 10_09_18/
│       ├── treadmill/
│       │   ├── emg/          # treadmill_01_01.mat …
│       │   ├── gcRight/      # gait cycle events (heel strikes, toe-offs)
│       │   └── …
│       ├── levelground/
│       ├── ramp/
│       └── stair/
├── AB07/ … AB30/
├── README.txt
├── SubjectInfo.mat
└── scripts_part1/
```

> **Known gaps**: Part 2 is missing AB22; Part 3 is missing AB26 and AB29. These are upstream omissions, not download errors.

---

### 2.2 Gait120 Comprehensive Locomotion & EMG Dataset

Published on Springer Nature Figshare. 100 able-bodied subjects (S001–S100), 7 locomotion modes, 12-channel right-leg surface EMG at 2 kHz. The dataset ships pre-processed MVC-normalised signals resampled to 101-point gait-cycle profiles — ready to visualise without additional processing.

| Article | [figshare.com/…/27677016](https://springernature.figshare.com/articles/dataset/Comprehensive_Human_Locomotion_and_Electromyography_Dataset_Gait120/27677016) |
|---------|---|

| Pack | File | Subjects | Compressed size |
|------|------|----------|-----------------|
| 1 | Gait120_001_to_010.zip | S001–S010 | ~1.45 GB |
| 2 | Gait120_011_to_020.zip | S011–S020 | ~1.42 GB |
| 3 | Gait120_021_to_030.zip | S021–S030 | ~1.37 GB |
| 4 | Gait120_031_to_040.zip | S031–S040 | ~1.37 GB |
| 5 | Gait120_041_to_050.zip | S041–S050 | ~1.35 GB |
| 6 | Gait120_051_to_060.zip | S051–S060 | ~1.34 GB |
| 7 | Gait120_061_to_070.zip | S061–S070 | ~1.42 GB |
| 8 | Gait120_071_to_080.zip | S071–S080 | ~1.35 GB |
| 9 | Gait120_081_to_090.zip | S081–S090 | ~1.38 GB |
| 10 | Gait120_091_to_100.zip | S091–S100 | ~1.41 GB |

> Full download: **~13.9 GB** compressed; extracted footprint: **~40 GB**.  
> Pack 1 only (S001–S010): **~1.45 GB**.

#### Quick Start

```bash
cd EMG-Data-Analyser/TOOLS
chmod +x download_gait120.sh

./download_gait120.sh --list-only          # preview all files, no download
./download_gait120.sh --packs 1            # only S001–S010 (~1.45 GB)
./download_gait120.sh                      # all 100 subjects (~13.9 GB)
./download_gait120.sh --dest /data/Gait120 # custom destination
```

| Flag | Description |
|------|-------------|
| `--dest DIR` | Destination directory (default: `../Dataset/Gait120`) |
| `--packs N[,N]` | Download only specified packs (e.g. `--packs 1` → S001–S010) |
| `--keep-zips` | Retain raw ZIP files after extraction |
| `--list-only` | Print the file manifest without downloading |

After completion, `Dataset/Gait120/` is laid out as:

```
Dataset/Gait120/
├── S001/
│   ├── EMG/
│   │   ├── RawData.mat          # raw 2 kHz EMG (MCOS table format)
│   │   └── ProcessedData.mat    # MVC-normalised + 101-point gait-cycle profiles
│   ├── JointAngle/              # OpenSim .mot joint angle files
│   └── MotionCapture/           # marker trajectories (.trc, 100 Hz)
├── S002/ … S100/
```

#### Resumable Downloads

The script is **idempotent** and can be interrupted and re-run at any time:

- **Download phase** — `curl -C -` / `wget -c` resumes partial ZIPs automatically.
- **Extraction phase** — any non-empty `Sxxx/` directory already present in the destination is skipped.
- **File manifest** — `_downloads/figshare_files.json` is cached locally; re-runs skip the API call.

---

## 3. Project Structure

```
EMG-Data-Analyser/
├── Dataset/                        # local datasets (git-ignored)
│   ├── Camargo2021/                # ← download_dataset.sh output
│   └── Gait120/                   # ← download_gait120.sh output
├── DOCS/
│   ├── DATASET.md                  # field conventions, sampling rates, channel maps
│   └── WORKFLOW.md                 # overall architecture design
├── SAMPLE_DATA/
│   └── 2026.4.13-EMG/             # self-collected sample session
├── TOOLS/
│   ├── download_dataset.sh         # Camargo 2021 downloader (Mendeley Data)
│   └── download_gait120.sh        # Gait120 downloader (Springer Nature Figshare)
├── src/emg_analyser/
│   ├── gui/pages/
│   │   ├── page1_timeline.py       # raw waveform viewer
│   │   ├── page2_gait.py           # gait-cycle segmentation view
│   │   ├── page3_camargo.py        # Camargo 2021 dataset view
│   │   └── page4_gait120.py        # Gait120 dataset view
│   ├── io/
│   │   ├── camargo_adapter.py      # Camargo adapter
│   │   ├── camargo_mat.py          # Camargo MCOS table decoder
│   │   ├── gait120_mat.py          # Gait120 MCOS table decoder
│   │   └── myo_csv.py              # MyoMetrics CSV loader
│   └── services/worker.py          # background threads (Load / Reprocess /
│                                   #   Segment / CamargoThread / Gait120Thread)
├── run.py                          # application entry point
├── README.md                       # Chinese README
└── README-EN.md                    # this file
```
