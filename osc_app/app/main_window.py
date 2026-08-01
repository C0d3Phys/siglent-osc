from __future__ import annotations

from pathlib import Path

import numpy as np
import pyqtgraph as pg
import pyqtgraph.exporters as pg_exporters
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
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
    QVBoxLayout,
    QWidget,
)

from osc_app.core.csv_importer import CsvImportError, GenericCsvImporter
from osc_app.core.measurements import (
    calculate_statistics,
    inclusive_region_indices,
    nearest_index,
)
from osc_app.core.models import Acquisition
from osc_app.core.siglent_bin_importer import BinImportError, SiglentBinImporter

CHANNEL_COLORS = ("#ffd43b", "#4dabf7", "#ff6b6b", "#69db7c")
STATISTIC_COLUMNS = ("Canal", "Mínimo", "Máximo", "Pico-pico", "Media", "RMS", "N")
CURSOR_VALUE_COLUMNS = ("Canal", "En X1", "En X2", "Diferencia")
CURSOR_ROWS = (
    "X1",
    "X2",
    "Δt",
    "Frecuencia",
    "Índice X1",
    "Índice X2",
    "Muestras",
    "Y1",
    "Y2",
    "ΔY",
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
        self._probe_controls: list[QDoubleSpinBox] = []
        self._placing_cursor: str | None = None
        self._show_cursor_overlay = True
        self._show_stats_overlay = True
        self._overlay_positions = {
            "cursor": (0.988, 0.975),
            "stats": (0.012, 0.025),
        }
        self._build_ui()
        self._build_menu()

    def _build_ui(self) -> None:
        self._build_plot()
        channel_panel = self._build_channel_panel()
        cursor_panel = self._build_cursor_panel()

        graph_panel = QWidget()
        graph_layout = QVBoxLayout(graph_panel)
        graph_layout.setContentsMargins(0, 0, 0, 0)
        graph_layout.addWidget(self.plot, 1)

        graph_buttons = QHBoxLayout()
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
        region_view_button = QPushButton("Zoom a región")
        region_view_button.clicked.connect(self._zoom_to_region)
        full_view_button = QPushButton("Vista completa")
        full_view_button.clicked.connect(self._show_full_view)
        graph_buttons.addWidget(self.time_div_label)
        graph_buttons.addWidget(QLabel("Vista:"))
        graph_buttons.addWidget(self.display_mode)
        graph_buttons.addStretch(1)
        graph_buttons.addWidget(auto_y_button)
        graph_buttons.addWidget(zoom_y_in_button)
        graph_buttons.addWidget(zoom_y_out_button)
        graph_buttons.addWidget(region_view_button)
        graph_buttons.addWidget(full_view_button)
        graph_layout.addLayout(graph_buttons)

        upper_splitter = QSplitter(Qt.Orientation.Horizontal)
        upper_splitter.addWidget(channel_panel)
        upper_splitter.addWidget(graph_panel)
        upper_splitter.addWidget(cursor_panel)
        upper_splitter.setSizes([220, 760, 330])
        upper_splitter.setStretchFactor(1, 1)

        self.statistics = QTableWidget(0, len(STATISTIC_COLUMNS))
        self.statistics.setHorizontalHeaderLabels(STATISTIC_COLUMNS)
        self.statistics.setAlternatingRowColors(True)
        self.statistics.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.statistics.verticalHeader().setVisible(False)
        self.statistics.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        statistics_panel = QGroupBox("Estadísticas")
        statistics_layout = QVBoxLayout(statistics_panel)
        self.use_region = QCheckBox("Calcular sobre la región X1–X2")
        self.use_region.setChecked(True)
        self.use_region.toggled.connect(self._refresh_measurements)
        statistics_layout.addWidget(self.use_region)
        statistics_layout.addWidget(self.statistics)

        main_splitter = QSplitter(Qt.Orientation.Vertical)
        main_splitter.addWidget(upper_splitter)
        main_splitter.addWidget(statistics_panel)
        main_splitter.setSizes([580, 180])
        main_splitter.setStretchFactor(0, 4)
        main_splitter.setStretchFactor(1, 1)

        self.info = QLabel("Abra un CSV para comenzar.")
        self.info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout = QVBoxLayout()
        layout.addWidget(main_splitter, 1)
        layout.addWidget(self.info)
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)
        self.statusBar().showMessage("Listo")

    def _build_plot(self) -> None:
        self.view_box = OscilloscopeViewBox()
        plot_item = pg.PlotItem(viewBox=self.view_box)
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
        self.cursor_y1.hide()
        self.cursor_y2.hide()
        self.cursor_x1.sigPositionChanged.connect(self._x_cursor_dragged)
        self.cursor_x2.sigPositionChanged.connect(self._x_cursor_dragged)
        self.cursor_x1.sigPositionChangeFinished.connect(self._x_cursor_finished)
        self.cursor_x2.sigPositionChangeFinished.connect(self._x_cursor_finished)
        self.cursor_y1.sigPositionChanged.connect(self._refresh_measurements)
        self.cursor_y2.sigPositionChanged.connect(self._refresh_measurements)
        self.region.sigRegionChanged.connect(self._region_dragged)
        self.region.sigRegionChangeFinished.connect(self._region_finished)

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
        self.plot.addItem(self.cursor_overlay, ignoreBounds=True)
        self.plot.addItem(self.stats_overlay, ignoreBounds=True)

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
        return panel

    def _build_cursor_panel(self) -> QWidget:
        panel = QGroupBox("Cursores")
        layout = QVBoxLayout(panel)
        cursor_switches = QHBoxLayout()
        self.show_x_cursors = QCheckBox("Verticales X")
        self.show_x_cursors.setChecked(False)
        self.show_x_cursors.toggled.connect(self._toggle_x_cursors)
        self.show_y_cursors = QCheckBox("Horizontales Y")
        self.show_y_cursors.setChecked(False)
        self.show_y_cursors.toggled.connect(self._toggle_y_cursors)
        cursor_switches.addWidget(self.show_x_cursors)
        cursor_switches.addWidget(self.show_y_cursors)
        layout.addLayout(cursor_switches)
        self.snap_x_to_samples = QCheckBox("Ajustar X a la muestra al soltar")
        self.snap_x_to_samples.setChecked(False)
        self.snap_x_to_samples.setToolTip(
            "Si está desactivado, X1 y X2 permanecen exactamente donde se sueltan"
        )
        self.snap_x_to_samples.toggled.connect(self._snap_option_changed)
        layout.addWidget(self.snap_x_to_samples)
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
        self.cursor_metrics.setMinimumHeight(275)
        self.cursor_metrics.setMaximumHeight(300)
        layout.addWidget(self.cursor_metrics)

        values_label = QLabel("Valores por canal")
        values_label.setStyleSheet("font-weight: 600;")
        layout.addWidget(values_label)
        self.cursor_values = QTableWidget(0, len(CURSOR_VALUE_COLUMNS))
        self.cursor_values.setHorizontalHeaderLabels(CURSOR_VALUE_COLUMNS)
        self.cursor_values.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.cursor_values.verticalHeader().setVisible(False)
        self.cursor_values.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.cursor_values, 1)
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

        view_menu = self.menuBar().addMenu("&Vista")
        view_menu.addAction("Vista completa", self._show_full_view)
        view_menu.addAction("Zoom a región", self._zoom_to_region)
        view_menu.addSeparator()
        view_menu.addAction("Mostrar todos los canales", self._show_all_channels)

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
        x_action = menu.addAction("Cursores verticales X1/X2")
        x_action.setCheckable(True)
        x_action.setChecked(self.show_x_cursors.isChecked())
        x_action.toggled.connect(self.show_x_cursors.setChecked)
        y_action = menu.addAction("Cursores horizontales Y1/Y2")
        y_action.setCheckable(True)
        y_action.setChecked(self.show_y_cursors.isChecked())
        y_action.toggled.connect(self.show_y_cursors.setChecked)
        menu.addSeparator()
        cursor_table_action = menu.addAction("Tabla superpuesta de cursores")
        cursor_table_action.setCheckable(True)
        cursor_table_action.setChecked(self._show_cursor_overlay)
        cursor_table_action.toggled.connect(self._set_cursor_overlay_visible)
        stats_table_action = menu.addAction("Tabla superpuesta de estadísticas")
        stats_table_action.setCheckable(True)
        stats_table_action.setChecked(self._show_stats_overlay)
        stats_table_action.toggled.connect(self._set_stats_overlay_visible)
        menu.addSeparator()
        menu.addAction("Auto Y", self._auto_y)
        menu.addAction("Vista completa", self._show_full_view)
        menu.addAction("Guardar imagen…", self.save_plot_image)
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

        self._acquisition = result.acquisition
        self._channel_checks.clear()
        self._native_probe_factors.clear()
        self._probe_controls.clear()
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

            channel_item = QTableWidgetItem(f"{channel.name}  [{channel.unit}]")
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
        samples = self._samples_with_probe(index, factor)
        if index < len(self._plot_items):
            self._plot_items[index].setData(acquisition.time, samples)
        if index < len(self._channel_checks) and self._channel_checks[index].isChecked():
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
        self._refresh_measurements()

    def _x_cursor_finished(self) -> None:
        if self._updating_selection or self._acquisition is None:
            return
        if self.snap_x_to_samples.isChecked():
            self._set_selection(float(self.cursor_x1.value()), float(self.cursor_x2.value()))
        else:
            self._x_cursor_dragged()

    def _region_dragged(self) -> None:
        if self._updating_selection or self._acquisition is None:
            return
        start, end = self.region.getRegion()
        self._updating_selection = True
        self.cursor_x1.setValue(float(start))
        self.cursor_x2.setValue(float(end))
        self._updating_selection = False
        self._refresh_measurements()

    def _region_finished(self) -> None:
        if self._updating_selection or self._acquisition is None:
            return
        start, end = self.region.getRegion()
        if self.snap_x_to_samples.isChecked():
            self._set_selection(float(start), float(end))
        else:
            self._region_dragged()

    def _snap_option_changed(self, enabled: bool) -> None:
        if enabled and self._acquisition is not None:
            self._set_selection(float(self.cursor_x1.value()), float(self.cursor_x2.value()))

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
        if self._placing_cursor == "x1":
            self.cursor_x1.setValue(x_value)
            self.cursor_x1.show()
            self._placing_cursor = "x2"
            self.statusBar().showMessage("Cursores X: haga clic para colocar X2")
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
        first, last = inclusive_region_indices(acquisition.time, time1, time2)

        x_visible = self.show_x_cursors.isChecked()
        cursor_results = (
            self._format_time(time1) if x_visible else "—",
            self._format_time(time2) if x_visible else "—",
            self._format_time(delta_time) if x_visible else "—",
            f"{frequency:,.6g} Hz" if frequency is not None and x_visible else "—",
            f"{index1:,}" if x_visible else "—",
            f"{index2:,}" if x_visible else "—",
            f"{last - first:,}" if x_visible else "—",
            self._format_value(float(self.cursor_y1.value()), "V")
            if self.show_y_cursors.isChecked()
            else "—",
            self._format_value(float(self.cursor_y2.value()), "V")
            if self.show_y_cursors.isChecked()
            else "—",
            self._format_value(
                abs(float(self.cursor_y2.value()) - float(self.cursor_y1.value())), "V"
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
        stats_overlay_rows: list[tuple[str, str, str, str, str, str]] = []
        for visible_row, channel_index in enumerate(visible):
            channel = acquisition.channels[channel_index]
            displayed_samples = self._samples_with_probe(channel_index)
            value1 = float(displayed_samples[index1])
            value2 = float(displayed_samples[index2])
            color = CHANNEL_COLORS[channel_index % len(CHANNEL_COLORS)]

            if x_visible:
                cursor_values = (
                    channel.name,
                    self._format_value(value1, channel.unit),
                    self._format_value(value2, channel.unit),
                    self._format_value(value2 - value1, channel.unit),
                )
                self._fill_row(self.cursor_values, visible_row, cursor_values, color)

            statistics = calculate_statistics(displayed_samples[first:last])
            statistic_values = (
                channel.name,
                self._format_value(statistics.minimum, channel.unit),
                self._format_value(statistics.maximum, channel.unit),
                self._format_value(statistics.peak_to_peak, channel.unit),
                self._format_value(statistics.mean, channel.unit),
                self._format_value(statistics.rms, channel.unit),
                f"{statistics.count_valid:,}/{statistics.count_total:,}",
            )
            self._fill_row(self.statistics, visible_row, statistic_values, color)
            stats_overlay_rows.append(
                (
                    channel.name,
                    self._format_value(statistics.minimum, channel.unit),
                    self._format_value(statistics.maximum, channel.unit),
                    self._format_value(statistics.peak_to_peak, channel.unit),
                    self._format_value(statistics.mean, channel.unit),
                    self._format_value(statistics.rms, channel.unit),
                )
            )
        self._update_cursor_overlay(cursor_results)
        self._update_stats_overlay(stats_overlay_rows)
        self._position_overlays()

    def _update_cursor_overlay(self, values: tuple[str, ...]) -> None:
        if self._placing_cursor in ("x1", "x2"):
            prompt = "Coloque X1" if self._placing_cursor == "x1" else "Coloque X2"
            body = f"<tr><td colspan='2'><b>{prompt}</b></td></tr>"
        else:
            rows: list[tuple[str, str]] = []
            if self.show_x_cursors.isChecked():
                rows.extend(zip(("X1", "X2", "Δt", "Frecuencia"), values[:4], strict=True))
            if self.show_y_cursors.isChecked():
                rows.extend(zip(("Y1", "Y2", "ΔY"), values[7:10], strict=True))
            body = "".join(
                f"<tr><td style='padding-right:10px'>{label}</td><td><b>{value}</b></td></tr>"
                for label, value in rows
            )
        self.cursor_overlay.setHtml(
            "<div style='color:#f2f4f8;font-size:10pt'>"
            "<table cellpadding='2'>" + body + "</table></div>"
        )
        self.cursor_overlay.setVisible(self._show_cursor_overlay and self._any_cursor_visible())

    def _update_stats_overlay(self, rows: list[tuple[str, str, str, str, str, str]]) -> None:
        header = (
            "<tr><td><b>Canal</b></td><td><b>Mín</b></td><td><b>Máx</b></td>"
            "<td><b>Pk-Pk</b></td><td><b>Media</b></td><td><b>RMS</b></td></tr>"
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
        ):
            x_fraction, y_fraction = self._overlay_positions[name]
            item.setPos(x_low + x_span * x_fraction, y_low + y_span * y_fraction)

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
