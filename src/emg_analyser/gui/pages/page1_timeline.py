from __future__ import annotations
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
    QVBoxLayout,
    QWidget,
    QComboBox,
)

from ...model.trial import Trial
from ...model.pipeline import PipelineConfig

# Distinct colors for up to 12 channels
_CHANNEL_COLORS = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728",
    "#9467bd", "#8c564b", "#e377c2", "#7f7f7f",
    "#bcbd22", "#17becf", "#aec7e8", "#ffbb78",
]


class Page1Timeline(QWidget):
    """Page 1 — folder picker + global raw timeline + time range selection."""

    folderRequested = pyqtSignal(str)          # user picked a folder
    regionChanged = pyqtSignal(float, float)   # (t_start, t_end)
    goToSegmentation = pyqtSignal()            # "→ Gait Cycle" button
    pipelineChanged = pyqtSignal(object)       # PipelineConfig

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._trial: Trial | None = None
        self._plot_items: list[pg.PlotItem] = []
        self._curves: dict[str, pg.PlotDataItem] = {}
        self._regions: list[pg.LinearRegionItem] = []
        self._channel_checks: dict[str, QCheckBox] = {}
        self._region_updating = False
        self._reprocess_timer = QTimer(self)
        self._reprocess_timer.setSingleShot(True)
        self._reprocess_timer.setInterval(60)
        self._reprocess_timer.timeout.connect(self._emit_pipeline)

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # ── Top bar ────────────────────────────────────────────────────
        top = QHBoxLayout()
        self._btn_folder = QPushButton("📁  Select Folder")
        self._btn_folder.setFixedWidth(150)
        self._lbl_path = QLabel("No folder selected")
        self._lbl_path.setStyleSheet("color: grey;")
        self._lbl_path.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._btn_reload = QPushButton("Reload")
        self._btn_reload.setFixedWidth(70)
        self._btn_reload.setEnabled(False)
        top.addWidget(self._btn_folder)
        top.addWidget(self._lbl_path)
        top.addWidget(self._btn_reload)
        root.addLayout(top)

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
        self._btn_folder.clicked.connect(self._on_pick_folder)
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

        layout.addStretch(1)

        # Connect controls
        self._spin_hp.valueChanged.connect(self._reprocess_timer.start)
        self._combo_smooth.currentTextChanged.connect(self._on_smooth_mode)
        self._combo_smooth.currentTextChanged.connect(self._reprocess_timer.start)
        self._spin_cutoff.valueChanged.connect(self._reprocess_timer.start)
        self._spin_window.valueChanged.connect(self._reprocess_timer.start)

        return panel

    def _on_smooth_mode(self, mode: str) -> None:
        self._spin_cutoff.setVisible(mode == "lowpass")
        self._spin_window.setVisible(mode in ("movavg", "rms"))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def load_trial(self, trial: Trial) -> None:
        self._trial = trial
        self._lbl_path.setStyleSheet("color: black;")
        self._btn_reload.setEnabled(True)
        self._build_plots(trial)
        self._btn_go.setEnabled(True)

    def update_curves(self, processed: dict[str, np.ndarray]) -> None:
        if self._trial is None:
            return
        t = self._trial.t
        for ch, arr in processed.items():
            if ch in self._curves:
                self._curves[ch].setData(t, arr)

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
    def _on_pick_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Data Folder")
        if path:
            self._lbl_path.setText(path)
            self._lbl_path.setStyleSheet("color: grey;")
            self._lbl_path.setText("Loading…  " + path)
            self.folderRequested.emit(path)

    def _on_reload(self) -> None:
        path = self._lbl_path.text()
        if path and path != "No folder selected":
            self.folderRequested.emit(path)

    def set_path_label(self, text: str) -> None:
        self._lbl_path.setText(text)
        self._lbl_path.setStyleSheet("color: black;")

    # ------------------------------------------------------------------
    # Plot building
    # ------------------------------------------------------------------
    def _build_plots(self, trial: Trial) -> None:
        self._glw.clear()
        self._plot_items.clear()
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

    def _update_range_label(self, t0: float, t1: float) -> None:
        dur = t1 - t0
        self._lbl_range.setText(
            f"Selected:  {t0:.2f} s – {t1:.2f} s  ({dur:.2f} s)"
        )

    # ------------------------------------------------------------------
    def _emit_pipeline(self) -> None:
        self.pipelineChanged.emit(self.current_pipeline())
