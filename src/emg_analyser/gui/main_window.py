from __future__ import annotations
from pathlib import Path

from PyQt5.QtCore import Qt, QSettings
from PyQt5.QtWidgets import QMainWindow, QTabWidget, QWidget

from ..services.session import SessionManager
from ..services.worker import LoadThread, ReprocessThread, SegmentThread
from ..io.registry import detect_adapter
from ..io.base import TrialHandle
from .pages.page1_timeline import Page1Timeline
from .pages.page2_gait import Page2GaitCycle
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

        self._build_ui()
        self._connect_signals()
        self._restore_geometry()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        # Central widget: QTabWidget with two pages
        self._tabs = QTabWidget()
        self._page1 = Page1Timeline()
        self._page2 = Page2GaitCycle()
        self._tabs.addTab(self._page1, "1 · Raw Timeline")
        self._tabs.addTab(self._page2, "2 · Gait Cycle Segmentation")
        self._tabs.setTabEnabled(1, False)  # disabled until a trial is loaded
        self.setCentralWidget(self._tabs)

        # Log dock
        self._log = LogDock(self)
        self.addDockWidget(Qt.BottomDockWidgetArea, self._log)

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

        # Tab switch → auto-trigger segmentation
        self._tabs.currentChanged.connect(self._on_tab_changed)

    # ------------------------------------------------------------------
    # Folder / load
    # ------------------------------------------------------------------
    def _on_folder_requested(self, path: str) -> None:
        root = Path(path)
        adapter = detect_adapter(root)
        if adapter is None:
            self._log.append(f"[WARN] No recognised dataset found in: {path}")
            self._page1.set_path_label(f"(unrecognised) {path}")
            return

        handles = adapter.scan(root)
        if not handles:
            self._log.append(f"[WARN] No trials found in: {path}")
            return

        # Auto-load the first (and typically only) trial
        handle = handles[0]
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
        self._page2.set_trial(trial)
        self._tabs.setTabEnabled(1, True)
        self._trigger_reprocess()

    # ------------------------------------------------------------------
    # Pipeline / reprocess
    # ------------------------------------------------------------------
    def _on_pipeline_changed(self, cfg) -> None:
        self._session.set_pipeline(cfg)
        self._trigger_reprocess()

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

        self._segment_thread = SegmentThread(
            trial,
            time_range,
            self._session.pipeline_cfg,
            self._session.seg_cfg,
            self,
        )
        self._segment_thread.done.connect(self._on_seg_done)
        self._segment_thread.error.connect(
            lambda e: (
                self._page2.show_loading(False),
                self._log.append(f"[ERROR] Segmentation failed: {e}"),
            )
        )
        self._segment_thread.start()

    def _on_seg_done(self, cycle_set) -> None:
        self._page2.show_loading(False)
        self._session.set_cycles(cycle_set)

    # ------------------------------------------------------------------
    # Geometry persistence
    # ------------------------------------------------------------------
    def _restore_geometry(self) -> None:
        s = QSettings("zst", "emg-analyser")
        if s.contains("geometry"):
            self.restoreGeometry(s.value("geometry"))
        if s.contains("windowState"):
            self.restoreState(s.value("windowState"))

    def closeEvent(self, event) -> None:
        s = QSettings("zst", "emg-analyser")
        s.setValue("geometry", self.saveGeometry())
        s.setValue("windowState", self.saveState())
        super().closeEvent(event)
