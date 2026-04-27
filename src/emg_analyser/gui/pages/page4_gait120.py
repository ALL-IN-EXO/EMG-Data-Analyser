"""
Page 4 — Gait120 dataset visualisation.

Features:
  · Subject and activity-mode selection
  · Pre-processed EMGs_interpolated data (101-point gait-cycle profiles, MVC-normalised)
  · Single subject  → mean ± std fill + optional individual step traces
  · All subjects    → one mean line per subject + bold global mean
  · Per-channel visibility toggles
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
    QFileDialog,
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

from ...io.gait120_mat import CHANNEL_NAMES, MODES, list_subjects
from ...services.worker import Gait120Thread

_SUBJECT_COLORS = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
]
_CHANNEL_COLORS = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    "#00bcd4", "#ff9800",
]
_MAX_INDIVIDUAL = 30
_DEFAULT_ROOT = "/home/jz7785/ZST/Exo_Dataset/EMG_Public_Data/Gait120_001_to_010"


class Page4Gait120(QWidget):
    """Page 4 — Gait120 dataset viewer."""

    logMessage = pyqtSignal(str)
    dataReady = pyqtSignal(dict)   # emitted after a successful analysis

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._root_path: str = ""
        self._subjects: list[str] = []
        self._analysis_thread: Gait120Thread | None = None
        self._analysis_seq = 0
        self._analysis_started_s = 0.0
        self._plot_items: list[pg.PlotItem] = []
        self._last_result: dict | None = None
        self._muscle_checks: dict[str, QCheckBox] = {}
        self._updating_muscle_checks = False

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

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        self._glw = pg.GraphicsLayoutWidget()
        self._glw.setBackground("w")
        splitter.addWidget(self._glw)

        splitter.addWidget(self._build_control_panel())
        splitter.setStretchFactor(0, 7)
        splitter.setStretchFactor(1, 3)
        root.addWidget(splitter, stretch=1)

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

        # Dataset folder
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

        # Activity mode
        grp_mode = QGroupBox("Activity Mode")
        vm = QVBoxLayout(grp_mode)
        vm.setSpacing(2)
        self._mode_group = QButtonGroup(self)
        self._mode_radios: dict[str, QRadioButton] = {}
        for mode in MODES:
            rb = QRadioButton(mode)
            rb.setEnabled(False)
            self._mode_group.addButton(rb)
            self._mode_radios[mode] = rb
            vm.addWidget(rb)
        self._mode_group.buttonClicked.connect(self._on_mode_changed)
        layout.addWidget(grp_mode)

        # Subject selection
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
        scroll.setMaximumHeight(140)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        vs.addWidget(scroll)
        layout.addWidget(grp_subj)

        # Display options
        grp_disp = QGroupBox("Display")
        vd = QVBoxLayout(grp_disp)
        vd.setSpacing(3)
        self._chk_norm = QCheckBox("Normalize per channel")
        self._chk_norm.setChecked(False)
        self._chk_individual = QCheckBox("Show individual steps")
        self._chk_individual.setChecked(False)
        vd.addWidget(self._chk_norm)
        vd.addWidget(self._chk_individual)
        self._chk_norm.toggled.connect(self._on_display_toggle)
        self._chk_individual.toggled.connect(self._on_display_toggle)
        layout.addWidget(grp_disp)

        # Muscle channel checkboxes
        grp_muscle = QGroupBox("Muscles")
        vmu = QVBoxLayout(grp_muscle)
        vmu.setSpacing(4)
        vmu.setContentsMargins(4, 4, 4, 4)
        btn_row = QHBoxLayout()
        self._btn_muscle_all = QPushButton("All")
        self._btn_muscle_none = QPushButton("None")
        self._btn_muscle_all.setEnabled(False)
        self._btn_muscle_none.setEnabled(False)
        self._btn_muscle_all.clicked.connect(lambda: self._set_all_muscles(True))
        self._btn_muscle_none.clicked.connect(lambda: self._set_all_muscles(False))
        btn_row.addWidget(self._btn_muscle_all)
        btn_row.addWidget(self._btn_muscle_none)
        vmu.addLayout(btn_row)
        self._muscle_scroll_widget = QWidget()
        self._muscle_scroll_layout = QVBoxLayout(self._muscle_scroll_widget)
        self._muscle_scroll_layout.setSpacing(2)
        self._muscle_scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_m = QScrollArea()
        scroll_m.setWidgetResizable(True)
        scroll_m.setWidget(self._muscle_scroll_widget)
        scroll_m.setMaximumHeight(160)
        scroll_m.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        vmu.addWidget(scroll_m)
        layout.addWidget(grp_muscle)

        self._btn_run = QPushButton("Run Analysis")
        self._btn_run.setEnabled(False)
        self._btn_run.clicked.connect(self._on_run)
        layout.addWidget(self._btn_run)

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
            self, "Select Gait120 dataset root",
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
            self._subjects = list_subjects(Path(self._root_path))
            if not self._subjects:
                self.logMessage.emit("[WARN] No Gait120 subjects found (expected S001…S010)")
                self._lbl_status.setText("No subjects found")
                return

            self._populate_subjects()

            first_mode = MODES[0]
            self._mode_radios[first_mode].setChecked(True)
            for rb in self._mode_radios.values():
                rb.setEnabled(True)

            self._btn_run.setEnabled(True)
            self._populate_muscles(CHANNEL_NAMES)

            self.logMessage.emit(
                f"[INFO] Found {len(self._subjects)} subject(s) in {self._root_path}"
            )
            self._lbl_status.setText(
                f"{len(self._subjects)} subject(s) · 7 modes · 12 channels"
            )
            self._lbl_status.setStyleSheet("color: black;")

        except Exception as exc:
            self.logMessage.emit(f"[ERROR] Scan failed: {exc}")

    def _on_mode_changed(self, _btn: QRadioButton) -> None:
        pass  # mode change alone doesn't re-run analysis

    def _populate_subjects(self) -> None:
        for btn in list(self._subj_group.buttons()):
            self._subj_group.removeButton(btn)
        while self._subj_scroll_layout.count():
            item = self._subj_scroll_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        rb_all = QRadioButton("All subjects")
        rb_all.setChecked(True)
        self._subj_group.addButton(rb_all)
        self._subj_scroll_layout.addWidget(rb_all)

        for subj in self._subjects:
            rb = QRadioButton(subj)
            self._subj_group.addButton(rb)
            self._subj_scroll_layout.addWidget(rb)

        self._subj_scroll_layout.addStretch(1)

    def _selected_mode(self) -> str:
        for mode, rb in self._mode_radios.items():
            if rb.isChecked():
                return mode
        return MODES[0]

    def _selected_subjects(self) -> list[str]:
        btn = self._subj_group.checkedButton()
        if btn is None or btn.text() == "All subjects":
            return list(self._subjects)
        return [btn.text()]

    def _on_run(self) -> None:
        mode = self._selected_mode()
        subjects = self._selected_subjects()
        if not subjects:
            return

        if self._analysis_thread and self._analysis_thread.isRunning():
            self._analysis_thread.wait(300)

        n = len(subjects)
        self._lbl_progress.setText(f"⏳  Loading…  0 / {n}")
        self._lbl_progress.setVisible(True)
        self._btn_run.setEnabled(False)
        self._analysis_started_s = time.perf_counter()
        self._analysis_seq += 1
        seq = self._analysis_seq

        self._analysis_thread = Gait120Thread(self._root_path, subjects, mode, self)
        self._analysis_thread.progress.connect(self._on_progress)
        self._analysis_thread.done.connect(lambda r, s=seq: self._on_done(r, s))
        self._analysis_thread.error.connect(lambda e, s=seq: self._on_error(e, s))
        self._analysis_thread.logMessage.connect(self.logMessage)
        self._analysis_thread.start()

    def _on_progress(self, done: int, total: int) -> None:
        self._lbl_progress.setText(f"⏳  Loading…  {done} / {total}")

    def _on_done(self, result: dict, seq: int) -> None:
        if seq != self._analysis_seq:
            return
        self._lbl_progress.setVisible(False)
        self._btn_run.setEnabled(True)
        elapsed_ms = int((time.perf_counter() - self._analysis_started_s) * 1000)
        self._lbl_status.setText(
            f"Updated in {elapsed_ms} ms  ·  mode: {result.get('mode', '?')}"
        )
        self._lbl_status.setStyleSheet("color: #444;")
        self._last_result = result
        self._populate_muscles(result.get("channels", []))
        self._build_plots(result)
        self.dataReady.emit(result)

    def _on_error(self, err: str, seq: int) -> None:
        if seq != self._analysis_seq:
            return
        self._lbl_progress.setVisible(False)
        self._btn_run.setEnabled(True)
        self._lbl_status.setText("Analysis failed")
        self._lbl_status.setStyleSheet("color: #b22222;")
        self.logMessage.emit(f"[ERROR] {err}")

    def _on_display_toggle(self, *_args) -> None:
        if self._last_result is not None:
            self._build_plots(self._last_result)

    def _populate_muscles(self, channels: list[str]) -> None:
        prev = {ch: cb.isChecked() for ch, cb in self._muscle_checks.items()}
        while self._muscle_scroll_layout.count():
            item = self._muscle_scroll_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._muscle_checks.clear()

        self._updating_muscle_checks = True
        for ch in channels:
            cb = QCheckBox(ch)
            cb.setChecked(prev.get(ch, True))
            cb.toggled.connect(self._on_muscle_toggled)
            self._muscle_scroll_layout.addWidget(cb)
            self._muscle_checks[ch] = cb
        self._muscle_scroll_layout.addStretch(1)
        self._updating_muscle_checks = False

        has = bool(channels)
        self._btn_muscle_all.setEnabled(has)
        self._btn_muscle_none.setEnabled(has)

    def _set_all_muscles(self, checked: bool) -> None:
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

        by_subject: dict[str, dict[str, np.ndarray]] = result.get("by_subject", {})
        channels: list[str] = result.get("channels", [])
        selected = self._selected_channels(channels)

        if not by_subject or not channels:
            pi = self._glw.addPlot()
            pi.setTitle("No data — check dataset path and mode")
            self._lbl_stats.setText("No data")
            self._btn_export.setEnabled(False)
            return
        if not selected:
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
        n_rows = int(np.ceil(len(selected) / n_cols))

        for idx, ch in enumerate(selected):
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
            if not normalize:
                pi.setLabel("left", "MVC fraction")
                pi.enableAutoRange(axis="y", enable=True)
            else:
                pi.enableAutoRange(axis="y", enable=False)
                pi.setYRange(0.0, 1.0, padding=0.0)
                pi.setLimits(yMin=0.0, yMax=1.0)

            if is_single:
                self._plot_single(pi, by_subject[subjects[0]], ch, x, idx, normalize, show_individual)
            else:
                self._plot_all(pi, by_subject, ch, x, subjects, normalize)

            self._plot_items.append(pi)

        total_steps = sum(
            next(iter(d.values())).shape[0] for d in by_subject.values() if d
        )
        mode = result.get("mode", "?")
        norm_str = "on" if normalize else "off"
        self._lbl_stats.setText(
            f"{len(subjects)} subject(s)  ·  {total_steps} steps  ·  "
            f"mode={mode}  ·  muscles={len(selected)}  ·  norm={norm_str}"
        )
        self._btn_export.setEnabled(True)

    def _plot_single(
        self,
        pi: pg.PlotItem,
        subj_data: dict[str, np.ndarray],
        ch: str,
        x: np.ndarray,
        ch_idx: int,
        normalize: bool,
        show_individual: bool,
    ) -> None:
        if ch not in subj_data:
            return
        mat = self._maybe_normalize(subj_data[ch], normalize)
        if mat.shape[0] == 0:
            return
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
        if show_individual:
            n = mat.shape[0]
            step = max(1, int(np.ceil(n / _MAX_INDIVIDUAL)))
            for i in range(0, n, step):
                pi.plot(x, mat[i], pen=pg.mkPen((*rgb, 50), width=1.0))
        pi.plot(x, mean, pen=pg.mkPen(color, width=2.5))

    def _plot_all(
        self,
        pi: pg.PlotItem,
        by_subject: dict[str, dict[str, np.ndarray]],
        ch: str,
        x: np.ndarray,
        subjects: list[str],
        normalize: bool,
    ) -> None:
        all_means: list[np.ndarray] = []
        for i, subj in enumerate(subjects):
            data = by_subject[subj]
            if ch not in data or data[ch].shape[0] == 0:
                continue
            mean = self._maybe_normalize(data[ch], normalize).mean(axis=0)
            all_means.append(mean)
            color = _SUBJECT_COLORS[i % len(_SUBJECT_COLORS)]
            pi.plot(x, mean, pen=pg.mkPen(color, width=1.5))
        if len(all_means) > 1:
            pi.plot(x, np.mean(all_means, axis=0), pen=pg.mkPen("k", width=3.0))

    @staticmethod
    def _maybe_normalize(mat: np.ndarray, enabled: bool) -> np.ndarray:
        if not enabled:
            return mat
        peak = float(np.max(mat)) if mat.size else 0.0
        return mat / peak if peak > 1e-12 else mat

    # ------------------------------------------------------------------
    def _export_png(self) -> None:
        opts = self._dialog_options()
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export PNG",
            "gait120_cycles.png",
            "PNG (*.png)",
            options=opts,
        )
        if path:
            self._glw.grab().save(path)

    @staticmethod
    def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
        h = hex_color.lstrip("#")
        return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))
