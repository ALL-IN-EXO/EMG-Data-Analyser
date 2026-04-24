# EMG-Data-Analyser

A PyQt desktop application for analysing and comparing self-collected EMG datasets against public benchmarks.  
Architecture design: [`DOCS/WORKFLOW.md`](DOCS/WORKFLOW.md) | Dataset reference: [`DOCS/DATASET.md`](DOCS/DATASET.md)

---

## 1. Dataset Download

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

## 2. Project Structure

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
