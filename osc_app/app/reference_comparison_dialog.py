from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from osc_app.core.references import ReferenceComparison


class ReferenceComparisonDialog(QDialog):
    def __init__(
        self,
        comparison: ReferenceComparison,
        actual_name: str,
        reference_name: str,
        error_visible: bool,
        error_callback,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Comparación con referencia")
        self.resize(620, 520)
        layout = QVBoxLayout(self)
        title = QLabel(f"Actual: {actual_name}  ·  Referencia: {reference_name}")
        title.setStyleSheet("font-weight: 600;")
        layout.addWidget(title)
        rows = (
            ("Muestras comparadas", f"{comparison.samples:,}"),
            ("Correlación", self._number(comparison.correlation)),
            ("MAE", self._number(comparison.mae)),
            ("RMSE", self._number(comparison.rmse)),
            ("Error máximo", self._number(comparison.maximum_error)),
            ("Ganancia Actual ≈ G×Ref + Offset", self._number(comparison.gain)),
            ("Offset estimado", self._number(comparison.offset)),
            ("Retardo residual", self._time(comparison.residual_delay)),
            ("Frecuencia actual", self._frequency(comparison.actual_frequency)),
            ("Frecuencia referencia", self._frequency(comparison.reference_frequency)),
            ("Diferencia de frecuencia", self._frequency(comparison.frequency_difference)),
            ("Diferencia Duty+", self._percent(comparison.duty_difference)),
            ("Escala temporal sugerida", self._number(comparison.time_scale)),
        )
        table = QTableWidget(len(rows), 2)
        table.setHorizontalHeaderLabels(["Métrica", "Resultado"])
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        for row, values in enumerate(rows):
            table.setItem(row, 0, QTableWidgetItem(values[0]))
            table.setItem(row, 1, QTableWidgetItem(values[1]))
        layout.addWidget(table, 1)
        self.show_error = QCheckBox("Mostrar curva Actual − Referencia")
        self.show_error.setChecked(error_visible)
        self.show_error.toggled.connect(error_callback)
        layout.addWidget(self.show_error)
        note = QLabel(
            "Una correlación cercana a 1 indica forma similar. Una escala temporal distinta "
            "de 1 sugiere diferente velocidad o período entre capturas."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _number(value: float | None) -> str:
        return "—" if value is None else f"{value:,.8g}"

    @staticmethod
    def _time(value: float | None) -> str:
        return "—" if value is None else f"{value:,.8g} s"

    @staticmethod
    def _frequency(value: float | None) -> str:
        return "—" if value is None else f"{value:,.8g} Hz"

    @staticmethod
    def _percent(value: float | None) -> str:
        return "—" if value is None else f"{value:,.6g} %"
