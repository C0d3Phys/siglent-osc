from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    try:
        import pyqtgraph  # noqa: F401
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print(
            "Faltan las dependencias gráficas. Instálelas con: "
            'python -m pip install -e ".[dev]"',
            file=sys.stderr,
        )
        return 2

    from osc_app.app.main_window import MainWindow

    application = QApplication(sys.argv)
    application.setApplicationName("OSC App")
    logo = Path(__file__).resolve().parents[1] / "resources" / "osc_app_logo.png"
    if logo.is_file():
        application.setWindowIcon(QIcon(str(logo)))
    window = MainWindow()
    window.resize(1200, 760)
    window.show()

    sample = Path.cwd() / "examples" / "siglent_fake_4ch.csv"
    if sample.is_file():
        window.open_csv(sample)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
