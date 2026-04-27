from __future__ import annotations
from html import escape
import random
import sys

import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...model.cycles import CycleSet
from ...model.pipeline import PipelineConfig, SegConfig
from ...model.trial import Trial

_CHANNEL_COLORS = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728",
    "#9467bd", "#8c564b", "#e377c2", "#7f7f7f",
]
_INDIVIDUAL_ALPHA = 40   # 0-255


class Page2GaitCycle(QWidget):
    """Page 2 — mean ± std gait cycle view + segmentation controls."""

    backRequested = pyqtSignal()
    segConfigChanged = pyqtSignal(object)   # SegConfig
    pipelineChanged = pyqtSignal(object)    # PipelineConfig (passed through)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._trial: Trial | None = None
        self._cycle_set: CycleSet | None = None
        self._plot_items: list[pg.PlotItem] = []
        self._seg_timer = QTimer(self)
        self._seg_timer.setSingleShot(True)
        self._seg_timer.setInterval(80)
        self._seg_timer.timeout.connect(self._emit_seg_config)
        self._overlay_visible = False

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
        self._btn_back = QPushButton("← Back")
        self._btn_back.setFixedWidth(80)
        self._lbl_info = QLabel("No data loaded")
        self._lbl_info.setStyleSheet("color: grey; font-style: italic;")
        self._lbl_info.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._lbl_overlay = QLabel("⏳  Segmenting…")
        self._lbl_overlay.setStyleSheet(
            "color: white; background: rgba(0,0,0,160); padding: 4px 10px; border-radius: 4px;"
        )
        self._lbl_overlay.setVisible(False)
        top.addWidget(self._btn_back)
        top.addWidget(self._lbl_info)
        top.addWidget(self._lbl_overlay)
        root.addLayout(top)

        # ── Splitter: plots | controls ──────────────────────────────────
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        self._glw = pg.GraphicsLayoutWidget()
        self._glw.setBackground("w")
        splitter.addWidget(self._glw)

        ctrl = self._build_control_panel()
        splitter.addWidget(ctrl)
        splitter.setStretchFactor(0, 7)
        splitter.setStretchFactor(1, 3)
        root.addWidget(splitter, stretch=1)

        # ── Bottom stats bar ───────────────────────────────────────────
        bottom = QHBoxLayout()
        self._lbl_stats = QLabel("—")
        self._lbl_stats.setStyleSheet("color: #555;")
        self._btn_export_png = QPushButton("Export PNG")
        self._btn_export_png.setEnabled(False)
        bottom.addWidget(self._lbl_stats, stretch=1)
        bottom.addWidget(self._btn_export_png)
        root.addLayout(bottom)

        # ── Connections ─────────────────────────────────────────────────
        self._btn_back.clicked.connect(self.backRequested)
        self._btn_export_png.clicked.connect(self._export_png)

    def _build_control_panel(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(220)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        # Segmentation group
        grp_seg = QGroupBox("Segmentation")
        form = QFormLayout(grp_seg)
        form.setSpacing(4)

        self._combo_method = QComboBox()
        self._combo_method.addItems(["autocorr", "heelstrike"])
        form.addRow("Method:", self._combo_method)

        self._combo_ref = QComboBox()
        form.addRow("Ref. muscle:", self._combo_ref)

        self._spin_min = QDoubleSpinBox()
        self._spin_min.setRange(0.1, 5.0)
        self._spin_min.setValue(0.4)
        self._spin_min.setSuffix(" s")
        self._spin_min.setSingleStep(0.1)
        form.addRow("Period min:", self._spin_min)

        self._spin_max = QDoubleSpinBox()
        self._spin_max.setRange(0.2, 10.0)
        self._spin_max.setValue(2.5)
        self._spin_max.setSuffix(" s")
        self._spin_max.setSingleStep(0.1)
        form.addRow("Period max:", self._spin_max)

        layout.addWidget(grp_seg)

        # Display group
        grp_disp = QGroupBox("Display")
        form2 = QFormLayout(grp_disp)
        form2.setSpacing(4)

        self._combo_norm = QComboBox()
        self._combo_norm.addItems(["mvc_env95", "task_env95", "off"])
        form2.addRow("Normalize:", self._combo_norm)

        self._chk_individuals = QCheckBox("Show individuals (≤30)")
        form2.addRow(self._chk_individuals)

        layout.addWidget(grp_disp)

        grp_stats = QGroupBox("Cycle Stats")
        stats_layout = QVBoxLayout(grp_stats)
        stats_layout.setContentsMargins(4, 4, 4, 4)
        self._txt_cycle_stats = QTextEdit()
        self._txt_cycle_stats.setReadOnly(True)
        self._txt_cycle_stats.setFixedHeight(170)
        stats_layout.addWidget(self._txt_cycle_stats)
        layout.addWidget(grp_stats)

        layout.addStretch(1)

        # Connect
        self._combo_method.currentTextChanged.connect(self._schedule_segmentation)
        self._combo_ref.currentTextChanged.connect(self._schedule_segmentation)
        self._spin_min.valueChanged.connect(self._schedule_segmentation)
        self._spin_max.valueChanged.connect(self._schedule_segmentation)
        self._combo_norm.currentTextChanged.connect(self._schedule_segmentation)
        self._chk_individuals.toggled.connect(self._redraw_individuals)

        return panel

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_trial(self, trial: Trial) -> None:
        self._trial = trial
        channels = list(trial.channels.keys())
        self._combo_ref.clear()
        self._combo_ref.addItems(channels)
        self._txt_cycle_stats.setHtml("<span style='color:#666;'>No cycles</span>")

    def set_info(self, subject: str, trial_id: str, t_start: float, t_end: float) -> None:
        self._lbl_info.setText(
            f"{subject}/{trial_id}  |  {t_start:.2f} s – {t_end:.2f} s"
        )
        self._lbl_info.setStyleSheet("color: black;")

    def show_loading(self, visible: bool) -> None:
        self._lbl_overlay.setVisible(visible)

    def display_cycles(self, cycle_set: CycleSet) -> None:
        self._cycle_set = cycle_set
        self._build_cycle_plots(cycle_set)
        self._update_cycle_stats(cycle_set)
        self._btn_export_png.setEnabled(cycle_set.n_cycles > 0)
        if cycle_set.n_cycles > 0:
            p95_vals = [
                float(np.percentile(mat.mean(axis=0), 95))
                for mat in cycle_set.cycles.values()
            ]
            scale_hint = float(np.mean(p95_vals)) if p95_vals else 0.0
            self._lbl_stats.setText(
                f"Detected: {cycle_set.n_cycles} cycles  |  "
                f"{cycle_set.mean_duration:.3f} ± {cycle_set.std_duration:.3f} s"
                f"  |  norm={self._combo_norm.currentText()} "
                f"(mean-p95≈{scale_hint:.3f})"
            )
        else:
            self._lbl_stats.setText("No cycles detected — adjust parameters")

    def current_seg_config(self) -> SegConfig:
        return SegConfig(
            method=self._combo_method.currentText(),
            ref_muscle=self._combo_ref.currentText(),
            period_min_s=self._spin_min.value(),
            period_max_s=self._spin_max.value(),
            normalize=self._combo_norm.currentText(),
            show_individuals=self._chk_individuals.isChecked(),
        )

    # ------------------------------------------------------------------
    # Plot building
    # ------------------------------------------------------------------
    def _build_cycle_plots(self, cs: CycleSet) -> None:
        self._glw.clear()
        self._plot_items.clear()

        if cs.n_cycles == 0:
            pi = self._glw.addPlot()
            pi.setTitle("No cycles detected")
            return

        ch_names = list(cs.cycles.keys())
        x = cs.phase_axis          # 0 … 100
        show_ind = self._chk_individuals.isChecked()

        first_pi: pg.PlotItem | None = None
        for row, ch in enumerate(ch_names):
            color = _CHANNEL_COLORS[row % len(_CHANNEL_COLORS)]
            pi = self._glw.addPlot(row=row, col=0)
            pi.showGrid(x=False, y=True, alpha=0.3)
            pi.setLabel("left", ch)
            pi.enableAutoRange(axis="y", enable=False)
            pi.setYRange(0.0, 1.0, padding=0.0)
            pi.setLimits(yMin=0.0, yMax=1.0)
            if row < len(ch_names) - 1:
                pi.getAxis("bottom").setStyle(showValues=False)
            else:
                pi.setLabel("bottom", "Gait cycle (%)")

            if first_pi is None:
                first_pi = pi
            else:
                pi.setXLink(first_pi)

            mat = cs.cycles[ch]         # (N, 101)
            mean = mat.mean(axis=0)
            std  = mat.std(axis=0)

            # ± std fill
            upper = mean + std
            lower = mean - std
            fill = pg.FillBetweenItem(
                pg.PlotDataItem(x, upper),
                pg.PlotDataItem(x, lower),
                brush=pg.mkBrush(
                    *self._hex_to_rgb(color), 60
                ),
            )
            pi.addItem(fill)

            # mean line
            pi.plot(x, mean, pen=pg.mkPen(color, width=2.5))

            # optional individual cycles
            if show_ind and cs.n_cycles > 0:
                self._draw_individuals(pi, mat, x, color)

            self._plot_items.append(pi)

    def _draw_individuals(
        self,
        pi: pg.PlotItem,
        mat: np.ndarray,
        x: np.ndarray,
        color: str,
    ) -> None:
        n = mat.shape[0]
        indices = random.sample(range(n), min(30, n))
        rgb = self._hex_to_rgb(color)
        for idx in indices:
            pi.plot(
                x,
                mat[idx],
                pen=pg.mkPen((*rgb, _INDIVIDUAL_ALPHA), width=1),
            )

    def _redraw_individuals(self) -> None:
        if self._cycle_set is not None:
            self._build_cycle_plots(self._cycle_set)

    # ------------------------------------------------------------------
    def _emit_seg_config(self) -> None:
        self.segConfigChanged.emit(self.current_seg_config())

    def _schedule_segmentation(self, *_args) -> None:
        self._seg_timer.start()

    def _update_cycle_stats(self, cs: CycleSet) -> None:
        if cs.n_cycles == 0 or not cs.cycles:
            self._txt_cycle_stats.setHtml("<span style='color:#666;'>No cycles</span>")
            return

        lines = [
            (
                "<span style='color:#444;'>"
                f"n={cs.n_cycles}, dur={cs.mean_duration:.3f}±{cs.std_duration:.3f}s"
                "</span>"
            )
        ]
        for i, (ch, mat) in enumerate(cs.cycles.items()):
            peak_each = np.max(np.abs(mat), axis=1)
            rms_each = np.sqrt(np.mean(mat ** 2, axis=1))
            color = _CHANNEL_COLORS[i % len(_CHANNEL_COLORS)]
            lines.append(
                f"<span style='color:{color};'>"
                f"{escape(ch)}: peak {peak_each.mean():.3f}±{peak_each.std():.3f}, "
                f"rms {rms_each.mean():.3f}±{rms_each.std():.3f}"
                f"</span>"
            )
        self._txt_cycle_stats.setHtml("<br/>".join(lines))

    def _export_png(self) -> None:
        from PyQt5.QtWidgets import QFileDialog
        from PyQt5.QtGui import QPixmap
        opts = QFileDialog.Options()
        if sys.platform == "darwin":
            opts |= QFileDialog.DontUseNativeDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "Export PNG", "gait_cycles.png", "PNG (*.png)", options=opts
        )
        if path:
            pixmap = self._glw.grab()
            pixmap.save(path)

    @staticmethod
    def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
        h = hex_color.lstrip("#")
        return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))
