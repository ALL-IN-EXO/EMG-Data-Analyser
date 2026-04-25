# 2026.4.13-EMG 数据集处理规则

> 自采数据集，`MyoMetrics` 导出 CSV 格式；采集日期 2026-04-13，受试者 1 人。
> 本文件定义**数据处理约定**（parse / clean / normalize / segment），并与
> 公开数据集 Camargo 2021（见 [CLAUDE/Dataset_Analysis_Camargo2021.md](../../CLAUDE/Dataset_Analysis_Camargo2021.md)）做对比，
> 用于后续在 RL 训练中作为生物先验 / 验证基准。

---

## 一、目录结构

```
Dataset/2026.4.13-EMG/
├── EMG-Electrode Max MVC/      # 最大自主收缩（MVC），用于激活量归一化分母
├── EMG-with Electrode/         # 穿戴外骨骼电极后走路 EMG（任务数据）
├── EMG-without Electrode/      # 不穿外骨骼（裸条件）走路 EMG（对照）
└── README.md                   # 本文件
```

三个 session 内部完全同构，每个 session 包含 **3 块右侧下肢肌肉**：

| 通道（文件名） | 肌肉 | 功能 |
|---|---|---|
| `BICEPS_FEM._RT`  | 股二头肌（右侧） | 膝屈 / 髋伸 |
| `GLUT._MED._RT`   | 臀中肌（右侧）   | 髋外展 / 侧向稳定 |
| `RECTUS_FEM._RT`  | 股直肌（右侧）   | 膝伸 / 髋屈 |

---

## 二、CSV 文件 schema

### 2.1 原始时序信号
`Channel_Curves-Analyzed_Work_Activities-<MUSCLE>.csv`

```
Line 1: "type","name","time_units","begin_time","frequency","count","units"
Line 2: "signal","","s",0.0000,2000.3556,<N>,"uV"
Line 3:                               (空行)
Line 4: "time","value"
Line 5+: <t(秒)>, <value(μV)>          × N 行
```

**parse 规则**：行 1–3 是元数据头；行 4 是数据列头；行 5 开始为 `(t, v)` 成对。
Python 推荐用 `csv` 逐行读取后丢弃前 4 行，或者用 `pandas.read_csv(..., skiprows=3)`
并过滤 `time` 列可转 float 的行。

### 2.2 辅助元数据

| 文件 | 内容 |
|---|---|
| `Subject_info.csv` | 姓名 / 性别（匿名） |
| `Record_info.csv` | 记录名 / 时间戳 / 分析段数 |
| `Analyse_periods.csv` | 整个录制的 `Begin / End` 时间（秒） |
| `Channel_Curves-...-events.csv` | 同上，单位 `%` |
| `Multi-Period_Analysis-Mean_Value...-<M>.csv` | 设备导出的时段均值（单值） |
| `Multi-Period_Analysis-Peak_Value_Within_Each_Activity-Peak_absolute-<M>.csv` | 时段内峰值（μV，**MVC 归一化会用到**） |

---

## 三、信号特性（实测）

```
fs = 2000.3556 Hz   unit = μV   ADC 饱和轨 = ±24000 μV
```

| Session | Muscle | N | dur | RMS | peak \| \| | **clip %** |
|---|---|--:|--:|--:|--:|--:|
| MVC             | BICEPS_FEM | 75 600  | 37.79 s | 99 μV  | 2 119 μV | 0.00 |
| MVC             | GLUT_MED   | 75 600  | 37.79 s | 3 260 μV | **24 000** μV | **1.20** |
| MVC             | RECTUS_FEM | 75 600  | 37.79 s | 107 μV | 1 573 μV | 0.00 |
| with Electrode  | BICEPS_FEM | 146 960 | 73.47 s | 59 μV  | 611 μV   | 0.00 |
| with Electrode  | GLUT_MED   | 146 960 | 73.47 s | 3 020 μV | **24 000** μV | **0.27** |
| with Electrode  | RECTUS_FEM | 146 960 | 73.47 s | 43 μV  | 489 μV   | 0.00 |
| without Electrode | BICEPS_FEM | 186 040 | 93.00 s | 6 555 μV | **24 000** μV | **4.64** |
| without Electrode | GLUT_MED   | 186 040 | 93.00 s | 1 547 μV | 12 851 μV | 0.00 |
| without Electrode | RECTUS_FEM | 186 040 | 93.00 s | 5 908 μV | **24 000** μV | **1.50** |

### ⚠️ 饱和 / 削顶（clipping）

**5 个通道存在削顶**（`|x| ≥ 23999 μV`），必须在 pipeline 中显式处理：

- **MVC-GLUT_MED** 1.20 % 削顶 → MVC 归一化分母**不可信**，需降级方案（见 §4.4）。
- **with Electrode-GLUT_MED** 0.27 % 削顶 → 任务数据本身也被削顶（可能电极接触 / 运动伪迹）。
- **without Electrode-BICEPS_FEM / RECTUS_FEM** 削顶 4.64 % / 1.50 % → 该 session
  作为「裸条件对照」在这两块肌肉上**整体不可用于定量对比**，只宜做定性参考。

