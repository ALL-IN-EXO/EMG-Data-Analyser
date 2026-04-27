# EMG-Data-Analyser

PyQt 桌面应用，用于自采 EMG 数据集与公共数据集的分析和对比。  
架构设计见 [`DOCS/WORKFLOW.md`](DOCS/WORKFLOW.md) | 数据集字段说明见 [`DOCS/DATASET.md`](DOCS/DATASET.md)

---

## 软件使用（GUI）

### 1. 环境与启动

```bash
# 可选：创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装运行依赖
pip install -U pip
pip install PyQt5 pyqtgraph numpy scipy pandas

# 启动 GUI
python3 run.py
# 或
PYTHONPATH=src python3 -m emg_analyser
```

#### macOS 打开崩溃（`NSOpenPanel` / `bus error`）排查

若你在 mac 上看到类似：

- `The class 'NSOpenPanel' overrides the method identifier`
- `zsh: bus error ... python3`

优先检查 Python 架构是否与机器一致（Apple Silicon 请避免 `/usr/local/bin/python3` 的 x86 解释器）：

```bash
python3 -c "import platform,sys; print(platform.machine(), sys.executable)"
```

- Apple Silicon 推荐输出 `arm64`，解释器路径通常是 `/opt/homebrew/bin/python3`。
- 若输出 `x86_64`，建议换 arm64 Python 后重建环境再安装依赖：

```bash
/opt/homebrew/bin/python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install PyQt5 pyqtgraph numpy scipy pandas
python3 run.py
```

---

### 2. 页面 1：Raw Timeline（自采数据）

1. 点击 `Data Folder` 选择数据目录（自采 MyoMetrics session 文件夹）。
2. 点击 `MVC Folder` 选择 MVC 目录（必须包含 `Channel_Curves-*.csv`）。
3. 右侧 `Display Pipeline` 调整 `Highpass / Smoothing / Cutoff / Window`，曲线实时更新。
4. 在图上拖动蓝色时间区间，选择要分段的时间窗。
5. 点击 `→ Gait Cycle Segmentation` 进入第 2 页。

---

### 3. 页面 2：Gait Cycle Segmentation

1. 在 `Segmentation` 中设置 `Method`（`autocorr` 或 `heelstrike`）、`Ref. muscle`、`Period min/max`。
2. 在 `Display` 中设置归一化（`mvc_env95 / task_env95 / off`）和是否显示单周期轨迹。
3. 参数变更会自动重新分段并刷新图像。
4. 右侧 `Cycle Stats` 与底部状态栏显示周期统计；可点击 `Export PNG` 导出当前图。

---

### 4. 页面 3：Camargo Dataset

1. 点击 `Dataset` 区域的文件夹按钮，选择 Camargo 根目录（如 `.../Camargo2021`）。
2. 点击 `Scan Dataset`。
3. 选择 `Activity`、`Subject`，设置 `Segmentation` 和 `Filter Chain`。
4. 点击 `Run Analysis` 执行分析。
5. 仅当点击 `Run Analysis` 才会重新分析（参数改动不会自动触发）。
6. `Display` 与 `Muscles` 复选框用于控制显示，不会触发重新分析。

---

### 5. 页面 4：Gait120 Dataset

Gait120 是包含 100 名受试者、7 种运动模式的公开 EMG 数据集，内置 MVC 归一化步态周期插值（101 点，0–100%），**无需手动分段即可直接可视化**。

1. 点击 `Dataset` 区域的文件夹按钮，选择 Gait120 根目录（包含 `S001/`、`S002/`… 子文件夹的目录）。
2. 点击 `Scan Dataset`，软件自动识别所有受试者。
3. 在 `Activity Mode` 中选择运动模式（共 7 种，见下表）。
4. 在 `Subject` 中选择单个受试者或 `All subjects`（多受试者模式显示每人一条均值曲线 + 加粗全局均值）。
5. 在 `Muscles` 中勾选需要显示的 12 个通道。
6. 点击 `Run Analysis` 加载数据并绘图。
7. 勾选 `Normalize per channel` 可将 Y 轴归一至 0–1；勾选 `Show individual steps` 可叠加单步轨迹。

