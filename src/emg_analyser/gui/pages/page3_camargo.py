"""
Page 3 — Camargo 2021 public dataset visualisation.

Features:
  · Activity selection (treadmill / levelground / ramp / stair)
  · Interactive filter chain (highpass / rectify / smoothing)
  · Single subject → mean ± std per channel (+ optional individual cycles)
  · All subjects  → one mean line per subject + bold global mean
  · Heel-strike segmentation with autocorr fallback
  · Per-channel normalization toggle
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ...io.camargo_adapter import CamargoAdapter
from ...io.base import TrialHandle
from ...model.cycles import CycleSet
from ...model.pipeline import PipelineConfig, SegConfig
from ...services.worker import CamargoThread

_DEFAULT_ROOT = "/home/jz7785/ZST/Exo_Dataset/EMG_Public_Data/Aaron/Camargo2021"

# 20 perceptually distinct colors for multi-subject overlay
_SUBJECT_COLORS = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    "#aec7e8", "#ffbb78", "#98df8a", "#ff9896", "#c5b0d5",
    "#c49c94", "#f7b6d2", "#c7c7c7", "#dbdb8d", "#9edae5",
]

# Per-channel colors for single-subject style (similar to the reference figure)
_CHANNEL_COLORS = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    "#00bcd4", "#ff9800",
]
_MAX_INDIVIDUAL_TRACES = 30


class Page3Camargo(QWidget):
    """Page 3 — Camargo 2021 dataset viewer."""

    logMessage = pyqtSignal(str)
    dataReady = pyqtSignal(dict)   # emitted after a successful analysis; includes "mode" key

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._adapter = CamargoAdapter()
        self._root_path: str = ""
        self._all_handles: list[TrialHandle] = []
        self._mode_to_subjects: dict[str, list[str]] = {}
        self._analysis_thread: CamargoThread | None = None
        self._analysis_seq = 0
        self._plot_items: list[pg.PlotItem] = []
        self._last_result: dict | None = None
        self._muscle_checks: dict[str, QCheckBox] = {}
        self._updating_muscle_checks = False
        self._analysis_started_s = 0.0

        self._build_ui()
        self._apply_default_path()

    def _apply_default_path(self) -> None:
        if Path(_DEFAULT_ROOT).is_dir():
            self._root_path = _DEFAULT_ROOT
            short = "…" + _DEFAULT_ROOT[-37:] if len(_DEFAULT_ROOT) > 40 else _DEFAULT_ROOT
            self._lbl_folder.setText(short)
            self._btn_scan.setEnabled(True)
            self._lbl_status.setText("Press 'Scan Dataset' to load structure")
            self._lbl_status.setStyleSheet("color: #555; font-style: normal;")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # Top bar: status + progress overlay
        top = QHBoxLayout()
        self._lbl_status = QLabel("No dataset loaded")
        self._lbl_status.setStyleSheet("color: grey; font-style: italic;")
        self._lbl_status.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._lbl_progress = QLabel("")
        self._lbl_progress.setStyleSheet(
            "color: white; background: rgba(0,0,0,160);"
            " padding: 4px 10px; border-radius: 4px;"
        )
        self._lbl_progress.setVisible(False)
        top.addWidget(self._lbl_status)
        top.addWidget(self._lbl_progress)
        root.addLayout(top)

        # Main splitter: right plots | left controls
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

        # Bottom stats + export
        bottom = QHBoxLayout()
        self._lbl_stats = QLabel("—")
        self._lbl_stats.setStyleSheet("color: #555;")
        self._btn_export = QPushButton("Export PNG")
        self._btn_export.setEnabled(False)
        self._btn_export.clicked.connect(self._export_png)
        bottom.addWidget(self._lbl_stats, stretch=1)
        bottom.addWidget(self._btn_export)
        root.addLayout(bottom)

    def _build_control_panel(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(260)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        # -- Dataset folder --
        grp_folder = QGroupBox("Dataset")
        vf = QVBoxLayout(grp_folder)
        vf.setSpacing(4)
        row = QHBoxLayout()
        self._lbl_folder = QLabel("(none)")
        self._lbl_folder.setWordWrap(True)
        self._lbl_folder.setStyleSheet("font-size: 10px; color: #555;")
        row.addWidget(self._lbl_folder, stretch=1)
        self._btn_browse = QPushButton("📁")
        self._btn_browse.setFixedWidth(32)
        self._btn_browse.clicked.connect(self._on_browse)
        row.addWidget(self._btn_browse)
        vf.addLayout(row)
        self._btn_scan = QPushButton("Scan Dataset")
        self._btn_scan.setEnabled(False)
        self._btn_scan.clicked.connect(self._on_scan)
        vf.addWidget(self._btn_scan)
        layout.addWidget(grp_folder)

        # -- Activity --
        grp_activity = QGroupBox("Activity")
        va = QVBoxLayout(grp_activity)
        va.setSpacing(2)
        self._mode_group = QButtonGroup(self)
        self._mode_radios: dict[str, QRadioButton] = {}
        for mode in ("treadmill", "levelground", "ramp", "stair"):
            rb = QRadioButton(mode)
            rb.setEnabled(False)
            self._mode_group.addButton(rb)
            self._mode_radios[mode] = rb
            va.addWidget(rb)
        self._mode_group.buttonClicked.connect(self._on_mode_changed)
        layout.addWidget(grp_activity)

        # -- Subject (scrollable radio list) --
        grp_subj = QGroupBox("Subject")
        vs = QVBoxLayout(grp_subj)
        vs.setSpacing(2)
        vs.setContentsMargins(4, 4, 4, 4)
        self._subj_group = QButtonGroup(self)
        self._subj_scroll_widget = QWidget()
        self._subj_scroll_layout = QVBoxLayout(self._subj_scroll_widget)
        self._subj_scroll_layout.setSpacing(2)
        self._subj_scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._subj_scroll_widget)
        scroll.setMaximumHeight(160)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        vs.addWidget(scroll)
        layout.addWidget(grp_subj)

        # -- Segmentation --
        grp_seg = QGroupBox("Segmentation")
        form = QFormLayout(grp_seg)
        form.setSpacing(4)
        self._combo_method = QComboBox()
        self._combo_method.addItems(["heelstrike", "autocorr"])
        self._combo_method.setCurrentText("heelstrike")
        form.addRow("Method:", self._combo_method)
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

        # -- Filter chain (matches gait_cycles.py logic) --
        grp_filter = QGroupBox("Filter Chain")
        ff = QFormLayout(grp_filter)
        ff.setSpacing(4)

        self._chk_rectify = QCheckBox("Rectify |x|")
        self._chk_rectify.setChecked(True)
        ff.addRow(self._chk_rectify)

        self._spin_hp = QDoubleSpinBox()
        self._spin_hp.setRange(0.0, 50.0)
        self._spin_hp.setValue(0.0)
        self._spin_hp.setSuffix(" Hz")
        self._spin_hp.setSingleStep(1.0)
        ff.addRow("Highpass:", self._spin_hp)

        self._combo_smooth = QComboBox()
        self._combo_smooth.addItems(["lowpass", "movavg", "rms", "none"])
        ff.addRow("Smoothing:", self._combo_smooth)

        self._spin_cutoff = QDoubleSpinBox()
        self._spin_cutoff.setRange(0.5, 30.0)
        self._spin_cutoff.setValue(6.0)
        self._spin_cutoff.setSuffix(" Hz")
        self._spin_cutoff.setSingleStep(0.5)
        ff.addRow("Cutoff:", self._spin_cutoff)

        self._spin_window = QDoubleSpinBox()
        self._spin_window.setRange(5.0, 500.0)
        self._spin_window.setValue(50.0)
        self._spin_window.setSuffix(" ms")
        self._spin_window.setSingleStep(5.0)
        ff.addRow("Window:", self._spin_window)
        layout.addWidget(grp_filter)

        # -- Display --
        grp_display = QGroupBox("Display")
        vd = QVBoxLayout(grp_display)
        vd.setSpacing(3)
        self._chk_norm = QCheckBox("Normalize per channel")
        self._chk_norm.setChecked(True)
        self._chk_individual = QCheckBox("Show individual cycles")
        self._chk_individual.setChecked(False)
        vd.addWidget(self._chk_norm)
        vd.addWidget(self._chk_individual)
        self._btn_reset = QPushButton("Reset")
        vd.addWidget(self._btn_reset)
        layout.addWidget(grp_display)

        # -- Muscles --
        grp_muscle = QGroupBox("Muscles")
        vm = QVBoxLayout(grp_muscle)
        vm.setSpacing(4)
        vm.setContentsMargins(4, 4, 4, 4)

        btn_row = QHBoxLayout()
        self._btn_muscle_all = QPushButton("All")
        self._btn_muscle_none = QPushButton("None")
        self._btn_muscle_all.setEnabled(False)
        self._btn_muscle_none.setEnabled(False)
        self._btn_muscle_all.clicked.connect(lambda: self._set_all_muscles(True))
        self._btn_muscle_none.clicked.connect(lambda: self._set_all_muscles(False))
        btn_row.addWidget(self._btn_muscle_all)
        btn_row.addWidget(self._btn_muscle_none)
        vm.addLayout(btn_row)

        self._muscle_scroll_widget = QWidget()
        self._muscle_scroll_layout = QVBoxLayout(self._muscle_scroll_widget)
        self._muscle_scroll_layout.setSpacing(2)
        self._muscle_scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_m = QScrollArea()
        scroll_m.setWidgetResizable(True)
        scroll_m.setWidget(self._muscle_scroll_widget)
        scroll_m.setMaximumHeight(160)
        scroll_m.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        vm.addWidget(scroll_m)
        layout.addWidget(grp_muscle)

        # -- Load & Analyze --
        self._btn_load = QPushButton("Run Analysis")
        self._btn_load.setEnabled(False)
        self._btn_load.clicked.connect(self._on_load_analyze)
        layout.addWidget(self._btn_load)
        self._combo_smooth.currentTextChanged.connect(self._on_smoothing_changed)

        self._chk_norm.toggled.connect(self._on_display_toggle)
        self._chk_individual.toggled.connect(self._on_display_toggle)
        self._btn_reset.clicked.connect(self._on_reset_controls)
        self._on_smoothing_changed(self._combo_smooth.currentText())

        layout.addStretch(1)
        return panel

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    @staticmethod
    def _dialog_options() -> QFileDialog.Options:
        opts = QFileDialog.Options()
        if sys.platform == "darwin":
            opts |= QFileDialog.DontUseNativeDialog
        return opts

    def _on_browse(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Select Camargo dataset root",
            self._root_path or _DEFAULT_ROOT,
            options=self._dialog_options(),
        )
        if path:
            self._root_path = path
            short = path if len(path) <= 40 else "…" + path[-37:]
            self._lbl_folder.setText(short)
            self._btn_scan.setEnabled(True)
            self._lbl_status.setText("Press 'Scan Dataset' to load structure")
            self._lbl_status.setStyleSheet("color: #555; font-style: normal;")

    def _on_scan(self) -> None:
        try:
            self._last_result = None
            self._populate_muscles([])
            root = Path(self._root_path)
            self.logMessage.emit(f"[INFO] Scanning {root} …")
            self._all_handles = self._adapter.scan(root)
            if not self._all_handles:
                self.logMessage.emit("[WARN] No Camargo trials found")
                self._lbl_status.setText("No trials found in selected folder")
                return

            # Build mode → unique subjects mapping
            self._mode_to_subjects = {}
            for h in self._all_handles:
                mode = str(h.paths.get("mode", ""))
                self._mode_to_subjects.setdefault(mode, [])
                if h.subject not in self._mode_to_subjects[mode]:
                    self._mode_to_subjects[mode].append(h.subject)

            # Enable mode radios for found activities
            first_mode: str | None = None
            for mode, rb in self._mode_radios.items():
                has = mode in self._mode_to_subjects
                rb.setEnabled(has)
                if has and first_mode is None:
                    first_mode = mode

            if first_mode:
                self._mode_radios[first_mode].setChecked(True)
                self._populate_subjects(first_mode)
                self._btn_load.setEnabled(True)

            modes_found = list(self._mode_to_subjects.keys())
            self.logMessage.emit(
                f"[INFO] Found {len(self._all_handles)} trials · "
                f"{len(modes_found)} activit(ies)"
            )
            self._lbl_status.setText(
                f"{len(self._all_handles)} trials · "
                f"{len(modes_found)} activit(ies) · "
                f"{sum(len(v) for v in self._mode_to_subjects.values())} subject-modes"
            )
            self._lbl_status.setStyleSheet("color: black;")

        except Exception as exc:
            self.logMessage.emit(f"[ERROR] Scan failed: {exc}")

    def _on_mode_changed(self, btn: QRadioButton) -> None:
        self._populate_subjects(btn.text())

    def _populate_subjects(self, mode: str) -> None:
        # Remove old buttons from group and layout
        for btn in list(self._subj_group.buttons()):
            self._subj_group.removeButton(btn)

        while self._subj_scroll_layout.count():
            item = self._subj_scroll_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        subjects = self._mode_to_subjects.get(mode, [])

        rb_all = QRadioButton("All subjects")
        rb_all.setChecked(True)
        self._subj_group.addButton(rb_all)
        self._subj_scroll_layout.addWidget(rb_all)

        for subj in subjects:
            rb = QRadioButton(subj)
            self._subj_group.addButton(rb)
            self._subj_scroll_layout.addWidget(rb)

        self._subj_scroll_layout.addStretch(1)

    def _selected_mode(self) -> str | None:
        for mode, rb in self._mode_radios.items():
            if rb.isChecked():
                return mode
        return None

    def _selected_subject(self) -> str | None:
        """Returns subject name or None for 'all subjects'."""
        btn = self._subj_group.checkedButton()
        if btn is None:
            return None
        text = btn.text()
        return None if text == "All subjects" else text

    def _current_pipeline_cfg(self) -> PipelineConfig:
        return PipelineConfig(
            highpass_hz=self._spin_hp.value(),
            rectify=self._chk_rectify.isChecked(),
            smoothing=self._combo_smooth.currentText(),
            smoothing_cutoff_hz=self._spin_cutoff.value(),
            smoothing_window_ms=self._spin_window.value(),
        )

    def _current_seg_cfg(self) -> SegConfig:
        # Keep raw cycle amplitudes here; per-channel normalization is a display toggle.
        return SegConfig(
            method=self._combo_method.currentText(),
            period_min_s=self._spin_min.value(),
            period_max_s=self._spin_max.value(),
            normalize="off",
        )

    def _on_load_analyze(self) -> None:
        mode = self._selected_mode()
        if mode is None:
            return

        subject = self._selected_subject()
        handles = [
            h for h in self._all_handles
            if h.paths.get("mode") == mode
            and (subject is None or h.subject == subject)
        ]
        if not handles:
            self.logMessage.emit("[WARN] No handles match current selection")
            return

        pipeline_cfg = self._current_pipeline_cfg()
        seg_cfg = self._current_seg_cfg()

        if self._analysis_thread and self._analysis_thread.isRunning():
            self._analysis_thread.wait(300)

        n = len(handles)
        self._lbl_progress.setText(f"⏳  Analysing…  0 / {n}")
        self._lbl_progress.setVisible(True)
        self._btn_load.setEnabled(False)
        self._analysis_started_s = time.perf_counter()
        self._analysis_seq += 1
        seq = self._analysis_seq

        self._analysis_thread = CamargoThread(
            self._adapter, handles, pipeline_cfg, seg_cfg, self
        )
        self._analysis_thread.progress.connect(self._on_progress)
        self._analysis_thread.done.connect(
            lambda r, s=seq: self._on_done(r, s)
        )
        self._analysis_thread.error.connect(
            lambda e, s=seq: self._on_error(e, s)
        )
        self._analysis_thread.logMessage.connect(self.logMessage)
        self._analysis_thread.start()

    def _on_progress(self, done: int, total: int) -> None:
        self._lbl_progress.setText(f"⏳  Analysing…  {done} / {total}")

    def _on_done(self, result: dict, seq: int) -> None:
        if seq != self._analysis_seq:
            return
        self._lbl_progress.setVisible(False)
        self._btn_load.setEnabled(True)
        elapsed_ms = int((time.perf_counter() - self._analysis_started_s) * 1000)
        self._lbl_status.setText(f"Updated in {elapsed_ms} ms")
        self._lbl_status.setStyleSheet("color: #444;")
        self._last_result = result
        self._populate_muscles(result.get("channels", []))
        self._build_plots(result)
        self.dataReady.emit({**result, "mode": self._selected_mode() or ""})

    def _on_error(self, err: str, seq: int) -> None:
        if seq != self._analysis_seq:
            return
        self._lbl_progress.setVisible(False)
        self._btn_load.setEnabled(True)
        self._lbl_status.setText("Analysis failed")
        self._lbl_status.setStyleSheet("color: #b22222;")
        self.logMessage.emit(f"[ERROR] Analysis failed: {err}")

    def _on_smoothing_changed(self, mode: str) -> None:
        self._spin_cutoff.setVisible(mode == "lowpass")
        self._spin_window.setVisible(mode in ("movavg", "rms"))

    def _on_display_toggle(self, *_args) -> None:
        if self._last_result is not None:
            self._build_plots(self._last_result)

    def _on_reset_controls(self) -> None:
        self._combo_method.setCurrentText("heelstrike")
        self._spin_min.setValue(0.4)
        self._spin_max.setValue(2.5)

        self._chk_rectify.setChecked(True)
        self._spin_hp.setValue(0.0)
        self._combo_smooth.setCurrentText("lowpass")
        self._spin_cutoff.setValue(6.0)
        self._spin_window.setValue(50.0)

        self._chk_norm.setChecked(True)
        self._chk_individual.setChecked(False)

    def _populate_muscles(self, channels: list[str]) -> None:
        prev_checked = {
            ch: cb.isChecked()
            for ch, cb in self._muscle_checks.items()
        }

        while self._muscle_scroll_layout.count():
            item = self._muscle_scroll_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._muscle_checks.clear()

        self._updating_muscle_checks = True
        for ch in channels:
            cb = QCheckBox(ch)
            cb.setChecked(prev_checked.get(ch, True))
            cb.toggled.connect(self._on_muscle_toggled)
            self._muscle_scroll_layout.addWidget(cb)
            self._muscle_checks[ch] = cb
        self._muscle_scroll_layout.addStretch(1)
        self._updating_muscle_checks = False

        has_channels = len(channels) > 0
        self._btn_muscle_all.setEnabled(has_channels)
        self._btn_muscle_none.setEnabled(has_channels)

    def _set_all_muscles(self, checked: bool) -> None:
        if not self._muscle_checks:
            return
        self._updating_muscle_checks = True
        for cb in self._muscle_checks.values():
            cb.setChecked(checked)
        self._updating_muscle_checks = False
        self._on_muscle_toggled()

    def _on_muscle_toggled(self, *_args) -> None:
        if self._updating_muscle_checks:
            return
        if self._last_result is not None:
            self._build_plots(self._last_result)

    def _selected_channels(self, channels: list[str]) -> list[str]:
        if not self._muscle_checks:
            return channels
        return [ch for ch in channels if self._muscle_checks.get(ch, None) and self._muscle_checks[ch].isChecked()]

    # ------------------------------------------------------------------
    # Plot building
    # ------------------------------------------------------------------
    def _build_plots(self, result: dict) -> None:
        self._glw.clear()
        self._plot_items.clear()

        by_subject: dict[str, CycleSet] = result.get("by_subject", {})
        channels: list[str] = result.get("channels", [])
        selected_channels = self._selected_channels(channels)

        if not by_subject or not channels:
            pi = self._glw.addPlot()
            pi.setTitle("No cycles detected — check dataset path and parameters")
            self._lbl_stats.setText("No cycles detected")
            self._btn_export.setEnabled(False)
            return
        if not selected_channels:
            pi = self._glw.addPlot()
            pi.setTitle("No muscles selected")
            self._lbl_stats.setText("No muscles selected")
            self._btn_export.setEnabled(False)
            return

        subjects = list(by_subject.keys())
        x = np.linspace(0, 100, 101)
        is_single = len(subjects) == 1
        normalize = self._chk_norm.isChecked()
        show_individual = self._chk_individual.isChecked() and is_single
        n_cols = 3

        n_rows = int(np.ceil(len(selected_channels) / n_cols))
        for idx, ch in enumerate(selected_channels):
            row = idx // n_cols
            col = idx % n_cols
            pi = self._glw.addPlot(row=row, col=col)
            pi.setTitle(ch, size="9pt")
            pi.showGrid(x=True, y=True, alpha=0.15)
            pi.setXRange(0, 100, padding=0.0)
            if row == n_rows - 1:
                pi.setLabel("bottom", "Gait cycle (%)")
            else:
                pi.getAxis("bottom").setStyle(showValues=False)
            if normalize:
                pi.enableAutoRange(axis="y", enable=False)
                pi.setYRange(0.0, 1.0, padding=0.0)
                pi.setLimits(yMin=0.0, yMax=1.0)

            if is_single:
                self._plot_single_subject(
                    pi,
                    by_subject[subjects[0]],
                    ch,
                    x,
                    idx,
                    normalize,
                    show_individual,
                )
            else:
                self._plot_all_subjects(
                    pi,
                    by_subject,
                    ch,
                    x,
                    subjects,
                    normalize,
                )

            self._plot_items.append(pi)

        # Stats bar
        total_cycles = sum(cs.n_cycles for cs in by_subject.values())
        all_durs = np.concatenate([cs.durations for cs in by_subject.values()])
        mean_dur = float(all_durs.mean()) if len(all_durs) else 0.0
        std_dur = float(all_durs.std()) if len(all_durs) else 0.0
        norm = "on" if normalize else "off"
        indiv = "on" if show_individual else "off"
        self._lbl_stats.setText(
            f"{len(subjects)} subject(s)  ·  {total_cycles} cycles  ·  "
            f"{mean_dur:.3f} ± {std_dur:.3f} s  ·  "
            f"muscles={len(selected_channels)}  ·  norm={norm}  ·  indiv={indiv}"
        )
        self._btn_export.setEnabled(True)

    def _plot_single_subject(
        self,
        pi: pg.PlotItem,
        cs: CycleSet,
        ch: str,
        x: np.ndarray,
        ch_idx: int,
        normalize: bool,
        show_individual: bool,
    ) -> None:
        if ch not in cs.cycles:
            return
        mat = self._normalize_channel(cs.cycles[ch], normalize)
        mean = mat.mean(axis=0)
        std = mat.std(axis=0)
        color = _CHANNEL_COLORS[ch_idx % len(_CHANNEL_COLORS)]
        rgb = self._hex_to_rgb(color)
        fill = pg.FillBetweenItem(
            pg.PlotDataItem(x, mean + std),
            pg.PlotDataItem(x, mean - std),
            brush=pg.mkBrush(*rgb, 60),
        )
        pi.addItem(fill)
        if show_individual and mat.shape[0] > 0:
            self._draw_individual_cycles(pi, mat, x, color)
        pi.plot(x, mean, pen=pg.mkPen(color, width=2.5))

    def _plot_all_subjects(
        self,
        pi: pg.PlotItem,
        by_subject: dict[str, CycleSet],
        ch: str,
        x: np.ndarray,
        subjects: list[str],
        normalize: bool,
    ) -> None:
        all_means: list[np.ndarray] = []
        for i, subj in enumerate(subjects):
            cs = by_subject[subj]
            if ch not in cs.cycles:
                continue
            mean = self._normalize_channel(cs.cycles[ch], normalize).mean(axis=0)
            all_means.append(mean)
            color = _SUBJECT_COLORS[i % len(_SUBJECT_COLORS)]
            pi.plot(x, mean, pen=pg.mkPen(color, width=1.5))

        if len(all_means) > 1:
            global_mean = np.mean(all_means, axis=0)
            pi.plot(x, global_mean, pen=pg.mkPen("k", width=3.0))

    def _draw_individual_cycles(
        self,
        pi: pg.PlotItem,
        mat: np.ndarray,
        x: np.ndarray,
        color: str,
    ) -> None:
        n_cycles = mat.shape[0]
        step = max(1, int(np.ceil(n_cycles / _MAX_INDIVIDUAL_TRACES)))
        rgb = self._hex_to_rgb(color)
        for idx in range(0, n_cycles, step):
            pi.plot(
                x,
                mat[idx],
                pen=pg.mkPen((*rgb, 55), width=1.0),
            )

    @staticmethod
    def _normalize_channel(mat: np.ndarray, enabled: bool) -> np.ndarray:
        if not enabled:
            return mat
        peak = float(np.max(mat)) if mat.size else 0.0
        if peak <= 1e-12:
            return mat
        return mat / peak

    # ------------------------------------------------------------------
    def _export_png(self) -> None:
        opts = self._dialog_options()
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export PNG",
            "camargo_cycles.png",
            "PNG (*.png)",
            options=opts,
        )
        if path:
            self._glw.grab().save(path)

    @staticmethod
    def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
        h = hex_color.lstrip("#")
        return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))
