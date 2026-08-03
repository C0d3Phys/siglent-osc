from __future__ import annotations

from pathlib import Path

import numpy as np
import pyqtgraph as pg
import pyqtgraph.exporters as pg_exporters
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QActionGroup, QBrush, QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from scipy.signal import lfilter, lfilter_zi

from osc_app.core.csv_importer import CsvImportError, GenericCsvImporter
from osc_app.core.measurements import (
    calculate_pulse_measurements,
    calculate_statistics,
    inclusive_region_indices,
    nearest_index,
)
from osc_app.core.models import Acquisition
from osc_app.core.siglent_bin_importer import BinImportError, SiglentBinImporter

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


class OscilloscopeViewBox(pg.ViewBox):
    """Rueda horizontal tipo Time/div; Ctrl+rueda controla V/div."""

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


class MainWindow(QMainWindow):
    """Visor CSV con paneles fijos para canales, cursores y mediciones."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OSC App — Análisis de señales")
        self._importer = GenericCsvImporter()
        self._bin_importer = SiglentBinImporter()
        self._acquisition: Acquisition | None = None
        self._updating_selection = False
        self._plot_items: list[pg.PlotDataItem] = []
        self._channel_checks: list[QCheckBox] = []
        self._native_probe_factors: list[float] = []
        self._applied_probe_factors: list[float] = []
        self._probe_controls: list[QDoubleSpinBox] = []
        self._coupling_modes: list[str] = []
        self._coupling_cache: dict[tuple[int, str, float], np.ndarray] = {}
        self._placing_cursor: str | None = None
        self._show_cursor_overlay = False
        self._show_stats_overlay = False
        self._pressure_mode_active = False
        self._cycle_reference: tuple[float, float] | None = None
        self._pending_cycle_start: float | None = None
        self._overlay_positions = {
            "cursor": (0.988, 0.975),
            "stats": (0.012, 0.025),
            "cycle": (0.5, 0.975),
        }
        self._build_ui()
        self._build_menu()

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
        self.left_panel_button = QToolButton()
        self.left_panel_button.setText("Canales")
        self.left_panel_button.setCheckable(True)
        self.left_panel_button.setChecked(False)
        self.left_panel_button.setToolTip("Mostrar u ocultar el panel de canales")
        self.left_panel_button.toggled.connect(self._set_channel_panel_visible)
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
        self.statistics_button = QToolButton()
        self.statistics_button.setText("Estadísticas")
        self.statistics_button.setCheckable(True)
        self.statistics_button.setChecked(False)
        self.statistics_button.setToolTip("Mostrar u ocultar la tabla inferior")
        self.statistics_button.toggled.connect(self._set_statistics_panel_visible)
        self.right_panel_button = QToolButton()
        self.right_panel_button.setText("Herramientas")
        self.right_panel_button.setCheckable(True)
        self.right_panel_button.setChecked(False)
        self.right_panel_button.setToolTip("Mostrar u ocultar cursores y ciclo motor")
        self.right_panel_button.toggled.connect(self._set_cursor_panel_visible)
        graph_buttons.addWidget(self.left_panel_button)
        graph_buttons.addSpacing(8)
        graph_buttons.addWidget(self.time_div_label)
        graph_buttons.addWidget(QLabel("Trazo:"))
        graph_buttons.addWidget(self.display_mode)
        graph_buttons.addStretch(1)
        graph_buttons.addWidget(auto_y_button)
        graph_buttons.addWidget(zoom_y_in_button)
        graph_buttons.addWidget(zoom_y_out_button)
        graph_buttons.addWidget(region_view_button)
        graph_buttons.addWidget(full_view_button)
        graph_buttons.addSpacing(8)
        graph_buttons.addWidget(self.statistics_button)
        graph_buttons.addWidget(self.right_panel_button)
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
        self.statistics.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        self.statistics_panel = QGroupBox("Estadísticas")
        statistics_layout = QVBoxLayout(self.statistics_panel)
        self.use_region = QCheckBox("Calcular sobre la región X1–X2")
        self.use_region.setChecked(True)
        self.use_region.toggled.connect(self._refresh_measurements)
        statistics_layout.addWidget(self.use_region)
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
        plot_item = pg.PlotItem(viewBox=self.view_box)
        self.plot_item = plot_item
        self.graph_navigation_menu = self.view_box.menu
        plot_item.setMenuEnabled(False)
        self.plot = pg.PlotWidget(background="#101419", plotItem=plot_item)
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.plot.setLabel("bottom", "Tiempo", units="s")
        self.plot.setLabel("left", "Amplitud", units="V")
        self.plot.setDownsampling(auto=True, mode="peak")
        self.plot.setClipToView(True)
        self.view_box.sigXRangeChanged.connect(self._update_time_div_label)
        self.view_box.sigRangeChanged.connect(self._position_overlays)
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
        self.channel_table = QTableWidget(0, 4)
        self.channel_table.setHorizontalHeaderLabels(["Ver", "Canal", "Sonda", "Solo"])
        self.channel_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.channel_table.verticalHeader().setVisible(False)
        self.channel_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.channel_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.channel_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.channel_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.channel_table, 1)

        show_all = QPushButton("Mostrar todos")
        show_all.clicked.connect(self._show_all_channels)
        hide_all = QPushButton("Ocultar todos")
        hide_all.clicked.connect(self._hide_all_channels)
        buttons = QHBoxLayout()
        buttons.addWidget(show_all)
        buttons.addWidget(hide_all)
        layout.addLayout(buttons)

        self.pressure_group = QGroupBox("Compresímetro (avanzado)")
        self.pressure_group.setCheckable(True)
        self.pressure_group.setChecked(False)
        pressure_outer_layout = QVBoxLayout(self.pressure_group)
        self.pressure_content = QWidget()
        pressure_layout = QFormLayout(self.pressure_content)
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
        pressure_outer_layout.addWidget(self.pressure_content)
        self.pressure_content.hide()
        self.pressure_group.toggled.connect(self.pressure_content.setVisible)
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
        layout.addWidget(self.pressure_group)
        return panel

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
        self.snap_x_to_samples = QCheckBox("Ajustar X a la muestra al soltar")
        self.snap_x_to_samples.setChecked(False)
        self.snap_x_to_samples.setToolTip(
            "Si está desactivado, X1 y X2 permanecen exactamente donde se sueltan"
        )
        self.snap_x_to_samples.toggled.connect(self._snap_option_changed)
        cursor_layout.addWidget(self.snap_x_to_samples)

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

        self.cursor_metrics = QTableWidget(len(CURSOR_ROWS), 2)
        self.cursor_metrics.setHorizontalHeaderLabels(["Medida", "Resultado"])
        self.cursor_metrics.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.cursor_metrics.verticalHeader().setVisible(False)
        self.cursor_metrics.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.cursor_metrics.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for row, label in enumerate(CURSOR_ROWS):
            self.cursor_metrics.setItem(row, 0, QTableWidgetItem(label))
            self.cursor_metrics.setItem(row, 1, QTableWidgetItem("—"))
            self.cursor_metrics.setRowHeight(row, 23)
        self.cursor_metrics.setMinimumHeight(250)
        cursor_layout.addWidget(self.cursor_metrics, 2)

        values_label = QLabel("Valores por canal")
        values_label.setStyleSheet("font-weight: 600;")
        cursor_layout.addWidget(values_label)
        self.cursor_values = QTableWidget(0, len(CURSOR_VALUE_COLUMNS))
        self.cursor_values.setHorizontalHeaderLabels(CURSOR_VALUE_COLUMNS)
        self.cursor_values.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.cursor_values.verticalHeader().setVisible(False)
        self.cursor_values.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        cursor_layout.addWidget(self.cursor_values, 1)

        tabs.addTab(cursor_tab, "Cursores")
        tabs.addTab(cycle_tab, "Ciclo motor")
        layout.addWidget(tabs)
        return panel

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&Archivo")
        open_action = file_menu.addAction("&Abrir adquisición…")
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.choose_acquisition)
        file_menu.addSeparator()
        save_image_action = file_menu.addAction("&Guardar imagen…")
        save_image_action.setShortcut("Ctrl+S")
        save_image_action.triggered.connect(self.save_plot_image)
        file_menu.addSeparator()
        file_menu.addAction("&Salir", self.close)

        channels_menu = self.menuBar().addMenu("&Canales")
        channels_menu.addAction("Mostrar todos", self._show_all_channels)
        channels_menu.addAction("Ocultar todos", self._hide_all_channels)
        channels_menu.addSeparator()
        channels_menu.addAction(
            "Configurar compresímetro…", lambda: self.pressure_group.setChecked(True)
        )

        cursors_menu = self.menuBar().addMenu("C&ursores")
        x_action = cursors_menu.addAction("Verticales X1/X2")
        x_action.setCheckable(True)
        x_action.setChecked(self.show_x_cursors.isChecked())
        x_action.toggled.connect(self.show_x_cursors.setChecked)
        self.show_x_cursors.toggled.connect(x_action.setChecked)
        y_action = cursors_menu.addAction("Horizontales Y1/Y2")
        y_action.setCheckable(True)
        y_action.setChecked(self.show_y_cursors.isChecked())
        y_action.toggled.connect(self.show_y_cursors.setChecked)
        self.show_y_cursors.toggled.connect(y_action.setChecked)

        tools_menu = self.menuBar().addMenu("&Herramientas")
        self.coupling_menu = tools_menu.addMenu("Acoplamiento DC/AC por canal")
        self.coupling_menu.aboutToShow.connect(self._rebuild_coupling_menu)

        analysis_menu = self.menuBar().addMenu("&Análisis")
        analysis_menu.addAction("Definir ciclo motor 0°–720°", self._begin_cycle_reference)
        analysis_menu.addAction("Quitar referencia angular", self._clear_cycle_reference)
        analysis_menu.addSeparator()
        analysis_menu.addAction("Zoom a región X1–X2", self._zoom_to_region)

        view_menu = self.menuBar().addMenu("&Opciones")
        view_menu.addAction("Vista completa", self._show_full_view)
        view_menu.addAction("Auto Y", self._auto_y)
        view_menu.addSeparator()
        self.channel_panel_action = view_menu.addAction("Panel de canales")
        self.channel_panel_action.setCheckable(True)
        self.channel_panel_action.setChecked(False)
        self.channel_panel_action.toggled.connect(self._set_channel_panel_visible)
        self.cursor_panel_action = view_menu.addAction("Panel de herramientas")
        self.cursor_panel_action.setCheckable(True)
        self.cursor_panel_action.setChecked(False)
        self.cursor_panel_action.toggled.connect(self._set_cursor_panel_visible)
        self.statistics_panel_action = view_menu.addAction("Panel de estadísticas")
        self.statistics_panel_action.setCheckable(True)
        self.statistics_panel_action.setChecked(False)
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
        self.left_panel_button.setChecked(visible)
        if hasattr(self, "channel_panel_action"):
            self.channel_panel_action.setChecked(visible)

    def _set_cursor_panel_visible(self, visible: bool) -> None:
        self.cursor_panel.setVisible(visible)
        self.right_panel_button.setChecked(visible)
        if hasattr(self, "cursor_panel_action"):
            self.cursor_panel_action.setChecked(visible)

    def _set_statistics_panel_visible(self, visible: bool) -> None:
        self.statistics_panel.setVisible(visible)
        self.statistics_button.setChecked(visible)
        if hasattr(self, "statistics_panel_action"):
            self.statistics_panel_action.setChecked(visible)
        if visible:
            upper_height = max(self.main_splitter.height() - 190, 320)
            self.main_splitter.setSizes([upper_height, 190])

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
            if pressure_locked:
                channel_menu.setToolTip("El compresímetro requiere acoplamiento DC")

    def choose_acquisition(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Abrir adquisición",
            str(Path.cwd()),
            "Adquisiciones (*.csv *.bin);;CSV (*.csv);;SIGLENT BIN (*.bin);;Todos (*.*)",
        )
        if selected:
            self.open_file(Path(selected))

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
        self.stats_overlay.setVisible(visible)

    def _any_cursor_visible(self) -> bool:
        return self.show_x_cursors.isChecked() or self.show_y_cursors.isChecked()

    def choose_csv(self) -> None:
        """Alias conservado para compatibilidad con la primera interfaz."""
        self.choose_acquisition()

    def open_csv(self, path: Path) -> None:
        """Abre un CSV o delega según la extensión para conservar compatibilidad."""
        self.open_file(path)

    def open_file(self, path: Path) -> None:
        self.statusBar().showMessage(f"Importando {path.name}…")
        try:
            if path.suffix.lower() == ".bin":
                result = self._bin_importer.load(path)
                accepted = result.report.samples_per_channel
            elif path.suffix.lower() == ".csv":
                result = self._importer.load(path)
                accepted = result.report.rows_accepted
            else:
                raise ValueError("Formato no compatible. Seleccione un archivo .csv o .bin.")
        except (BinImportError, CsvImportError, OSError, ValueError) as exc:
            QMessageBox.critical(self, "No se pudo abrir la adquisición", str(exc))
            self.statusBar().showMessage("Error de importación")
            return

        self.show_x_cursors.blockSignals(True)
        self.show_y_cursors.blockSignals(True)
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
        self._coupling_modes = ["dc"] * len(result.acquisition.channels)
        self._coupling_cache.clear()
        self.pressure_enabled.setChecked(False)
        self._pressure_mode_active = False
        self._clear_cycle_reference()
        self.channel_table.setRowCount(0)
        self._draw_acquisition(result.acquisition)
        self._populate_channel_panel(result.acquisition)
        self._initialize_selection()
        rate = result.acquisition.sample_rate
        rate_text = f"{rate:,.3f} Sa/s" if rate else "no disponible"
        self.info.setText(
            f"{path.name}  |  {result.acquisition.sample_count:,} muestras  |  "
            f"{result.acquisition.duration:.6g} s  |  {rate_text}  |  "
            f"{len(result.acquisition.channels)} canales"
        )
        self.statusBar().showMessage(
            f"Importación completa: {accepted:,} muestras por canal"
        )

    def _draw_acquisition(self, acquisition: Acquisition) -> None:
        self.plot.clear()
        self._plot_items.clear()
        self.plot.addLegend()
        for row, channel in enumerate(acquisition.channels):
            item = self.plot.plot(
                acquisition.time,
                channel.samples,
                pen=pg.mkPen(CHANNEL_COLORS[row % len(CHANNEL_COLORS)], width=1),
                name=channel.name,
            )
            self._plot_items.append(item)
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

    def _populate_channel_panel(self, acquisition: Acquisition) -> None:
        self.channel_table.setRowCount(len(acquisition.channels))
        self._channel_checks.clear()
        self.pressure_channel.blockSignals(True)
        self.pressure_channel.clear()
        self.pressure_channel.addItems([channel.name for channel in acquisition.channels])
        self.pressure_channel.blockSignals(False)
        for row, channel in enumerate(acquisition.channels):
            checkbox = QCheckBox()
            checkbox.setChecked(True)
            checkbox.setToolTip(f"Mostrar u ocultar {channel.name}")
            checkbox.toggled.connect(lambda checked, index=row: self._set_channel_visible(index, checked))
            checkbox_container = QWidget()
            checkbox_layout = QHBoxLayout(checkbox_container)
            checkbox_layout.setContentsMargins(0, 0, 0, 0)
            checkbox_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            checkbox_layout.addWidget(checkbox)
            self.channel_table.setCellWidget(row, 0, checkbox_container)
            self._channel_checks.append(checkbox)

            channel_item = QTableWidgetItem(f"{channel.name}  [{channel.unit}]  [DC]")
            channel_item.setForeground(QBrush(QColor(CHANNEL_COLORS[row % len(CHANNEL_COLORS)])))
            self.channel_table.setItem(row, 1, channel_item)

            metadata_key = f"{channel.name} Probe"
            try:
                native_probe = float(acquisition.metadata.get(metadata_key, "1"))
            except ValueError:
                native_probe = 1.0
            if not np.isfinite(native_probe) or native_probe <= 0:
                native_probe = 1.0
            self._native_probe_factors.append(native_probe)
            self._applied_probe_factors.append(native_probe)
            probe_control = QDoubleSpinBox()
            probe_control.setDecimals(2)
            probe_control.setRange(0.01, 1000.0)
            probe_control.setSingleStep(1.0)
            probe_control.setSuffix("X")
            probe_control.setValue(native_probe)
            probe_control.setToolTip(
                "Factor de atenuación de la sonda. Ajusta voltajes, gráfica y mediciones."
            )
            probe_control.valueChanged.connect(
                lambda value, index=row: self._set_probe_factor(index, value)
            )
            self._probe_controls.append(probe_control)
            self.channel_table.setCellWidget(row, 2, probe_control)

            solo_button = QPushButton("Solo")
            solo_button.setToolTip(f"Mostrar únicamente {channel.name}")
            solo_button.clicked.connect(lambda _checked=False, index=row: self._solo_channel(index))
            self.channel_table.setCellWidget(row, 3, solo_button)
        self.channel_table.resizeRowsToContents()

    def _set_channel_visible(self, index: int, visible: bool) -> None:
        if index < len(self._plot_items):
            self._plot_items[index].setVisible(visible)
        self._refresh_measurements()

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
        if index < len(self._plot_items):
            self._plot_items[index].setData(acquisition.time, samples)
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
        self._plot_items[index].setData(
            acquisition.time, self._displayed_samples(index)
        )
        self._update_channel_label(index)
        if self._channel_checks[index].isChecked():
            self._auto_y()
        label = dict(COUPLING_MODES)[mode]
        self.statusBar().showMessage(
            f"{acquisition.channels[index].name}: acoplamiento {label}"
        )
        self._refresh_measurements()

    def _update_channel_label(self, index: int) -> None:
        acquisition = self._acquisition
        if acquisition is None or not 0 <= index < len(acquisition.channels):
            return
        channel = acquisition.channels[index]
        unit = self._display_unit(index)
        coupling = "DC"
        if index < len(self._coupling_modes):
            coupling = dict(COUPLING_MODES)[self._coupling_modes[index]].split(" —", 1)[0]
        self.channel_table.item(index, 1).setText(
            f"{channel.name}  [{unit}]  [{coupling}]"
        )

    def _display_unit(self, index: int) -> str:
        acquisition = self._acquisition
        if acquisition is None:
            return "V"
        return "PSI" if self._pressure_enabled_for(index) else acquisition.channels[index].unit

    def _apply_pressure_configuration(self, *_args: object) -> None:
        acquisition = self._acquisition
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
            self._coupling_cache.clear()
        if requested and 0 <= selected < len(self._channel_checks):
            for index, checkbox in enumerate(self._channel_checks):
                checkbox.setChecked(index == selected)
        for index, item in enumerate(self._plot_items):
            item.setData(acquisition.time, self._displayed_samples(index))
            self._update_channel_label(index)
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

    def _begin_cycle_reference(self) -> None:
        if self._acquisition is None:
            QMessageBox.information(
                self, "Ciclo motor", "Abra una adquisición antes de definir el ciclo."
            )
            return
        self._pending_cycle_start = None
        self._placing_cursor = "cycle0"
        self.statusBar().showMessage("Ciclo motor: haga clic en el punto de 0°")
        self._refresh_measurements()

    def _clear_cycle_reference(self) -> None:
        self._cycle_reference = None
        self._pending_cycle_start = None
        if self._placing_cursor in ("cycle0", "cycle720"):
            self._placing_cursor = None
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

    def _toggle_x_cursors(self, visible: bool) -> None:
        if visible and self._acquisition is not None:
            self._placing_cursor = "x1"
            self.cursor_x1.hide()
            self.cursor_x2.hide()
            self.region.hide()
            self.statusBar().showMessage("Cursores X: haga clic para colocar X1")
        else:
            if self._placing_cursor in ("x1", "x2"):
                self._placing_cursor = None
            self.cursor_x1.setVisible(visible)
            self.cursor_x2.setVisible(visible)
            self.region.setVisible(visible)
        self.use_region.setEnabled(visible)
        self.cursor_overlay.setVisible(self._show_cursor_overlay and self._any_cursor_visible())
        self._refresh_measurements()

    def _toggle_y_cursors(self, visible: bool) -> None:
        if visible:
            low, high = self.plot.getViewBox().viewRange()[1]
            y1 = float(self.cursor_y1.value())
            y2 = float(self.cursor_y2.value())
            if not (low <= y1 <= high) or not (low <= y2 <= high):
                span = high - low
                self.cursor_y1.setValue(low + span * 0.35)
                self.cursor_y2.setValue(low + span * 0.65)
            if self._acquisition is not None:
                self._placing_cursor = "y1"
                self.cursor_y1.hide()
                self.cursor_y2.hide()
                self.statusBar().showMessage("Cursores Y: haga clic para colocar Y1")
        else:
            if self._placing_cursor in ("y1", "y2"):
                self._placing_cursor = None
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

        x_visible = self.show_x_cursors.isChecked()
        vertical_unit = "PSI" if self._pressure_mode_active else "V"
        cursor_results = (
            self._format_time(time1) if x_visible else "—",
            self._format_time(time2) if x_visible else "—",
            self._format_time(delta_time) if x_visible else "—",
            f"{frequency:,.6g} Hz" if frequency is not None and x_visible else "—",
            f"{degrees1:,.3f}°" if degrees1 is not None and x_visible else "—",
            f"{degrees2:,.3f}°" if degrees2 is not None and x_visible else "—",
            f"{delta_degrees:,.3f}°" if delta_degrees is not None and x_visible else "—",
            f"{index1:,}" if x_visible else "—",
            f"{index2:,}" if x_visible else "—",
            f"{last - first:,}" if x_visible else "—",
            self._format_value(float(self.cursor_y1.value()), vertical_unit)
            if self.show_y_cursors.isChecked()
            else "—",
            self._format_value(float(self.cursor_y2.value()), vertical_unit)
            if self.show_y_cursors.isChecked()
            else "—",
            self._format_value(
                abs(float(self.cursor_y2.value()) - float(self.cursor_y1.value())),
                vertical_unit,
            )
            if self.show_y_cursors.isChecked()
            else "—",
        )
        for row, value in enumerate(cursor_results):
            self.cursor_metrics.setItem(row, 1, QTableWidgetItem(value))

        if not self.use_region.isChecked() or not x_visible:
            first, last = 0, acquisition.sample_count

        visible = self._visible_channel_indices()
        self.cursor_values.setRowCount(len(visible) if x_visible else 0)
        self.statistics.setRowCount(len(visible))
        stats_overlay_rows: list[tuple[str, str, str, str, str, str, str, str]] = []
        for visible_row, channel_index in enumerate(visible):
            channel = acquisition.channels[channel_index]
            displayed_samples = self._displayed_samples(channel_index)
            display_unit = self._display_unit(channel_index)
            value1 = float(displayed_samples[index1])
            value2 = float(displayed_samples[index2])
            color = CHANNEL_COLORS[channel_index % len(CHANNEL_COLORS)]

            if x_visible:
                cursor_values = (
                    channel.name,
                    self._format_value(value1, display_unit),
                    self._format_value(value2, display_unit),
                    self._format_value(value2 - value1, display_unit),
                )
                self._fill_row(self.cursor_values, visible_row, cursor_values, color)

            statistics = calculate_statistics(displayed_samples[first:last])
            pulse = calculate_pulse_measurements(
                acquisition.time[first:last], displayed_samples[first:last]
            )
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
                f"{statistics.count_valid:,}/{statistics.count_total:,}",
            )
            self._fill_row(self.statistics, visible_row, statistic_values, color)
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
        self._update_cursor_overlay(cursor_results)
        self._update_stats_overlay(stats_overlay_rows)
        if self._cycle_reference is not None:
            self._update_cycle_overlay()
        self._position_overlays()

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
            if self.show_x_cursors.isChecked():
                rows.extend(zip(("X1", "X2", "Δt", "1/Δt"), values[:4], strict=True))
                if self._cycle_reference is not None:
                    rows.extend(
                        zip(("X1°", "X2°", "Δ°"), values[4:7], strict=True)
                    )
            if self.show_y_cursors.isChecked():
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
        return f"{value:.6g} {unit}" if np.isfinite(value) else "—"

    @staticmethod
    def _format_time(value: float) -> str:
        absolute = abs(value)
        if absolute < 1e-6:
            return f"{value * 1e9:.6g} ns"
        if absolute < 1e-3:
            return f"{value * 1e6:.6g} µs"
        if absolute < 0.9995:
            return f"{value * 1e3:.6g} ms"
        return f"{value:.6g} s"

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

    def _update_time_div_label(self, *_args: object) -> None:
        low, high = self.view_box.viewRange()[0]
        self.time_div_label.setText(f"Time/div: {self._format_time((high - low) / 14.0)}")

    def _zoom_to_region(self) -> None:
        if self._acquisition is None:
            return
        start, end = sorted(self.region.getRegion())
        if end > start:
            self.plot.setXRange(start, end, padding=0.02)
