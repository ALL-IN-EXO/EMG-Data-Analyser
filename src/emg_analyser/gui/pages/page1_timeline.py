from __future__ import annotations
import sys
from html import escape
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QComboBox,
)

from ...model.trial import Trial
from ...model.pipeline import PipelineConfig

_DEFAULT_DATA = str(Path(__file__).parents[4] / "SAMPLE_DATA" / "2026.4.13-EMG")
_DEFAULT_MVC  = str(Path(__file__).parents[4] / "SAMPLE_DATA" / "2026.4.13-EMG" / "EMG-Electrode Max MVC")

# Distinct colors for up to 12 channels
_CHANNEL_COLORS = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728",
    "#9467bd", "#8c564b", "#e377c2", "#7f7f7f",
    "#bcbd22", "#17becf", "#aec7e8", "#ffbb78",
]


class Page1Timeline(QWidget):
    """Page 1 — folder picker + global raw timeline + time range selection."""

    folderRequested = pyqtSignal(str, str)     # (data_folder, mvc_folder)
    regionChanged = pyqtSignal(float, float)   # (t_start, t_end)
    goToSegmentation = pyqtSignal()            # "→ Gait Cycle" button
    pipelineChanged = pyqtSignal(object)       # PipelineConfig

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._trial: Trial | None = None
        self._data_path: str = ""
        self._mvc_path: str = ""
        self._plot_items: list[pg.PlotItem] = []
        self._plot_channels: list[str] = []
        self._curves: dict[str, pg.PlotDataItem] = {}
        self._cycle_start_times = np.array([], dtype=float)
        self._cycle_markers: list[tuple[pg.PlotItem, pg.ErrorBarItem]] = []
        self._regions: list[pg.LinearRegionItem] = []
        self._channel_checks: dict[str, QCheckBox] = {}
        self._region_updating = False
        self._is_dark = False
        self._reprocess_timer = QTimer(self)
        self._reprocess_timer.setSingleShot(True)
        self._reprocess_timer.setInterval(60)
        self._reprocess_timer.timeout.connect(self._emit_pipeline)

        self._build_ui()
        self._apply_default_paths()

    def _apply_default_paths(self) -> None:
        if Path(_DEFAULT_DATA).is_dir():
            self._data_path = _DEFAULT_DATA
            self._lbl_data_path.setText(_DEFAULT_DATA)
            self._lbl_data_path.setStyleSheet("color: grey;")
        if Path(_DEFAULT_MVC).is_dir():
            self._mvc_path = _DEFAULT_MVC
            self._lbl_mvc_path.setText(_DEFAULT_MVC)
            self._lbl_mvc_path.setStyleSheet("color: grey;")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # ── Top bar ────────────────────────────────────────────────────
        top_data = QHBoxLayout()
        self._btn_data_folder = QPushButton("📁  Data Folder")
        self._btn_data_folder.setFixedWidth(150)
        self._lbl_data_path = QLabel("No data folder selected")
        self._lbl_data_path.setStyleSheet("color: grey;")
        self._lbl_data_path.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._btn_reload = QPushButton("Reload")
        self._btn_reload.setFixedWidth(70)
        self._btn_reload.setEnabled(False)
        top_data.addWidget(self._btn_data_folder)
        top_data.addWidget(self._lbl_data_path)
        top_data.addWidget(self._btn_reload)
        root.addLayout(top_data)

        top_mvc = QHBoxLayout()
        self._btn_mvc_folder = QPushButton("📁  MVC Folder")
        self._btn_mvc_folder.setFixedWidth(150)
        self._lbl_mvc_path = QLabel("No MVC folder selected")
        self._lbl_mvc_path.setStyleSheet("color: grey;")
        self._lbl_mvc_path.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        top_mvc.addWidget(self._btn_mvc_folder)
        top_mvc.addWidget(self._lbl_mvc_path)
        top_mvc.addSpacing(70)
        root.addLayout(top_mvc)

        # ── Splitter: plots | controls ──────────────────────────────────
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Left: pyqtgraph GraphicsLayoutWidget
        self._glw = pg.GraphicsLayoutWidget()
        self._glw.setBackground("w")
        splitter.addWidget(self._glw)

        # Right: control panel
        ctrl = self._build_control_panel()
        splitter.addWidget(ctrl)
        splitter.setStretchFactor(0, 7)
        splitter.setStretchFactor(1, 3)
        root.addWidget(splitter, stretch=1)

        # ── Bottom bar ─────────────────────────────────────────────────
        bottom = QHBoxLayout()
        self._lbl_range = QLabel("Selected: —")
        self._lbl_range.setStyleSheet("color: #555;")
        self._btn_go = QPushButton("→  Gait Cycle Segmentation")
        self._btn_go.setEnabled(False)
        self._btn_go.setStyleSheet(
            "QPushButton { background: #1f77b4; color: white; padding: 4px 12px; }"
            "QPushButton:disabled { background: #aaa; }"
        )
        bottom.addWidget(self._lbl_range, stretch=1)
        bottom.addWidget(self._btn_go)
        root.addLayout(bottom)

        # ── Connections ─────────────────────────────────────────────────
        self._btn_data_folder.clicked.connect(self._on_pick_data_folder)
        self._btn_mvc_folder.clicked.connect(self._on_pick_mvc_folder)
        self._btn_reload.clicked.connect(self._on_reload)
        self._btn_go.clicked.connect(self.goToSegmentation)

    def _build_control_panel(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(220)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        # Pipeline group
        grp_pipe = QGroupBox("Display Pipeline")
        form = QFormLayout(grp_pipe)
        form.setSpacing(4)

        self._spin_hp = QDoubleSpinBox()
        self._spin_hp.setRange(0, 499)
        self._spin_hp.setValue(20.0)
        self._spin_hp.setSuffix(" Hz")
        self._spin_hp.setSingleStep(1.0)
        form.addRow("Highpass:", self._spin_hp)

        self._combo_smooth = QComboBox()
        self._combo_smooth.addItems(["lowpass", "movavg", "rms", "none"])
        form.addRow("Smoothing:", self._combo_smooth)

        self._spin_cutoff = QDoubleSpinBox()
        self._spin_cutoff.setRange(0.1, 499)
        self._spin_cutoff.setValue(6.0)
        self._spin_cutoff.setSuffix(" Hz")
        form.addRow("Cutoff:", self._spin_cutoff)

        self._spin_window = QDoubleSpinBox()
        self._spin_window.setRange(1, 500)
        self._spin_window.setValue(50.0)
        self._spin_window.setSuffix(" ms")
        self._spin_window.setVisible(False)
        form.addRow("Window:", self._spin_window)

        layout.addWidget(grp_pipe)

        # Channel visibility group
        self._grp_ch = QGroupBox("Channels")
        self._ch_layout = QVBoxLayout(self._grp_ch)
        self._ch_layout.setSpacing(2)
        layout.addWidget(self._grp_ch)

        # Normalized stats group
        grp_stats = QGroupBox("Normalized Stats")
        stats_layout = QVBoxLayout(grp_stats)
        stats_layout.setContentsMargins(4, 4, 4, 4)
        self._txt_norm_stats = QTextEdit()
        self._txt_norm_stats.setReadOnly(True)
        self._txt_norm_stats.setFixedHeight(170)
        stats_layout.addWidget(self._txt_norm_stats)
        layout.addWidget(grp_stats)

        layout.addStretch(1)

        # Connect controls
        self._spin_hp.valueChanged.connect(self._schedule_reprocess)
        self._combo_smooth.currentTextChanged.connect(self._on_smooth_mode)
        self._combo_smooth.currentTextChanged.connect(self._schedule_reprocess)
        self._spin_cutoff.valueChanged.connect(self._schedule_reprocess)
        self._spin_window.valueChanged.connect(self._schedule_reprocess)

        return panel

    def _on_smooth_mode(self, mode: str) -> None:
        self._spin_cutoff.setVisible(mode == "lowpass")
        self._spin_window.setVisible(mode in ("movavg", "rms"))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def load_trial(self, trial: Trial) -> None:
        self._trial = trial
        self._cycle_start_times = np.array([], dtype=float)
        self._lbl_data_path.setStyleSheet("color: black;")
        self._lbl_mvc_path.setStyleSheet("color: black;")
        self._btn_reload.setEnabled(True)
        self._build_plots(trial)
        self._update_norm_stats()
        self._btn_go.setEnabled(True)

    def update_curves(self, processed: dict[str, np.ndarray]) -> None:
        if self._trial is None:
            return
        t = self._trial.t
        for ch, arr in processed.items():
            if ch in self._curves:
                self._curves[ch].setData(t, arr)
        self._refresh_cycle_markers()
        self._update_norm_stats()

    def set_cycle_starts(self, start_times: list[float] | np.ndarray) -> None:
        arr = np.asarray(start_times, dtype=float).reshape(-1)
        self._cycle_start_times = np.sort(arr) if arr.size else np.array([], dtype=float)
        self._refresh_cycle_markers()

    def current_pipeline(self) -> PipelineConfig:
        return PipelineConfig(
            highpass_hz=self._spin_hp.value(),
            smoothing=self._combo_smooth.currentText(),
            smoothing_cutoff_hz=self._spin_cutoff.value(),
            smoothing_window_ms=self._spin_window.value(),
        )

    def current_region(self) -> tuple[float, float] | None:
        if not self._regions:
            return None
        return tuple(self._regions[0].getRegion())

    # ------------------------------------------------------------------
    # Folder handling
    # ------------------------------------------------------------------
    @staticmethod
    def _dialog_options() -> QFileDialog.Options:
        opts = QFileDialog.Options()
        if sys.platform == "darwin":
            opts |= QFileDialog.DontUseNativeDialog
        return opts

    def _on_pick_data_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Select Data Folder",
            self._data_path or _DEFAULT_DATA,
            options=self._dialog_options(),
        )
        if path:
            self._data_path = path
            self._lbl_data_path.setText(path)
            self._lbl_data_path.setStyleSheet("color: grey;")
            self._try_emit_folder_request()

    def _on_pick_mvc_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Select MVC Folder",
            self._mvc_path or _DEFAULT_MVC,
            options=self._dialog_options(),
        )
        if path:
            self._mvc_path = path
            self._lbl_mvc_path.setText(path)
            self._lbl_mvc_path.setStyleSheet("color: grey;")
            self._try_emit_folder_request()

    def _try_emit_folder_request(self) -> None:
        if not self._data_path or not self._mvc_path:
            return
        self._lbl_data_path.setText("Loading…  " + self._data_path)
        self._lbl_data_path.setStyleSheet("color: grey;")
        self.folderRequested.emit(self._data_path, self._mvc_path)

    def _on_reload(self) -> None:
        if self._data_path and self._mvc_path:
            self.folderRequested.emit(self._data_path, self._mvc_path)

    def set_path_label(self, text: str) -> None:
        self._lbl_data_path.setText(text)
        self._lbl_data_path.setStyleSheet("color: black;")

    # ------------------------------------------------------------------
    # Plot building
    # ------------------------------------------------------------------
    def _build_plots(self, trial: Trial) -> None:
        self._clear_cycle_markers()
        self._glw.clear()
        self._plot_items.clear()
        self._plot_channels.clear()
        self._curves.clear()
        self._regions.clear()

        # Rebuild channel checkboxes
        for cb in self._channel_checks.values():
            cb.deleteLater()
        self._channel_checks.clear()

        ch_names = list(trial.channels.keys())
        t = trial.t

        first_plot: pg.PlotItem | None = None
        for i, ch in enumerate(ch_names):
            color = _CHANNEL_COLORS[i % len(_CHANNEL_COLORS)]
            pi = self._glw.addPlot(row=i, col=0)
            pi.showGrid(x=False, y=True, alpha=0.3)
            pi.setLabel("left", ch, units=trial.units)
            if i < len(ch_names) - 1:
                pi.getAxis("bottom").setStyle(showValues=False)
            else:
                pi.setLabel("bottom", "Time", units="s")

            if first_plot is None:
                first_plot = pi
            else:
                pi.setXLink(first_plot)

            curve = pi.plot(t, trial.channels[ch], pen=pg.mkPen(color, width=1))
            self._curves[ch] = curve
            self._plot_items.append(pi)
            self._plot_channels.append(ch)

            # Channel visibility checkbox
            cb = QCheckBox(ch)
            cb.setChecked(True)
            cb.setStyleSheet(f"color: {color}; font-weight: bold;")
            cb.toggled.connect(lambda checked, p=pi: p.setVisible(checked))
            self._ch_layout.addWidget(cb)
            self._channel_checks[ch] = cb

        # Add a LinearRegionItem to every plot (synced)
        if self._plot_items:
            t0, t1 = float(t[0]), float(t[-1])
            for pi in self._plot_items:
                region = pg.LinearRegionItem(
                    values=[t0, t1],
                    brush=pg.mkBrush(31, 119, 180, 40),
                    pen=pg.mkPen("#1f77b4", width=1.5),
                    movable=True,
                )
                pi.addItem(region)
                self._regions.append(region)
                region.sigRegionChanged.connect(self._on_region_changed)
                region.sigRegionChangeFinished.connect(self._on_region_finished)

            self._update_range_label(t0, t1)
        self._refresh_cycle_markers()
        self._apply_plot_theme()

    def _on_region_changed(self) -> None:
        if self._region_updating or not self._regions:
            return
        sender = self.sender()
        r = sender.getRegion()
        self._region_updating = True
        for reg in self._regions:
            if reg is not sender:
                reg.setRegion(r)
        self._region_updating = False
        self._update_range_label(r[0], r[1])

    def _on_region_finished(self) -> None:
        if not self._regions:
            return
        r = self._regions[0].getRegion()
        self.regionChanged.emit(float(r[0]), float(r[1]))
        self._update_norm_stats()

    def _update_range_label(self, t0: float, t1: float) -> None:
        dur = t1 - t0
        self._lbl_range.setText(
            f"Selected:  {t0:.2f} s – {t1:.2f} s  ({dur:.2f} s)"
        )

    # ------------------------------------------------------------------
    def _emit_pipeline(self) -> None:
        self.pipelineChanged.emit(self.current_pipeline())

    def _schedule_reprocess(self, *_args) -> None:
        self._reprocess_timer.start()

    def _clear_cycle_markers(self) -> None:
        for pi, marker in self._cycle_markers:
            try:
                pi.removeItem(marker)
            except Exception:
                pass
        self._cycle_markers.clear()

    def _refresh_cycle_markers(self) -> None:
        self._clear_cycle_markers()
        if self._trial is None or not self._plot_items:
            return
        if self._cycle_start_times.size == 0:
            return

        t = self._trial.t
        t_min = float(t[0])
        t_max = float(t[-1])
        starts = self._cycle_start_times[
            (self._cycle_start_times >= t_min) & (self._cycle_start_times <= t_max)
        ]
        if starts.size == 0:
            return

        idx = np.searchsorted(t, starts, side="left")
        idx = np.clip(idx, 0, len(t) - 1)

        for pi, ch in zip(self._plot_items, self._plot_channels):
            curve = self._curves.get(ch)
            if curve is None:
                continue
            _, y_vals = curve.getData()
            if y_vals is None or len(y_vals) != len(t):
                y_vals = self._trial.channels.get(ch)
            if y_vals is None or len(y_vals) == 0:
                continue

            y_vals = np.asarray(y_vals, dtype=float)
            y_marks = y_vals[idx]
            span = float(np.percentile(y_vals, 95) - np.percentile(y_vals, 5))
            half = max(span * 0.08, 1e-6)
            marker = pg.ErrorBarItem(
                x=starts,
                y=y_marks,
                top=np.full(starts.size, half, dtype=float),
                bottom=np.full(starts.size, half, dtype=float),
                beam=0.0,
                pen=pg.mkPen("#111111", width=1.2),
            )
            pi.addItem(marker)
            self._cycle_markers.append((pi, marker))

    def _update_norm_stats(self) -> None:
        if self._trial is None or not self._plot_channels:
            self._txt_norm_stats.setHtml("<span style='color:#666;'>No trial loaded</span>")
            return

        t = self._trial.t
        if self._regions:
            t0, t1 = self._regions[0].getRegion()
            lo, hi = float(min(t0, t1)), float(max(t0, t1))
            mask = (t >= lo) & (t <= hi)
        else:
            mask = np.ones_like(t, dtype=bool)

        if int(mask.sum()) < 3:
            mask = np.ones_like(t, dtype=bool)

        mvc_map = self._trial.meta.get("mvc_peak_abs", {})
        lines = ["<span style='color:#444;'>peak/rms (normalized)</span>"]
        for i, ch in enumerate(self._plot_channels):
            curve = self._curves.get(ch)
            if curve is None:
                continue
            _, y_vals = curve.getData()
            if y_vals is None or len(y_vals) != len(t):
                y_vals = self._trial.channels.get(ch)
            if y_vals is None or len(y_vals) == 0:
                continue

            seg = np.asarray(y_vals, dtype=float)[mask]
            if seg.size == 0:
                continue

            peak = float(np.max(np.abs(seg)))
            rms = float(np.sqrt(np.mean(seg ** 2)))

            denom = float(mvc_map.get(ch, 0.0))
            denom_tag = "mvc95"
            if denom <= 1e-12:
                denom = float(np.percentile(np.abs(seg), 95))
                denom_tag = "task95"
            if denom <= 1e-12:
                n_peak = 0.0
                n_rms = 0.0
                denom_tag = "na"
            else:
                n_peak = peak / denom
                n_rms = rms / denom

            color = _CHANNEL_COLORS[i % len(_CHANNEL_COLORS)]
            lines.append(
                f"<span style='color:{color};'>"
                f"{escape(ch)}: peak {n_peak:.3f}, rms {n_rms:.3f} [{denom_tag}]"
                f"</span>"
            )

        self._txt_norm_stats.setHtml("<br/>".join(lines))

    def set_theme(self, dark: bool) -> None:
        self._is_dark = dark
        self._glw.setBackground("#1b1b1b" if dark else "w")
        self._lbl_range.setStyleSheet("color: #bbb;" if dark else "color: #555;")
        self._apply_plot_theme()

    def _apply_plot_theme(self) -> None:
        if not self._plot_items:
            return
        pen = pg.mkPen("#ddd" if self._is_dark else "#222")
        for pi in self._plot_items:
            for axis_name in ("left", "bottom"):
                axis = pi.getAxis(axis_name)
                axis.setPen(pen)
                axis.setTextPen(pen)
