from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pyqtgraph as pg
import pyqtgraph.exporters as pg_exporters
from PySide6.QtCore import QObject, QPoint, QPointF, QSettings, QSize, Qt, QThread, Signal
from PySide6.QtGui import QActionGroup, QBrush, QColor, QPalette
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from scipy.signal import lfilter, lfilter_zi

from osc_app.app.guided_tests_dialog import GuidedTestsDialog
from osc_app.app.icons import make_icon
from osc_app.app.math_channel_dialog import MathChannelDialog
from osc_app.app.reference_comparison_dialog import ReferenceComparisonDialog
from osc_app.app.reference_dialog import ReferenceSettingsDialog
from osc_app.app.serial_dialog import SerialDecodeDialog
from osc_app.app.spectrum_dialog import SpectrumDialog
from osc_app.core.advanced_measurements import (
    calculate_edge_measurements,
    estimate_delay_and_phase,
)
from osc_app.core.csv_importer import CsvImportError, GenericCsvImporter
from osc_app.core.file_support import is_supported_acquisition_file
from osc_app.core.hantek_importer import HantekImportError, HantekLwfImporter
from osc_app.core.math_channels import calculate_math_channel
from osc_app.core.measurements import (
    calculate_pulse_measurements,
    calculate_statistics,
    inclusive_region_indices,
    nearest_index,
)
from osc_app.core.models import Acquisition
from osc_app.core.quantity import format_quantity, parse_quantity
from osc_app.core.recent_files import MAX_RECENT_FILES, filter_existing_paths, push_recent_file
from osc_app.core.references import compare_reference, reference_time_shift, transform_reference
from osc_app.core.siglent_bin_importer import BinImportError, SiglentBinImporter
from osc_app.core.siglent_slg_importer import SiglentSlgImporter, SlgImportError
from osc_app.core.status_summary import build_status_summary, estimate_acquisition_memory_bytes

CHANNEL_COLORS = ("#ffd43b", "#4dabf7", "#ff6b6b", "#69db7c")
AC_FILTER_CUTOFF_HZ = 10.0
COUPLING_MODES = (
    ("dc", "DC"),
    ("ac_mean", "AC — eliminar media"),
    ("ac_filter", f"AC — filtro pasa-altos {AC_FILTER_CUTOFF_HZ:g} Hz"),
)
STATISTIC_COLUMNS = (
    "Canal",
    "Mínimo",
    "Máximo",
    "Pico-pico",
    "Media",
    "RMS",
    "Freq",
    "Duty+",
    "Subida",
    "Bajada",
    "Pulso+",
    "Pulso−",
    "Flancos↑",
    "Flancos↓",
    "Overshoot",
    "Undershoot",
    "N",
)
CURSOR_VALUE_COLUMNS = ("Canal", "En X1", "En X2", "Diferencia")
CURSOR_ROWS = (
    "X1",
    "X2",
    "Δt",
    "1/Δt",
    "X1 (grados)",
    "X2 (grados)",
    "Δ grados",
    "Índice X1",
    "Índice X2",
    "Muestras",
    "Y1",
    "Y2",
    "ΔY",
)

ENGINE_PHASES = (
    ("Trabajo", (225, 70, 70, 38)),
    ("Escape", (130, 130, 130, 34)),
    ("Admisión", (70, 165, 205, 34)),
    ("Compresión", (245, 205, 45, 34)),
)


def next_125(value: float, zoom_in: bool) -> float:
    """Devuelve el siguiente paso 1-2-5 para una división de osciloscopio."""
    if not np.isfinite(value) or value <= 0:
        return 1.0
    exponent = int(np.floor(np.log10(value)))
    candidates = sorted(
        multiplier * 10.0**power
        for power in range(exponent - 2, exponent + 3)
        for multiplier in (1.0, 2.0, 5.0)
    )
    tolerance = value * 1e-9
    if zoom_in:
        smaller = [candidate for candidate in candidates if candidate < value - tolerance]
        return smaller[-1] if smaller else candidates[0]
    larger = [candidate for candidate in candidates if candidate > value + tolerance]
    return larger[0] if larger else candidates[-1]


def _table_height(table: QTableWidget, rows: int) -> int:
    """Alto necesario para mostrar ``rows`` filas de ``table`` sin barra vertical."""
    row_height = table.verticalHeader().defaultSectionSize()
    header_height = table.horizontalHeader().sizeHint().height()
    return header_height + rows * row_height + 2 * table.frameWidth() + 2


