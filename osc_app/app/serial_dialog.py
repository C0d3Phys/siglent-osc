from __future__ import annotations

import numpy as np
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from osc_app.core.serial_decoding import decode_uart


class SerialDecodeDialog(QDialog):
    def __init__(
        self,
        time: np.ndarray,
        channel_names: list[str],
        channels: list[np.ndarray],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Decodificación serial UART")
        self.resize(680, 520)
        self._time = time
        self._channels = channels
        layout = QVBoxLayout(self)
        controls = QFormLayout()
        self.channel = QComboBox()
        self.channel.addItems(channel_names)
        self.baud = QDoubleSpinBox()
        self.baud.setRange(1.0, 100_000_000.0)
        self.baud.setValue(9600.0)
        self.baud.setDecimals(0)
        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(-1e9, 1e9)
        self.threshold.setDecimals(6)
        first = channels[0]
        finite = first[np.isfinite(first)]
        self.threshold.setValue(float((np.min(finite) + np.max(finite)) / 2.0) if finite.size else 0.0)
        self.inverted = QCheckBox("Polaridad invertida")
        controls.addRow("Canal:", self.channel)
        controls.addRow("Baud rate:", self.baud)
        controls.addRow("Umbral:", self.threshold)
        controls.addRow(self.inverted)
        decode_button = QPushButton("Decodificar")
        decode_button.clicked.connect(self._decode)
        controls.addRow(decode_button)
        layout.addLayout(controls)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Tiempo", "Hex", "Decimal", "Estado"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _decode(self) -> None:
        frames = decode_uart(
            self._time,
            self._channels[self.channel.currentIndex()],
            baud_rate=self.baud.value(),
            threshold=self.threshold.value(),
            inverted=self.inverted.isChecked(),
        )
        self.table.setRowCount(len(frames))
        for row, frame in enumerate(frames):
            for column, value in enumerate(
                (
                    f"{frame.time:.9g} s",
                    f"0x{frame.value:02X}",
                    str(frame.value),
                    "OK" if frame.valid_stop else "Error de parada",
                )
            ):
                self.table.setItem(row, column, QTableWidgetItem(value))