### 直流偏置

大多数通道零均值；但 `without Electrode/BICEPS_FEM` 均值 +59 μV，属于基线漂移，
pipeline 第 1 步应减去通道均值或做 ≥ 20 Hz 高通。

---

## 四、推荐处理 Pipeline

### 4.0 加载（所有 session 通用）

```python
import pandas as pd, numpy as np
from pathlib import Path

def load_myometrics(csv_path: Path):
    with open(csv_path) as f:
        hdr = f.readline().strip().split(",")       # field labels
        meta = f.readline().strip().split(",")      # values
    fs = float(meta[4])
    df = pd.read_csv(csv_path, skiprows=3)          # 跳过前 3 行元数据 + 空行
    df = df[pd.to_numeric(df["time"], errors="coerce").notna()]
    t = df["time"].astype(float).to_numpy()
    v = df["value"].astype(float).to_numpy()
    return t, v, fs     # fs ≈ 2000.36 Hz
```

### 4.1 削顶检测 + mask

```python
CLIP = 23999.0
clip_mask = np.abs(v) >= CLIP
if clip_mask.mean() > 0.005:                        # > 0.5 % → 警告
    print(f"WARNING clip {clip_mask.mean()*100:.2f}% in {csv_path.stem}")
v[clip_mask] = np.nan                               # 后续滤波前需插值
```

**削顶插值**：短段削顶（< 20 ms）可用 `scipy.interpolate.interp1d` 线性补；
长段（> 50 ms）应整段丢弃并在后续周期分割中排除。

### 4.2 带通 + 陷波

设备厂商预处理链路未知，统一重做一遍以与 Camargo 对齐：

1. **DC 移除**：`v -= np.nanmean(v)`。
2. **陷波** 50 Hz 及其二次谐波（电源工频干扰，中国大陆 50 Hz）。
3. **带通 20 – 400 Hz**（Butterworth, order 4, zero-phase `filtfilt`）。
   Camargo 数据集的原始带通即 20–400 Hz，沿用该约定便于两套数据混用。

### 4.3 包络（与 `gait_cycles.py` 一致）

```
rectify |x|  →  6 Hz 低通 (IIR 零相位 或 6 Hz 滑动平均)
```

