from __future__ import annotations

import os
import platform
import subprocess
import sys


def _configure_macos_runtime() -> None:
    """Set conservative Qt defaults on macOS before importing PyQt."""
    if sys.platform != "darwin":
        return

    # Avoid unstable native integrations on mixed Python/Qt installs.
    os.environ.setdefault("QT_OPENGL", "software")
    os.environ.setdefault("QT_QUICK_BACKEND", "software")
    os.environ.setdefault("QT_MAC_WANTS_LAYER", "1")
    os.environ.setdefault("PYQTGRAPH_QT_LIB", "PyQt5")


def _collect_crash_risk_warnings() -> list[str]:
    """Return startup warnings for macOS environments with higher crash risk."""
    warnings: list[str] = []
    if sys.platform != "darwin":
        return warnings

    if sys.version_info >= (3, 13):
        warnings.append(
            "Python 3.13 + PyQt5 can be unstable on some macOS setups. "
            "If crashes persist, use Python 3.12 for this app."
        )

    if platform.machine().lower() == "x86_64":
        try:
            out = subprocess.check_output(
                ["sysctl", "-n", "hw.optional.arm64"], text=True
            ).strip()
        except Exception:
            out = "0"
        if out == "1":
            warnings.append(
                "Detected x86_64 Python on Apple Silicon (Rosetta). "
                "This setup may crash with PyQt5. Prefer arm64 Python "
                "(usually /opt/homebrew/bin/python3)."
            )

    return warnings


def _print_startup_warnings(warnings: list[str]) -> None:
    for msg in warnings:
        print(f"[WARN] {msg}", file=sys.stderr)


def main() -> None:
    _configure_macos_runtime()
    startup_warnings = _collect_crash_risk_warnings()
    _print_startup_warnings(startup_warnings)

    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QApplication, QMessageBox

    from .gui.main_window import MainWindow

    if hasattr(Qt, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, "AA_UseHighDpiPixmaps"):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    if sys.platform == "darwin":
        if hasattr(Qt, "AA_UseSoftwareOpenGL"):
            QApplication.setAttribute(Qt.AA_UseSoftwareOpenGL, True)
        if hasattr(Qt, "AA_DontUseNativeDialogs"):
            QApplication.setAttribute(Qt.AA_DontUseNativeDialogs, True)
        if hasattr(Qt, "AA_DontUseNativeMenuBar"):
            QApplication.setAttribute(Qt.AA_DontUseNativeMenuBar, True)

    app = QApplication(sys.argv)
    app.setApplicationName("EMG Data Analyser")
    app.setOrganizationName("zst")
    win = MainWindow()
    win.show()

    if startup_warnings:
        for msg in startup_warnings:
            win.append_log(f"[WARN] Startup risk: {msg}")
        detail = "\n\n".join(f"- {msg}" for msg in startup_warnings)
        QMessageBox.warning(
            win,
            "Runtime Crash Risk Warning",
            "Potential crash risk detected in current macOS runtime:\n\n"
            f"{detail}\n\n"
            "Recommended: use arm64 Python 3.12 and reinstall dependencies.",
        )

    sys.exit(app.exec_())
