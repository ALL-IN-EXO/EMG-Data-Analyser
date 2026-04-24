# EMG-Data-Analyser (PyQt) — 整体架构设计

本文档定义新版 **PyQt 桌面应用** 的总体架构。目标是把
`2026-FullBody-RL/Code/EMG-Data-Analyser` 里已经跑通的一组脚本
（Camargo `.mat` 加载 / MyoMetrics CSV 加载 / 时间序列绘图 / 步态周期分割
/ 跨数据集对比）整理成一个统一的、可交互的分析工具，同时支持**自采数据集**
与**公共数据集**的分析与对比。

参考实现的功能全部保留；差异主要在两点：
1. 前端从 "一次性渲染 Plotly HTML" 迁移到 **PyQt + pyqtgraph** 的实时交互。
2. 把现在散落在脚本里的"加载 / 处理 / 渲染"拆成清晰的三层，方便扩展新数据集、
   新视图、新指标。

---

## 1. 目标与范围

### 1.1 必须具备

- 并排支持 **至少两类数据源**：
  - 公共数据集（首期：Camargo 2021 的 11 通道下肢 EMG，MATLAB `table` `.mat`）
  - 自采数据集（首期：MyoMetrics CSV，3 通道右腿）
- 两类**可视化视图**：
  - 时间序列（Raw + 实时可调滤波链）
  - 步态周期 mean ± std（Heel-strike 或 envelope-autocorr 双模式）
- 一个**对比视图**：把任意 N 个 trial / session 的同名肌肉曲线叠到同一子图。
- 交互链：用户改参数 → 后台重算 → 图面实时更新；不重新运行 Python。
- 可把当前视图导出为 **PNG / SVG** 以及（向后兼容）现有的 Plotly HTML。

### 1.2 明确不做（首期）

- 实时采集（在线串流 EMG）。只做已保存数据的离线分析。
- 训练 / 预测类机器学习工作流。NMF / 肌肉协同作为**占位模块**放在处理层，
  GUI 首期不暴露。
- 多用户 / 云同步。本地桌面工具。

### 1.3 非功能

- 单 trial（~143 s × 1 kHz × 11 通道 ≈ 1.6 M 样本）的参数调节应在 ≤ 200 ms
  内完成"重滤波 → 重绘"。
- 合并多 trial（≈ 1000 周期 × 11 通道）的步态周期视图，参数调节应在 ≤ 500 ms
  完成。
- Python ≥ 3.10；跨 Linux / Windows；无需 GPU。

---

## 2. 技术栈

| 层次 | 选型 | 理由 |
| --- | --- | --- |
| GUI 框架 | **PyQt5*（PySide6 可平替） | 成熟、文档齐全、`QDockWidget` 能直接拼出我们的布局 |
| 实时绘图 | **pyqtgraph** | 同量级数据下比 matplotlib 快 1–2 个数量级；原生嵌入 Qt，无需 WebEngine |
| 数值 / 信号 | `numpy`, `scipy.signal` | 参考脚本已在用；复用 `iirfilter` / `filtfilt` / `find_peaks` |
| 表格 / CSV | `pandas` | MyoMetrics CSV 解析已依赖 |
| `.mat` 解析 | 沿用参考项目的 `camargo_mat.py`（MCOS 逆向） | 数据集独有约束，别重造 |
| HTML 导出（可选） | `plotly` | 保留与旧脚本一致的离线分享产物 |
| 配置 | `pydantic` + YAML | 类型安全的可序列化设置 |
| 打包 | `pyproject.toml` + `uv` / `pip-tools` | 单 `src/` 目录的标准 Python 包 |
| 测试 | `pytest` + `pytest-qt` | 纯函数测处理层；`pytest-qt` 跑 GUI smoke |

**为什么不用 Plotly + QWebEngineView**：WebEngine 打包体积大、IPC
成本高；而且我们已经有 Plotly HTML 产物，桌面端换成 pyqtgraph 才有增量价值
（更快、参数联动更顺、可嵌入复杂控件）。HTML 导出只作为"分享 / 汇报"通道。

---

