"""
Page 5 — Cross-Dataset Comparison with Lin's CCC.

Data is pushed in from the rest of the application — no independent loading:
  • Page 3 (Camargo)  → receive_camargo(result)  via MainWindow
  • Page 4 (Gait120)  → receive_gait120(result)   via MainWindow
  • SessionManager    → receive_myometrics(cs, trial) via MainWindow

Channels are aligned to a shared canonical name space and pairwise Lin's
Concordance Correlation Coefficient (CCC) is computed per channel.
"""
from __future__ import annotations

import sys
from itertools import combinations

import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)


# ── Canonical channel-name maps ───────────────────────────────────────────
# The canonical key space follows Camargo's convention (lowercase_underscore).
# Each dataset's own names are mapped TO canonical keys below.

# Gait120 CamelCase → canonical
_GAIT120_TO_CANONICAL: dict[str, str] = {
    "VastusLateralis":         "vastus_lateralis",
    "RectusFemoris":           "rectus_femoris",
    "VastusMedialis":          "vastus_medialis",
    "TibialisAnterior":        "tibialis_anterior",
    "BicepsFemoris":           "biceps_femoris",
    "Semitendinosus":          "semitendinosus",
    "GastrocnemuisMedialis":   "gastrocnemius_m",   # typo preserved from dataset
    "GastrocnemiusLateralis":  "gastrocnemius_l",
    "SoleusMedialis":          "soleus",             # best match for Camargo "soleus"
    "SoleusLateralis":         "soleus_l",           # Gait120-only
    "PeroneusLongus":          "peroneus_longus",    # Gait120-only
    "PeroneusBrevis":          "peroneus_brevis",    # Gait120-only
}

# MyoMetrics raw name → canonical
_MYO_TO_CANONICAL: dict[str, str] = {
    "BICEPS_FEM._RT":  "biceps_femoris",
    "GLUT_MED._RT":    "gluteus_medius",
    "RECTUS_FEM._RT":  "rectus_femoris",
}

# Camargo channel names are already canonical (used as-is)

# Human-readable display labels used in plot titles
_CANONICAL_DISPLAY: dict[str, str] = {
    "gastrocnemius_l":   "Gastroc. Lateralis",
    "gastrocnemius_m":   "Gastroc. Medialis",
    "soleus":            "Soleus",
    "soleus_l":          "Soleus Lateralis",
    "tibialis_anterior": "Tibialis Anterior",
    "vastus_medialis":   "Vastus Medialis",
    "vastus_lateralis":  "Vastus Lateralis",
    "rectus_femoris":    "Rectus Femoris",
    "biceps_femoris":    "Biceps Femoris",
    "semitendinosus":    "Semitendinosus",
    "gluteus_medius":    "Gluteus Medius",
    "gluteus_maximus":   "Gluteus Maximus",
    "peroneus_longus":   "Peroneus Longus",
    "peroneus_brevis":   "Peroneus Brevis",
}

_DATASET_COLORS = {
    "camargo":    "#1f77b4",
    "gait120":    "#ff7f0e",
    "myometrics": "#2ca02c",
}
_DATASET_LABELS = {
    "camargo":    "Camargo 2021",
    "gait120":    "Gait120",
    "myometrics": "Ours",
}

_N_COLS = 3


# ── Pure-function helpers ─────────────────────────────────────────────────

def _ccc(x: np.ndarray, y: np.ndarray) -> float:
    """Lin's Concordance Correlation Coefficient for two equal-length 1-D arrays."""
    if len(x) < 2:
        return float("nan")
    mx, my = x.mean(), y.mean()
    vx = np.var(x, ddof=0)
    vy = np.var(y, ddof=0)
    cov = float(np.cov(x, y, ddof=0)[0, 1])
    denom = vx + vy + (mx - my) ** 2
    return float(2.0 * cov / denom) if denom > 1e-12 else float("nan")


def _peak_norm(arr: np.ndarray) -> np.ndarray:
    peak = float(np.max(np.abs(arr)))
    return arr / peak if peak > 1e-12 else arr


def _camargo_to_profiles(result: dict) -> dict[str, np.ndarray]:
    """Global-mean 101-pt profile per canonical channel from a CamargoThread result."""
    by_subject = result.get("by_subject", {})
    channels: list[str] = result.get("channels", [])
    profiles: dict[str, np.ndarray] = {}
    for ch in channels:
        subj_means = [
            cs.cycles[ch].mean(axis=0)
            for cs in by_subject.values()
            if ch in cs.cycles and cs.cycles[ch].shape[0] > 0
        ]
        if subj_means:
            profiles[ch] = np.mean(subj_means, axis=0)
    return profiles   # Camargo names are already canonical


