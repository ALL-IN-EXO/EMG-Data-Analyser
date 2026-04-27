from __future__ import annotations
from pathlib import Path

import pyqtgraph as pg
from PyQt5.QtCore import Qt, QSettings
from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtWidgets import QAction, QApplication, QMainWindow, QTabWidget, QToolBar, QWidget

from ..services.session import SessionManager
from ..services.worker import LoadThread, ReprocessThread, SegmentThread
from ..io.registry import detect_adapter
from ..io.base import TrialHandle
from .pages.page1_timeline import Page1Timeline
from .pages.page2_gait import Page2GaitCycle
from .pages.page3_camargo import Page3Camargo
from .pages.page4_gait120 import Page4Gait120
from .pages.page5_compare import Page5Compare
from .log_dock import LogDock


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("EMG Data Analyser")
        self.resize(1200, 750)

        self._session = SessionManager(self)
        self._load_thread: LoadThread | None = None
        self._reprocess_thread: ReprocessThread | None = None
        self._segment_thread: SegmentThread | None = None
        self._segment_seq = 0
        self._theme_dark = False

        self._build_ui()
        self._connect_signals()
        self._restore_geometry()
        self._restore_theme()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        # Central widget: QTabWidget with two pages
        self._tabs = QTabWidget()
        self._page1 = Page1Timeline()
        self._page2 = Page2GaitCycle()
        self._page3 = Page3Camargo()
        self._page4 = Page4Gait120()
        self._page5 = Page5Compare()
        self._tabs.addTab(self._page1, "1 · Raw Timeline")
        self._tabs.addTab(self._page2, "2 · Gait Cycle Segmentation")
        self._tabs.addTab(self._page3, "3 · Camargo Dataset")
        self._tabs.addTab(self._page4, "4 · Gait120 Dataset")
        self._tabs.addTab(self._page5, "5 · Cross-Dataset Comparison")
        self._tabs.setTabEnabled(1, False)  # disabled until a trial is loaded
        self.setCentralWidget(self._tabs)

        # Log dock
        self._log = LogDock(self)
        self.addDockWidget(Qt.BottomDockWidgetArea, self._log)

        # Theme toolbar
        self._toolbar_view = QToolBar("View", self)
        self._toolbar_view.setMovable(False)
        self.addToolBar(Qt.TopToolBarArea, self._toolbar_view)
        self._act_dark = QAction("Dark Theme", self)
        self._act_dark.setCheckable(True)
        self._toolbar_view.addAction(self._act_dark)

    # ------------------------------------------------------------------
    # Signal connections
    # ------------------------------------------------------------------
    def _connect_signals(self) -> None:
        # Page 1 → MainWindow
        self._page1.folderRequested.connect(self._on_folder_requested)
        self._page1.pipelineChanged.connect(self._on_pipeline_changed)
        self._page1.regionChanged.connect(self._session.set_time_range)
        self._page1.goToSegmentation.connect(self._go_to_page2)

        # Page 2 → MainWindow
        self._page2.backRequested.connect(lambda: self._tabs.setCurrentIndex(0))
        self._page2.segConfigChanged.connect(self._on_seg_config_changed)

        # Session → UI
        self._session.trialLoaded.connect(self._on_trial_loaded)
        self._session.cyclesReady.connect(self._page2.display_cycles)
        self._session.logMessage.connect(self._log.append)

        # Page 3 log
        self._page3.logMessage.connect(self._log.append)

        # Page 4 log
        self._page4.logMessage.connect(self._log.append)

        # Page 5 log + data feeds
        self._page5.logMessage.connect(self._log.append)
        self._page3.dataReady.connect(self._page5.receive_camargo)
        self._page4.dataReady.connect(self._page5.receive_gait120)
        self._session.cyclesReady.connect(
            lambda cs: self._page5.receive_myometrics(cs, self._session.trial)
        )

        # Tab switch → auto-trigger segmentation
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self._act_dark.toggled.connect(self._apply_theme)

    # ------------------------------------------------------------------
    # External log hook
    # ------------------------------------------------------------------
    def append_log(self, message: str) -> None:
        self._log.append(message)

    # ------------------------------------------------------------------
    # Folder / load
    # ------------------------------------------------------------------
    def _on_folder_requested(self, path: str, mvc_path: str) -> None:
        root = Path(path)
        mvc_root = Path(mvc_path)
        adapter = detect_adapter(root)
        if adapter is None:
            self._log.append(f"[WARN] No recognised dataset found in: {path}")
            self._page1.set_path_label(f"(unrecognised) {path}")
            return

        if not mvc_root.is_dir():
            self._log.append(f"[WARN] MVC folder not found: {mvc_path}")
            return
        if not self._looks_like_mvc_folder(mvc_root):
            self._log.append(
                f"[WARN] Selected MVC folder has no Channel_Curves CSV: {mvc_path}"
            )
            return

        handles = adapter.scan(root)
        if not handles:
            self._log.append(f"[WARN] No trials found in: {path}")
            return

        # Auto-load the first (and typically only) trial
        handle = handles[0]
        handle.paths["mvc_dir"] = mvc_root
        self._log.append(f"[INFO] Loading {handle} …")
        self._page1.set_path_label(str(root))

        if self._load_thread and self._load_thread.isRunning():
            self._load_thread.wait(200)

        self._load_thread = LoadThread(adapter, handle, self)
        self._load_thread.loaded.connect(self._session.set_trial)
        self._load_thread.error.connect(
            lambda e: self._log.append(f"[ERROR] Load failed: {e}")
        )
        self._load_thread.start()

    # ------------------------------------------------------------------
    # Trial loaded
    # ------------------------------------------------------------------
    def _on_trial_loaded(self, trial) -> None:
        self._page1.load_trial(trial)
        self._page1.set_cycle_starts([])
        self._page2.set_trial(trial)
        self._tabs.setTabEnabled(1, True)
        self._trigger_reprocess()

    # ------------------------------------------------------------------
    # Pipeline / reprocess
    # ------------------------------------------------------------------
    def _on_pipeline_changed(self, cfg) -> None:
        self._session.set_pipeline(cfg)
        self._trigger_reprocess()
        if self._tabs.currentIndex() == 1:
            self._trigger_segmentation()

    def _trigger_reprocess(self) -> None:
        trial = self._session.trial
        if trial is None:
            return

        if self._reprocess_thread and self._reprocess_thread.isRunning():
            self._reprocess_thread.cancel()
            self._reprocess_thread.wait(100)

        self._reprocess_thread = ReprocessThread(
            trial, self._session.pipeline_cfg, self
        )
        self._reprocess_thread.done.connect(self._page1.update_curves)
        self._reprocess_thread.start()

    # ------------------------------------------------------------------
    # Segmentation
    # ------------------------------------------------------------------
    def _on_tab_changed(self, index: int) -> None:
        if index == 1:
            self._trigger_segmentation()

    def _go_to_page2(self) -> None:
        r = self._page1.current_region()
        if r:
            self._session.set_time_range(r[0], r[1])
        tr = self._session.trial
        if tr and self._session.time_range:
            self._page2.set_info(
                tr.subject,
                tr.trial_id,
                self._session.time_range.t_start,
                self._session.time_range.t_end,
            )
        self._tabs.setCurrentIndex(1)

    def _on_seg_config_changed(self, cfg) -> None:
        self._session.set_seg_config(cfg)
        self._trigger_segmentation()

    def _trigger_segmentation(self) -> None:
        trial = self._session.trial
        time_range = self._session.time_range
        if trial is None or time_range is None:
            return

        if self._segment_thread and self._segment_thread.isRunning():
            self._segment_thread.wait(200)

        self._page2.show_loading(True)
        self._segment_seq += 1
        seq = self._segment_seq

        self._segment_thread = SegmentThread(
            trial,
            time_range,
            self._session.pipeline_cfg,
            self._session.seg_cfg,
            self,
        )
        self._segment_thread.done.connect(
            lambda cycle_set, s=seq: self._on_seg_done(cycle_set, s)
        )
        self._segment_thread.error.connect(
            lambda e, s=seq: self._on_seg_error(e, s)
        )
        self._segment_thread.start()

    def _on_seg_done(self, cycle_set, seq: int) -> None:
        if seq != self._segment_seq:
            return
        self._page2.show_loading(False)
        self._page1.set_cycle_starts(cycle_set.start_times)
        self._session.set_cycles(cycle_set)

    def _on_seg_error(self, err: str, seq: int) -> None:
        if seq != self._segment_seq:
            return
        self._page2.show_loading(False)
        self._log.append(f"[ERROR] Segmentation failed: {err}")

    # ------------------------------------------------------------------
    # Geometry persistence
    # ------------------------------------------------------------------
    def _restore_geometry(self) -> None:
        s = QSettings("zst", "emg-analyser")
        if s.contains("geometry"):
            self.restoreGeometry(s.value("geometry"))
        if s.contains("windowState"):
            self.restoreState(s.value("windowState"))

    def _restore_theme(self) -> None:
        s = QSettings("zst", "emg-analyser")
        dark = bool(s.value("themeDark", False, type=bool))
        self._act_dark.blockSignals(True)
        self._act_dark.setChecked(dark)
        self._act_dark.blockSignals(False)
        self._apply_theme(dark)

    def _apply_theme(self, dark: bool) -> None:
        app = QApplication.instance()
        if app is None:
            return

        if dark:
            palette = QPalette()
            palette.setColor(QPalette.Window, QColor(43, 43, 43))
            palette.setColor(QPalette.WindowText, QColor(230, 230, 230))
            palette.setColor(QPalette.Base, QColor(30, 30, 30))
            palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
            palette.setColor(QPalette.ToolTipBase, QColor(255, 255, 255))
            palette.setColor(QPalette.ToolTipText, QColor(255, 255, 255))
            palette.setColor(QPalette.Text, QColor(220, 220, 220))
            palette.setColor(QPalette.Button, QColor(60, 60, 60))
            palette.setColor(QPalette.ButtonText, QColor(230, 230, 230))
            palette.setColor(QPalette.BrightText, QColor(255, 80, 80))
            palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
            palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
            app.setPalette(palette)
            app.setStyleSheet(
                "QToolTip { color: #fff; background: #2a82da; border: 1px solid #1f5ea8; }"
            )
            pg.setConfigOption("foreground", "#e6e6e6")
        else:
            app.setPalette(app.style().standardPalette())
            app.setStyleSheet("")
            pg.setConfigOption("foreground", "k")

        self._theme_dark = dark
        for page in (self._page1, self._page2, self._page3, self._page4, self._page5):
            if hasattr(page, "set_theme"):
                page.set_theme(dark)

    @staticmethod
    def _looks_like_mvc_folder(path: Path) -> bool:
        if any(path.glob("Channel_Curves-*.csv")):
            return True
        for sub in path.iterdir():
            if sub.is_dir() and any(sub.glob("Channel_Curves-*.csv")):
                return True
        return False

    def closeEvent(self, event) -> None:
        s = QSettings("zst", "emg-analyser")
        s.setValue("geometry", self.saveGeometry())
        s.setValue("windowState", self.saveState())
        s.setValue("themeDark", self._theme_dark)
        super().closeEvent(event)