## 3. 顶层架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        GUI Layer (PyQt)                          │
│  MainWindow  ├─ DatasetTree (左侧)                              │
│              ├─ ViewTabs (中央)                                  │
│              │   ├─ TimeSeriesView                               │
│              │   ├─ GaitCycleView                                │
│              │   └─ CompareView                                  │
│              ├─ ControlPanel (右侧，上下文相关)                  │
│              └─ LogDock (底部)                                   │
└──────────────────────▲──────────────────────────────────────────┘
                       │  Qt signals / slots（参数变更、选中变更）
┌──────────────────────┴──────────────────────────────────────────┐
│                      Service Layer                               │
│  SessionManager   — 当前打开的 trial / session / 选中集合        │
│  ProcessingWorker — 把 Pipeline 放到 QThread，防止 GUI 卡顿      │
│  ExportService    — PNG / SVG / Plotly HTML / CSV                │
└──────────────────────▲──────────────────────────────────────────┘
                       │  纯 Python 调用；不感知 Qt
┌──────────────────────┴──────────────────────────────────────────┐
│                      Domain Layer (pure Python)                  │
│  io/           — DatasetAdapter 协议 + 具体实现                  │
│  processing/   — Filter / Envelope / GaitSegmenter / Normalize   │
│  model/        — Trial, Channel, CycleSet, Pipeline (dataclass)  │
└─────────────────────────────────────────────────────────────────┘
```

**关键原则**：`model/` 和 `processing/` 里**不允许** `import PyQt6`。
这条红线保证处理层可以在 pytest / Jupyter / CLI 里独立跑，也能被未来的
Web 前端或脚本模式复用。

---

## 4. 目录结构

```
EMG-Data-Analyser/
├── DOCS/
│   ├── WORKFLOW.md            # 本文
│   ├── DATASETS.md            # 每个数据集的字段约定、采样率、单位
│   └── UI_MOCKUPS/            # 界面草图 / 截图
├── src/
│   └── emg_analyser/
│       ├── __init__.py
│       ├── __main__.py        # `python -m emg_analyser` 入口
│       ├── app.py             # QApplication 初始化、主题、i18n
│       ├── model/
│       │   ├── trial.py       # Trial / Channel / Metadata
│       │   ├── cycles.py      # CycleSet (迁移自 gait_cycles.py)
│       │   └── pipeline.py    # PipelineConfig (pydantic)
│       ├── io/
│       │   ├── base.py        # DatasetAdapter Protocol
│       │   ├── registry.py    # 运行时发现 / 注册
│       │   ├── camargo_mat.py # 迁移自参考项目
│       │   ├── myo_csv.py     # 迁移自参考项目
│       │   └── loaders_test_data/
│       ├── processing/
│       │   ├── filters.py     # highpass / lowpass / rectify / MA / RMS
│       │   ├── envelope.py    # linear_envelope
│       │   ├── gait.py        # heel-strike + autocorr 两种分段器
│       │   ├── normalize.py   # MVC / peak / 95-percentile
│       │   └── pipeline.py    # 组合上面的链；输入 raw 输出处理后 + cycles
│       ├── services/
│       │   ├── session.py     # SessionManager (Qt QObject)
│       │   ├── worker.py      # ProcessingWorker (QThread / QRunnable)
│       │   └── export.py
│       ├── gui/
│       │   ├── main_window.py
│       │   ├── dataset_tree.py
│       │   ├── control_panel.py
│       │   ├── views/
│       │   │   ├── base.py        # ViewBase 抽象
│       │   │   ├── timeseries.py
│       │   │   ├── gait_cycle.py
│       │   │   └── compare.py
│       │   └── widgets/           # 可复用的滑块、下拉等
│       └── resources/
│           ├── icons/
│           └── style.qss
├── tests/
│   ├── test_loaders.py
│   ├── test_filters.py
│   ├── test_gait.py
│   └── smoke/
│       └── test_gui_boot.py    # pytest-qt
├── configs/
│   └── default.yaml           # 默认数据集根路径、默认流水线参数
├── outputs/                   # 导出产物（HTML / PNG / CSV），git-ignore
├── pyproject.toml
├── README.md
└── .gitignore
```

---

## 5. 核心抽象

### 5.1 `Trial` — 统一的 "一次试验"

无论来自哪个数据集，上层只看到同一个 dataclass：

```python
@dataclass
class Trial:
    source: str                    # "camargo" | "myometrics" | ...
    subject: str                   # "AB06" | "self-2026.4.13" | ...
    trial_id: str                  # "treadmill_01_01" | "EMG-with Electrode"
    fs: float                      # Hz
    t: np.ndarray                  # (N,) 秒
    channels: dict[str, np.ndarray]  # 肌肉名 -> (N,)
    units: str                     # "mV" | "uV"
    meta: dict                     # 任意键值对：MVC 峰值、clip 率、路径...
    events: dict[str, np.ndarray] = field(default_factory=dict)
    # events["heel_strike"] -> (M,) 秒；没有就为空，后续 envelope-autocorr 会填