def _gait120_to_profiles(result: dict) -> dict[str, np.ndarray]:
    """Global-mean 101-pt profile per canonical channel from a Gait120Thread result."""
    by_subject = result.get("by_subject", {})
    channels: list[str] = result.get("channels", [])
    profiles: dict[str, np.ndarray] = {}
    for ch in channels:
        canonical = _GAIT120_TO_CANONICAL.get(ch)
        if canonical is None:
            continue
        subj_means = [
            d[ch].mean(axis=0)
            for d in by_subject.values()
            if ch in d and d[ch].shape[0] > 0
        ]
        if subj_means:
            profiles[canonical] = np.mean(subj_means, axis=0)
    return profiles


def _myo_to_profiles(cycle_set) -> dict[str, np.ndarray]:
    """Mean profile per canonical channel from a MyoMetrics CycleSet."""
    return {
        _MYO_TO_CANONICAL[ch]: mat.mean(axis=0)
        for ch, mat in cycle_set.cycles.items()
        if ch in _MYO_TO_CANONICAL and mat.shape[0] > 0
    }


# ── Page ─────────────────────────────────────────────────────────────────

class Page5Compare(QWidget):
    """Page 5 — Cross-dataset EMG comparison with pairwise Lin's CCC.

    Data arrives via receive_*() calls from MainWindow; no standalone
    dataset loading lives on this page.
    """

    logMessage = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # Most-recent raw results from each source
        self._cam_raw_result: dict | None = None
        self._g120_raw_result: dict | None = None
        self._myo_cycle_set = None   # CycleSet | None

        self._plot_items: list[pg.PlotItem] = []
        self._channel_checks: dict[str, QCheckBox] = {}
        self._updating_checks = False

        self._build_ui()

    # ──────────────────────────────────────────────────────────────────────
    # UI construction
    # ──────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # Status bar
        top = QHBoxLayout()
        self._lbl_status = QLabel(
            "Run analysis in tabs 3 and/or 4 (and gait-cycle segmentation in tab 2) first"
        )
        self._lbl_status.setStyleSheet("color: grey; font-style: italic;")
        self._lbl_status.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        top.addWidget(self._lbl_status)
        root.addLayout(top)

        # Splitter: plots | control panel
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        self._glw = pg.GraphicsLayoutWidget()
        self._glw.setBackground("w")
        splitter.addWidget(self._glw)
        splitter.addWidget(self._build_control_panel())
        splitter.setStretchFactor(0, 7)
        splitter.setStretchFactor(1, 3)
        root.addWidget(splitter, stretch=1)

        # Bottom stats + export button
        bot = QHBoxLayout()
        self._lbl_stats = QLabel("—")
        self._lbl_stats.setStyleSheet("color: #555;")
        self._lbl_stats.setWordWrap(True)
        self._btn_export = QPushButton("Export PNG")
        self._btn_export.setEnabled(False)
        self._btn_export.clicked.connect(self._export_png)
        bot.addWidget(self._lbl_stats, stretch=1)
        bot.addWidget(self._btn_export)
        root.addLayout(bot)

    def _build_control_panel(self) -> QWidget:
        outer = QWidget()
        outer.setFixedWidth(240)
        outer_v = QVBoxLayout(outer)
        outer_v.setContentsMargins(0, 0, 0, 0)
        outer_v.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        inner = QWidget()
        v = QVBoxLayout(inner)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(8)

        # ── Data-source status ──
        grp_src = QGroupBox("Data Sources")
        vs = QVBoxLayout(grp_src)
        vs.setSpacing(5)

        hint = QLabel("Run 'Load & Analyse' in tabs 3 and 4. "
                      "Gait-cycle segmentation in tab 2 provides MyoMetrics data.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666; font-size: 10px;")
        vs.addWidget(hint)

        self._lbl_cam_src = QLabel("Camargo 2021 : not loaded")
        self._lbl_cam_src.setWordWrap(True)
        self._lbl_cam_src.setStyleSheet("color: grey; font-size: 10px;")
        vs.addWidget(self._lbl_cam_src)

        self._lbl_g120_src = QLabel("Gait120 : not loaded")
        self._lbl_g120_src.setWordWrap(True)
        self._lbl_g120_src.setStyleSheet("color: grey; font-size: 10px;")
        vs.addWidget(self._lbl_g120_src)

        self._lbl_myo_src = QLabel("MyoMetrics : not loaded")
        self._lbl_myo_src.setWordWrap(True)
        self._lbl_myo_src.setStyleSheet("color: grey; font-size: 10px;")
        vs.addWidget(self._lbl_myo_src)

        v.addWidget(grp_src)

        # ── Display options ──
        grp_disp = QGroupBox("Display")
        vd = QVBoxLayout(grp_disp)
        vd.setSpacing(3)
        self._chk_norm = QCheckBox("Normalize per channel (peak = 1)")
        self._chk_norm.setChecked(True)
        self._chk_norm.toggled.connect(self._refresh_if_ready)
        vd.addWidget(self._chk_norm)
        v.addWidget(grp_disp)

        # ── Channel visibility ──
        grp_ch = QGroupBox("Channels")
        vch = QVBoxLayout(grp_ch)
        vch.setSpacing(4)

        btn_row = QHBoxLayout()
        self._btn_ch_all = QPushButton("All")
        self._btn_ch_none = QPushButton("None")
        self._btn_ch_all.setEnabled(False)
        self._btn_ch_none.setEnabled(False)
        self._btn_ch_all.clicked.connect(lambda: self._set_all_channels(True))
        self._btn_ch_none.clicked.connect(lambda: self._set_all_channels(False))
        btn_row.addWidget(self._btn_ch_all)
        btn_row.addWidget(self._btn_ch_none)
        vch.addLayout(btn_row)

        self._ch_scroll_widget = QWidget()
        self._ch_scroll_layout = QVBoxLayout(self._ch_scroll_widget)
        self._ch_scroll_layout.setSpacing(2)
        self._ch_scroll_layout.setContentsMargins(0, 0, 0, 0)
        ch_scroll = QScrollArea()
        ch_scroll.setWidgetResizable(True)
        ch_scroll.setMaximumHeight(220)
        ch_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        ch_scroll.setWidget(self._ch_scroll_widget)
        vch.addWidget(ch_scroll)
        v.addWidget(grp_ch)

        # ── Run button ──
        self._btn_compare = QPushButton("Run Comparison")
        self._btn_compare.setEnabled(False)
        self._btn_compare.clicked.connect(self._on_run_comparison)
        v.addWidget(self._btn_compare)

        v.addStretch(1)
        scroll.setWidget(inner)
        outer_v.addWidget(scroll)
        return outer

    # ──────────────────────────────────────────────────────────────────────
    # Data receivers  (called by MainWindow)
    # ──────────────────────────────────────────────────────────────────────

    def receive_camargo(self, result: dict) -> None:
        """Accept a completed Camargo analysis result from Page 3."""
        self._cam_raw_result = result
        by_subject = result.get("by_subject", {})
        mode = result.get("mode", "?")
        n_subj = len(by_subject)
        n_cyc = sum(cs.n_cycles for cs in by_subject.values())
        self._lbl_cam_src.setText(
            f"Camargo 2021 : ✓  {mode}, {n_subj} subj, {n_cyc} cycles"
        )
        self._lbl_cam_src.setStyleSheet("color: #2a7; font-size: 10px;")
        self.logMessage.emit(
            f"[INFO] Compare: Camargo data received ({mode}, {n_subj} subjects)"
        )
        self._refresh_if_ready()

    def receive_gait120(self, result: dict) -> None:
        """Accept a completed Gait120 analysis result from Page 4."""
        self._g120_raw_result = result
        by_subject = result.get("by_subject", {})
        mode = result.get("mode", "?")
        n_subj = len(by_subject)
        n_steps = sum(
            next(iter(d.values())).shape[0]
            for d in by_subject.values()
            if d
        )
        self._lbl_g120_src.setText(
            f"Gait120 : ✓  {mode}, {n_subj} subj, {n_steps} steps"
        )
        self._lbl_g120_src.setStyleSheet("color: #2a7; font-size: 10px;")
        self.logMessage.emit(
            f"[INFO] Compare: Gait120 data received ({mode}, {n_subj} subjects)"
        )
        self._refresh_if_ready()

    def receive_myometrics(self, cycle_set, trial) -> None:
        """Accept a CycleSet from SessionManager's cyclesReady signal."""
        if cycle_set is None or cycle_set.n_cycles == 0:
            return
        self._myo_cycle_set = cycle_set
        subject = getattr(trial, "subject", "?") if trial is not None else "?"
        n_cyc = cycle_set.n_cycles
        self._lbl_myo_src.setText(
            f"MyoMetrics : ✓  {subject}, {n_cyc} cycles"
        )
        self._lbl_myo_src.setStyleSheet("color: #2a7; font-size: 10px;")
        self.logMessage.emit(
            f"[INFO] Compare: MyoMetrics data received ({n_cyc} cycles)"
        )
        self._refresh_if_ready()

    # ──────────────────────────────────────────────────────────────────────
    # Channel-list management
    # ──────────────────────────────────────────────────────────────────────

    def _populate_channels(self, canonical_channels: list[str]) -> None:
        prev = {ch: cb.isChecked() for ch, cb in self._channel_checks.items()}
        while self._ch_scroll_layout.count():
            item = self._ch_scroll_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._channel_checks.clear()

        self._updating_checks = True
        for ch in canonical_channels:
            label = _CANONICAL_DISPLAY.get(ch, ch)
            cb = QCheckBox(label)
            cb.setChecked(prev.get(ch, True))
            cb.setToolTip(ch)
            cb.toggled.connect(self._on_channel_toggled)
            self._ch_scroll_layout.addWidget(cb)
            self._channel_checks[ch] = cb
        self._ch_scroll_layout.addStretch(1)
        self._updating_checks = False

        has = bool(canonical_channels)
        self._btn_ch_all.setEnabled(has)
        self._btn_ch_none.setEnabled(has)

    def _set_all_channels(self, checked: bool) -> None:
        self._updating_checks = True
        for cb in self._channel_checks.values():
            cb.setChecked(checked)
        self._updating_checks = False
        self._on_channel_toggled()

    def _on_channel_toggled(self, *_) -> None:
        if not self._updating_checks:
            self._on_run_comparison()

    def _selected_channels(self, all_ch: list[str]) -> list[str]:
        if not self._channel_checks:
            return all_ch
        return [ch for ch in all_ch
                if self._channel_checks.get(ch) and self._channel_checks[ch].isChecked()]

    # ──────────────────────────────────────────────────────────────────────
    # Comparison logic
    # ──────────────────────────────────────────────────────────────────────

    def _n_loaded(self) -> int:
        return sum([
            self._cam_raw_result is not None,
            self._g120_raw_result is not None,
            self._myo_cycle_set is not None and self._myo_cycle_set.n_cycles > 0,
        ])

    def _refresh_if_ready(self) -> None:
        loaded = self._n_loaded()
        self._btn_compare.setEnabled(loaded >= 2)
        if loaded >= 2:
            self._on_run_comparison()

    def _on_run_comparison(self) -> None:
        all_profiles: dict[str, dict[str, np.ndarray]] = {}

        if self._cam_raw_result is not None:
            p = _camargo_to_profiles(self._cam_raw_result)
            if p:
                all_profiles["camargo"] = p

        if self._g120_raw_result is not None:
            p = _gait120_to_profiles(self._g120_raw_result)
            if p:
                all_profiles["gait120"] = p

        if self._myo_cycle_set is not None and self._myo_cycle_set.n_cycles > 0:
            p = _myo_to_profiles(self._myo_cycle_set)
            if p:
                all_profiles["myometrics"] = p

        if len(all_profiles) < 2:
            return

        # Peak-normalize each channel in each dataset independently
        if self._chk_norm.isChecked():
            all_profiles = {
                ds: {ch: _peak_norm(arr) for ch, arr in p.items()}
                for ds, p in all_profiles.items()
            }

        # All canonical channels present in at least one loaded dataset
        all_channels = sorted(set.union(*[set(p.keys()) for p in all_profiles.values()]))

        # Refresh channel-checkbox list if the available channels changed
        if set(all_channels) != set(self._channel_checks.keys()):
            self._populate_channels(all_channels)

        selected = self._selected_channels(all_channels)
        if not selected:
            selected = all_channels

        self._build_plots(all_profiles, selected)

    # ──────────────────────────────────────────────────────────────────────
    # Plot building
    # ──────────────────────────────────────────────────────────────────────

    def _build_plots(
        self,
        all_profiles: dict[str, dict[str, np.ndarray]],
        channels: list[str],
    ) -> None:
        self._glw.clear()
        self._plot_items.clear()

        if not channels or not all_profiles:
            self._glw.addPlot().setTitle("No data available")
            self._btn_export.setEnabled(False)
            return

        datasets = list(all_profiles.keys())
        x = np.linspace(0, 100, 101)
        n_rows = max(1, int(np.ceil(len(channels) / _N_COLS)))
        normalize = self._chk_norm.isChecked()

        # Pairwise CCC — only computed for channels present in both datasets of a pair
        ccc_by_pair: dict[tuple[str, str], dict[str, float]] = {}
        for a, b in combinations(datasets, 2):
            pair: dict[str, float] = {}
            for ch in channels:
                if ch in all_profiles.get(a, {}) and ch in all_profiles.get(b, {}):
                    pair[ch] = _ccc(all_profiles[a][ch], all_profiles[b][ch])
            ccc_by_pair[(a, b)] = pair

        for idx, ch in enumerate(channels):
            row_i = idx // _N_COLS
            col_i = idx % _N_COLS
            pi = self._glw.addPlot(row=row_i, col=col_i)
            pi.showGrid(x=True, y=True, alpha=0.15)
            pi.setXRange(0, 100, padding=0.0)

            if normalize:
                pi.enableAutoRange(axis="y", enable=False)
                pi.setYRange(0.0, 1.05, padding=0.0)
            else:
                pi.enableAutoRange(axis="y", enable=True)

            if row_i == n_rows - 1:
                pi.setLabel("bottom", "Gait cycle (%)")
            else:
                pi.getAxis("bottom").setStyle(showValues=False)

            # Legend only on the first subplot
            if idx == 0:
                pi.addLegend(offset=(1, 1))

            # Overlay one line per dataset
            for ds, profiles in all_profiles.items():
                if ch not in profiles:
                    continue
                pi.plot(
                    x, profiles[ch],
                    pen=pg.mkPen(_DATASET_COLORS[ds], width=2.5),
                    name=_DATASET_LABELS[ds],
                )

            # Subplot title: readable muscle name + CCC values
            display_name = _CANONICAL_DISPLAY.get(ch, ch)
            ccc_parts = []
            for (a, b), pair in ccc_by_pair.items():
                if ch in pair and not np.isnan(pair[ch]):
                    la = _DATASET_LABELS[a][:3]
                    lb = _DATASET_LABELS[b][:3]
                    ccc_parts.append(f"CCC({la}↔{lb})={pair[ch]:.3f}")
            title_html = f"<b>{display_name}</b>"
            if ccc_parts:
                title_html += (
                    "<br><span style='font-size:7pt;color:#555;'>"
                    + "  ".join(ccc_parts)
                    + "</span>"
                )
            pi.setTitle(title_html, size="9pt")
            self._plot_items.append(pi)

        # Stats bar
        channel_sets = [set(p.keys()) for p in all_profiles.values()]
        n_shared = len(set.intersection(*channel_sets))
        avg_cccs: list[str] = []
        for (a, b), pair in ccc_by_pair.items():
            vals = [v for v in pair.values() if not np.isnan(v)]
            if vals:
                la, lb = _DATASET_LABELS[a][:3], _DATASET_LABELS[b][:3]
                avg_cccs.append(f"avg CCC({la}↔{lb})={np.mean(vals):.3f}")

        norm_str = "on" if normalize else "off"
        stats = (
            f"{len(datasets)} datasets  ·  {len(channels)} channels shown "
            f"({n_shared} shared across all)  ·  norm={norm_str}"
        )
        if avg_cccs:
            stats += "  ·  " + "  ".join(avg_cccs)
        self._lbl_stats.setText(stats)
        self._btn_export.setEnabled(True)
        self._lbl_status.setText(
            "Comparison: " + "  ·  ".join(_DATASET_LABELS[ds] for ds in datasets)
        )
        self._lbl_status.setStyleSheet("color: #444;")

    # ──────────────────────────────────────────────────────────────────────
    # Export
    # ──────────────────────────────────────────────────────────────────────

    def _export_png(self) -> None:
        opts = QFileDialog.Options()
        if sys.platform == "darwin":
            opts |= QFileDialog.DontUseNativeDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "Export PNG", "comparison.png", "PNG (*.png)", options=opts
        )
        if path:
            self._glw.grab().save(path)
