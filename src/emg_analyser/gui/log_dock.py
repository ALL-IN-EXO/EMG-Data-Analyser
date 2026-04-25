from __future__ import annotations
from datetime import datetime
from PyQt5.QtWidgets import QDockWidget, QPlainTextEdit, QWidget
from PyQt5.QtCore import Qt


class LogDock(QDockWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Log", parent)
        self.setAllowedAreas(Qt.BottomDockWidgetArea)
        self.setFeatures(
            QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable
        )
        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setMaximumBlockCount(500)
        self._text.setFixedHeight(90)
        self.setWidget(self._text)

    def append(self, msg: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._text.appendPlainText(f"[{timestamp}] {msg}")