```

迁移映射：
- `camargo_mat.load_emg_table` → 在 `CamargoAdapter.load_trial()` 里包成 `Trial`；
  把 `gcRight.HeelStrike` 解成 `events["heel_strike"]`。
- `myo_csv.load_session` → 在 `MyoMetricsAdapter.load_trial()` 里包成 `Trial`；
  MVC 峰值进 `meta["mvc_peak_abs"]`，clip 率进 `meta["clip_fraction"]`。

### 5.2 `DatasetAdapter` — 数据源插件协议

```python
class DatasetAdapter(Protocol):
    name: str                       # "camargo" 用于注册表 key
    display_name: str               # "Camargo 2021 (Aaron Lab, Part 1/3)"

    def scan(self, root: Path) -> list[TrialHandle]: ...
    # TrialHandle = (subject, date?, mode?, trial_id, payload_paths, est_duration_s)

    def load_trial(self, handle: TrialHandle) -> Trial: ...

    def channel_taxonomy(self) -> dict[str, ChannelInfo]: ...
    # 通道名 → {muscle_group, side, canonical_name}；用于跨数据集对齐
```

- `scan` 只做目录遍历 + 轻量元数据读取，返回给 `DatasetTree` 显示，**不**加载样本。
- `load_trial` 按需读入。大 trial 用 `functools.lru_cache(maxsize=8)` 包一层。
- `channel_taxonomy` 提供**规范名**（canonical name），对比视图靠它匹配。
  首期的规范名就是 Camargo 的英文小写去符号：`bicepsfemoris`、`gluteusmedius`、
  `rectusfemoris` 等。MyoMetrics 的 `BICEPS_FEM._RT` 映射到
  `bicepsfemoris`，以此类推（表沿用参考项目 README）。

### 5.3 `Pipeline` — 可组合的处理链

```python
@dataclass
class PipelineConfig:
    highpass_hz: float = 0.0        # 0 = off
    rectify: bool = True
    smoothing: Literal["lowpass", "movavg", "rms", "none"] = "lowpass"
    smoothing_cutoff_hz: float = 6.0      # 仅 lowpass
    smoothing_window_ms: float = 50.0     # 仅 movavg / rms
    normalize: Literal["off", "mvc_peak", "mvc_env95", "task_env95"] = "off"