| 运动模式 | 说明 | 步数/trial |
|----------|------|-----------|
| LevelWalking | 平地步行 | 2 |
| StairAscent | 上楼梯 | 2 |
| StairDescent | 下楼梯 | 2 |
| SlopeAscent | 坡道上行 | 2 |
| SlopeDescent | 坡道下行 | 2 |
| SitToStand | 坐立转换 | 1 |
| StandToSit | 立坐转换 | 1 |

> Y 轴单位为 **MVC 分数**（0–1），数据集内部已完成归一化，无需外部 MVC 文件。

---

### 6. 常见路径与问题

| 场景 | 建议 |
|------|------|
| MyoMetrics | `Data Folder` 选 session 父目录；`MVC Folder` 选包含 `Channel_Curves-*.csv` 的目录 |
| Camargo | 第 3 页选择 `Camargo2021/` 根目录，不要选到 `ABxx/.../emg` 子目录 |
| Gait120 | 第 4 页选择包含 `S001/`、`S002/`… 的目录（即 `download_gait120.sh` 的 `--dest`）|
| `No recognised dataset found` | 数据目录不符合适配器扫描结构 |
| `Selected MVC folder has no Channel_Curves CSV` | MVC 目录选择错误 |

---

## 数据下载

### Camargo 2021 下肢生物力学数据集

**Aaron Young 实验室** 采集的 22 名健全成人受试者在跑步机、平地、坡道、楼梯等模式下的 11 通道下肢 EMG（1 kHz）与关节运动学/动力学数据。

