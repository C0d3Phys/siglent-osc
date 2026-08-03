from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
)


class ReferenceSettingsDialog(QDialog):
    """Small configuration dialog for a waveform reference."""

    def __init__(self, channel_names: list[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Señal de referencia")
        layout = QFormLayout(self)
        self.channel = QComboBox()
        self.channel.addItems(channel_names)
        self.alignment = QComboBox()
        self.alignment.addItem("Tiempo original", "original")
        self.alignment.addItem("Inicio en X1", "x1")
        self.alignment.addItem("Pico de la región en X1", "peak")
        self.gain = QDoubleSpinBox()
        self.gain.setRange(-1000.0, 1000.0)
        self.gain.setDecimals(4)
        self.gain.setValue(1.0)
        self.offset = QDoubleSpinBox()
        self.offset.setRange(-1e9, 1e9)
        self.offset.setDecimals(6)
        self.alpha = QDoubleSpinBox()
        self.alpha.setRange(0.05, 1.0)
        self.alpha.setSingleStep(0.05)
        self.alpha.setValue(0.65)
        layout.addRow("Canal:", self.channel)
        layout.addRow("Alineación:", self.alignment)
        layout.addRow("Ganancia visual:", self.gain)
        layout.addRow("Desplazamiento:", self.offset)
        layout.addRow("Transparencia:", self.alpha)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
