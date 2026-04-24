from __future__ import annotations
import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from .gui.main_window import MainWindow


def main() -> None:
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setApplicationName("EMG Data Analyser")
    app.setOrganizationName("zst")
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