```

一条链：`raw → [Highpass] → [Rectify] → [Smoothing] → [Normalize]`。
这正是参考项目 `plot_emg.py` / `gait_cycles.py` 浏览器端 JS 做的事，
现在把它搬回 Python 端用 scipy 做，效果更精确。

### 5.4 `CycleSet`

直接复用 `gait_cycles.py::CycleSet`，字段：`cycles[name] (C, 101)`,
`durations (C,)`, `source (C,)`。`merge_cyclesets` 保持不变。

---

## 6. I/O 层细则

| 文件 | 职责 | 来源 |
| --- | --- | --- |
| `io/camargo_mat.py` | Camargo `.mat` table 的 MCOS 逆向读取；`load_emg_table` / `load_table` | 直接复制参考项目的 `camargo_mat.py`（不改） |
| `io/myo_csv.py` | MyoMetrics CSV；饱和 clip 掩膜 + MVC 缩放 | 复制参考项目，但 `load_session` 的返回值包成 `Trial` |
| `io/camargo_adapter.py` | `DatasetAdapter`；目录扫描 `<root>/<subject>/<date>/<mode>/emg/*.mat`；解析 `gcRight/*.mat` 填 `events["heel_strike"]` | 新增 |
| `io/myo_adapter.py` | `DatasetAdapter`；扫描 session 目录；`events` 留空（后续由 gait 模块填 autocorr 结果） | 新增 |
| `io/registry.py` | 启动时注册所有 adapter；支持 entry-point 以后插第三方 | 新增 |

**扫描策略**：`scan()` 返回的 `TrialHandle` 应该是轻量 dataclass，只含路径 +
用户可见的标签。真正的大数据 `load_trial()` 才读。

---

## 7. 处理层细则

### 7.1 `filters.py`

所有滤波统一用 `scipy.signal.iirfilter` + `filtfilt`（零相位，
和参考项目浏览器端前向-后向的等效实现）。接口：

```python
def highpass(x, fs, cutoff_hz): ...
def lowpass(x, fs, cutoff_hz): ...
def rectify(x): ...
def moving_average(x, fs, window_ms): ...
def sliding_rms(x, fs, window_ms): ...
def apply_pipeline(x: np.ndarray, fs: float, cfg: PipelineConfig) -> np.ndarray: ...
```

`apply_pipeline` 内部就是一串 `if`。性能关键路径的数据预降采样到
`fs_display`（默认 500 Hz），和参考项目一致。

### 7.2 `envelope.py`

`linear_envelope(sig, fs, cutoff_hz=6.0)` 直接照搬 `gait_cycles.py`
的实现。对比视图的默认处理链就是"rectify + 6 Hz envelope + per-channel peak
normalize"，这是保证**形状**可比的关键约定。

### 7.3 `gait.py`

两种策略，对外同名 `segment(trial: Trial, cfg) -> CycleSet`：

1. **`HeelStrikeSegmenter`**：`trial.events["heel_strike"]` 非空时使用。
   逻辑复用 `gait_cycles.py::detect_heel_strikes` + `extract_cycles`。
2. **`AutocorrSegmenter`**：`events["heel_strike"]` 为空时使用。参考
   `gait_cycles_self.py`：取一条参考肌肉 → 整流 + 6 Hz envelope →
   autocorrelation 限 0.4–2.5 s → 峰值检测 → 边界。
   `ref_muscle` 默认 `bicepsfemoris`（其规范名），GUI 里让用户下拉选。

策略选择在 `Pipeline.run()` 里根据 `trial.events` 自动决定；用户可手动 override。

### 7.4 `normalize.py`

实现 4 档：
- `off` → 不动
- `mvc_peak` → 除以 `meta["mvc_peak_abs"]`（MyoMetrics 设备给的）
- `mvc_env95` → 除以 MVC session rectified envelope 的 95 百分位
- `task_env95` → 除以当前 trial 自己 envelope 的 95 百分位

MVC-style 归一化对 Camargo 不可用（没有 MVC session），GUI 要 gray-out
这两个选项。

### 7.5 `pipeline.py`

`run(trial, cfg) -> ProcessedTrial`，其中：

```python
@dataclass
class ProcessedTrial:
    trial: Trial
    t_ds: np.ndarray               # 降采样后的时间
    processed: dict[str, np.ndarray]  # 通道名 -> 处理后信号（同 t_ds）
    cycles: CycleSet | None
```

这是 GUI 层唯一消费的数据结构。参数变 → `ProcessingWorker` 重新跑
`run()` → `SessionManager.processedTrialChanged` 信号 → 各 View `refresh()`。

---

## 8. GUI 层细则

### 8.1 主窗口布局

`QMainWindow` + `QTabWidget`（两个主页面）+ `QDockWidget`（底部 Log）：

```
┌─────────────────────────────────────────────────────────────────┐
│ MenuBar  File  View  Tools  Help                                 │
├─────────────────────────────────────────────────────────────────┤
│  [ Page 1: Raw Timeline ]  [ Page 2: Gait Cycle Segmentation ]  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   （当前页内容，见 8.2 / 8.3）                                    │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│ Log: [INFO] loaded 2026-04-13/EMG-with Electrode (180.0 s, 3 ch)│
└─────────────────────────────────────────────────────────────────┘
```

两个页面共享同一个 `SessionManager` 实例（持有当前 `Trial` 和 `TimeRange`），
通过 Qt 信号槽解耦。页面布局和窗口尺寸经 `QSettings` 持久化。

---

### 8.2 Page 1 — Raw Timeline（原始时间轴）

**职责**：选定数据文件夹 → 自动加载 trial → 全局时间轴展示 → 框选分析时间段。

#### 8.2.1 布局

```
┌─────────────────────────────────────────────────────────────────┐
│  [📁 Select Folder]  /path/to/MyoMetrics/2026-04-13   [Reload] │  ← 顶栏
├────────────────────────────────────────────────┬────────────────┤
│                                                │  右侧控制面板  │
│  ┌──────────────── GraphicsLayout ───────────┐ │                │
│  │  BICEPS_FEM._RT  ──────────────────────── │ │  Pipeline      │
│  │                                            │ │  ─────────     │
│  │  GLUT_MED._RT    ──────────────────────── │ │  Highpass Hz   │
│  │                                            │ │  [20    ]      │
│  │  RECTUS_FEM._RT  ──────────────────────── │ │                │
│  │                   ████████                 │ │  Smoothing     │
│  │                   ← region →               │ │  [Lowpass ▼]   │
│  └────────────────────────────────────────────┘ │  Cutoff Hz     │
│                                                │  [6     ]      │
│  Selected: 45.20 s – 120.80 s  (75.60 s)      │                │
│  [  → Go to Gait Cycle Segmentation  ]         │  Channels      │
│                                                │  ☑ BICEPS      │
│                                                │  ☑ GLUT        │
│                                                │  ☑ RECTUS      │
└────────────────────────────────────────────────┴────────────────┘
```

#### 8.2.2 交互细节

**文件夹选取与自动加载**

- 点击 `[📁 Select Folder]` 弹出 `QFileDialog.getExistingDirectory`。
- 选定后 `SessionManager.openFolder(path)` 调用对应 adapter 的 `scan(path)` 找到
  所有 trial，若结果唯一则立即 `load_trial`；若多个则弹出简单列表让用户选一个。
- 加载在后台 `QThread` 完成；顶栏路径标签实时变灰加"Loading…"动画。
- 加载完成后 `trialLoaded` 信号触发页面刷新。

**全局时间轴**

- 使用 `pyqtgraph.GraphicsLayout`，每通道一个 `PlotItem`，**共享 X 轴**
  （`setXLink`）。
- `setDownsampling(auto=True, mode='peak')` — pyqtgraph 在缩放时自动抽稀，
  保证大 trial（180 s × 2 kHz × 3 通道）渲染不卡顿。
- Y 轴各自独立缩放；单位标签从 `trial.units` 读取。
- 初始显示已应用 highpass 滤波但**未整流**的信号（便于目视质量检查）。

**时间段框选**

- 在最底层 `PlotItem` 叠加一个 `pyqtgraph.LinearRegionItem`（半透明蓝色），
  其他层通过 `addItem` + `sigRegionChanged` 保持同步位置。
- 拖动端点或整体拖动区域；双击区域重置为全段。
- 状态栏实时更新：`Selected: t_start – t_end  (duration)`。
- `[→ Go to Gait Cycle Segmentation]` 按钮点击后：
  1. 把 `(t_start, t_end)` 写入 `SessionManager.time_range`。
  2. 把 Tab 切换到 Page 2（不销毁 Page 1 状态）。

**右侧控制面板（Page 1 上下文）**

| 控件 | 作用 |
|------|------|
| Highpass Hz 数字框 | 实时重算 highpass → 刷新时间轴（debounce 50 ms） |
| Smoothing 下拉 + Cutoff/Window | 同上 |
| 通道开关复选框 | 显示 / 隐藏对应 PlotItem |

---

### 8.3 Page 2 — Gait Cycle Segmentation（步态周期切割）

**职责**：接收从 Page 1 传来的时间段和 trial → 切割步态周期 → 展示 mean ± std。

#### 8.3.1 布局

```
┌─────────────────────────────────────────────────────────────────┐
│  ← Back   Segmenting: 2026-04-13/EMG  |  45.20 s – 120.80 s   │  ← 顶栏
├────────────────────────────────────────────┬────────────────────┤
│                                            │  右侧控制面板      │
│  ┌──── mean ± std grid (N × 1) ─────────┐ │                    │
│  │ BICEPS_FEM._RT                        │ │  Segmentation      │
│  │   ██████░░░░░░░░░░░░░░░░░            │ │  ──────────────    │
│  │                                       │ │  Method            │
│  │ GLUT_MED._RT                          │ │  [Autocorr   ▼]    │
│  │   ░░░░░██████████░░░░░░░░░           │ │                    │
│  │                                       │ │  Ref. muscle       │
│  │ RECTUS_FEM._RT                        │ │  [BICEPS_FEM ▼]    │
│  │   ░░░░░░░░░░░░░████████░░░           │ │                    │
│  └───────────────────────────────────────┘ │  Period range      │
│                                            │  Min [0.4] s       │
│  Detected: 82 cycles  |  0.92 ± 0.04 s    │  Max [2.5] s       │
│  [Export PNG]  [Export HTML]               │                    │
│                                            │  Show individuals  │
│                                            │  ☐ (max 30)        │
│                                            │                    │
│                                            │  Normalize         │
│                                            │  [task_env95 ▼]    │
└────────────────────────────────────────────┴────────────────────┘
```

#### 8.3.2 交互细节

**进入页面时的自动触发**

- Tab 切换到 Page 2 时，若 `SessionManager.time_range` 与上次计算的不同，
  立即向 `ProcessingWorker` 投递 `segment` 任务（不阻塞 UI）。
- 计算期间显示进度条 + "Segmenting…" 覆盖层；完成后覆盖层消失，图面刷新。

**分割方法**

| 方法 | 触发条件 | 说明 |
|------|---------|------|
| `HeelStrike` | `trial.events["heel_strike"]` 非空 | 直接用 Camargo gcRight 事件 |
| `Autocorr` | 默认（MyoMetrics 无事件） | 取 `ref_muscle` → 整流 + 6 Hz envelope → 自相关 → 峰值检测 |

- 下拉可强制切换（例如在 Camargo 上也用 Autocorr 做对比验证）。
- **Period range** 限制自相关搜索窗口（默认 0.4–2.5 s，对应 24–150 步/分钟）。

**均值 ± 标准差网格**

- 每通道一个 `PlotItem`，纵向排列，共享 X 轴（归一化后的步态相位 0–100 %）。
- 每格：
  - 半透明填充带（`pg.FillBetweenItem`）表示 ± 1 std。
  - 粗线表示 mean。
  - 若勾选"Show individuals"，额外叠加最多 30 条随机抽样单周期（`alpha=0.15`）。
- 状态栏显示 `Detected: N cycles | mean_duration ± std_duration s`。

**返回 Page 1**

- `← Back` 按钮切回 Page 1，`LinearRegionItem` 恢复到上次的 `time_range`，
  不触发重新加载 trial。

**右侧控制面板（Page 2 上下文）**

| 控件 | 作用 |
|------|------|
| Method 下拉 | HeelStrike / Autocorr；切换后重新分割 |
| Ref. muscle 下拉 | Autocorr 模式下的参考通道 |
| Period range Min/Max | 自相关搜索窗口（秒） |
| Show individuals 复选 | 显示 / 隐藏单周期细线 |
| Normalize 下拉 | off / task_env95 / mvc_peak（无 MVC 文件时 gray-out）|

所有控件变化 → debounce 50 ms → `ProcessingWorker.segment(trial, range, cfg)`。

---

### 8.4 信号槽约定

```
# Page 1
FolderPicker.folderSelected(path)      → SessionManager.openFolder(path)
SessionManager.trialLoaded(trial)      → Page1.onTrialLoaded(trial)
Page1.regionChanged(t_start, t_end)    → SessionManager.setTimeRange(t_start, t_end)
Page1.goToSegmentation()               → MainWindow.switchToPage2()

# Page 2
MainWindow.switchToPage2()             → Page2.triggerSegmentation()
Page2.pipelineChanged(cfg)             → SessionManager.setPipeline(cfg)
SessionManager.cyclesReady(cycle_set)  → Page2.refresh(cycle_set)
ProcessingWorker.progress(msg)         → LogDock / statusbar
```

`Trial` 加载结果用 `lru_cache(maxsize=4)`；`CycleSet` 不缓存（分割参数一变即废）。

---

## 9. 数据流（典型交互）

### 9.1 Page 1 — 打开文件夹到看图

```
用户点 [📁 Select Folder]，选定 /data/MyoMetrics/2026-04-13/
   │
   ▼
SessionManager.openFolder(path)
   │  adapter.scan(path) → [TrialHandle("EMG-with Electrode")]
   │  唯一 trial → 自动 load
   ▼
ProcessingWorker.load(handle)  ──  MyoMetricsAdapter.load_trial() → Trial
   │
   ▼
SessionManager.trialLoaded(trial)
   │
   ▼
Page1.onTrialLoaded(trial)
   │  apply highpass → Page1.GraphicsLayout.setData(...)
   ▼
用户看到全局时间轴（180 s × 3 通道）
```

### 9.2 Page 1 — 调整滤波参数

```
用户改 Highpass Hz 数字框
   │  (debounce 50 ms)
   ▼
SessionManager.setPipeline(new_cfg)
   │  不重新 load_trial；只重新 apply_pipeline
   ▼
ProcessingWorker.reprocess(cached Trial, new_cfg)
   ▼
Page1.GraphicsLayout.setData(...)  — 实时刷新时间轴
```

### 9.3 Page 1 → Page 2 — 框选并跳转

```
用户拖动 LinearRegionItem → t_start=45.20 s, t_end=120.80 s
   │
Page1.regionChanged(45.20, 120.80)
   │
SessionManager.setTimeRange(45.20, 120.80)

用户点 [→ Go to Gait Cycle Segmentation]
   │
MainWindow.switchToPage2()
   │
Page2.triggerSegmentation()
   │  切取 trial[t_start : t_end] → segment(slice, pipeline_cfg)
   ▼
ProcessingWorker.segment(trial_slice, cfg)
   │  AutocorrSegmenter 或 HeelStrikeSegmenter → CycleSet
   ▼
SessionManager.cyclesReady(cycle_set)
   │
Page2.refresh(cycle_set)  →  mean ± std grid 刷新
```

### 9.4 Page 2 — 修改分割参数

```
用户改 Ref. muscle 或 Period range
   │  (debounce 50 ms)
   ▼
ProcessingWorker.segment(cached trial_slice, new_cfg)
   ▼
Page2.refresh(new_cycle_set)
```

---

## 10. 对比视图重点

`CompareView` 是这个工具相对参考项目最重要的增值点，因此单列。

- 输入：多个 `ProcessedTrial`（每个自带 `CycleSet`）。
- 渲染前做**通道规范化映射**：用各 adapter 的 `channel_taxonomy()` 把原始
  通道名映到规范名，只画"在全部 trial 里都存在"的规范名（3 通道时就是
  `bicepsfemoris / gluteusmedius / rectusfemoris`；未来如自采扩到 11 通道
  就全画出来）。
- 画法：每规范名一格，3×1 或 2×2 网格；颜色按 trial 分配（不是按通道）。
- 指标栏（可选）：下方显示每对 trial 的 mean envelope 皮尔森 /
  交叉相关峰值及对应 lag，供定量参考。
- 导出：一键把当前对比视图导出为 Plotly HTML（调用已有 `compare_with_camargo.py`
  的渲染函数 —— 保留旧产物形式）。

---

## 11. 异步与性能

- `ProcessingWorker` = `QObject` + `QThread`（不是 `QThread` 子类）。
- 每次 `process()` 调用分配一个 `run_id`；`SessionManager` 只接纳最新
  `run_id` 的结果，旧结果丢弃（避免慢滑块拖出去一串过期重绘）。
- 大 trial 扫描 / 加载用 `QRunnable` + `QThreadPool`，扫描进度走 `LogDock`。
- pyqtgraph 的 `setData` 永远用 `numpy.ascontiguousarray(...)`；
  `useOpenGL=True` 默认关（Linux 上 GL 驱动不稳），由设置开关。

---

## 12. 配置与持久化

- 用户设置：`QSettings("zst", "emg-analyser")`
  - 窗口布局
  - 最近数据集路径
  - 语言 / 主题
- 默认流水线参数：`configs/default.yaml`（pydantic 加载校验）。
- Session export：`File → Export Session...` 写一个 JSON（当前 trial
  列表 + PipelineConfig + view 状态），方便再次打开继续。

---

## 13. 扩展性：加一个新数据集要做什么

1. 在 `io/` 建 `newds_adapter.py`，实现 `DatasetAdapter`（`scan` /
   `load_trial` / `channel_taxonomy`）。
2. 如果是新的底层格式（如 EDF、Delsys EMGworks），新建一个 loader 模块放在
   `io/`，adapter 调用它。
3. 在 `io/registry.py` 注册（或走 entry-point）。
4. 在 `DOCS/DATASETS.md` 加一节说明字段、采样率、通道。
5. 不需要改 GUI、processing 层任何代码。

加一个新 View 同理：`gui/views/xxx.py` 继承 `ViewBase`，在 `MainWindow`
注册。

---

## 14. 导出

| 产物 | 路径 | 生成方 |
| --- | --- | --- |
| 当前视图 PNG / SVG | `outputs/snapshot_<ts>.png` | `pyqtgraph.exporters` |
| 时间序列 / 步态周期 Plotly HTML | `outputs/<trial>.html` | 复用参考项目的 `render_interactive` |
| 对比 HTML | `outputs/compare_<ts>.html` | 复用 `compare_with_camargo.py::render_interactive` |
| 规范化后的 EMG CSV | `outputs/<trial>_processed.csv` | 新增（`ProcessedTrial.to_csv()`） |
| Session JSON | 任意 | `ExportService.save_session` |

---

## 15. 测试

- `tests/test_loaders.py`：小型 `.mat` / 小型 CSV 固件（放 `io/loaders_test_data/`），
  断言 `Trial.fs`、通道名、`events["heel_strike"]` 的形状。
- `tests/test_filters.py`：对合成正弦信号跑 pipeline，断言幅频响应。
- `tests/test_gait.py`：合成带周期性峰的信号，`AutocorrSegmenter` 能找回
  注入周期（± 5 %）。
- `tests/smoke/test_gui_boot.py`：`pytest-qt` 打开主窗口，加载 fixture
  trial，模拟滑块拖动 → 断言 View 的 plot item 至少有一条曲线。

CI：GitHub Actions Linux，`xvfb-run pytest`.

---

## 16. 开发里程碑

| 里程碑 | 范围 | 交付物 |
| --- | --- | --- |
| **M0 – 骨架** | 项目脚手架、`Trial` / `PipelineConfig` / adapter 协议 | 空 GUI 能启动；MyoMetrics adapter + Camargo adapter 有单元测试 |
| **M1 – Page 1 基础** | 文件夹选取 → 自动加载 → 全局时间轴（3 通道共享 X 轴） | 能打开 MyoMetrics session，拖滑块实时看到 highpass 结果 |
| **M2 – Page 1 框选** | `LinearRegionItem` 时间段选取 + "跳转到 Page 2"按钮 | 可框出任意时间段，状态栏实时显示时长 |
| **M3 – Page 2 分割** | `AutocorrSegmenter` + mean ± std 网格；接收 Page 1 时间段 | MyoMetrics 数据能切出步态周期并展示均值曲线 |
| **M4 – Camargo 支持** | `CamargoAdapter`（.mat 加载）+ `HeelStrikeSegmenter` | Camargo trial 在 Page 1 / Page 2 完整可用 |
| **M5 – 导出 & 持久化** | PNG / SVG / Plotly HTML / Session JSON；`QSettings` | 关软件再打开能回到上次状态 |
| **M6 – 质量** | i18n（中 / 英）、错误提示、`pytest-qt` smoke | 可交付给实验室其他同学使用 |
| **M7+（可选）** | CompareView 跨数据集对比 / NMF 协同 / 在线采集桥接 | —— |

---

## 17. 与参考项目的对应表

（给后续迁移者看的清单）

| 参考脚本 | 新位置 | 变化 |
| --- | --- | --- |
| `camargo_mat.py` | `io/camargo_mat.py` | 不变；被 `CamargoAdapter` 包一层 |
| `myo_csv.py` | `io/myo_csv.py` | 不变；被 `MyoMetricsAdapter` 包一层 |
| `plot_emg.py`（Python 绘图主体） | 拆成 `views/timeseries.py` + `processing/filters.py` | JS 滤波逻辑搬回 Python |
| `plot_emg.py`（Plotly HTML 交互式导出） | `services/export.py::export_timeseries_html` | 保留作为"一键导出 HTML" |
| `gait_cycles.py::extract_cycles / linear_envelope / CycleSet` | `processing/gait.py` + `model/cycles.py` | `extract_cycles` 改签名吃 `Trial` |
| `gait_cycles.py`（Plotly 渲染） | `services/export.py::export_gait_html` | 保留 |
| `gait_cycles_self.py` 的 autocorr | `processing/gait.py::AutocorrSegmenter` | 封成类 |
| `compare_with_camargo.py` 的跨源对齐 | `views/compare.py` + 同 `export.py` | GUI 第一等公民 |

---

*文档先到此；后续每完成一个里程碑回填具体接口签名与截图。*