| 部分 | DOI | 受试者 | 压缩体积 |
|------|-----|--------|---------|
| Part 1/3 | [10.17632/fcgm3chfff.1](http://dx.doi.org/10.17632/fcgm3chfff.1) | AB06–AB14 | ~9.5 GB |
| Part 2/3 | [10.17632/k9kvm5tn3f.1](http://dx.doi.org/10.17632/k9kvm5tn3f.1) | AB15–AB25 | ~10.1 GB |
| Part 3/3 | [10.17632/jj3r5f9pnf.1](http://dx.doi.org/10.17632/jj3r5f9pnf.1) | AB27, AB28, AB30 | ~3.2 GB |

> 合计约 **22.6 GB** 下载量；解压后约 **45 GB**（含临时 ZIP）。  
> 请确保目标磁盘有 **≥ 50 GB** 可用空间（使用 `--keep-zips` 则需 ≥ 70 GB）。

#### 前置依赖

| 工具 | Ubuntu | macOS | Windows（Git Bash / WSL）|
|------|--------|-------|--------------------------|
| `bash` ≥ 3.2 | 系统自带 | 系统自带 | Git Bash / WSL 自带 |
| `curl` 或 `wget` | `sudo apt install curl` | `brew install curl` | Git Bash 自带 curl |
| `unzip` | `sudo apt install unzip` | `brew install unzip` | `pacman -S unzip`（MSYS2）|
| `python3` | 系统自带 | 系统自带 | Python 安装包自带 |

#### 快速开始

```bash
cd EMG-Data-Analyser/TOOLS
chmod +x download_dataset.sh

./download_dataset.sh --list-only          # 预览文件清单
./download_dataset.sh                      # 下载并合并（默认：../Dataset/Camargo2021）
./download_dataset.sh --dest /data/Camargo # 自定义目标路径
./download_dataset.sh --parts 1 --keep-zips
```

| 参数 | 说明 |
|------|------|
| `--dest DIR` | 指定合并目标目录 |
| `--parts N[,N]` | 只下载指定部分（默认全部） |
| `--keep-zips` | 保留原始 ZIP 文件 |
| `--list-only` | 仅列出文件清单，不下载 |

> **注意**：Part 2 缺少 AB22，Part 3 缺少 AB26 / AB29，这是数据集本身的发布状态。

---

### Gait120 综合步态与 EMG 数据集

**Springer Nature Figshare** 发布，100 名受试者（S001–S100），7 种运动模式，12 通道右腿 EMG（2 kHz），内含 MVC 归一化后的步态周期插值数据（101 点）。

| Pack | 文件 | 受试者 | 压缩体积 |
|------|------|--------|---------|
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

> 全量下载约 **13.9 GB**；解压后约 **40 GB**（含临时 ZIP）。  
> 仅下载 Pack 1（S001–S010）约需 **1.45 GB**。

#### 快速开始

```bash
cd EMG-Data-Analyser/TOOLS
chmod +x download_gait120.sh

./download_gait120.sh --list-only          # 预览全部文件，不下载
./download_gait120.sh --packs 1            # 仅下载 S001–S010（~1.45 GB）
./download_gait120.sh                      # 下载全部 100 名受试者（~13.9 GB）
./download_gait120.sh --dest /data/Gait120 # 自定义目标路径
```

下载完成后，目录结构如下：

```
Dataset/Gait120/
├── S001/
│   ├── EMG/
│   │   ├── RawData.mat          # 2 kHz 原始 EMG（MCOS 格式）
│   │   └── ProcessedData.mat    # 归一化 + 步态周期插值（101 点）
│   ├── JointAngle/              # OpenSim .mot 关节角度文件
│   └── MotionCapture/           # 标记点轨迹（.trc，100 Hz）
├── S002/ … S100/
```

| 参数 | 说明 |
|------|------|
| `--dest DIR` | 指定目标目录（默认：`../Dataset/Gait120`）|
| `--packs N[,N]` | 只下载指定 pack（如 `--packs 1` 只下 S001–S010）|
| `--keep-zips` | 保留原始 ZIP 文件 |
| `--list-only` | 仅列出文件清单，不下载 |

#### 断点续传 / 重新运行

脚本是**幂等的**，可随时中断再重新运行：

- 下载阶段：`curl -C -` / `wget -c` 自动续传未完成的 ZIP。
- 解压阶段：目标中已存在且非空的 `Sxxx/` 目录会自动跳过。
- 文件列表（`_downloads/figshare_files.json`）缓存在本地，重跑不重新查询 API。

---

## 项目结构

```
EMG-Data-Analyser/
├── Dataset/                        # 本地数据集（git-ignored）
│   ├── Camargo2021/                # ← download_dataset.sh 输出目录
│   └── Gait120/                   # ← download_gait120.sh 输出目录
├── DOCS/
│   ├── DATASET.md                  # 数据集字段、采样率、通道映射说明
│   └── WORKFLOW.md                 # 整体架构设计
├── SAMPLE_DATA/
│   └── 2026.4.13-EMG/             # 自采样例数据
├── TOOLS/
│   ├── download_dataset.sh         # Camargo 2021 下载脚本（Mendeley）
│   └── download_gait120.sh        # Gait120 下载脚本（Figshare）
├── src/emg_analyser/
│   ├── gui/pages/
│   │   ├── page1_timeline.py       # 原始波形页
│   │   ├── page2_gait.py           # 步态周期分段页
│   │   ├── page3_camargo.py        # Camargo 数据集页
│   │   └── page4_gait120.py        # Gait120 数据集页
│   ├── io/
│   │   ├── camargo_adapter.py      # Camargo 适配器
│   │   ├── camargo_mat.py          # Camargo MCOS 解码
│   │   ├── gait120_mat.py          # Gait120 MCOS 解码
│   │   └── myo_csv.py              # MyoMetrics CSV 加载
│   └── services/worker.py          # 后台线程（Load / Reprocess / Segment /
│                                   #          Camargo / Gait120）
├── run.py                          # 启动入口
├── README.md                       # 本文件（中文）
└── README-EN.md                    # 英文 README
```
