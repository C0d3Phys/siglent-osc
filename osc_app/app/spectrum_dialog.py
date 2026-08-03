from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
)

from osc_app.core.spectrum import calculate_spectrum


class SpectrumDialog(QDialog):
    def __init__(
        self,
        channel_names: list[str],
        channels: list[np.ndarray],
        sample_rate: float,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Análisis FFT")
        self.resize(900, 620)
        self._channels = channels
        self._sample_rate = sample_rate
        layout = QVBoxLayout(self)
        controls = QFormLayout()
        self.channel = QComboBox()
        self.channel.addItems(channel_names)
        self.window = QComboBox()
        for label, value in (
            ("Hann", "hann"),
            ("Hamming", "hamming"),
            ("Blackman", "blackman"),
            ("Rectangular", "boxcar"),
        ):
            self.window.addItem(label, value)
        self.db_scale = QCheckBox("Escala dB")
        self.remove_dc = QCheckBox("Eliminar DC")
        self.remove_dc.setChecked(True)
        controls.addRow("Canal:", self.channel)
        controls.addRow("Ventana:", self.window)
        controls.addRow(self.db_scale)
        controls.addRow(self.remove_dc)
        layout.addLayout(controls)
        self.summary = QLabel()
        layout.addWidget(self.summary)
        self.plot = pg.PlotWidget(background="#101419")
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.plot.setLabel("bottom", "Frecuencia", units="Hz")
        layout.addWidget(self.plot, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.channel.currentIndexChanged.connect(self._refresh)
        self.window.currentIndexChanged.connect(self._refresh)
        self.db_scale.toggled.connect(self._refresh)
        self.remove_dc.toggled.connect(self._refresh)
        self._refresh()

    def _refresh(self, *_args: object) -> None:
        samples = self._channels[self.channel.currentIndex()]
        limited = samples[: min(samples.size, 1_048_576)]
        result = calculate_spectrum(
            limited,
            self._sample_rate,
            window=str(self.window.currentData()),
            remove_dc=self.remove_dc.isChecked(),
        )
        amplitude = result.amplitude
        unit = "amplitud"
        if self.db_scale.isChecked():
            amplitude = 20.0 * np.log10(np.maximum(amplitude, np.finfo(float).tiny))
            unit = "dB"
        self.plot.clear()
        self.plot.plot(result.frequency, amplitude, pen=pg.mkPen("#4dabf7", width=1.2))
        self.plot.setLabel("left", unit)
        if result.dominant_frequency is None:
            self.summary.setText("No hay suficientes muestras para calcular FFT")
        else:
            rpm = result.dominant_frequency * 60.0
            suffix = "" if limited.size == samples.size else f" · usando {limited.size:,} muestras"
            self.summary.setText(
                f"Pico: {result.dominant_frequency:,.6g} Hz · "
                f"{result.dominant_amplitude:,.6g} · {rpm:,.3f} RPM{suffix}"
            )
