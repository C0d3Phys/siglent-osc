from __future__ import annotations

from html import escape

from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout

from osc_app.core.guided_tests import GUIDED_TESTS, GuidedTest


class GuidedTestsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Pruebas automotrices guiadas")
        self.resize(680, 520)
        layout = QVBoxLayout(self)
        self.selector = QComboBox()
        self.selector.addItems([test.name for test in GUIDED_TESTS])
        self.content = QTextBrowser()
        self.content.setOpenExternalLinks(True)
        self.selector.currentIndexChanged.connect(self._show_selected)
        layout.addWidget(self.selector)
        layout.addWidget(self.content, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._show_selected(0)

    @staticmethod
    def _list(items: tuple[str, ...]) -> str:
        return "<ul>" + "".join(f"<li>{escape(item)}</li>" for item in items) + "</ul>"

    def _show_selected(self, index: int) -> None:
        test: GuidedTest = GUIDED_TESTS[index]
        self.content.setHtml(
            f"<h2>{escape(test.name)}</h2><p>{escape(test.purpose)}</p>"
            f"<h3>Conexiones</h3>{self._list(test.connections)}"
            f"<h3>Preparación</h3>{self._list(test.setup)}"
            f"<h3>Comprobaciones</h3>{self._list(test.checks)}"
            f"<h3 style='color:#d97706'>Seguridad</h3><p>{escape(test.warning)}</p>"
            "<p><b>Esta guía ayuda a configurar y observar; no emite un diagnóstico definitivo.</b></p>"
        )
