# EMG-Data-Analyser

PyQt 桌面应用，用于自采 EMG 数据集与公共数据集的分析和对比。  
架构设计见 [`DOCS/WORKFLOW.md`](DOCS/WORKFLOW.md)。

---

## 数据下载

### 数据集简介

**Camargo 2021 下肢生物力学数据集**（Aaron Young 实验室）  
包含 22 名健全成人受试者在跑步机、平地、坡道、楼梯等运动模式下的
11 通道下肢 EMG（1 kHz）及关节运动学/动力学数据。

| 部分 | DOI | 受试者 | 公开体积 |
|------|-----|--------|---------|
| Part 1/3 | [10.17632/fcgm3chfff.1](http://dx.doi.org/10.17632/fcgm3chfff.1) | AB06 – AB14 | ~9.5 GB |
| Part 2/3 | [10.17632/k9kvm5tn3f.1](http://dx.doi.org/10.17632/k9kvm5tn3f.1) | AB15 – AB25 | ~10.1 GB |
| Part 3/3 | [10.17632/jj3r5f9pnf.1](http://dx.doi.org/10.17632/jj3r5f9pnf.1) | AB27, AB28, AB30 | ~3.2 GB |

> 合计约 **22.6 GB** 下载量；解压后约 **45 GB**（含临时 ZIP）。  
> 请确保目标磁盘有 **≥ 50 GB** 可用空间（使用 `--keep-zips` 则需 ≥ 70 GB）。

---

### 前置依赖

| 工具 | Ubuntu | macOS | Windows (Git Bash / WSL) |
|------|--------|-------|--------------------------|
| `bash` ≥ 3.2 | 系统自带 | 系统自带 | Git Bash / WSL 自带 |
| `curl` 或 `wget` | `sudo apt install curl` | `brew install curl` | Git Bash 自带 curl |
| `unzip` | `sudo apt install unzip` | `brew install unzip` | `pacman -S unzip`（MSYS2）|
| `python3` | 系统自带 | 系统自带 | 安装 Python 时自带 |

`python3` 仅用于解析 Mendeley 的 JSON 文件列表，无需额外 pip 包。

---

### 快速开始

```bash
# 1. 进入脚本目录
cd EMG-Data-Analyser/TOOLS

# 2. 赋予可执行权限（Linux / macOS）
chmod +x download_dataset.sh

# 3. 先用 --list-only 预览文件清单，不实际下载
./download_dataset.sh --list-only

# 4. 正式下载并合并（默认目标：../Dataset/Camargo2021）
./download_dataset.sh
```

下载完成后，`Dataset/Camargo2021/` 的结构如下：

```
Dataset/Camargo2021/
├── AB06/
│   ├── 10_09_18/
│   │   ├── treadmill/
│   │   │   ├── emg/          # treadmill_01_01.mat ...
│   │   │   ├── gcRight/      # gait cycle events
│   │   │   ├── gon/          # goniometer (joint angles)
│   │   │   └── ...
│   │   ├── levelground/
│   │   ├── ramp/
│   │   └── stair/
├── AB07/ ... AB30/
├── README.txt                 # 数据集原版说明
├── README_part2.txt
├── README_part3.txt
├── SubjectInfo.mat
└── scripts_part1/             # 数据集配套 MATLAB 脚本
```

---

### 常用参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `--dest DIR` | 指定合并目标目录 | `--dest /data/Camargo` |
| `--parts N[,N]` | 只下载指定部分（默认全部） | `--parts 1,3` |
| `--keep-zips` | 保留原始 ABxx.zip（默认下载并解压后删除） | `--keep-zips` |
| `--list-only` | 仅列出文件清单，不下载 | `--list-only` |

```bash
# 仅下载 Part 1，保留 ZIP
./download_dataset.sh --parts 1 --keep-zips

# 下载到自定义路径
./download_dataset.sh --dest /mnt/data/Camargo2021

# 只补下 Part 3（已下载的 Part 1/2 会自动跳过）
./download_dataset.sh --parts 3
```

---

### 断点续传 / 重新运行

脚本是**幂等的**，可以随时中断再重新运行：

- 下载阶段：`curl -C -` / `wget -c` 自动续传未完成的 ZIP。
- 解压阶段：已存在且非空的 `ABxx/` 目录会跳过解压。
- 文件列表（每个 Part 的 `_downloads/*_files.json`）缓存在本地，重跑不重新查询 API。

---

### 注意事项

- Part 2 缺少 **AB22**，Part 3 缺少 **AB26 / AB29**，这是数据集本身的发布状态，不是下载问题。
- Mendeley Data 的下载 URL 由脚本实时从官方 API 获取，有效期至 2126 年，无需手动更新。
- Windows 用户建议使用 **WSL** 或 **Git Bash**；WSL 下 `unzip` 需单独安装（`sudo apt install unzip`）。

---

## 项目结构

```
EMG-Data-Analyser/
├── Dataset/                   # 本地数据集（git-ignored）
│   └── Camargo2021/
├── DOCS/
│   └── WORKFLOW.md            # 整体架构设计
├── TOOLS/
│   └── download_dataset.sh    # 数据下载脚本
└── README.md                  # 本文件
```
