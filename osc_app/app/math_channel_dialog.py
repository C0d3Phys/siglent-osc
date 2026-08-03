from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
)

MATH_OPERATIONS = (
    ("Suma A+B", "add"),
    ("Resta A−B", "subtract"),
    ("Multiplicación A×B", "multiply"),
    ("División A/B", "divide"),
    ("Invertir −A", "invert"),
    ("Valor absoluto |A|", "absolute"),
    ("Derivada dA/dt", "derivative"),
    ("Integral ∫A dt", "integral"),
    ("Filtro pasa-bajos", "lowpass"),
    ("Filtro pasa-altos", "highpass"),
)


class MathChannelDialog(QDialog):
    def __init__(self, channel_names: list[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Crear canal matemático")
        layout = QFormLayout(self)
        self.name = QLineEdit("M1")
        self.unit = QLineEdit("V")
        self.operation = QComboBox()
        for label, value in MATH_OPERATIONS:
            self.operation.addItem(label, value)
        self.first = QComboBox()
        self.second = QComboBox()
        self.first.addItems(channel_names)
        self.second.addItems(channel_names)
        self.cutoff = QDoubleSpinBox()
        self.cutoff.setRange(0.001, 1e9)
        self.cutoff.setDecimals(3)
        self.cutoff.setValue(100.0)
        self.cutoff.setSuffix(" Hz")
        self.operation.currentIndexChanged.connect(self._update_controls)
        layout.addRow("Nombre:", self.name)
        layout.addRow("Operación:", self.operation)
        layout.addRow("Canal A:", self.first)
        layout.addRow("Canal B:", self.second)
        layout.addRow("Frecuencia de corte:", self.cutoff)
        layout.addRow("Unidad:", self.unit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        self._update_controls()

    def _update_controls(self) -> None:
        operation = str(self.operation.currentData())
        self.second.setEnabled(operation in {"add", "subtract", "multiply", "divide"})
        self.cutoff.setEnabled(operation in {"lowpass", "highpass"})