这是 Camargo 随附脚本 `STRIDES.m` 的做法，本项目 [Code/EMG-Data-Analyser/gait_cycles.py:49](../../Code/EMG-Data-Analyser/gait_cycles.py#L49)
已实现 `linear_envelope(sig, fs, 6.0)`，直接复用。

### 4.4 MVC 归一化

**首选**：对每块肌肉，以 MVC session 的 **rectified 95-percentile**（而非 peak）
作为 `a_max`：

```python
def mvc_scale(t_mvc, v_mvc, fs):
    env = linear_envelope(np.abs(v_mvc), fs, 6.0)
    return float(np.nanpercentile(env, 95))
```

用 `percentile(env, 95)` 而非 `max(env)` 的原因：
- **抗削顶**：95-percentile 对 ≤ 5 % 样本的异常值不敏感，
  但仍反映真实最大发力区间；
- **抗冲击伪迹**：MVC 录制时偶有跳跃式伪迹会让 `max` 虚高。

**GLUT_MED 的 MVC 不可用**：削顶 1.20 %，95-percentile 仍可能落在饱和轨附近。
有两种降级方案（择一或两者融合）：

1. **任务内归一化**：用 `EMG-with Electrode/GLUT_MED` 自身的 95-percentile（即
   "peak of task"），承认这只是相对激活而非真·MVC。
2. **Camargo 参考值**：从 Camargo 公开数据集同肌肉、同性别、同体重附近
   受试者的 MVC 分布中取中位数（见 §五 Camargo 对比）。

归一化公式：`a_norm(t) = env(t) / a_max`，理论值域 `[0, 1]`，允许偶发 > 1。

### 4.5 步态周期分割

**本数据集不含 heel-strike 事件**（对比 Camargo 自带 `gcRight.mat`）。走路
session 只知道起止时间戳，没有 FP / IMU / 视频同步。可选三种策略：

| 策略 | 原理 | 适用条件 | 本数据集状态 |
|---|---|---|---|
| **A. EMG-based 自动周期检测** | 对 RECTUS_FEM 或 BICEPS_FEM 包络做自相关 / FFT，识别周期，再按峰值锚点切分 | 稳态步行，周期 ≈ 1 s | 推荐（两个 session 均为跑步机稳态） |
| **B. 手动打点** | 可视化包络后人工标注几个周期起始点，再用固定步长外推 | 任何场景 | 备选 |
| **C. 参考信号同步** | 同步 IMU / FP / 视频重标 | 数据采集时缺失 | 不可用 |

推荐：策略 A 实现为 `Code/EMG-Data-Analyser/gait_cycles_self.py`
（后续实现），直接调用 `detect_heel_strikes` 的通用化版本（对任意周期信号的
`autocorr → dominant period → peak finding`）。

---

## 五、与 Camargo 2021 公开数据集对比

| 维度 | 本数据集（2026.4.13-EMG） | Camargo 2021 |
|---|---|---|
| 来源 | 自采，`MyoMetrics` 商用设备 | 开源，Mendeley Data，佐治亚理工 EPIC Lab |
| 受试者 | **1 人**（单次采集） | **22 人**（`AB06–AB30`，健康成年人） |
| 肌肉数 | **3**（BF / GMed / RF，均右侧） | **11**（右侧下肢全覆盖） |
| 其他模态 | 无（仅 EMG） | 11-EMG + 3-Gonio + 4-IMU + 32-Marker MoCap + FP，自带 OpenSim IK/ID/Power |
| 任务 | 穿 / 不穿外骨骼走路 + MVC | 跑步机 / 平地 / 坡道 / 楼梯 / 模式切换 |
| 采样率 | **2000.36 Hz** | 1000 Hz |
| 带通 | 未知（设备出厂） | 20 – 400 Hz |
| 单位 | μV（原始，带负号） | mV（估计）Camargo 的 EMG 文件内值接近 1e-4 量级，已是预处理后 |
| 周期事件 | **无** | `gcRight.HeelStrike` 0–100 % 相位列 |
| 对抗 / 外骨骼 | ✅ 有 `with / without Electrode` 对照 | ❌ 仅裸条件 |
| MVC | ✅ 有（但 GMed 削顶） | ❌ 无显式 MVC，各论文通常用 peak-of-task 归一化 |
| 文件格式 | CSV（`MyoMetrics` 导出） | MATLAB MCOS `table` in `.mat`（需自定义 parser） |
| 削顶 / 异常 | 5 / 9 通道削顶，需掩蔽 | 极少削顶；偶见 sensor dropout |
| 数据量级 | 单 session ~37–93 s × 3 ch | 每受试者 > 20 min × 11 ch × 多任务 |

### 5.1 定位差异

- **Camargo** = **训练数据源**：提供 reference trajectory、EMG synergy NMF 分解的
  `W` 矩阵、跨受试者鲁棒的激活模板。容量足够训练 policy。
- **2026.4.13-EMG** = **验证 / 对比数据**：
  1. 首次验证「外骨骼介入是否改变 BF / GMed / RF 的激活模式」；
  2. 作为 RL 策略输出的 activation 模式的**个体化校验集**
     （对 policy 来说是 OOD 的，若 policy 在 Camargo 上 learnt 的 pattern
      能和自采数据定性吻合，则说明学到的是 biomechanical 不变量而非 subject-specific）；
  3. 测试 pipeline 跨数据集适配能力：相同的
     `bandpass → rectify → 6 Hz envelope → MVC 归一化` 链路应在两套数据上
     都产生形状接近的 0–1 激活曲线。

### 5.2 需要显式处理的差异

| 差异 | 影响 | 处理 |
|---|---|---|
| 采样率 2 kHz vs 1 kHz | 带宽 / 样本数 2× | 把自采数据下采样到 1 kHz，或把 Camargo 上采样；前者信息损失小 |
| 3 肌肉 vs 11 肌肉 | 自采是 Camargo 的**严格子集** | 在对比图中只画 BF / GMed / RF 三格，忽略其余 8 条 |
| Camargo 无 MVC | Z-score 或 peak-of-task 都可，两边需用同一个归一化约定 | 统一改用「walking session 内 95-percentile」做分母，避免 MVC 缺失 |
| 自采无 heel strike | 无法与 Camargo 的 0–100 % 相位轴直接对齐 | 实现 §4.5 策略 A（EMG-based 自相关周期检测） |
| 单位 μV vs mV | 数值尺度差 1000× | 归一化后都是 `[0, 1]`，无影响；若画原始波形要统一单位 |

---

## 六、建议的下一步脚本（要加入本 repo 的）

1. **`Code/EMG-Data-Analyser/myo_csv.py`** — CSV loader（§4.0），返回
   `(t, v, fs, meta)`，API 对齐 [camargo_mat.py](../../Code/EMG-Data-Analyser/camargo_mat.py)
   的 `load_emg_table`。
2. **`Code/EMG-Data-Analyser/plot_emg_self.py`** — 复用 `plot_emg.py` 的
   交互式 HTML 模板（浏览器端滤波 + 归一化），把输入切到 MyoMetrics CSV；
   控件栏增加 **"MVC normalize" 下拉**（off / per-muscle MVC / 95-percentile）。
3. **`Code/EMG-Data-Analyser/gait_cycles_self.py`** — 在缺 heel strike 的
   条件下，用 §4.5 策略 A 自动分周期，UI 与
   [gait_cycles.py](../../Code/EMG-Data-Analyser/gait_cycles.py) 保持一致，
   只换事件检测后端。
4. **`Code/EMG-Data-Analyser/compare_with_camargo.py`** — 从 Camargo 抽
   BF / GMed / RF 三通道的 mean ± std 步态曲线，叠加本数据集的同名曲线到
   同一张 3-subplot 图，输出 HTML。作为「自采 vs. 公开」的视觉比对。