class OscilloscopeViewBox(pg.ViewBox):
    """Rueda horizontal tipo Time/div; Ctrl+rueda controla V/div."""

    def __init__(self) -> None:
        super().__init__()
        self.reference_drag_callback = None
        self.reference_is_selected = None
        self.zoom_extended_callback = None

    def wheelEvent(self, event, axis=None) -> None:
        delta = event.delta()
        if delta == 0:
            event.accept()
            return
        scene_position = event.scenePos()
        center = self.mapSceneToView(scene_position)
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 0.8 if delta > 0 else 1.25
            self.disableAutoRange(axis="y")
            self.scaleBy(y=factor, center=QPointF(center.x(), center.y()))
        else:
            low, high = self.viewRange()[0]
            current_division = (high - low) / 14.0
            target_division = next_125(current_division, zoom_in=delta > 0)
            factor = target_division / current_division
            self.disableAutoRange(axis="x")
            self.scaleBy(x=factor, center=QPointF(center.x(), center.y()))
        event.accept()

    def mouseDragEvent(self, event, axis=None) -> None:
        reference_selected = (
            self.reference_is_selected is not None and self.reference_is_selected()
        )
        if (
            reference_selected
            and event.button() == Qt.MouseButton.LeftButton
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
            and self.reference_drag_callback is not None
        ):
            current = self.mapToView(event.pos())
            previous = self.mapToView(event.lastPos())
            self.reference_drag_callback(current - previous, event.isFinish())
            event.accept()
            return
        super().mouseDragEvent(event, axis=axis)

    def mouseDoubleClickEvent(self, event) -> None:
        if (
            event.button() == Qt.MouseButton.MiddleButton
            and self.zoom_extended_callback is not None
        ):
            self.zoom_extended_callback()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class ChannelOffsetTag(QLabel):
    """External 0 V marker constrained to vertical movement."""

    def __init__(
        self,
        parent: QWidget,
        channel_label: str,
        color: str,
        moved_callback,
        reset_callback,
    ) -> None:
        super().__init__(f"{channel_label} ▶", parent)
        self._moved_callback = moved_callback
        self._reset_callback = reset_callback
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(38, 22)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setStyleSheet(
            f"QLabel {{ background-color: {color}; color: #101419; "
            "font-weight: bold; border-radius: 3px; padding: 1px; }"
        )
        self.setToolTip(
            f"{channel_label}: nivel de 0 V. Arrastre solo verticalmente; "
            "doble clic para volver a cero"
        )

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            parent_position = self.parentWidget().mapFromGlobal(
                event.globalPosition().toPoint()
            )
            self._moved_callback(float(parent_position.y()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._reset_callback()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class ChannelCard(QFrame):
    """Tarjeta de un canal identificada por su color.

    Reúne en un solo lugar lo que se ajusta por canal: visibilidad, polaridad,
    sonda (con valores comunes a un clic), acoplamiento y offset visual. Cada
    control usa una fila completa del panel para que el valor y su unidad se
    lean sin recortes.
    """

    PROBE_PRESETS = (1.0, 10.0, 100.0)
    COUPLING_LABELS = {
        "dc": "DC",
        "ac_mean": "AC (quitar media)",
        "ac_filter": f"AC (pasa-altos {AC_FILTER_CUTOFF_HZ:g} Hz)",
    }

    def __init__(
        self,
        index: int,
        name: str,
        unit: str,
        color: str,
        *,
        visibility_changed,
        probe_changed,
        offset_changed,
        solo_requested,
        coupling_changed,
        inversion_changed,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.index = index
        self.setObjectName("channelCard")
        self.setStyleSheet(
            "#channelCard {"
            f"  border-left: 4px solid {color};"
            "  background-color: rgba(255, 255, 255, 16);"
            "  border-radius: 6px;"
            "}"
            "#channelCard QLabel[role='field'] { color: #b4bcc8; }"
        )
        grid = QGridLayout(self)
        grid.setContentsMargins(8, 6, 8, 8)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)
        grid.setColumnStretch(1, 1)

        header = QHBoxLayout()
        header.setSpacing(6)
        self.visibility_checkbox = QCheckBox()
        self.visibility_checkbox.setChecked(True)
        self.visibility_checkbox.setToolTip(f"Mostrar u ocultar {name}")
        self.visibility_checkbox.toggled.connect(
            lambda checked: visibility_changed(index, checked)
        )
        header.addWidget(self.visibility_checkbox)
        self.name_label = QLabel(f"{name}  ·  {unit}")
        self.name_label.setStyleSheet(f"color: {color}; font-weight: 700; font-size: 10.5pt;")
        header.addWidget(self.name_label, 1)
        self.invert_button = QToolButton()
        self.invert_button.setText("Invertir")
        self.invert_button.setCheckable(True)
        self.invert_button.setToolTip(f"Invertir la polaridad de {name}")
        self.invert_button.toggled.connect(lambda checked: inversion_changed(index, checked))
        header.addWidget(self.invert_button)
        solo_button = QToolButton()
        solo_button.setText("Solo")
        solo_button.setToolTip(f"Mostrar únicamente {name}")
        solo_button.clicked.connect(lambda: solo_requested(index))
        header.addWidget(solo_button)
        grid.addLayout(header, 0, 0, 1, 2)

        self.probe_control = QDoubleSpinBox()
        self.probe_control.setDecimals(2)
        self.probe_control.setRange(0.01, 1000.0)
        self.probe_control.setSingleStep(1.0)
        self.probe_control.setSuffix(" X")
        self.probe_control.setToolTip(
            "Factor de atenuación de la sonda. Ajusta voltajes, gráfica y mediciones."
        )
        self.probe_control.valueChanged.connect(lambda value: probe_changed(index, value))
        probe_row = QHBoxLayout()
        probe_row.setSpacing(4)
        probe_row.addWidget(self.probe_control, 1)
        self._probe_preset_buttons: dict[float, QToolButton] = {}
        for preset in self.PROBE_PRESETS:
            preset_button = QToolButton()
            preset_button.setText(f"{preset:g}X")
            preset_button.setToolTip(f"Sonda {preset:g}X")
            preset_button.setCheckable(True)
            preset_button.clicked.connect(
                lambda _checked=False, value=preset: self._select_probe_preset(value)
            )
            probe_row.addWidget(preset_button)
            self._probe_preset_buttons[preset] = preset_button
        self.probe_control.valueChanged.connect(self._mark_probe_preset)
        self._mark_probe_preset(self.probe_control.value())
        grid.addWidget(self._field_label("Sonda"), 1, 0)
        grid.addLayout(probe_row, 1, 1)

        self.coupling_control = QComboBox()
        for mode, _label in COUPLING_MODES:
            self.coupling_control.addItem(self.COUPLING_LABELS[mode], mode)
        self.coupling_control.setToolTip("Acoplamiento del canal")
        self.coupling_control.activated.connect(
            lambda _row: coupling_changed(index, str(self.coupling_control.currentData()))
        )
        grid.addWidget(self._field_label("Acopl."), 2, 0)
        grid.addWidget(self.coupling_control, 2, 1)

        self.offset_control = QDoubleSpinBox()
        self.offset_control.setDecimals(3)
        self.offset_control.setRange(-1e9, 1e9)
        self.offset_control.setKeyboardTracking(False)
        self.offset_control.setSuffix(f" {unit}")
        self.offset_control.setToolTip(
            "Desplazamiento exclusivamente visual; no cambia mediciones ni muestras"
        )
        self.offset_control.valueChanged.connect(lambda value: offset_changed(index, value))
        grid.addWidget(self._field_label("Offset"), 3, 0)
        grid.addWidget(self.offset_control, 3, 1)

    def _select_probe_preset(self, value: float) -> None:
        self.probe_control.setValue(value)
        self._mark_probe_preset(self.probe_control.value())  # por si el valor no cambió

    def _mark_probe_preset(self, value: float) -> None:
        for preset, button in self._probe_preset_buttons.items():
            button.setChecked(abs(value - preset) < 1e-9)

    @staticmethod
    def _field_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("role", "field")
        return label

    def set_signal_state(self, unit: str, mode: str, inverted: bool, locked: bool) -> None:
        """Refleja el estado actual del canal sin volver a emitir cambios."""
        name = self.name_label.text().split("  ·  ", 1)[0]
        self.name_label.setText(f"{name}  ·  {unit}")
        self.coupling_control.blockSignals(True)
        self.coupling_control.setCurrentIndex(max(self.coupling_control.findData(mode), 0))
        self.coupling_control.blockSignals(False)
        self.invert_button.blockSignals(True)
        self.invert_button.setChecked(inverted)
        self.invert_button.blockSignals(False)
        lock_tip = "Bloqueado: el compresímetro requiere DC y polaridad normal"
        self.coupling_control.setEnabled(not locked)
        self.invert_button.setEnabled(not locked)
        self.coupling_control.setToolTip(lock_tip if locked else "Acoplamiento del canal")


class CursorField(QLineEdit):
    """Campo de posición de un cursor con unidades automáticas.

    Muestra el valor con prefijo SI (``-50.0000 ms``) y acepta lo que escriba
    el usuario en cualquier escala (``12.5 ms``, ``250u``, ``0,3 V``). Un texto
    no válido se marca en rojo y se restablece el último valor correcto.
    """

    valueEntered = Signal(float)

    def __init__(self, unit: str, *, digits: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._unit = unit
        self._digits = digits
        self._value = 0.0
        self._update_tooltip()
        self.editingFinished.connect(self._commit)
        self.textEdited.connect(lambda _text: self.setStyleSheet(""))
        self.set_value(0.0)

    def value(self) -> float:
        return self._value

    def set_unit(self, unit: str) -> None:
        if unit != self._unit:
            self._unit = unit
            self._update_tooltip()
            self.set_value(self._value)

    def set_value(self, value: float) -> None:
        self._value = value
        if not self.hasFocus():
            self.setText(format_quantity(value, self._unit, self._digits))

    def _update_tooltip(self) -> None:
        self.setToolTip(
            f"Escriba un valor con o sin prefijo, p. ej. 12.5 m{self._unit} o 250 µ{self._unit}"
        )

    def _commit(self) -> None:
        if not self.isModified():
            return
        try:
            value = parse_quantity(self.text(), self._unit)
        except ValueError:
            self.setStyleSheet("border: 1px solid #e5534b;")
            self.setText(format_quantity(self._value, self._unit, self._digits))
            return
        self.setStyleSheet("")
        self._value = value
        self.setText(format_quantity(value, self._unit, self._digits))
        self.valueEntered.emit(value)


class DraggableTextItem(pg.TextItem):
    """Texto superpuesto que el usuario puede recolocar dentro de la gráfica."""

    def __init__(self, *args: object, moved_callback=None, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._moved_callback = moved_callback
        self._drag_offset = QPointF()
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def hoverEvent(self, event) -> None:
        if event.acceptDrags(Qt.MouseButton.LeftButton):
            self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseDragEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return

        pointer_position = self.mapToParent(event.pos())
        if event.isStart():
            self._drag_offset = self.pos() - pointer_position
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

        self.setPos(pointer_position + self._drag_offset)
        event.accept()

        if self._moved_callback is not None:
            self._moved_callback(self)
        if event.isFinish():
            self.setCursor(Qt.CursorShape.OpenHandCursor)


class CtrlDraggableReferenceItem(pg.PlotDataItem):
    """Reference waveform with a lightweight selected visual state."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._selected = False
        self._base_pen = pg.mkPen(self.opts["pen"])
        selected_color = QColor(self._base_pen.color())
        selected_color.setAlpha(255)
        self._selected_pen = pg.mkPen(
            selected_color, width=max(float(self._base_pen.widthF()) + 2.5, 4.0)
        )
        self.setToolTip("Mantenga Ctrl y arrastre para sincronizar la referencia")

    def set_reference_selected(self, selected: bool) -> None:
        self._selected = selected
        if selected:
            self.setPen(self._selected_pen)
        else:
            self.setPen(self._base_pen)


class _StatisticsWorker(QObject):
    """Calcula estadísticas, pulsos y flancos por canal fuera del hilo de la UI.

    Con el panel de Estadísticas visible, este cálculo -antes síncrono sobre la adquisición
    completa en ``_refresh_measurements``- corría en el hilo de Qt y congelaba
    la interfaz con capturas grandes (muchas muestras y/o muchos cruces de
    flanco). Se ejecuta aquí en un QThread aparte; el resultado se aplica en
    el hilo principal a través de señales, nunca tocando widgets desde este
    hilo.
    """

    finished = Signal(int, list, object)
    failed = Signal(int, str)

    def __init__(
        self,
        request_id: int,
        channel_specs: list[tuple[int, np.ndarray, np.ndarray]],
        phase_specs: tuple[np.ndarray, np.ndarray, np.ndarray] | None,
    ) -> None:
        super().__init__()
        self._request_id = request_id
        self._channel_specs = channel_specs
        self._phase_specs = phase_specs

    def run(self) -> None:
        try:
            results = []
            for channel_index, time_slice, samples_slice in self._channel_specs:
                statistics = calculate_statistics(samples_slice)
                pulse = calculate_pulse_measurements(time_slice, samples_slice)
                edges = calculate_edge_measurements(time_slice, samples_slice)
                results.append((channel_index, statistics, pulse, edges))
            phase_result = None
            if self._phase_specs is not None:
                scoped_time, first_channel, second_channel = self._phase_specs
                reference_pulse = calculate_pulse_measurements(scoped_time, first_channel)
                phase_result = estimate_delay_and_phase(
                    scoped_time, first_channel, second_channel, reference_pulse.frequency
                )
        except Exception as exc:  # noqa: BLE001 - report to the UI instead of crashing the thread
            self.failed.emit(self._request_id, str(exc))
            return
        self.finished.emit(self._request_id, results, phase_result)


class _ImportWorker(QObject):
    """Lee y decodifica un archivo de adquisición (CSV/BIN/SLG/LWF) fuera del hilo
    de la UI. ``dropEvent()`` llama a ``open_file()`` directamente dentro del
    callback OLE síncrono de arrastrar-y-soltar de Windows; si el parseo
    corriera ahí, congelaría el gesto de arrastre completo, no solo el event
    loop de Qt, con archivos grandes. El resultado se aplica en el hilo
    principal a través de señales.
    """

    finished = Signal(int, object, object, object)  # request_id, result, path, accepted
    failed = Signal(int, str)

    def __init__(
        self,
        request_id: int,
        path: Path,
        force_hantek: bool,
        csv_importer: GenericCsvImporter,
        hantek_importer: HantekLwfImporter,
        bin_importer: SiglentBinImporter,
        slg_importer: SiglentSlgImporter,
    ) -> None:
        super().__init__()
        self._request_id = request_id
        self._path = path
        self._force_hantek = force_hantek
        self._csv_importer = csv_importer
        self._hantek_importer = hantek_importer
        self._bin_importer = bin_importer
        self._slg_importer = slg_importer

    def run(self) -> None:
        try:
            if self._force_hantek or self._path.suffix.lower() == ".lwf":
                result = self._hantek_importer.load(self._path)
                accepted = result.report.samples_per_channel
            elif self._path.suffix.lower() == ".bin":
                result = self._bin_importer.load(self._path)
                accepted = result.report.samples_per_channel
            elif self._path.suffix.lower() == ".slg":
                result = self._slg_importer.load(self._path)
                accepted = result.report.samples_per_channel
            elif self._path.suffix.lower() == ".csv":
                result = self._csv_importer.load(self._path)
                accepted = result.report.rows_accepted
            else:
                raise ValueError(
                    "Formato no compatible. Seleccione CSV, BIN, SLG o una captura Hantek."
                )
        except (
            BinImportError, CsvImportError, HantekImportError, SlgImportError, OSError, ValueError
        ) as exc:
            self.failed.emit(self._request_id, str(exc))
            return
        self.finished.emit(self._request_id, result, self._path, accepted)


class MainWindow(QMainWindow):
    """Visor CSV con paneles fijos para canales, cursores y mediciones."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OSC App — Análisis de señales")
        self.setAcceptDrops(True)
        self._settings = QSettings("OSCApp", "OSCApp")
        self._importer = GenericCsvImporter()
        self._hantek_importer = HantekLwfImporter()
        self._bin_importer = SiglentBinImporter()
        self._slg_importer = SiglentSlgImporter()
        self._acquisition: Acquisition | None = None
        self._current_file_name: str | None = None
        self._updating_selection = False
        self._plot_items: list[pg.PlotDataItem] = []
        self._reference_item: CtrlDraggableReferenceItem | None = None
        self._reference_acquisition: Acquisition | None = None
        self._reference_selected = False
        self._reference_error_item: pg.PlotDataItem | None = None
        self._last_reference_comparison = None
        self._math_items: list[pg.PlotDataItem] = []
        self._math_results: list[np.ndarray] = []
        self._math_names: list[str] = []
        self._channel_checks: list[QCheckBox] = []
        self._native_probe_factors: list[float] = []
        self._applied_probe_factors: list[float] = []
        self._probe_controls: list[QDoubleSpinBox] = []
        self._channel_display_offsets: list[float] = []
        self._offset_controls: list[QDoubleSpinBox] = []
        self._channel_offset_tags: list[ChannelOffsetTag] = []
        self._coupling_modes: list[str] = []
        self._channel_inverted: list[bool] = []
        self._coupling_cache: dict[tuple[int, str, float], np.ndarray] = {}
        self._placing_cursor: str | None = None
        # Pares de cursores ("x"/"y") que esperan a que termine otra colocación.
        self._placement_queue: list[str] = []
        self._show_cursor_overlay = False
        self._show_stats_overlay = False
        self._pressure_mode_active = False
        self._cycle_reference: tuple[float, float] | None = None
        self._pending_cycle_start: float | None = None
        self._locked_x_delta = 0.0
        self._overlay_positions = {
            "cursor": (0.988, 0.975),
            "stats": (0.012, 0.025),
            "cycle": (0.5, 0.975),
        }
        self._stats_request_id = 0
        self._stats_worker_busy = False
        self._stats_pending_args: tuple[
            int,
            list[tuple[int, np.ndarray, np.ndarray]],
            tuple[np.ndarray, np.ndarray, np.ndarray] | None,
        ] | None = None
        self._stats_thread: QThread | None = None
        self._stats_worker: _StatisticsWorker | None = None
        self._import_request_id = 0
        self._import_worker_busy = False
        self._import_pending_args: tuple[int, Path, bool] | None = None
        self._import_thread: QThread | None = None
        self._import_worker: _ImportWorker | None = None
        self._build_ui()
        self._build_menu()
        self._build_toolbar()

    def _build_ui(self) -> None:
        self._build_plot()
        self.channel_panel = self._build_channel_panel()
        self.cursor_panel = self._build_cursor_panel()

        graph_panel = QWidget()
        graph_layout = QVBoxLayout(graph_panel)
        graph_layout.setContentsMargins(0, 0, 0, 0)
        graph_layout.addWidget(self.plot, 1)

        graph_buttons = QHBoxLayout()
        graph_buttons.setSpacing(6)
        graph_buttons.setContentsMargins(4, 2, 4, 2)
        self.time_div_label = QLabel("Time/div: —")
        self.time_div_label.setMinimumWidth(145)
        self.time_div_label.setStyleSheet("font-weight: 600;")
        self.display_mode = QComboBox()
        self.display_mode.addItem("Picos (fiel)", "peak")
        self.display_mode.addItem("Promedio visual", "mean")
        self.display_mode.setToolTip(
            "Picos conserva extremos; Promedio visual reduce el ruido aparente sin cambiar los datos"
        )
        self.display_mode.currentIndexChanged.connect(self._change_display_mode)
        self.draw_style = QComboBox()
        self.draw_style.addItem("Vectores", "vectors")
        self.draw_style.addItem("Puntos", "dots")
        self.draw_style.setToolTip(
            "Vectores une las muestras con líneas; Puntos dibuja solo las muestras"
        )
        self.draw_style.currentIndexChanged.connect(self._change_draw_style)
        auto_y_button = QPushButton("Auto Y")
        auto_y_button.setToolTip("Ajustar la escala vertical a los canales visibles")
        auto_y_button.clicked.connect(self._auto_y)
        zoom_y_in_button = QPushButton("Y +")
        zoom_y_in_button.setToolTip("Acercar la escala vertical")
        zoom_y_in_button.clicked.connect(lambda: self._zoom_y(0.7))
        zoom_y_out_button = QPushButton("Y −")
        zoom_y_out_button.setToolTip("Alejar la escala vertical")
        zoom_y_out_button.clicked.connect(lambda: self._zoom_y(1.4))
        region_view_button = QPushButton("Región")
        region_view_button.setToolTip("Ampliar la región delimitada por X1 y X2")
        region_view_button.clicked.connect(self._zoom_to_region)
        full_view_button = QPushButton("Todo")
        full_view_button.setToolTip("Mostrar la adquisición completa")
        full_view_button.clicked.connect(self._show_full_view)
        graph_buttons.addWidget(self.time_div_label)
        graph_buttons.addWidget(QLabel("Trazo:"))
        graph_buttons.addWidget(self.display_mode)
        graph_buttons.addWidget(QLabel("Dibujo:"))
        graph_buttons.addWidget(self.draw_style)
        graph_buttons.addStretch(1)
        graph_buttons.addWidget(auto_y_button)
        graph_buttons.addWidget(zoom_y_in_button)
        graph_buttons.addWidget(zoom_y_out_button)
        graph_buttons.addWidget(region_view_button)
        graph_buttons.addWidget(full_view_button)
        graph_layout.addLayout(graph_buttons)

        self.upper_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.upper_splitter.addWidget(self.channel_panel)
        self.upper_splitter.addWidget(graph_panel)
        self.upper_splitter.addWidget(self.cursor_panel)
        self.upper_splitter.setSizes([0, 1200, 0])
        self.upper_splitter.setStretchFactor(0, 0)
        self.upper_splitter.setStretchFactor(1, 1)
        self.upper_splitter.setStretchFactor(2, 0)
        self.upper_splitter.setCollapsible(0, True)
        self.upper_splitter.setCollapsible(2, True)
        self.channel_panel.hide()
        self.cursor_panel.hide()

        self.statistics = QTableWidget(0, len(STATISTIC_COLUMNS))
        self.statistics.setHorizontalHeaderLabels(STATISTIC_COLUMNS)
        self.statistics.setAlternatingRowColors(True)
        self.statistics.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.statistics.verticalHeader().setVisible(False)
        self.statistics.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.statistics.horizontalHeader().setStretchLastSection(False)
        self.statistics.horizontalHeader().setMinimumSectionSize(72)

        self.statistics_panel = QGroupBox("Estadísticas")
        statistics_layout = QVBoxLayout(self.statistics_panel)
        self.use_region = QCheckBox("Calcular sobre la región X1–X2")
        self.use_region.setChecked(True)
        self.use_region.toggled.connect(self._refresh_measurements)
        statistics_layout.addWidget(self.use_region)
        self.phase_summary = QLabel("Retardo/fase: seleccione al menos dos canales")
        self.phase_summary.setWordWrap(True)
        statistics_layout.addWidget(self.phase_summary)
        statistics_layout.addWidget(self.statistics)

        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter.addWidget(self.upper_splitter)
        self.main_splitter.addWidget(self.statistics_panel)
        self.main_splitter.setSizes([700, 0])
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 0)
        self.main_splitter.setCollapsible(1, True)
        self.statistics_panel.hide()

        self.info = QLabel("Abra un CSV para comenzar.")
        self.info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout = QVBoxLayout()
        layout.addWidget(self.main_splitter, 1)
        layout.addWidget(self.info)
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)
        self.statusBar().showMessage("Listo")

    def _build_plot(self) -> None:
        self.view_box = OscilloscopeViewBox()
        self.view_box.reference_is_selected = lambda: self._reference_selected
        self.view_box.reference_drag_callback = self._drag_selected_reference
        self.view_box.zoom_extended_callback = self._show_full_view
        plot_item = pg.PlotItem(viewBox=self.view_box)
        self.plot_item = plot_item
        self.graph_navigation_menu = self.view_box.menu
        plot_item.setMenuEnabled(False)
        self.plot = pg.PlotWidget(background="#101419", plotItem=plot_item)
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.plot.setLabel("bottom", "Tiempo", units="s")
        self.plot.setLabel("left", "Amplitud", units="V")
        # Reserve a real gutter for the channel 0 V markers. They must never sit
        # over the graticule or compete with the numeric tick labels.
        plot_item.getAxis("left").setWidth(82)
        self.plot.setDownsampling(auto=True, mode="peak")
        self.plot.setClipToView(True)
        self.view_box.sigXRangeChanged.connect(self._update_time_div_label)
        self.view_box.sigRangeChanged.connect(self._position_overlays)
        self.view_box.sigRangeChanged.connect(self._position_channel_offset_tags)
        self.plot.scene().sigMouseClicked.connect(self._plot_mouse_clicked)

        self.cursor_x1 = pg.InfiniteLine(
            angle=90,
            movable=True,
            pen=pg.mkPen("#00e5ff", width=2),
            label="X1",
            labelOpts={"position": 0.94, "color": "#00e5ff"},
        )
        self.cursor_x2 = pg.InfiniteLine(
            angle=90,
            movable=True,
            pen=pg.mkPen("#ff4ecd", width=2),
            label="X2",
            labelOpts={"position": 0.84, "color": "#ff4ecd"},
        )
        self.cursor_y1 = pg.InfiniteLine(
            angle=0,
            movable=True,
            pen=pg.mkPen("#7cff6b", width=2),
            label="Y1  {value:.6g} V",
            labelOpts={"position": 0.96, "color": "#7cff6b", "movable": True},
        )
        self.cursor_y2 = pg.InfiniteLine(
            angle=0,
            movable=True,
            pen=pg.mkPen("#ff9f43", width=2),
            label="Y2  {value:.6g} V",
            labelOpts={"position": 0.88, "color": "#ff9f43", "movable": True},
        )
        self.region = pg.LinearRegionItem(
            values=(0, 1),
            orientation=pg.LinearRegionItem.Vertical,
            brush=pg.mkBrush(70, 110, 255, 35),
            pen=pg.mkPen(100, 140, 255, 130),
            movable=True,
        )
        self.plot.addItem(self.region, ignoreBounds=True)
        self.plot.addItem(self.cursor_x1, ignoreBounds=True)
        self.plot.addItem(self.cursor_x2, ignoreBounds=True)
        self.plot.addItem(self.cursor_y1, ignoreBounds=True)
        self.plot.addItem(self.cursor_y2, ignoreBounds=True)
        self.region.hide()
        self.cursor_x1.hide()
        self.cursor_x2.hide()
        self.cursor_y1.hide()
        self.cursor_y2.hide()
        self.cursor_x1.sigPositionChanged.connect(self._x_cursor_dragged)
        self.cursor_x2.sigPositionChanged.connect(self._x_cursor_dragged)
        self.cursor_x1.sigPositionChangeFinished.connect(self._x_cursor_finished)
        self.cursor_x2.sigPositionChangeFinished.connect(self._x_cursor_finished)
        self.cursor_y1.sigPositionChangeFinished.connect(self._refresh_measurements)
        self.cursor_y2.sigPositionChangeFinished.connect(self._refresh_measurements)
        self.region.sigRegionChanged.connect(self._region_dragged)
        self.region.sigRegionChangeFinished.connect(self._region_finished)

        self._phase_regions: list[pg.LinearRegionItem] = []
        self._phase_labels: list[pg.TextItem] = []
        self._partition_lines: list[pg.InfiniteLine] = []
        for phase_name, color in ENGINE_PHASES:
            phase_region = pg.LinearRegionItem(
                values=(0, 1),
                orientation=pg.LinearRegionItem.Vertical,
                brush=pg.mkBrush(*color),
                pen=pg.mkPen(color[0], color[1], color[2], 100),
                movable=False,
            )
            phase_region.setZValue(-20)
            phase_region.hide()
            phase_label = pg.TextItem(
                text=phase_name,
                anchor=(0.5, 0),
                color=pg.mkColor(color[0], color[1], color[2]),
                fill=pg.mkBrush(16, 20, 25, 205),
                border=pg.mkPen(color[0], color[1], color[2], 150),
            )
            phase_label.setZValue(80)
            phase_label.hide()
            self._phase_regions.append(phase_region)
            self._phase_labels.append(phase_label)
            self.plot.addItem(phase_region, ignoreBounds=True)
            self.plot.addItem(phase_label, ignoreBounds=True)

        self.cursor_overlay = DraggableTextItem(
            anchor=(1, 0),
            fill=pg.mkBrush(24, 28, 34, 225),
            border=pg.mkPen(110, 120, 135, 220),
            moved_callback=lambda item: self._remember_overlay_position("cursor", item),
        )
        self.cursor_overlay.setZValue(100)
        self.stats_overlay = DraggableTextItem(
            anchor=(0, 1),
            fill=pg.mkBrush(24, 28, 34, 225),
            border=pg.mkPen(110, 120, 135, 220),
            moved_callback=lambda item: self._remember_overlay_position("stats", item),
        )
        self.stats_overlay.setZValue(100)
        self.cycle_overlay = DraggableTextItem(
            anchor=(0.5, 0),
            fill=pg.mkBrush(24, 28, 34, 225),
            border=pg.mkPen(110, 120, 135, 220),
            moved_callback=lambda item: self._remember_overlay_position("cycle", item),
        )
        self.cycle_overlay.setZValue(100)
        self.cycle_overlay.hide()
        self.plot.addItem(self.cursor_overlay, ignoreBounds=True)
        self.plot.addItem(self.stats_overlay, ignoreBounds=True)
        self.plot.addItem(self.cycle_overlay, ignoreBounds=True)

    def _build_channel_panel(self) -> QWidget:
        panel = QGroupBox("Canales")
        layout = QVBoxLayout(panel)

        show_all = QPushButton("Mostrar todos")
        show_all.clicked.connect(self._show_all_channels)
        hide_all = QPushButton("Ocultar todos")
        hide_all.clicked.connect(self._hide_all_channels)
        buttons = QHBoxLayout()
        buttons.addWidget(show_all)
        buttons.addWidget(hide_all)
        layout.addLayout(buttons)

        self.channel_cards: list[ChannelCard] = []
        self._channel_cards_container = QWidget()
        self._channel_cards_layout = QVBoxLayout(self._channel_cards_container)
        self._channel_cards_layout.setContentsMargins(0, 0, 4, 0)
        self._channel_cards_layout.setSpacing(6)
        self._channel_cards_layout.addStretch(1)

        channel_scroll = QScrollArea()
        channel_scroll.setWidgetResizable(True)
        channel_scroll.setFrameShape(QFrame.Shape.NoFrame)
        channel_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        channel_scroll.setWidget(self._channel_cards_container)
        layout.addWidget(channel_scroll, 1)
        # Las tarjetas no se pueden desplazar en horizontal: sin este mínimo, el
        # splitter recorta los botones 1X/10X/100X al abrir también Herramientas.
        panel.setMinimumWidth(320)
        return panel

    def _build_pressure_tab(self) -> QWidget:
        tab = QWidget()
        pressure_layout = QFormLayout(tab)
        self.pressure_enabled = QCheckBox("Mostrar y medir en PSI")
        self.pressure_channel = QComboBox()
        self.pressure_voltage_min = self._pressure_spin(-1000.0, 1000.0, 0.0, " V")
        self.pressure_voltage_max = self._pressure_spin(-1000.0, 1000.0, 5.0, " V")
        self.pressure_min = self._pressure_spin(-100000.0, 100000.0, 0.0, " PSI")
        self.pressure_max = self._pressure_spin(-100000.0, 100000.0, 500.0, " PSI")
        self.pressure_gain = self._pressure_spin(0.001, 1000.0, 1.0, "×")
        self.pressure_gain.setToolTip("Factor de corrección adicional para calibrar el sensor")
        pressure_layout.addRow(self.pressure_enabled)
        pressure_layout.addRow("Canal:", self.pressure_channel)
        pressure_layout.addRow("Voltaje mínimo:", self.pressure_voltage_min)
        pressure_layout.addRow("Voltaje máximo:", self.pressure_voltage_max)
        pressure_layout.addRow("Presión mínima:", self.pressure_min)
        pressure_layout.addRow("Presión máxima:", self.pressure_max)
        pressure_layout.addRow("Factor sensor:", self.pressure_gain)
        self.pressure_calibration = QLabel("Ganancia: 100 PSI/V")
        self.pressure_calibration.setWordWrap(True)
        pressure_layout.addRow(self.pressure_calibration)
        self.pressure_enabled.toggled.connect(self._apply_pressure_configuration)
        self.pressure_channel.currentIndexChanged.connect(self._apply_pressure_configuration)
        for control in (
            self.pressure_voltage_min,
            self.pressure_voltage_max,
            self.pressure_min,
            self.pressure_max,
            self.pressure_gain,
        ):
            control.valueChanged.connect(self._apply_pressure_configuration)
        return tab

    @staticmethod
    def _pressure_spin(
        minimum: float, maximum: float, value: float, suffix: str
    ) -> QDoubleSpinBox:
        control = QDoubleSpinBox()
        control.setDecimals(4)
        control.setRange(minimum, maximum)
        control.setValue(value)
        control.setSuffix(suffix)
        return control

    def _build_cursor_panel(self) -> QWidget:
        panel = QGroupBox("Herramientas")
        layout = QVBoxLayout(panel)
        tabs = QTabWidget()
        self.tools_tabs = tabs
        cursor_tab = QWidget()
        cursor_layout = QVBoxLayout(cursor_tab)
        cycle_tab = QWidget()
        cycle_layout = QVBoxLayout(cycle_tab)

        cursor_switches = QHBoxLayout()
        self.show_x_cursors = QCheckBox("Verticales X")
        self.show_x_cursors.setChecked(False)
        self.show_x_cursors.toggled.connect(self._toggle_x_cursors)
        self.show_y_cursors = QCheckBox("Horizontales Y")
        self.show_y_cursors.setChecked(False)
        self.show_y_cursors.toggled.connect(self._toggle_y_cursors)
        cursor_switches.addWidget(self.show_x_cursors)
        cursor_switches.addWidget(self.show_y_cursors)
        cursor_layout.addLayout(cursor_switches)

        # Cada bloque reúne la posición editable y sus resultados: X1/X2 se
        # escriben y leen en el mismo campo, sin una tabla aparte que los repita.
        self._cursor_readouts: dict[str, QLabel] = {}
        self._cursor_readout_titles: dict[str, QLabel] = {}
        self.x_cursor_group = QGroupBox("Tiempo  ·  X1 / X2")
        x_grid = QGridLayout(self.x_cursor_group)
        x_grid.setColumnStretch(1, 1)
        x_grid.setColumnStretch(3, 1)
        self.x1_numeric = CursorField("s", digits=6)
        self.x2_numeric = CursorField("s", digits=6)
        self.x1_numeric.valueEntered.connect(lambda value: self._set_numeric_cursor("x1", value))
        self.x2_numeric.valueEntered.connect(lambda value: self._set_numeric_cursor("x2", value))
        x_grid.addWidget(QLabel("X1"), 0, 0)
        x_grid.addWidget(self.x1_numeric, 0, 1, 1, 3)
        x_grid.addWidget(QLabel("X2"), 1, 0)
        x_grid.addWidget(self.x2_numeric, 1, 1, 1, 3)
        self._add_readout(x_grid, 2, 0, "Δt")
        self._add_readout(x_grid, 2, 2, "1/Δt")
        self._add_readout(x_grid, 3, 0, "Muestras", span=3)
        self._add_readout(x_grid, 4, 0, "Grados", span=3)
        self.snap_x_to_samples = QCheckBox("Ajustar X a la muestra al soltar")
        self.snap_x_to_samples.setChecked(False)
        self.snap_x_to_samples.setToolTip(
            "Si está desactivado, X1 y X2 permanecen exactamente donde se sueltan"
        )
        self.snap_x_to_samples.toggled.connect(self._snap_option_changed)
        x_grid.addWidget(self.snap_x_to_samples, 5, 0, 1, 4)
        self.lock_x_cursors = QCheckBox("Bloquear separación X1–X2")
        self.lock_x_cursors.toggled.connect(self._lock_x_changed)
        x_grid.addWidget(self.lock_x_cursors, 6, 0, 1, 4)
        self.partition_count = QSpinBox()
        self.partition_count.setRange(0, 32)
        self.partition_count.setSpecialValueText("Ninguna")
        self.partition_count.setValue(0)
        self.partition_count.valueChanged.connect(self._update_partition_lines)
        x_grid.addWidget(QLabel("Particiones"), 7, 0, 1, 2)
        x_grid.addWidget(self.partition_count, 7, 2, 1, 2)
        self.x_cursor_group.setEnabled(False)
        cursor_layout.addWidget(self.x_cursor_group)

        self.y_cursor_group = QGroupBox("Amplitud  ·  Y1 / Y2")
        y_grid = QGridLayout(self.y_cursor_group)
        y_grid.setColumnStretch(1, 1)
        self.y1_numeric = CursorField("V", digits=5)
        self.y2_numeric = CursorField("V", digits=5)
        self.y1_numeric.valueEntered.connect(lambda value: self._set_numeric_cursor("y1", value))
        self.y2_numeric.valueEntered.connect(lambda value: self._set_numeric_cursor("y2", value))
        y_grid.addWidget(QLabel("Y1"), 0, 0)
        y_grid.addWidget(self.y1_numeric, 0, 1)
        y_grid.addWidget(QLabel("Y2"), 1, 0)
        y_grid.addWidget(self.y2_numeric, 1, 1)
        self._add_readout(y_grid, 2, 0, "ΔY")
        self.y_cursor_group.setEnabled(False)
        cursor_layout.addWidget(self.y_cursor_group)

        self.define_cycle_button = QPushButton("Marcar 0° y 720°")
        self.define_cycle_button.setToolTip(
            "Seleccione primero el inicio 0° y después el final 720° sobre la señal"
        )
        self.define_cycle_button.clicked.connect(self._begin_cycle_reference)
        self.clear_cycle_button = QPushButton("Quitar ciclo")
        self.clear_cycle_button.setEnabled(False)
        self.clear_cycle_button.clicked.connect(self._clear_cycle_reference)
        cycle_buttons = QHBoxLayout()
        cycle_buttons.addWidget(self.define_cycle_button)
        cycle_buttons.addWidget(self.clear_cycle_button)
        cycle_layout.addLayout(cycle_buttons)
        self.cycle_start_phase = QComboBox()
        self.cycle_start_phase.addItems([phase[0] for phase in ENGINE_PHASES])
        self.cycle_start_phase.currentIndexChanged.connect(self._cycle_phase_changed)
        cycle_layout.addWidget(QLabel("Etapa que comienza en 0°:"))
        cycle_layout.addWidget(self.cycle_start_phase)
        self.cycle_summary = QLabel("Sin referencia angular")
        self.cycle_summary.setWordWrap(True)
        cycle_layout.addWidget(self.cycle_summary)
        cycle_layout.addStretch(1)

        values_label = QLabel("Valores por canal")
        values_label.setStyleSheet("font-weight: 600;")
        cursor_layout.addWidget(values_label)
        self.cursor_values = QTableWidget(0, len(CURSOR_VALUE_COLUMNS))
        self.cursor_values.setHorizontalHeaderLabels(CURSOR_VALUE_COLUMNS)
        self.cursor_values.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.cursor_values.verticalHeader().setVisible(False)
        self.cursor_values.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.cursor_values.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.cursor_values.setMinimumHeight(_table_height(self.cursor_values, 4))
        cursor_layout.addWidget(self.cursor_values, 1)

        cursor_scroll = QScrollArea()
        cursor_scroll.setWidgetResizable(True)
        cursor_scroll.setFrameShape(QFrame.Shape.NoFrame)
        cursor_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        cursor_scroll.setWidget(cursor_tab)
        tabs.addTab(cursor_scroll, "Cursores")
        tabs.addTab(cycle_tab, "Ciclo motor")
        self.pressure_tab = self._build_pressure_tab()
        tabs.addTab(self.pressure_tab, "Compresímetro")
        layout.addWidget(tabs)
        return panel

    def _add_readout(
        self, grid: QGridLayout, row: int, column: int, name: str, *, span: int = 1
    ) -> None:
        title = QLabel(name)
        title.setStyleSheet("color: #b4bcc8;")
        value = QLabel("—")
        value.setStyleSheet("font-weight: 600;")
        value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        grid.addWidget(title, row, column)
        grid.addWidget(value, row, column + 1, 1, span)
        self._cursor_readouts[name] = value
        self._cursor_readout_titles[name] = title

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&Archivo")
        self.open_action = file_menu.addAction("&Abrir adquisición…")
        self.open_action.setIconText("Abrir")
        self.open_action.setShortcut("Ctrl+O")
        self.open_action.setToolTip("Abrir un CSV, BIN, SLG o LWF (Ctrl+O)")
        self.open_action.triggered.connect(self.choose_acquisition)
        self.hantek_action = file_menu.addAction("Abrir captura &Hantek…")
        self.hantek_action.triggered.connect(self.choose_hantek_capture)
        self.recent_files_menu = file_menu.addMenu("Abrir &reciente")
        self.recent_files_menu.aboutToShow.connect(self._rebuild_recent_files_menu)
        file_menu.addSeparator()
        self.save_image_action = file_menu.addAction("&Guardar imagen…")
        self.save_image_action.setIconText("Imagen")
        self.save_image_action.setShortcut("Ctrl+S")
        self.save_image_action.setToolTip("Guardar la gráfica actual como PNG (Ctrl+S)")
        self.save_image_action.triggered.connect(self.save_plot_image)
        file_menu.addSeparator()
        file_menu.addAction("&Salir", self.close)

        view_menu = self.menuBar().addMenu("&Ver")
        self.view_menu = view_menu
        self.full_view_action = view_menu.addAction("Vista completa", self._show_full_view)
        self.full_view_action.setShortcut("Ctrl+0")
        self.full_view_action.setToolTip("Mostrar la adquisición completa (Ctrl+0)")
        self.zoom_region_action = view_menu.addAction("Zoom a región X1–X2", self._zoom_to_region)
        self.zoom_region_action.setShortcut("Ctrl+R")
        self.zoom_region_action.setToolTip("Ampliar la región X1–X2 (Ctrl+R)")
        self.auto_y_action = view_menu.addAction("Auto Y", self._auto_y)
        self.auto_y_action.setShortcut("Ctrl+Y")
        self.auto_y_action.setToolTip("Ajustar la escala vertical automáticamente (Ctrl+Y)")
        self._view_menu_panels_separator = view_menu.addSeparator()
        self.channel_panel_action = view_menu.addAction("Panel de canales")
        self.channel_panel_action.setIconText("Canales")
        self.channel_panel_action.setCheckable(True)
        self.channel_panel_action.setChecked(False)
        self.channel_panel_action.setShortcut("Ctrl+1")
        self.channel_panel_action.setToolTip("Mostrar u ocultar el panel de canales (Ctrl+1)")
        self.channel_panel_action.toggled.connect(self._set_channel_panel_visible)
        self.cursor_panel_action = view_menu.addAction("Panel de herramientas")
        self.cursor_panel_action.setIconText("Herramientas")
        self.cursor_panel_action.setCheckable(True)
        self.cursor_panel_action.setChecked(False)
        self.cursor_panel_action.setShortcut("Ctrl+2")
        self.cursor_panel_action.setToolTip("Mostrar u ocultar cursores y ciclo motor (Ctrl+2)")
        self.cursor_panel_action.toggled.connect(self._set_cursor_panel_visible)
        self.statistics_panel_action = view_menu.addAction("Panel de estadísticas")
        self.statistics_panel_action.setIconText("Estadísticas")
        self.statistics_panel_action.setCheckable(True)
        self.statistics_panel_action.setChecked(False)
        self.statistics_panel_action.setShortcut("Ctrl+3")
        self.statistics_panel_action.setToolTip("Mostrar u ocultar la tabla de estadísticas (Ctrl+3)")
        self.statistics_panel_action.toggled.connect(self._set_statistics_panel_visible)
        view_menu.addSeparator()
        cursor_overlay_action = view_menu.addAction("Tabla superpuesta de cursores")
        cursor_overlay_action.setCheckable(True)
        cursor_overlay_action.setChecked(self._show_cursor_overlay)
        cursor_overlay_action.toggled.connect(self._set_cursor_overlay_visible)
        stats_overlay_action = view_menu.addAction("Tabla superpuesta de estadísticas")
        stats_overlay_action.setCheckable(True)
        stats_overlay_action.setChecked(self._show_stats_overlay)
        stats_overlay_action.toggled.connect(self._set_stats_overlay_visible)
        view_menu.addSeparator()
        self.graph_navigation_menu.setTitle("Navegación y ejes")
        self._translate_plot_menu(self.graph_navigation_menu)
        self.plot_item.ctrlMenu.setTitle("Opciones de trazado")
        self._translate_plot_menu(self.plot_item.ctrlMenu)
        view_menu.addMenu(self.graph_navigation_menu)
        view_menu.addMenu(self.plot_item.ctrlMenu)

        channels_menu = self.menuBar().addMenu("&Canales")
        channels_menu.addAction("Mostrar todos", self._show_all_channels)
        channels_menu.addAction("Ocultar todos", self._hide_all_channels)
        channels_menu.addSeparator()
        channels_menu.addAction("Separar canales automáticamente", self._auto_arrange_channels)
        channels_menu.addAction("Restablecer offsets visuales", self._reset_channel_offsets)
        self.coupling_menu = channels_menu.addMenu("Acoplamiento DC/AC por canal")
        self.coupling_menu.aboutToShow.connect(self._rebuild_coupling_menu)
        channels_menu.addSeparator()
        self.math_channel_action = channels_menu.addAction(
            "Crear canal matemático…", self._create_math_channel
        )
        self.math_channel_action.setIconText("Matemático")
        self.math_channel_action.setShortcut("Ctrl+M")
        self.math_channel_action.setToolTip("Crear un canal matemático (Ctrl+M)")
        self.remove_math_action = channels_menu.addAction(
            "Quitar canales matemáticos", self._remove_math_channels
        )
        self.remove_math_action.setEnabled(False)
        channels_menu.addSeparator()
        channels_menu.addAction("Configurar compresímetro…", self._show_pressure_settings)

        cursors_menu = self.menuBar().addMenu("C&ursores")
        self.toggle_x_cursors_action = cursors_menu.addAction("Verticales X1/X2")
        self.toggle_x_cursors_action.setIconText("Cursores X")
        self.toggle_x_cursors_action.setCheckable(True)
        self.toggle_x_cursors_action.setChecked(self.show_x_cursors.isChecked())
        self.toggle_x_cursors_action.setShortcut("Ctrl+4")
        self.toggle_x_cursors_action.setToolTip("Mostrar u ocultar cursores X1/X2 (Ctrl+4)")
        self.toggle_x_cursors_action.toggled.connect(self.show_x_cursors.setChecked)
        self.show_x_cursors.toggled.connect(self.toggle_x_cursors_action.setChecked)
        self.toggle_y_cursors_action = cursors_menu.addAction("Horizontales Y1/Y2")
        self.toggle_y_cursors_action.setIconText("Cursores Y")
        self.toggle_y_cursors_action.setCheckable(True)
        self.toggle_y_cursors_action.setChecked(self.show_y_cursors.isChecked())
        self.toggle_y_cursors_action.setShortcut("Ctrl+5")
        self.toggle_y_cursors_action.setToolTip("Mostrar u ocultar cursores Y1/Y2 (Ctrl+5)")
        self.toggle_y_cursors_action.toggled.connect(self.show_y_cursors.setChecked)
        self.show_y_cursors.toggled.connect(self.toggle_y_cursors_action.setChecked)
        cursors_menu.addSeparator()
        for checkbox in (self.snap_x_to_samples, self.lock_x_cursors):
            action = cursors_menu.addAction(checkbox.text())
            action.setCheckable(True)
            action.setChecked(checkbox.isChecked())
            action.toggled.connect(checkbox.setChecked)
            checkbox.toggled.connect(action.setChecked)

        analysis_menu = self.menuBar().addMenu("&Análisis")
        self.fft_action = analysis_menu.addAction("Analizador FFT…", self._show_spectrum)
        self.fft_action.setIconText("FFT")
        self.fft_action.setShortcut("Ctrl+F")
        self.fft_action.setToolTip("Abrir el analizador FFT (Ctrl+F)")
        analysis_menu.addAction("Decodificación UART…", self._show_serial_decoder)
        analysis_menu.addSeparator()
        self.open_reference_action = analysis_menu.addAction(
            "Abrir señal de referencia…", self._choose_reference
        )
        self.open_reference_action.setIconText("Referencia")
        self.open_reference_action.setToolTip("Superponer una señal de referencia")
        self.compare_reference_action = analysis_menu.addAction(
            "Comparar con referencia…", self._compare_with_reference
        )
        self.compare_reference_action.setEnabled(False)
        self.remove_reference_action = analysis_menu.addAction(
            "Quitar señal de referencia", self._remove_reference
        )
        self.remove_reference_action.setEnabled(False)
        analysis_menu.addSeparator()
        analysis_menu.addAction("Definir ciclo motor 0°–720°", self._begin_cycle_reference)
        analysis_menu.addAction("Quitar referencia angular", self._clear_cycle_reference)
        analysis_menu.addSeparator()
        analysis_menu.addAction("Pruebas automotrices guiadas…", self._show_guided_tests)

    def _show_pressure_settings(self) -> None:
        self._set_cursor_panel_visible(True)
        self.tools_tabs.setCurrentWidget(self.pressure_tab)

    def _build_toolbar(self) -> None:
        """Barra de herramientas con las acciones más usadas.

        Los íconos se dibujan por código (``osc_app.app.icons``) en vez de usar
        los íconos nativos del sistema, para evitar el aspecto inconsistente y
        anticuado de los íconos estándar de Qt en distintas plataformas. Las
        acciones de zoom (Auto Y, región, vista completa) no se repiten aquí
        porque ya están en la barra bajo la gráfica; solo llevan ícono para el
        menú Ver.
        """
        toolbar = QToolBar("Barra de herramientas", self)
        toolbar.setObjectName("main_toolbar")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toolbar.setIconSize(QSize(20, 20))
        icon_color = self.palette().color(QPalette.ColorRole.WindowText)

        for action, icon_name in (
            (self.open_action, "open"),
            (self.save_image_action, "save_image"),
            (self.channel_panel_action, "panel_left"),
            (self.cursor_panel_action, "panel_right"),
            (self.statistics_panel_action, "panel_bottom"),
            (self.toggle_x_cursors_action, "cursor_x"),
            (self.toggle_y_cursors_action, "cursor_y"),
            (self.auto_y_action, "auto_y"),
            (self.zoom_region_action, "region"),
            (self.full_view_action, "full_view"),
            (self.math_channel_action, "math_channel"),
            (self.fft_action, "fft"),
            (self.open_reference_action, "reference"),
        ):
            action.setIcon(make_icon(icon_name, icon_color))

        toolbar.addAction(self.open_action)
        toolbar.addAction(self.save_image_action)
        toolbar.addSeparator()
        toolbar.addAction(self.channel_panel_action)
        toolbar.addAction(self.cursor_panel_action)
        toolbar.addAction(self.statistics_panel_action)
        toolbar.addSeparator()
        toolbar.addAction(self.toggle_x_cursors_action)
        toolbar.addAction(self.toggle_y_cursors_action)
        toolbar.addSeparator()
        toolbar.addAction(self.math_channel_action)
        toolbar.addAction(self.fft_action)
        toolbar.addAction(self.open_reference_action)

        self.main_toolbar = toolbar
        self.addToolBar(toolbar)

        self.toolbar_toggle_action = toolbar.toggleViewAction()
        self.toolbar_toggle_action.setText("Barra de herramientas")
        self.toolbar_toggle_action.setToolTip(
            "Mostrar u ocultar la barra de herramientas superior"
        )
        self.view_menu.insertAction(self._view_menu_panels_separator, self.toolbar_toggle_action)

    @staticmethod
    def _translate_plot_menu(menu: QMenu) -> None:
        translations = {
            "View All": "Ver todo",
            "X axis": "Eje X",
            "Y axis": "Eje Y",
            "Mouse Mode": "Modo del ratón",
            "Transforms": "Transformaciones",
            "Downsample": "Reducción de muestras",
            "Average": "Promedio",
            "Alpha": "Transparencia",
            "Grid": "Cuadrícula",
            "Points": "Puntos",
        }
        for action in menu.actions():
            if action.text() in translations:
                action.setText(translations[action.text()])
            if action.menu() is not None:
                MainWindow._translate_plot_menu(action.menu())

    def _set_channel_panel_visible(self, visible: bool) -> None:
        self.channel_panel.setVisible(visible)
        if hasattr(self, "channel_panel_action"):
            self.channel_panel_action.setChecked(visible)
        self._update_upper_splitter_sizes()

    def _show_guided_tests(self) -> None:
        GuidedTestsDialog(self).exec()

    def _set_cursor_panel_visible(self, visible: bool) -> None:
        self.cursor_panel.setVisible(visible)
        if hasattr(self, "cursor_panel_action"):
            self.cursor_panel_action.setChecked(visible)
        self._update_upper_splitter_sizes()
        if visible and self._acquisition is not None:
            self._refresh_measurements()

    def _update_upper_splitter_sizes(self) -> None:
        total = max(self.upper_splitter.width(), 900)
        channel_width = 330 if self.channel_panel.isVisible() else 0
        cursor_width = 340 if self.cursor_panel.isVisible() else 0
        graph_width = max(total - channel_width - cursor_width, 320)
        self.upper_splitter.setSizes([channel_width, graph_width, cursor_width])

    def _set_statistics_panel_visible(self, visible: bool) -> None:
        self.statistics_panel.setVisible(visible)
        if hasattr(self, "statistics_panel_action"):
            self.statistics_panel_action.setChecked(visible)
        if visible:
            upper_height = max(self.main_splitter.height() - 190, 320)
            self.main_splitter.setSizes([upper_height, 190])
            if self._acquisition is not None:
                self._refresh_measurements()

    def _rebuild_coupling_menu(self) -> None:
        self.coupling_menu.clear()
        acquisition = self._acquisition
        if acquisition is None:
            unavailable = self.coupling_menu.addAction("Abra una adquisición primero")
            unavailable.setEnabled(False)
            return
        pressure_channel = self.pressure_channel.currentIndex()
        for index, channel in enumerate(acquisition.channels):
            channel_menu = self.coupling_menu.addMenu(channel.name)
            action_group = QActionGroup(channel_menu)
            action_group.setExclusive(True)
            pressure_locked = self._pressure_mode_active and index == pressure_channel
            for mode, label in COUPLING_MODES:
                action = channel_menu.addAction(label)
                action.setCheckable(True)
                action.setChecked(self._coupling_modes[index] == mode)
                action.setEnabled(not pressure_locked or mode == "dc")
                action_group.addAction(action)
                action.triggered.connect(
                    lambda checked=False, channel_index=index, selected_mode=mode: (
                        self._set_coupling_mode(channel_index, selected_mode)
                        if checked
                        else None
                    )
                )
            channel_menu.addSeparator()
            invert_action = channel_menu.addAction("Invertir polaridad")
            invert_action.setCheckable(True)
            invert_action.setChecked(self._channel_inverted[index])
            invert_action.setEnabled(not pressure_locked)
            invert_action.toggled.connect(
                lambda checked, channel_index=index: self._set_channel_inverted(
                    channel_index, checked
                )
            )
            if pressure_locked:
                channel_menu.setToolTip("El compresímetro requiere acoplamiento DC")

    def choose_acquisition(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Abrir adquisición",
            str(Path.cwd()),
            "Adquisiciones (*.csv *.bin *.slg *.lwf);;Hantek LWF (*.lwf);;CSV (*.csv);;SIGLENT BIN (*.bin);;"
            "SIGLENT SLG (*.slg);;Todos (*.*)",
        )
        if selected:
            self.open_file(Path(selected))

    def choose_hantek_capture(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Abrir captura Hantek",
            str(Path.cwd()),
            "Binario Hantek (*.lwf)",
        )
        if selected:
            self.open_file(Path(selected), force_hantek=True)

    # -- Archivos recientes ------------------------------------------------

    def _load_recent_files(self) -> list[str]:
        stored = self._settings.value("recent_files", [])
        if not stored:
            return []
        paths = list(stored) if isinstance(stored, list) else [stored]
        existing = filter_existing_paths(paths, os.path.exists)
        if existing != paths:
            self._settings.setValue("recent_files", existing)
        return existing

    def _remember_recent_file(self, path: Path) -> None:
        stored = self._settings.value("recent_files", [])
        existing = list(stored) if isinstance(stored, list) else ([stored] if stored else [])
        updated = push_recent_file(existing, str(path), limit=MAX_RECENT_FILES)
        self._settings.setValue("recent_files", updated)

    def _clear_recent_files(self) -> None:
        self._settings.setValue("recent_files", [])

    def _rebuild_recent_files_menu(self) -> None:
        self.recent_files_menu.clear()
        recent = self._load_recent_files()
        if not recent:
            empty_action = self.recent_files_menu.addAction("(sin archivos recientes)")
            empty_action.setEnabled(False)
            return
        for path_text in recent:
            path = Path(path_text)
            action = self.recent_files_menu.addAction(path.name)
            action.setToolTip(path_text)
            action.triggered.connect(lambda checked=False, p=path: self.open_file(p))
        self.recent_files_menu.addSeparator()
        self.recent_files_menu.addAction("Limpiar lista", self._clear_recent_files)

    # -- Arrastrar y soltar --------------------------------------------------

    def dragEnterEvent(self, event) -> None:
        if self._acceptable_drop_path(event) is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        path = self._acceptable_drop_path(event)
        if path is None:
            event.ignore()
            return
        event.acceptProposedAction()
        self.open_file(path)

    @staticmethod
    def _acceptable_drop_path(event) -> Path | None:
        mime_data = event.mimeData()
        if not mime_data.hasUrls():
            return None
        for url in mime_data.urls():
            if not url.isLocalFile():
                continue
            path = Path(url.toLocalFile())
            if is_supported_acquisition_file(path):
                return path
        return None

    def _choose_reference(self) -> None:
        if self._acquisition is None:
            QMessageBox.information(
                self, "Señal de referencia", "Abra primero la adquisición principal."
            )
            return
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Abrir señal de referencia",
            str(Path.cwd()),
            "Adquisiciones (*.csv *.bin *.slg);;CSV (*.csv);;SIGLENT BIN (*.bin);;SIGLENT SLG (*.slg)",
        )
        if not selected:
            return
        path = Path(selected)
        try:
            if path.suffix.lower() == ".bin":
                acquisition = self._bin_importer.load(path).acquisition
            elif path.suffix.lower() == ".slg":
                acquisition = self._slg_importer.load(path).acquisition
            else:
                acquisition = self._importer.load(path).acquisition
        except (BinImportError, CsvImportError, SlgImportError, OSError, ValueError) as exc:
            QMessageBox.critical(self, "Referencia no válida", str(exc))
            return
        dialog = ReferenceSettingsDialog(
            [channel.name for channel in acquisition.channels], self
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        index = dialog.channel.currentIndex()
        channel = acquisition.channels[index]
        mode = str(dialog.alignment.currentData())
        region = tuple(float(value) for value in self.region.getRegion())
        shift = reference_time_shift(
            acquisition.time,
            channel.samples,
            mode,
            active_x1=float(self.cursor_x1.value()),
            region=region if mode == "peak" else None,
        )
        samples = transform_reference(
            channel.samples, gain=dialog.gain.value(), offset=dialog.offset.value()
        )
        color = QColor("#d0d7de")
        color.setAlphaF(dialog.alpha.value())
        self._remove_reference()
        self._reference_acquisition = acquisition
        self._reference_item = CtrlDraggableReferenceItem(
            acquisition.time + shift,
            samples,
            pen=pg.mkPen(color, width=2, style=Qt.PenStyle.DashLine),
            name=f"REF {channel.name} — {path.name}",
        )
        self.plot.addItem(self._reference_item)
        self.remove_reference_action.setEnabled(True)
        self.compare_reference_action.setEnabled(True)
        self.statusBar().showMessage(
            f"Referencia cargada: {path.name} / {channel.name} · "
            "Ctrl + arrastrar para sincronizar"
        )

    def _toggle_reference_selection(self, item: CtrlDraggableReferenceItem) -> None:
        self._reference_selected = not self._reference_selected
        item.set_reference_selected(self._reference_selected)
        if self._reference_selected:
            self.statusBar().showMessage(
                "Referencia seleccionada · Ctrl + arrastrar sobre la gráfica para sincronizar"
            )
        else:
            self.statusBar().showMessage("Referencia protegida")

    def _try_toggle_reference_at(self, scene_position: QPointF) -> bool:
        item = self._reference_item
        if item is None or item.xData is None or item.yData is None or item.xData.size == 0:
            return False
        clicked = self.view_box.mapSceneToView(scene_position)
        local_x = float(clicked.x() - item.pos().x())
        index = int(np.searchsorted(item.xData, local_x))
        candidates = [candidate for candidate in (index - 1, index) if 0 <= candidate < item.xData.size]
        if not candidates:
            return False
        nearest = min(
            candidates,
            key=lambda candidate: abs(float(item.xData[candidate]) - local_x),
        )
        reference_scene = self.view_box.mapViewToScene(
            QPointF(
                float(item.xData[nearest] + item.pos().x()),
                float(item.yData[nearest] + item.pos().y()),
            )
        )
        distance = reference_scene - scene_position
        if distance.x() ** 2 + distance.y() ** 2 > 18.0**2:
            return False
        self._toggle_reference_selection(item)
        return True

    def _drag_selected_reference(self, delta: QPointF, finished: bool = False) -> None:
        item = self._reference_item
        if item is None or not self._reference_selected:
            return
        current = item.pos()
        item.setPos(current.x() + delta.x(), current.y() + delta.y())
        self._remove_reference_error()
        position = item.pos()
        state = "Sincronización guardada" if finished else "Moviendo referencia"
        self.statusBar().showMessage(
            f"{state}: Δt {self._format_time(float(position.x()))} · "
            f"ΔY {float(position.y()):,.6g}"
        )

    def _remove_reference(self) -> None:
        self._reference_selected = False
        self._remove_reference_error()
        if self._reference_item is not None:
            self.plot.removeItem(self._reference_item)
        self._reference_item = None
        self._reference_acquisition = None
        if hasattr(self, "remove_reference_action"):
            self.remove_reference_action.setEnabled(False)
        if hasattr(self, "compare_reference_action"):
            self.compare_reference_action.setEnabled(False)

    def _compare_with_reference(self) -> None:
        acquisition = self._acquisition
        reference = self._reference_item
        if acquisition is None or reference is None:
            QMessageBox.information(
                self, "Comparación", "Abra una adquisición y una señal de referencia."
            )
            return
        names = [channel.name for channel in acquisition.channels]
        selected, accepted = QInputDialog.getItem(
            self,
            "Comparar con referencia",
            "Canal actual:",
            names,
            0,
            False,
        )
        if not accepted:
            return
        channel_index = names.index(selected)
        scope = self._analysis_slice()
        try:
            comparison = compare_reference(
                acquisition.time[scope],
                self._displayed_samples(channel_index)[scope],
                np.asarray(reference.xData, dtype=np.float64) + reference.pos().x(),
                np.asarray(reference.yData, dtype=np.float64) + reference.pos().y(),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "No se pudo comparar", str(exc))
            return
        self._last_reference_comparison = comparison
        dialog = ReferenceComparisonDialog(
            comparison,
            selected,
            reference.name() or "Referencia",
            self._reference_error_item is not None,
            self._set_reference_error_visible,
            self,
        )
        dialog.exec()

    def _set_reference_error_visible(self, visible: bool) -> None:
        comparison = self._last_reference_comparison
        if self._reference_error_item is not None:
            self.plot.removeItem(self._reference_error_item)
        self._reference_error_item = None
        if not visible or comparison is None:
            return
        self._reference_error_item = self.plot.plot(
            comparison.time,
            comparison.error,
            pen=pg.mkPen("#ff4ecd", width=1.4),
            name="ERROR Actual − Referencia",
        )

    def _remove_reference_error(self) -> None:
        if self._reference_error_item is not None:
            self.plot.removeItem(self._reference_error_item)
        self._reference_error_item = None
        self._last_reference_comparison = None

    def _create_math_channel(self) -> None:
        acquisition = self._acquisition
        if acquisition is None:
            QMessageBox.information(
                self, "Canal matemático", "Abra primero una adquisición."
            )
            return
        dialog = MathChannelDialog(
            [channel.name for channel in acquisition.channels], self
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        first_index = dialog.first.currentIndex()
        second_index = dialog.second.currentIndex()
        operation = str(dialog.operation.currentData())
        try:
            samples = calculate_math_channel(
                acquisition.time,
                self._displayed_samples(first_index),
                operation,
                self._displayed_samples(second_index),
                sample_rate=acquisition.sample_rate,
                cutoff_hz=dialog.cutoff.value(),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Canal matemático no válido", str(exc))
            return
        color = CHANNEL_COLORS[
            (len(self._plot_items) + len(self._math_items)) % len(CHANNEL_COLORS)
        ]
        name = dialog.name.text().strip() or f"M{len(self._math_items) + 1}"
        unit = dialog.unit.text().strip() or "—"
        item = self.plot.plot(
            acquisition.time,
            samples,
            pen=pg.mkPen(color, width=1.5),
            name=f"{name} [{unit}]",
        )
        item.setDownsampling(auto=True, method=str(self.display_mode.currentData()))
        self._apply_draw_style(item)
        self._math_items.append(item)
        self._math_results.append(samples)
        self._math_names.append(name)
        self.remove_math_action.setEnabled(True)
        self._auto_y()
        self.statusBar().showMessage(f"Canal matemático creado: {name}")

    def _remove_math_channels(self) -> None:
        for item in self._math_items:
            self.plot.removeItem(item)
        self._math_items.clear()
        self._math_results.clear()
        self._math_names.clear()
        if hasattr(self, "remove_math_action"):
            self.remove_math_action.setEnabled(False)

    def _analysis_slice(self) -> slice:
        acquisition = self._acquisition
        if (
            acquisition is None
            or not self.use_region.isChecked()
            or not self._x_cursors_ready()
        ):
            return slice(None)
        first, last = inclusive_region_indices(
            acquisition.time,
            float(self.cursor_x1.value()),
            float(self.cursor_x2.value()),
        )
        return slice(first, last)

    def _show_spectrum(self) -> None:
        acquisition = self._acquisition
        if acquisition is None or not acquisition.sample_rate:
            QMessageBox.information(
                self, "FFT", "Abra una adquisición con tasa de muestreo válida."
            )
            return
        scope = self._analysis_slice()
        names = [channel.name for channel in acquisition.channels] + self._math_names
        channels = [
            self._displayed_samples(index)[scope]
            for index in range(len(acquisition.channels))
        ] + [samples[scope] for samples in self._math_results]
        SpectrumDialog(names, channels, acquisition.sample_rate, self).exec()

    def _show_serial_decoder(self) -> None:
        acquisition = self._acquisition
        if acquisition is None:
            QMessageBox.information(
                self, "Decodificación UART", "Abra primero una adquisición."
            )
            return
        scope = self._analysis_slice()
        SerialDecodeDialog(
            acquisition.time[scope],
            [channel.name for channel in acquisition.channels],
            [
                self._displayed_samples(index)[scope]
                for index in range(len(acquisition.channels))
            ],
            self,
        ).exec()

    def save_plot_image(self) -> None:
        if self._acquisition is None:
            QMessageBox.information(self, "Guardar imagen", "Abra una adquisición primero.")
            return
        suggested = self._acquisition.source_file.with_suffix(".png").name
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar gráfica con mediciones",
            str(Path.cwd() / suggested),
            "Imagen PNG (*.png)",
        )
        if not selected:
            return
        destination = Path(selected)
        if destination.suffix.lower() != ".png":
            destination = destination.with_suffix(".png")
        try:
            exporter = pg_exporters.ImageExporter(self.plot.plotItem)
            exporter.parameters()["width"] = max(self.plot.width() * 2, 1600)
            exporter.export(str(destination))
        except (OSError, RuntimeError, ValueError) as exc:
            QMessageBox.critical(self, "No se pudo guardar la imagen", str(exc))
            return
        self.statusBar().showMessage(f"Imagen guardada: {destination}")

    def _plot_mouse_clicked(self, event) -> None:
        if not self.plot.sceneBoundingRect().contains(event.scenePos()):
            return
        if event.button() == Qt.MouseButton.RightButton:
            event.accept()
            self._show_plot_context_menu(event.screenPos().toPoint())
            return
        if (
            event.button() == Qt.MouseButton.LeftButton
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
            and self._try_toggle_reference_at(event.scenePos())
        ):
            event.accept()
            return
        if event.button() != Qt.MouseButton.LeftButton or self._placing_cursor is None:
            return
        position = self.view_box.mapSceneToView(event.scenePos())
        self._place_requested_cursor(float(position.x()), float(position.y()))
        event.accept()

    def _show_plot_context_menu(self, screen_position) -> None:
        menu = QMenu(self)
        x_action = menu.addAction("Colocar cursores verticales X1/X2")
        x_action.setCheckable(True)
        x_action.setChecked(self.show_x_cursors.isChecked())
        x_action.toggled.connect(self.show_x_cursors.setChecked)
        y_action = menu.addAction("Colocar cursores horizontales Y1/Y2")
        y_action.setCheckable(True)
        y_action.setChecked(self.show_y_cursors.isChecked())
        y_action.toggled.connect(self.show_y_cursors.setChecked)
        menu.addSeparator()
        menu.addAction("Definir ciclo motor 0°–720°", self._begin_cycle_reference)
        if self._cycle_reference is not None:
            menu.addAction("Quitar referencia angular", self._clear_cycle_reference)
        menu.addSeparator()
        menu.addAction("Auto Y", self._auto_y)
        menu.addAction("Zoom a región X1–X2", self._zoom_to_region)
        menu.addAction("Vista completa", self._show_full_view)
        menu.exec(screen_position)

    def _set_cursor_overlay_visible(self, visible: bool) -> None:
        self._show_cursor_overlay = visible
        self.cursor_overlay.setVisible(visible and self._any_cursor_visible())

    def _set_stats_overlay_visible(self, visible: bool) -> None:
        self._show_stats_overlay = visible
        if visible and self._acquisition is not None:
            self._refresh_measurements()
        else:
            self.stats_overlay.setVisible(False)

    def _any_cursor_visible(self) -> bool:
        return self.show_x_cursors.isChecked() or self.show_y_cursors.isChecked()

    def choose_csv(self) -> None:
        """Alias conservado para compatibilidad con la primera interfaz."""
        self.choose_acquisition()

    def open_csv(self, path: Path) -> None:
        """Abre un CSV o delega según la extensión para conservar compatibilidad."""
        self.open_file(path)

    def open_file(self, path: Path, *, force_hantek: bool = False) -> None:
        # La lectura/decodificación real (E/S de disco + parseo CSV o binario)
        # corre en un hilo aparte vía _dispatch_import: dropEvent() llama a este
        # método directamente dentro del callback OLE síncrono de arrastrar-y-
        # soltar de Windows, así que si open_file() bloqueaba aquí, se congelaba
        # el gesto de arrastre completo (no solo el event loop de Qt) con
        # archivos grandes. open_file() ahora solo encola el trabajo y regresa
        # de inmediato; _on_import_ready aplica el resultado en el hilo de la UI.
        self.statusBar().showMessage(f"Importando {path.name}…")
        self._dispatch_import(Path(path), force_hantek=force_hantek)

    def _dispatch_import(self, path: Path, *, force_hantek: bool) -> None:
        self._import_request_id += 1
        request_id = self._import_request_id
        if self._import_worker_busy:
            # Ya hay una importación en curso: se descarta cualquier pedido
            # encolado anterior y se recuerda solo el más reciente (p. ej. el
            # usuario suelta varios archivos seguidos) para lanzarlo en cuanto
            # el actual termine.
            self._import_pending_args = (request_id, path, force_hantek)
            return
        self._start_import_worker(request_id, path, force_hantek)

    def _start_import_worker(self, request_id: int, path: Path, force_hantek: bool) -> None:
        self._import_worker_busy = True
        thread = QThread(self)
        worker = _ImportWorker(
            request_id,
            path,
            force_hantek,
            self._importer,
            self._hantek_importer,
            self._bin_importer,
            self._slg_importer,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_import_ready)
        worker.failed.connect(self._on_import_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(self._on_import_thread_finished)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._import_thread = thread
        self._import_worker = worker
        thread.start()

    def _on_import_thread_finished(self) -> None:
        self._import_worker_busy = False
        self._import_thread = None
        self._import_worker = None
        if self._import_pending_args is not None:
            request_id, path, force_hantek = self._import_pending_args
            self._import_pending_args = None
            self.statusBar().showMessage(f"Importando {path.name}…")
            self._start_import_worker(request_id, path, force_hantek)

    def _on_import_failed(self, request_id: int, message: str) -> None:
        if request_id != self._import_request_id:
            return  # una importación más nueva ya reemplazó a esta
        QMessageBox.critical(self, "No se pudo abrir la adquisición", message)
        self.statusBar().showMessage("Error de importación")

    def _on_import_ready(self, request_id: int, result: object, path: Path, accepted: int) -> None:
        if request_id != self._import_request_id:
            return  # el usuario abrió/soltó otro archivo antes de que este terminara

        self.show_x_cursors.blockSignals(True)
        self.show_y_cursors.blockSignals(True)
        self._remove_reference()
        self._remove_math_channels()
        self.show_x_cursors.setChecked(False)
        self.show_y_cursors.setChecked(False)
        self.show_x_cursors.blockSignals(False)
        self.show_y_cursors.blockSignals(False)
        self._placing_cursor = None
        self._acquisition = result.acquisition
        self._channel_checks.clear()
        self._native_probe_factors.clear()
        self._applied_probe_factors.clear()
        self._probe_controls.clear()
        self._offset_controls.clear()
        self._coupling_modes = ["dc"] * len(result.acquisition.channels)
        self._channel_inverted = [False] * len(result.acquisition.channels)
        self._channel_display_offsets = [0.0] * len(result.acquisition.channels)
        self._coupling_cache.clear()
        self.pressure_enabled.setChecked(False)
        self._pressure_mode_active = False
        self._clear_cycle_reference()
        self._draw_acquisition(result.acquisition)
        self._populate_channel_panel(result.acquisition)
        self._initialize_selection()
        self._current_file_name = path.name
        self._remember_recent_file(path)
        self._refresh_status_summary()
        self.statusBar().showMessage(
            f"Importación completa: {accepted:,} muestras por canal"
        )

    def _refresh_status_summary(self) -> None:
        """Actualiza el resumen permanente (archivo, muestras, tasa, canales, memoria)."""
        acquisition = self._acquisition
        if acquisition is None:
            self.info.setText("Abra un CSV para comenzar.")
            return
        active_channels = len(self._visible_channel_indices())
        summary = build_status_summary(
            file_name=self._current_file_name or acquisition.source_file.name,
            sample_count=acquisition.sample_count,
            duration=acquisition.duration,
            sample_rate=acquisition.sample_rate,
            active_channels=active_channels,
            total_channels=len(acquisition.channels),
            memory_bytes=estimate_acquisition_memory_bytes(acquisition),
        )
        self.info.setText(summary)

    def _draw_acquisition(self, acquisition: Acquisition) -> None:
        self.plot.clear()
        self._plot_items.clear()
        for old_tag in self._channel_offset_tags:
            old_tag.deleteLater()
        self._channel_offset_tags.clear()
        self.plot.addLegend()
        for row, channel in enumerate(acquisition.channels):
            item = self.plot.plot(
                acquisition.time,
                channel.samples + self._channel_display_offsets[row],
                pen=pg.mkPen(CHANNEL_COLORS[row % len(CHANNEL_COLORS)], width=1),
                name=channel.name,
            )
            self._apply_draw_style(item)
            self._plot_items.append(item)
            tag = ChannelOffsetTag(
                self.plot,
                f"C{row + 1}",
                CHANNEL_COLORS[row % len(CHANNEL_COLORS)],
                lambda pixel_y, index=row: self._channel_offset_tag_moved(
                    index, pixel_y
                ),
                lambda index=row: self._reset_single_channel_offset(index),
            )
            self._channel_offset_tags.append(tag)
            tag.show()
        self.plot.addItem(self.region, ignoreBounds=True)
        self.plot.addItem(self.cursor_x1, ignoreBounds=True)
        self.plot.addItem(self.cursor_x2, ignoreBounds=True)
        self.plot.addItem(self.cursor_y1, ignoreBounds=True)
        self.plot.addItem(self.cursor_y2, ignoreBounds=True)
        self.plot.addItem(self.cursor_overlay, ignoreBounds=True)
        self.plot.addItem(self.stats_overlay, ignoreBounds=True)
        self.plot.addItem(self.cycle_overlay, ignoreBounds=True)
        for phase_region, phase_label in zip(
            self._phase_regions, self._phase_labels, strict=True
        ):
            self.plot.addItem(phase_region, ignoreBounds=True)
            self.plot.addItem(phase_label, ignoreBounds=True)
        self._toggle_x_cursors(self.show_x_cursors.isChecked())
        self._toggle_y_cursors(self.show_y_cursors.isChecked())
        self.plot.setXRange(
            float(acquisition.time[0]), float(acquisition.time[-1]), padding=0
        )
        self.plot.enableAutoRange(axis="y")
        self._update_time_div_label()
        self._position_channel_offset_tags()

    def _populate_channel_panel(self, acquisition: Acquisition) -> None:
        self._channel_checks.clear()
        self.pressure_channel.blockSignals(True)
        self.pressure_channel.clear()
        self.pressure_channel.addItems([channel.name for channel in acquisition.channels])
        self.pressure_channel.blockSignals(False)
        self._clear_channel_cards()
        for row, channel in enumerate(acquisition.channels):
            metadata_key = f"{channel.name} Probe"
            try:
                native_probe = float(acquisition.metadata.get(metadata_key, "1"))
            except ValueError:
                native_probe = 1.0
            if not np.isfinite(native_probe) or native_probe <= 0:
                native_probe = 1.0
            self._native_probe_factors.append(native_probe)
            self._applied_probe_factors.append(native_probe)

            card = ChannelCard(
                row,
                channel.name,
                channel.unit,
                CHANNEL_COLORS[row % len(CHANNEL_COLORS)],
                visibility_changed=self._set_channel_visible,
                probe_changed=self._set_probe_factor,
                offset_changed=self._set_channel_display_offset,
                solo_requested=self._solo_channel,
                coupling_changed=self._card_coupling_changed,
                inversion_changed=self._card_inversion_changed,
            )
            card.probe_control.setValue(native_probe)
            self._channel_cards_layout.insertWidget(row, card)
            self.channel_cards.append(card)
            self._channel_checks.append(card.visibility_checkbox)
            self._probe_controls.append(card.probe_control)
            self._offset_controls.append(card.offset_control)

    def _card_coupling_changed(self, index: int, mode: str) -> None:
        self._set_coupling_mode(index, mode)
        self._update_channel_label(index)  # revierte la tarjeta si el cambio fue rechazado

    def _card_inversion_changed(self, index: int, inverted: bool) -> None:
        self._set_channel_inverted(index, inverted)
        self._update_channel_label(index)

    def _clear_channel_cards(self) -> None:
        for card in self.channel_cards:
            self._channel_cards_layout.removeWidget(card)
            card.deleteLater()
        self.channel_cards.clear()

    def _set_channel_visible(self, index: int, visible: bool) -> None:
        if index < len(self._plot_items):
            self._plot_items[index].setVisible(visible)
        if index < len(self._channel_offset_tags):
            self._channel_offset_tags[index].setVisible(visible)
        self._refresh_measurements()
        self._refresh_status_summary()

    def _set_probe_factor(self, index: int, factor: float) -> None:
        acquisition = self._acquisition
        if acquisition is None or index >= len(acquisition.channels):
            return
        previous_factor = (
            self._applied_probe_factors[index]
            if index < len(self._applied_probe_factors)
            else self._native_probe_factors[index]
        )
        ratio = factor / previous_factor if previous_factor > 0 else 1.0
        if index < len(self._applied_probe_factors):
            self._applied_probe_factors[index] = factor
        self._coupling_cache.clear()
        samples = self._displayed_samples(index, factor)
        self._update_plot_channel(index, factor)
        if index < len(self._channel_checks) and self._channel_checks[index].isChecked():
            visible = self._visible_channel_indices()
            if (
                visible == [index]
                and not self._pressure_enabled_for(index)
                and not np.isclose(ratio, 1.0)
            ):
                self.cursor_y1.setValue(float(self.cursor_y1.value()) * ratio)
                self.cursor_y2.setValue(float(self.cursor_y2.value()) * ratio)
            elif visible == [index] and self._pressure_enabled_for(index):
                self._reset_y_cursors(samples)
            self._auto_y()
        self.statusBar().showMessage(
            f"{acquisition.channels[index].name}: atenuación ajustada a {factor:g}X"
        )
        self._refresh_measurements()

    def _samples_with_probe(self, index: int, factor: float | None = None) -> np.ndarray:
        acquisition = self._acquisition
        if acquisition is None:
            return np.empty(0, dtype=np.float32)
        native = self._native_probe_factors[index] if index < len(self._native_probe_factors) else 1.0
        if factor is None:
            factor = self._probe_controls[index].value() if index < len(self._probe_controls) else native
        ratio = factor / native
        original = acquisition.channels[index].samples
        if np.isclose(ratio, 1.0):
            return original
        return np.asarray(original * np.float32(ratio), dtype=np.float32)

    def _pressure_enabled_for(self, index: int) -> bool:
        return self._pressure_mode_active and index == self.pressure_channel.currentIndex()

    def _displayed_samples(self, index: int, factor: float | None = None) -> np.ndarray:
        voltage = self._samples_with_probe(index, factor)
        if (
            index < len(self._channel_inverted)
            and self._channel_inverted[index]
            and not self._pressure_enabled_for(index)
        ):
            voltage = np.asarray(-voltage, dtype=np.float32)
        voltage = self._apply_coupling(index, voltage, factor)
        if not self._pressure_enabled_for(index):
            return voltage
        voltage_min = self.pressure_voltage_min.value()
        voltage_span = self.pressure_voltage_max.value() - voltage_min
        if np.isclose(voltage_span, 0.0):
            return voltage
        pressure_span = self.pressure_max.value() - self.pressure_min.value()
        slope = pressure_span / voltage_span * self.pressure_gain.value()
        return np.asarray(
            self.pressure_min.value() + (voltage - voltage_min) * slope,
            dtype=np.float32,
        )

    def _plot_samples(self, index: int, factor: float | None = None) -> np.ndarray:
        """Return transformed samples; visual offset is applied by the plot item."""
        return self._displayed_samples(index, factor)

    def _update_plot_channel(self, index: int, factor: float | None = None) -> None:
        acquisition = self._acquisition
        if acquisition is None or not 0 <= index < len(self._plot_items):
            return
        item = self._plot_items[index]
        item.setData(acquisition.time, self._plot_samples(index, factor))
        offset = (
            self._channel_display_offsets[index]
            if index < len(self._channel_display_offsets)
            else 0.0
        )
        item.setPos(0.0, offset)

    def _set_channel_display_offset(self, index: int, value: float) -> None:
        acquisition = self._acquisition
        if acquisition is None or not 0 <= index < len(acquisition.channels):
            return
        self._channel_display_offsets[index] = float(value)
        if index < len(self._plot_items):
            # Freeze the current V/div while the user positions one channel.
            # Otherwise auto-range chases the trace and makes the tag appear to jump.
            self.view_box.disableAutoRange(axis="y")
            self._plot_items[index].setPos(0.0, value)
        self._position_channel_offset_tags()
        unit = self._display_unit(index)
        self.statusBar().showMessage(
            f"{acquisition.channels[index].name}: offset visual {value:+.6g} {unit} "
            "(las mediciones no cambian)"
        )

    def _channel_offset_tag_moved(self, index: int, pixel_y: float) -> None:
        scene_position = self.plot.mapToScene(QPoint(0, round(pixel_y)))
        value = float(self.view_box.mapSceneToView(scene_position).y())
        if index < len(self._offset_controls):
            self._offset_controls[index].setValue(value)
        else:
            self._set_channel_display_offset(index, value)

    def _position_channel_offset_tags(self, *_args: object) -> None:
        if not self._channel_offset_tags:
            return
        plot_left = self.plot.mapFromScene(
            QPointF(self.view_box.sceneBoundingRect().left(), 0.0)
        ).x()
        tag_x = max(0, plot_left - self._channel_offset_tags[0].width() - 3)
        for index, tag in enumerate(self._channel_offset_tags):
            if index >= len(self._channel_display_offsets):
                continue
            scene_position = self.view_box.mapViewToScene(
                QPointF(0.0, self._channel_display_offsets[index])
            )
            widget_position = self.plot.mapFromScene(scene_position)
            tag_y = widget_position.y() - tag.height() // 2
            tag_y = min(max(tag_y, 0), max(self.plot.height() - tag.height(), 0))
            tag.move(tag_x, tag_y)
            tag.raise_()

    def _reset_single_channel_offset(self, index: int) -> None:
        if index < len(self._offset_controls):
            self._offset_controls[index].setValue(0.0)
        else:
            self._set_channel_display_offset(index, 0.0)

    def _reset_channel_offsets(self) -> None:
        for index, control in enumerate(self._offset_controls):
            control.setValue(0.0)
            if index < len(self._channel_display_offsets):
                self._channel_display_offsets[index] = 0.0
            self._update_plot_channel(index)
        self._auto_y()
        self.statusBar().showMessage("Offsets visuales restablecidos")

    def _auto_arrange_channels(self) -> None:
        visible = self._visible_channel_indices()
        if len(visible) < 2:
            self.statusBar().showMessage(
                "Muestra al menos dos canales para separarlos automáticamente"
            )
            return

        summaries: list[tuple[int, float, float]] = []
        for index in visible:
            samples = self._displayed_samples(index)
            step = max(1, samples.size // 100_000)
            finite = samples[::step]
            finite = finite[np.isfinite(finite)]
            if finite.size == 0:
                continue
            low, high = np.percentile(finite, (5.0, 95.0))
            center = float((low + high) / 2.0)
            span = max(float(high - low), np.finfo(np.float32).eps)
            summaries.append((index, center, span))
        if len(summaries) < 2:
            return

        spacing = max(span for _index, _center, span in summaries) * 1.25
        midpoint = (len(summaries) - 1) / 2.0
        for position, (index, center, _span) in enumerate(summaries):
            target_center = (midpoint - position) * spacing
            offset = target_center - center
            if index < len(self._offset_controls):
                self._offset_controls[index].setValue(offset)
            else:
                self._channel_display_offsets[index] = offset
                self._update_plot_channel(index)
        self._auto_y()
        self.statusBar().showMessage(
            "Canales separados visualmente; las mediciones conservan sus valores reales"
        )

    def _apply_coupling(
        self, index: int, samples: np.ndarray, factor: float | None = None
    ) -> np.ndarray:
        if index >= len(self._coupling_modes) or self._pressure_enabled_for(index):
            return samples
        mode = self._coupling_modes[index]
        if mode == "dc" or samples.size == 0:
            return samples
        effective_factor = (
            float(factor)
            if factor is not None
            else float(self._probe_controls[index].value())
            if index < len(self._probe_controls)
            else 1.0
        )
        cache_key = (index, mode, effective_factor)
        cached = self._coupling_cache.get(cache_key)
        if cached is not None:
            return cached
        finite = np.isfinite(samples)
        if not np.any(finite):
            return samples
        mean = float(np.mean(samples[finite], dtype=np.float64))
        centered = np.asarray(samples - mean, dtype=np.float32)
        if mode == "ac_mean":
            result = centered
        else:
            acquisition = self._acquisition
            sample_rate = acquisition.sample_rate if acquisition is not None else None
            if sample_rate is None or sample_rate <= 0:
                result = centered
            else:
                delta_time = 1.0 / sample_rate
                rc = 1.0 / (2.0 * np.pi * AC_FILTER_CUTOFF_HZ)
                alpha = rc / (rc + delta_time)
                working = np.where(finite, samples, mean).astype(np.float64, copy=False)
                initial_state = lfilter_zi((alpha, -alpha), (1.0, -alpha)) * working[0]
                filtered, _ = lfilter(
                    (alpha, -alpha), (1.0, -alpha), working, zi=initial_state
                )
                filtered[~finite] = np.nan
                result = np.asarray(filtered, dtype=np.float32)
        self._coupling_cache[cache_key] = result
        return result

    def _set_coupling_mode(self, index: int, mode: str) -> None:
        acquisition = self._acquisition
        valid_modes = {candidate for candidate, _label in COUPLING_MODES}
        if (
            acquisition is None
            or not 0 <= index < len(acquisition.channels)
            or mode not in valid_modes
        ):
            return
        if self._pressure_enabled_for(index) and mode != "dc":
            QMessageBox.information(
                self,
                "Acoplamiento no disponible",
                "El compresímetro necesita conservar el nivel DC del canal.",
            )
            return
        self._coupling_modes[index] = mode
        self._coupling_cache.clear()
        self._update_plot_channel(index)
        self._update_channel_label(index)
        if self._channel_checks[index].isChecked():
            self._auto_y()
        label = dict(COUPLING_MODES)[mode]
        self.statusBar().showMessage(
            f"{acquisition.channels[index].name}: acoplamiento {label}"
        )
        self._refresh_measurements()

    def _set_channel_inverted(self, index: int, inverted: bool) -> None:
        acquisition = self._acquisition
        if acquisition is None or not 0 <= index < len(acquisition.channels):
            return
        if self._pressure_enabled_for(index) and inverted:
            QMessageBox.information(
                self,
                "Inversión no disponible",
                "El compresímetro necesita conservar la polaridad absoluta del canal.",
            )
            return
        self._channel_inverted[index] = inverted
        self._coupling_cache.clear()
        self._update_plot_channel(index)
        self._update_channel_label(index)
        if self._channel_checks[index].isChecked():
            self._auto_y()
        state = "invertida" if inverted else "normal"
        self.statusBar().showMessage(
            f"{acquisition.channels[index].name}: polaridad {state}"
        )
        self._refresh_measurements()

    def _update_channel_label(self, index: int) -> None:
        acquisition = self._acquisition
        if acquisition is None or not 0 <= index < len(acquisition.channels):
            return
        unit = self._display_unit(index)
        inverted = index < len(self._channel_inverted) and self._channel_inverted[index]
        mode = self._coupling_modes[index] if index < len(self._coupling_modes) else "dc"
        locked = self._pressure_mode_active and index == self.pressure_channel.currentIndex()
        if index < len(self.channel_cards):
            self.channel_cards[index].set_signal_state(unit, mode, inverted, locked)

    def _display_unit(self, index: int) -> str:
        acquisition = self._acquisition
        if acquisition is None:
            return "V"
        return "PSI" if self._pressure_enabled_for(index) else acquisition.channels[index].unit

    def _apply_pressure_configuration(self, *_args: object) -> None:
        requested = self.pressure_enabled.isChecked()
        voltage_span = self.pressure_voltage_max.value() - self.pressure_voltage_min.value()
        if requested and np.isclose(voltage_span, 0.0):
            self.pressure_enabled.blockSignals(True)
            self.pressure_enabled.setChecked(False)
            self.pressure_enabled.blockSignals(False)
            QMessageBox.warning(
                self,
                "Calibración inválida",
                "El voltaje mínimo y máximo del sensor deben ser diferentes.",
            )
            requested = False
        self._pressure_mode_active = requested
        pressure_span = self.pressure_max.value() - self.pressure_min.value()
        slope = pressure_span / voltage_span * self.pressure_gain.value() if voltage_span else 0.0
        self.pressure_calibration.setText(
            f"Ganancia efectiva: {slope:,.6g} PSI/V · sin recorte fuera del rango"
        )
        selected = self.pressure_channel.currentIndex()
        if requested and 0 <= selected < len(self._coupling_modes):
            self._coupling_modes[selected] = "dc"
            self._channel_inverted[selected] = False
            self._coupling_cache.clear()
        if requested and 0 <= selected < len(self._channel_checks):
            for index, checkbox in enumerate(self._channel_checks):
                checkbox.setChecked(index == selected)
        for index, _item in enumerate(self._plot_items):
            self._update_plot_channel(index)
            self._update_channel_label(index)
            if index < len(self._offset_controls):
                self._offset_controls[index].setSuffix(f" {self._display_unit(index)}")
        vertical_axis = self.plot.plotItem.getAxis("left")
        vertical_axis.enableAutoSIPrefix(not requested)
        vertical_unit = "PSI" if requested else "V"
        self.cursor_y1.label.setFormat(f"Y1  {{value:.6g}} {vertical_unit}")
        self.cursor_y2.label.setFormat(f"Y2  {{value:.6g}} {vertical_unit}")
        self.plot.setLabel(
            "left",
            "Presión" if requested else "Amplitud",
            units="PSI" if requested else "V",
        )
        if 0 <= selected < len(self._plot_items):
            self._reset_y_cursors(self._displayed_samples(selected))
        self._auto_y()
        self._refresh_measurements()

    def _reset_y_cursors(self, samples: np.ndarray) -> None:
        finite = samples[np.isfinite(samples)]
        if finite.size == 0:
            return
        minimum = float(np.min(finite))
        maximum = float(np.max(finite))
        span = maximum - minimum or max(abs(maximum), 1.0)
        self.cursor_y1.setValue(minimum + span * 0.25)
        self.cursor_y2.setValue(minimum + span * 0.75)

    def _solo_channel(self, selected_index: int) -> None:
        for index, checkbox in enumerate(self._channel_checks):
            checkbox.setChecked(index == selected_index)
        self.plot.enableAutoRange(axis="y")

    def _show_all_channels(self) -> None:
        for checkbox in self._channel_checks:
            checkbox.setChecked(True)
        self.plot.enableAutoRange(axis="y")

    def _hide_all_channels(self) -> None:
        for checkbox in self._channel_checks:
            checkbox.setChecked(False)

    def _visible_channel_indices(self) -> list[int]:
        return [index for index, checkbox in enumerate(self._channel_checks) if checkbox.isChecked()]

    def _initialize_selection(self) -> None:
        acquisition = self._acquisition
        if acquisition is None:
            return
        start = float(acquisition.time[0])
        end = float(acquisition.time[-1])
        span = end - start
        self._set_selection(start + span * 0.25, start + span * 0.75)
        visible_samples = [
            channel.samples[np.isfinite(channel.samples)] for channel in acquisition.channels
        ]
        finite_samples = [samples for samples in visible_samples if samples.size]
        if finite_samples:
            minimum = min(float(np.min(samples)) for samples in finite_samples)
            maximum = max(float(np.max(samples)) for samples in finite_samples)
            y_span = maximum - minimum
            if y_span == 0:
                y_span = max(abs(maximum), 1.0)
            self.cursor_y1.setValue(minimum + y_span * 0.25)
            self.cursor_y2.setValue(minimum + y_span * 0.75)
        self._refresh_measurements()

    def _set_selection(self, x1: float, x2: float) -> None:
        acquisition = self._acquisition
        if acquisition is None:
            return
        index1 = nearest_index(acquisition.time, x1)
        index2 = nearest_index(acquisition.time, x2)
        snapped1 = float(acquisition.time[index1])
        snapped2 = float(acquisition.time[index2])
        self._updating_selection = True
        self.cursor_x1.setValue(snapped1)
        self.cursor_x2.setValue(snapped2)
        self.region.setRegion(sorted((snapped1, snapped2)))
        self._updating_selection = False
        self._refresh_measurements()

    def _x_cursor_dragged(self) -> None:
        if self._updating_selection or self._acquisition is None:
            return
        self._updating_selection = True
        if hasattr(self, "lock_x_cursors") and self.lock_x_cursors.isChecked():
            if self.sender() is self.cursor_x1:
                self.cursor_x2.setValue(float(self.cursor_x1.value()) + self._locked_x_delta)
            elif self.sender() is self.cursor_x2:
                self.cursor_x1.setValue(float(self.cursor_x2.value()) - self._locked_x_delta)
        self.region.setRegion(
            sorted((float(self.cursor_x1.value()), float(self.cursor_x2.value())))
        )
        self._updating_selection = False

    def _x_cursor_finished(self) -> None:
        if self._updating_selection or self._acquisition is None:
            return
        if self.snap_x_to_samples.isChecked():
            self._set_selection(float(self.cursor_x1.value()), float(self.cursor_x2.value()))
        else:
            self._x_cursor_dragged()
            self._refresh_measurements()

    def _region_dragged(self) -> None:
        if self._updating_selection or self._acquisition is None:
            return
        start, end = self.region.getRegion()
        self._updating_selection = True
        self.cursor_x1.setValue(float(start))
        self.cursor_x2.setValue(float(end))
        self._updating_selection = False

    def _region_finished(self) -> None:
        if self._updating_selection or self._acquisition is None:
            return
        start, end = self.region.getRegion()
        if self.snap_x_to_samples.isChecked():
            self._set_selection(float(start), float(end))
        else:
            self._region_dragged()
            self._refresh_measurements()

    def _snap_option_changed(self, enabled: bool) -> None:
        if enabled and self._acquisition is not None:
            self._set_selection(float(self.cursor_x1.value()), float(self.cursor_x2.value()))

    def _lock_x_changed(self, enabled: bool) -> None:
        if enabled:
            self._locked_x_delta = float(self.cursor_x2.value()) - float(
                self.cursor_x1.value()
            )

    def _set_numeric_cursor(self, name: str, value: float) -> None:
        cursor = {
            "x1": self.cursor_x1,
            "x2": self.cursor_x2,
            "y1": self.cursor_y1,
            "y2": self.cursor_y2,
        }[name]
        cursor.setValue(value)
        cursor.show()
        if name.startswith("x"):
            self._x_cursor_dragged()
            self._x_cursor_finished()
        else:
            self._refresh_measurements()

    def _sync_numeric_cursors(self) -> None:
        if not hasattr(self, "x1_numeric"):
            return
        for control, value in (
            (self.x1_numeric, float(self.cursor_x1.value())),
            (self.x2_numeric, float(self.cursor_x2.value())),
            (self.y1_numeric, float(self.cursor_y1.value())),
            (self.y2_numeric, float(self.cursor_y2.value())),
        ):
            control.set_value(value)

    def _update_partition_lines(self, *_args: object) -> None:
        for line in self._partition_lines:
            self.plot.removeItem(line)
        self._partition_lines.clear()
        count = self.partition_count.value() if hasattr(self, "partition_count") else 0
        if count < 2 or self._acquisition is None:
            return
        start, end = sorted(
            (float(self.cursor_x1.value()), float(self.cursor_x2.value()))
        )
        if end <= start:
            return
        for index in range(1, count):
            position = start + (end - start) * index / count
            line = pg.InfiniteLine(
                position,
                angle=90,
                movable=False,
                pen=pg.mkPen(180, 190, 205, 115, width=1, style=Qt.PenStyle.DotLine),
            )
            line.setZValue(20)
            self.plot.addItem(line, ignoreBounds=True)
            self._partition_lines.append(line)

    def _begin_cycle_reference(self) -> None:
        if self._acquisition is None:
            QMessageBox.information(
                self, "Ciclo motor", "Abra una adquisición antes de definir el ciclo."
            )
            return
        self._pending_cycle_start = None
        if self._placing_cursor in ("x1", "x2", "y1", "y2"):
            # Se retoma después del ciclo, desde el primer cursor del par.
            self._placement_queue.insert(0, self._placing_cursor[0])
        self._placing_cursor = "cycle0"
        self.statusBar().showMessage("Ciclo motor: haga clic en el punto de 0°")
        self._refresh_measurements()

    def _clear_cycle_reference(self) -> None:
        self._cycle_reference = None
        self._pending_cycle_start = None
        if self._placing_cursor in ("cycle0", "cycle720"):
            self._finish_cursor_placement()
        if hasattr(self, "_phase_regions"):
            for phase_region, phase_label in zip(
                self._phase_regions, self._phase_labels, strict=True
            ):
                phase_region.hide()
                phase_label.hide()
        if hasattr(self, "clear_cycle_button"):
            self.clear_cycle_button.setEnabled(False)
            self.cycle_summary.setText("Sin referencia angular")
        if hasattr(self, "cycle_overlay"):
            self.cycle_overlay.hide()
        if self._acquisition is not None:
            self._refresh_measurements()

    def _set_cycle_reference(self, start: float, end: float) -> None:
        if end <= start:
            self._placing_cursor = "cycle720"
            self.statusBar().showMessage("El punto 720° debe estar a la derecha de 0°")
            self._refresh_measurements()
            return
        self._cycle_reference = (start, end)
        self._pending_cycle_start = None
        self._placing_cursor = None
        duration = end - start
        rpm = 120.0 / duration
        self.cycle_summary.setText(
            f"Ciclo: {self._format_time(duration)} · {rpm:,.1f} RPM · 180° por etapa"
        )
        self.clear_cycle_button.setEnabled(True)
        self._update_cycle_phases()
        self._update_cycle_overlay()
        for index, (phase_region, phase_label) in enumerate(
            zip(self._phase_regions, self._phase_labels, strict=True)
        ):
            phase_start = start + duration * index / 4.0
            phase_end = start + duration * (index + 1) / 4.0
            phase_region.setRegion((phase_start, phase_end))
            phase_region.show()
            phase_label.show()
        self._position_overlays()
        self._refresh_measurements()
        self.statusBar().showMessage("Ciclo 0°–720° definido")
        self._finish_cursor_placement()

    def _cycle_phase_changed(self, *_args: object) -> None:
        if self._cycle_reference is None:
            return
        self._update_cycle_phases()
        self._update_cycle_overlay()
        self._position_overlays()

    def _ordered_engine_phases(self) -> tuple[tuple[str, tuple[int, int, int, int]], ...]:
        start = self.cycle_start_phase.currentIndex()
        return ENGINE_PHASES[start:] + ENGINE_PHASES[:start]

    def _update_cycle_phases(self) -> None:
        for (phase_name, color), phase_region, phase_label in zip(
            self._ordered_engine_phases(),
            self._phase_regions,
            self._phase_labels,
            strict=True,
        ):
            phase_region.setBrush(pg.mkBrush(*color))
            for boundary in phase_region.lines:
                boundary.setPen(pg.mkPen(color[0], color[1], color[2], 100))
            phase_label.setText(phase_name, color=pg.mkColor(color[0], color[1], color[2]))
            phase_label.fill = pg.mkBrush(16, 20, 25, 205)
            phase_label.border = pg.mkPen(color[0], color[1], color[2], 150)
            phase_label.update()

    def _update_cycle_overlay(self) -> None:
        if self._cycle_reference is None:
            self.cycle_overlay.hide()
            return
        start, end = self._cycle_reference
        duration = end - start
        rpm = 120.0 / duration
        first_phase = self._ordered_engine_phases()[0][0]
        rows: list[tuple[str, str]] = [
            ("0°", self._format_time(start)),
            ("720°", self._format_time(end)),
            ("Ciclo", self._format_time(duration)),
            ("RPM", f"{rpm:,.1f}"),
            ("Inicio", first_phase),
        ]
        rows.extend(self._pressure_cycle_measurements(start, end))
        body = "".join(
            f"<tr><td style='padding-right:10px'>{label}</td><td><b>{value}</b></td></tr>"
            for label, value in rows
        )
        self.cycle_overlay.setHtml(
            "<div style='color:#f2f4f8;font-size:10pt'><table cellpadding='2'>"
            + body
            + "</table></div>"
        )
        self.cycle_overlay.show()

    def _pressure_cycle_measurements(self, start: float, end: float) -> list[tuple[str, str]]:
        acquisition = self._acquisition
        channel_index = self.pressure_channel.currentIndex()
        if (
            acquisition is None
            or not self._pressure_enabled_for(channel_index)
            or not 0 <= channel_index < len(acquisition.channels)
        ):
            return []
        samples = self._displayed_samples(channel_index)
        first, last = inclusive_region_indices(acquisition.time, start, end)
        cycle_samples = samples[first:last]
        finite_indices = np.flatnonzero(np.isfinite(cycle_samples))
        if finite_indices.size == 0:
            return []
        finite_values = cycle_samples[finite_indices]
        local_peak = int(finite_indices[int(np.argmax(finite_values))])
        peak_index = first + local_peak
        peak_degrees = self._time_to_degrees(float(acquisition.time[peak_index]))
        rows = [
            ("P mín ciclo", self._format_value(float(np.min(finite_values)), "PSI")),
            ("P máx ciclo", self._format_value(float(np.max(finite_values)), "PSI")),
            ("Pico en", f"{peak_degrees:,.3f}°" if peak_degrees is not None else "—"),
        ]
        phase_duration = (end - start) / 4.0
        for index, (phase_name, _color) in enumerate(self._ordered_engine_phases()):
            phase_start = start + phase_duration * index
            phase_end = phase_start + phase_duration
            phase_first, phase_last = inclusive_region_indices(
                acquisition.time, phase_start, phase_end
            )
            phase_values = samples[phase_first:phase_last]
            phase_values = phase_values[np.isfinite(phase_values)]
            maximum = float(np.max(phase_values)) if phase_values.size else float("nan")
            rows.append((f"Máx. {phase_name}", self._format_value(maximum, "PSI")))
        return rows

    def _time_to_degrees(self, time_value: float) -> float | None:
        if self._cycle_reference is None:
            return None
        start, end = self._cycle_reference
        return (time_value - start) * 720.0 / (end - start)

    def _start_cursor_placement(self, kind: str) -> None:
        """Pide colocar con dos clics el par de cursores ``kind`` ("x" o "y").

        Si ya se está colocando otro par (o el ciclo motor), este espera en la
        cola en vez de interrumpirlo; antes, activar Y mientras se colocaba X
        dejaba los cursores X ocultos para siempre.
        """
        if self._placing_cursor is not None and self._placing_cursor[0] != kind:
            if kind not in self._placement_queue:
                self._placement_queue.append(kind)
            return
        label = kind.upper()
        self._placing_cursor = f"{kind}1"
        self.statusBar().showMessage(f"Cursores {label}: haga clic para colocar {label}1")

    def _finish_cursor_placement(self) -> None:
        """Termina la colocación actual y empieza la siguiente que esté en cola."""
        self._placing_cursor = None
        while self._placement_queue:
            kind = self._placement_queue.pop(0)
            checkbox = self.show_x_cursors if kind == "x" else self.show_y_cursors
            if checkbox.isChecked():
                self._start_cursor_placement(kind)
                self._refresh_measurements()
                return

    def _x_cursors_ready(self) -> bool:
        """Los cursores X están activos y ya colocados (no esperando clics)."""
        return (
            self.show_x_cursors.isChecked()
            and self._placing_cursor not in ("x1", "x2")
            and "x" not in self._placement_queue
        )

    def _y_cursors_ready(self) -> bool:
        return (
            self.show_y_cursors.isChecked()
            and self._placing_cursor not in ("y1", "y2")
            and "y" not in self._placement_queue
        )

    def _toggle_x_cursors(self, visible: bool) -> None:
        self.x_cursor_group.setEnabled(visible)
        if visible and self._acquisition is not None:
            self.cursor_x1.hide()
            self.cursor_x2.hide()
            self.region.hide()
            self._start_cursor_placement("x")
        else:
            if "x" in self._placement_queue:
                self._placement_queue.remove("x")
            if self._placing_cursor in ("x1", "x2"):
                self._finish_cursor_placement()
            self.cursor_x1.setVisible(visible)
            self.cursor_x2.setVisible(visible)
            self.region.setVisible(visible)
        self.use_region.setEnabled(visible)
        self.cursor_overlay.setVisible(self._show_cursor_overlay and self._any_cursor_visible())
        self._refresh_measurements()

    def _toggle_y_cursors(self, visible: bool) -> None:
        self.y_cursor_group.setEnabled(visible)
        if visible:
            low, high = self.plot.getViewBox().viewRange()[1]
            y1 = float(self.cursor_y1.value())
            y2 = float(self.cursor_y2.value())
            if not (low <= y1 <= high) or not (low <= y2 <= high):
                span = high - low
                self.cursor_y1.setValue(low + span * 0.35)
                self.cursor_y2.setValue(low + span * 0.65)
            if self._acquisition is not None:
                self.cursor_y1.hide()
                self.cursor_y2.hide()
                self._start_cursor_placement("y")
        else:
            if "y" in self._placement_queue:
                self._placement_queue.remove("y")
            if self._placing_cursor in ("y1", "y2"):
                self._finish_cursor_placement()
            self.cursor_y1.setVisible(False)
            self.cursor_y2.setVisible(False)
        self.cursor_overlay.setVisible(self._show_cursor_overlay and self._any_cursor_visible())
        self._refresh_measurements()

    def _place_requested_cursor(self, x_value: float, y_value: float) -> None:
        if self._placing_cursor == "cycle0":
            self._pending_cycle_start = x_value
            self._placing_cursor = "cycle720"
            self.statusBar().showMessage("Ciclo motor: haga clic en el punto de 720°")
            self._refresh_measurements()
            return
        if self._placing_cursor == "cycle720":
            if self._pending_cycle_start is not None:
                self._set_cycle_reference(self._pending_cycle_start, x_value)
            return
        if self._placing_cursor == "x1":
            self.cursor_x1.setValue(x_value)
            self.cursor_x1.show()
            self._placing_cursor = "x2"
            self.statusBar().showMessage("Cursores X: haga clic para colocar X2")
            self._refresh_measurements()
            return
        if self._placing_cursor == "x2":
            self.cursor_x2.setValue(x_value)
            self.cursor_x2.show()
            self.region.setRegion(sorted((float(self.cursor_x1.value()), x_value)))
            self.region.show()
            self._placing_cursor = None
            self._x_cursor_finished()
            self.statusBar().showMessage("Cursores X colocados; puede arrastrarlos")
            self._finish_cursor_placement()
            return
        if self._placing_cursor == "y1":
            self.cursor_y1.setValue(y_value)
            self.cursor_y1.show()
            self._placing_cursor = "y2"
            self.statusBar().showMessage("Cursores Y: haga clic para colocar Y2")
            self._refresh_measurements()
            return
        if self._placing_cursor == "y2":
            self.cursor_y2.setValue(y_value)
            self.cursor_y2.show()
            self._placing_cursor = None
            self._refresh_measurements()
            self.statusBar().showMessage("Cursores Y colocados; puede arrastrarlos")
            self._finish_cursor_placement()

    def _refresh_measurements(self) -> None:
        acquisition = self._acquisition
        if acquisition is None:
            return
        time1 = float(self.cursor_x1.value())
        time2 = float(self.cursor_x2.value())
        index1 = nearest_index(acquisition.time, time1)
        index2 = nearest_index(acquisition.time, time2)
        delta_time = abs(time2 - time1)
        frequency = 1.0 / delta_time if delta_time > 0 else None
        degrees1 = self._time_to_degrees(time1)
        degrees2 = self._time_to_degrees(time2)
        delta_degrees = abs(degrees2 - degrees1) if None not in (degrees1, degrees2) else None
        first, last = inclusive_region_indices(acquisition.time, time1, time2)

        x_visible = self._x_cursors_ready()
        y_visible = self._y_cursors_ready()
        vertical_unit = "PSI" if self._pressure_mode_active else "V"
        cursor_results = (
            self._format_time(time1) if x_visible else "—",
            self._format_time(time2) if x_visible else "—",
            self._format_time(delta_time) if x_visible else "—",
            self._format_value(frequency, "Hz") if frequency is not None and x_visible else "—",
            f"{degrees1:,.3f}°" if degrees1 is not None and x_visible else "—",
            f"{degrees2:,.3f}°" if degrees2 is not None and x_visible else "—",
            f"{delta_degrees:,.3f}°" if delta_degrees is not None and x_visible else "—",
            f"{index1:,}" if x_visible else "—",
            f"{index2:,}" if x_visible else "—",
            f"{last - first:,}" if x_visible else "—",
            self._format_value(float(self.cursor_y1.value()), vertical_unit)
            if y_visible
            else "—",
            self._format_value(float(self.cursor_y2.value()), vertical_unit)
            if y_visible
            else "—",
            self._format_value(
                abs(float(self.cursor_y2.value()) - float(self.cursor_y1.value())),
                vertical_unit,
            )
            if y_visible
            else "—",
        )
        self._show_cursor_readouts(cursor_results, vertical_unit)

        if not self.use_region.isChecked() or not x_visible:
            first, last = 0, acquisition.sample_count

        visible = self._visible_channel_indices()
        self.cursor_values.setRowCount(len(visible) if x_visible else 0)
        needs_statistics = not self.statistics_panel.isHidden() or self._show_stats_overlay
        if x_visible:
            for visible_row, channel_index in enumerate(visible):
                self._fill_cursor_value_row(visible_row, channel_index, index1, index2)
        if not needs_statistics:
            self.statistics.setRowCount(0)
            self._update_cursor_overlay(cursor_results)
            self.stats_overlay.hide()
            if self._cycle_reference is not None:
                self._update_cycle_overlay()
            self._position_overlays()
            self._sync_numeric_cursors()
            self._update_partition_lines()
            return

        # El cálculo de estadísticas/pulsos/flancos (calculate_statistics,
        # calculate_pulse_measurements, calculate_edge_measurements y, con dos
        # canales visibles, estimate_delay_and_phase) puede tardar segundos en
        # capturas grandes. open_file() deja este panel abierto por defecto, así
        # que se despacha a un hilo aparte (_dispatch_statistics) en vez de
        # bloquear la UI aquí; el resto de la vista (cursores, overlays, líneas
        # de partición) se actualiza de inmediato, sin esperar ese resultado.
        channel_specs = [
            (
                channel_index,
                acquisition.time[first:last],
                self._displayed_samples(channel_index)[first:last],
            )
            for channel_index in visible
        ]
        phase_specs = None
        if len(visible) >= 2:
            phase_specs = (
                acquisition.time[first:last],
                self._displayed_samples(visible[0])[first:last],
                self._displayed_samples(visible[1])[first:last],
            )
        # Se limpia de inmediato en vez de dejar la tabla de la carga/selección
        # anterior a la vista mientras el hilo calcula - el statusBar (puesto en
        # _start_statistics_worker) es el indicador de que hay un cálculo en curso.
        self.statistics.setRowCount(0)
        self._dispatch_statistics(channel_specs, phase_specs)

        self._update_cursor_overlay(cursor_results)
        if self._cycle_reference is not None:
            self._update_cycle_overlay()
        self._position_overlays()
        self._sync_numeric_cursors()
        self._update_partition_lines()

    def _show_cursor_readouts(self, values: tuple[str, ...], vertical_unit: str) -> None:
        """Vuelca los resultados (en el orden de ``CURSOR_ROWS``) en la pestaña."""
        by_name = dict(zip(CURSOR_ROWS, values, strict=True))
        readouts = self._cursor_readouts
        readouts["Δt"].setText(by_name["Δt"])
        readouts["1/Δt"].setText(by_name["1/Δt"])
        readouts["Muestras"].setText(
            "—"
            if by_name["Muestras"] == "—"
            else f"{by_name['Muestras']}   (índices {by_name['Índice X1']} – {by_name['Índice X2']})"
        )
        readouts["Grados"].setText(
            f"X1 {by_name['X1 (grados)']} · X2 {by_name['X2 (grados)']} · Δ {by_name['Δ grados']}"
        )
        has_cycle = self._cycle_reference is not None
        readouts["Grados"].setVisible(has_cycle)
        self._cursor_readout_titles["Grados"].setVisible(has_cycle)
        readouts["ΔY"].setText(by_name["ΔY"])
        self.y1_numeric.set_unit(vertical_unit)
        self.y2_numeric.set_unit(vertical_unit)

    def _fill_cursor_value_row(
        self, visible_row: int, channel_index: int, index1: int, index2: int
    ) -> None:
        acquisition = self._acquisition
        if acquisition is None:
            return
        channel = acquisition.channels[channel_index]
        displayed_samples = self._displayed_samples(channel_index)
        display_unit = self._display_unit(channel_index)
        value1 = float(displayed_samples[index1])
        value2 = float(displayed_samples[index2])
        color = CHANNEL_COLORS[channel_index % len(CHANNEL_COLORS)]
        self._fill_row(
            self.cursor_values,
            visible_row,
            (
                channel.name,
                self._format_value(value1, display_unit),
                self._format_value(value2, display_unit),
                self._format_value(value2 - value1, display_unit),
            ),
            color,
        )

    def _dispatch_statistics(
        self,
        channel_specs: list[tuple[int, np.ndarray, np.ndarray]],
        phase_specs: tuple[np.ndarray, np.ndarray, np.ndarray] | None,
    ) -> None:
        self._stats_request_id += 1
        request_id = self._stats_request_id
        if self._stats_worker_busy:
            # Un cálculo anterior sigue en curso: no se apilan hilos, solo se
            # recuerda el pedido más reciente y se descarta cualquier otro que
            # estuviera pendiente - en cuanto termine el actual se dispara este.
            self._stats_pending_args = (request_id, channel_specs, phase_specs)
            return
        self._start_statistics_worker(request_id, channel_specs, phase_specs)

    def _start_statistics_worker(
        self,
        request_id: int,
        channel_specs: list[tuple[int, np.ndarray, np.ndarray]],
        phase_specs: tuple[np.ndarray, np.ndarray, np.ndarray] | None,
    ) -> None:
        self._stats_worker_busy = True
        self.statusBar().showMessage("Calculando estadísticas…")
        thread = QThread(self)
        worker = _StatisticsWorker(request_id, channel_specs, phase_specs)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_statistics_ready)
        worker.failed.connect(self._on_statistics_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(self._on_statistics_thread_finished)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._stats_thread = thread
        self._stats_worker = worker
        thread.start()

    def _on_statistics_thread_finished(self) -> None:
        self._stats_worker_busy = False
        self._stats_thread = None
        self._stats_worker = None
        if self._stats_pending_args is not None:
            request_id, channel_specs, phase_specs = self._stats_pending_args
            self._stats_pending_args = None
            self._start_statistics_worker(request_id, channel_specs, phase_specs)

    def _on_statistics_ready(
        self,
        request_id: int,
        results: list[tuple[int, object, object, object]],
        phase_result: tuple[float | None, float | None] | None,
    ) -> None:
        acquisition = self._acquisition
        if request_id != self._stats_request_id or acquisition is None:
            return  # una petición más nueva ya está en curso o se cerró el archivo
        self.statistics.setRowCount(len(results))
        stats_overlay_rows: list[tuple[str, str, str, str, str, str, str, str]] = []
        visible: list[int] = []
        for row_index, (channel_index, statistics, pulse, edges) in enumerate(results):
            visible.append(channel_index)
            channel = acquisition.channels[channel_index]
            display_unit = self._display_unit(channel_index)
            color = CHANNEL_COLORS[channel_index % len(CHANNEL_COLORS)]
            frequency_text = (
                f"{pulse.frequency:,.6g} Hz" if pulse.frequency is not None else "—"
            )
            duty_text = (
                f"{pulse.duty_positive:,.3f} %"
                if pulse.duty_positive is not None
                else "—"
            )
            statistic_values = (
                channel.name,
                self._format_value(statistics.minimum, display_unit),
                self._format_value(statistics.maximum, display_unit),
                self._format_value(statistics.peak_to_peak, display_unit),
                self._format_value(statistics.mean, display_unit),
                self._format_value(statistics.rms, display_unit),
                frequency_text,
                duty_text,
                self._format_time(edges.rise_time) if edges.rise_time is not None else "—",
                self._format_time(edges.fall_time) if edges.fall_time is not None else "—",
                self._format_time(edges.high_width) if edges.high_width is not None else "—",
                self._format_time(edges.low_width) if edges.low_width is not None else "—",
                f"{edges.rising_edges:,}",
                f"{edges.falling_edges:,}",
                self._format_value(edges.overshoot, display_unit)
                if edges.overshoot is not None
                else "—",
                self._format_value(edges.undershoot, display_unit)
                if edges.undershoot is not None
                else "—",
                f"{statistics.count_valid:,}/{statistics.count_total:,}",
            )
            self._fill_row(self.statistics, row_index, statistic_values, color)
            stats_overlay_rows.append(
                (
                    channel.name,
                    self._format_value(statistics.minimum, display_unit),
                    self._format_value(statistics.maximum, display_unit),
                    self._format_value(statistics.peak_to_peak, display_unit),
                    self._format_value(statistics.mean, display_unit),
                    self._format_value(statistics.rms, display_unit),
                    frequency_text,
                    duty_text,
                )
            )
        self._update_stats_overlay(stats_overlay_rows)
        if phase_result is not None and len(visible) >= 2:
            delay, phase = phase_result
            delay_text = self._format_time(delay) if delay is not None else "—"
            phase_text = f"{phase:,.3f}°" if phase is not None else "—"
            self.phase_summary.setText(
                f"{acquisition.channels[visible[1]].name} respecto a "
                f"{acquisition.channels[visible[0]].name}: "
                f"retardo {delay_text} · fase {phase_text}"
            )
        else:
            self.phase_summary.setText("Retardo/fase: seleccione al menos dos canales")
        self.statusBar().clearMessage()

    def _on_statistics_failed(self, request_id: int, message: str) -> None:
        if request_id != self._stats_request_id:
            return
        self.statusBar().showMessage(f"No se pudieron calcular las estadísticas: {message}", 5000)

    def closeEvent(self, event) -> None:  # noqa: N802 - nombre impuesto por Qt
        # No se puede interrumpir un cálculo/import a mitad de camino; se
        # espera a que terminen para no destruir un QThread en marcha (evita
        # el crash/aviso "QThread destroyed while running").
        if self._stats_thread is not None:
            self._stats_thread.wait(5000)
        if self._import_thread is not None:
            self._import_thread.wait(5000)
        super().closeEvent(event)

    def _update_cursor_overlay(self, values: tuple[str, ...]) -> None:
        placement_prompts = {
            "x1": ("Cursores verticales", "Haga clic para colocar X1"),
            "x2": ("Cursores verticales", "Haga clic para colocar X2"),
            "y1": ("Cursores horizontales", "Haga clic para colocar Y1"),
            "y2": ("Cursores horizontales", "Haga clic para colocar Y2"),
            "cycle0": ("Ciclo motor", "Haga clic para colocar 0°"),
            "cycle720": ("Ciclo motor", "Haga clic para colocar 720°"),
        }
        if self._placing_cursor in placement_prompts:
            title, prompt = placement_prompts[self._placing_cursor]
            body = (
                "<tr><td><b style='color:#00e5ff'>" + title + "</b></td></tr>"
                "<tr><td style='padding-top:4px'>" + prompt + "</td></tr>"
            )
        else:
            rows: list[tuple[str, str]] = []
            if self._x_cursors_ready():
                rows.extend(zip(("X1", "X2", "Δt", "1/Δt"), values[:4], strict=True))
                if self._cycle_reference is not None:
                    rows.extend(
                        zip(("X1°", "X2°", "Δ°"), values[4:7], strict=True)
                    )
            if self._y_cursors_ready():
                rows.extend(zip(("Y1", "Y2", "ΔY"), values[10:13], strict=True))
            body = "".join(
                f"<tr><td style='padding-right:10px'>{label}</td><td><b>{value}</b></td></tr>"
                for label, value in rows
            )
        self.cursor_overlay.setHtml(
            "<div style='color:#f2f4f8;font-size:10pt'>"
            "<table cellpadding='2'>" + body + "</table></div>"
        )
        self.cursor_overlay.setVisible(
            self._placing_cursor in placement_prompts
            or (self._show_cursor_overlay and self._any_cursor_visible())
        )

    def _update_stats_overlay(
        self, rows: list[tuple[str, str, str, str, str, str, str, str]]
    ) -> None:
        header = (
            "<tr><td><b>Canal</b></td><td><b>Mín</b></td><td><b>Máx</b></td>"
            "<td><b>Pk-Pk</b></td><td><b>Media</b></td><td><b>RMS</b></td>"
            "<td><b>Freq</b></td><td><b>Duty+</b></td></tr>"
        )
        body = "".join(
            "<tr>" + "".join(f"<td style='padding-right:8px'>{value}</td>" for value in row) + "</tr>"
            for row in rows
        )
        self.stats_overlay.setHtml(
            "<div style='color:#f2f4f8;font-size:9pt'><table cellpadding='2'>"
            + header
            + body
            + "</table></div>"
        )
        self.stats_overlay.setVisible(self._show_stats_overlay)

    def _position_overlays(self, *_args: object) -> None:
        if not hasattr(self, "cursor_overlay"):
            return
        (x_low, x_high), (y_low, y_high) = self.view_box.viewRange()
        x_span = x_high - x_low
        y_span = y_high - y_low
        for name, item in (
            ("cursor", self.cursor_overlay),
            ("stats", self.stats_overlay),
            ("cycle", self.cycle_overlay),
        ):
            x_fraction, y_fraction = self._overlay_positions[name]
            item.setPos(x_low + x_span * x_fraction, y_low + y_span * y_fraction)
        if self._cycle_reference is not None:
            start, end = self._cycle_reference
            phase_span = (end - start) / 4.0
            label_y = y_high - y_span * 0.035
            for index, phase_label in enumerate(self._phase_labels):
                phase_label.setPos(start + phase_span * (index + 0.5), label_y)

    def _remember_overlay_position(self, name: str, item: pg.TextItem) -> None:
        (x_low, x_high), (y_low, y_high) = self.view_box.viewRange()
        x_span = x_high - x_low
        y_span = y_high - y_low
        if x_span <= 0 or y_span <= 0:
            return
        position = item.pos()
        self._overlay_positions[name] = (
            float(np.clip((position.x() - x_low) / x_span, 0.0, 1.0)),
            float(np.clip((position.y() - y_low) / y_span, 0.0, 1.0)),
        )

    @staticmethod
    def _fill_row(table: QTableWidget, row: int, values: tuple[str, ...], color: str) -> None:
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            if column == 0:
                item.setForeground(QBrush(QColor(color)))
            table.setItem(row, column, item)

    @staticmethod
    def _format_value(value: float, unit: str) -> str:
        return format_quantity(value, unit, 4)

    @staticmethod
    def _format_time(value: float) -> str:
        return format_quantity(value, "s", 5)

    def _show_full_view(self) -> None:
        if self._acquisition is None:
            return
        self.plot.setXRange(
            float(self._acquisition.time[0]),
            float(self._acquisition.time[-1]),
            padding=0,
        )
        self.plot.enableAutoRange(axis="y")
        self._update_time_div_label()

    def _auto_y(self) -> None:
        self.plot.enableAutoRange(axis="y")

    def _zoom_y(self, factor: float) -> None:
        low, high = self.plot.getViewBox().viewRange()[1]
        center = (low + high) / 2.0
        half_span = max((high - low) * factor / 2.0, np.finfo(float).eps)
        self.plot.getViewBox().disableAutoRange(axis="y")
        self.plot.setYRange(center - half_span, center + half_span, padding=0)

    def _change_display_mode(self, *_args: object) -> None:
        mode = self.display_mode.currentData()
        self.plot.setDownsampling(auto=True, mode=mode)
        for item in self._plot_items:
            item.setDownsampling(auto=True, method=mode)

    def _change_draw_style(self, *_args: object) -> None:
        for item in (*self._plot_items, *self._math_items):
            self._apply_draw_style(item)

    def _apply_draw_style(self, item: pg.PlotDataItem) -> None:
        """Dibuja ``item`` como vectores (líneas) o como puntos sueltos.

        El lápiz original se guarda en el ítem para restaurarlo al volver a
        vectores; en modo puntos el color del lápiz pasa al relleno del punto.
        """
        line_pen = getattr(item, "_osc_line_pen", None)
        if line_pen is None:
            line_pen = pg.mkPen(item.opts["pen"])
            item._osc_line_pen = line_pen
        if self.draw_style.currentData() == "dots":
            item.setPen(None)
            item.setSymbol("o")
            item.setSymbolSize(3)
            item.setSymbolPen(None)
            item.setSymbolBrush(line_pen.color())
        else:
            item.setSymbol(None)
            item.setPen(line_pen)

    def _update_time_div_label(self, *_args: object) -> None:
        low, high = self.view_box.viewRange()[0]
        self.time_div_label.setText(f"Time/div: {self._format_time((high - low) / 14.0)}")

    def _zoom_to_region(self) -> None:
        if self._acquisition is None:
            return
        start, end = sorted(self.region.getRegion())
        if end > start:
            self.plot.setXRange(start, end, padding=0.02)
