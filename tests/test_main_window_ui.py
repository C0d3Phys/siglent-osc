"""Pruebas de humo de la interfaz principal en modo Qt sin pantalla (offscreen).

Cubren el comportamiento nuevo: barra de herramientas (con la opción de
ocultarla), los paneles ocultos al importar, las tarjetas por canal,
el resumen de estado permanente, los archivos recientes y el filtrado de
arrastrar-y-soltar. No sustituyen pruebas manuales de la interfaz, pero
detectan regresiones al instanciar y operar la ventana.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QMimeData, QSettings, Qt, QUrl
from PySide6.QtWidgets import QApplication, QToolButton

from osc_app.app.main_window import MainWindow
from osc_app.tools.generate_sample_csv import generate_sample_csv


class _FakeDropEvent:
    """Sustituto mínimo de QDropEvent/QDragEnterEvent para pruebas."""

    def __init__(self, urls: list[QUrl]) -> None:
        self._mime = QMimeData()
        self._mime.setUrls(urls)

    def mimeData(self) -> QMimeData:
        return self._mime


def _open_and_wait(window: MainWindow, qapp, path: Path, *, timeout: float = 5.0, **kwargs) -> None:
    """Abre un archivo y bombea el event loop hasta que el import en segundo
    plano (ver ``_dispatch_import``/``_ImportWorker`` en main_window.py) haya
    terminado de aplicarse. ``open_file`` ya no bloquea - solo encola el
    trabajo - así que las pruebas deben esperar el resultado explícitamente
    en vez de asumir que vuelve aplicado de forma síncrona.
    """
    window.open_file(path, **kwargs)
    deadline = time.perf_counter() + timeout
    while window._import_worker_busy and time.perf_counter() < deadline:
        qapp.processEvents()
        time.sleep(0.005)
    assert not window._import_worker_busy, "la importación en background no terminó a tiempo"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    ini_path = str(tmp_path / "settings.ini")
    monkeypatch.setattr(
        "osc_app.app.main_window.QSettings",
        lambda *args, **kwargs: QSettings(ini_path, QSettings.Format.IniFormat),
    )
    win = MainWindow()
    yield win
    win.deleteLater()


@pytest.fixture
def sample_csv(tmp_path) -> Path:
    return generate_sample_csv(tmp_path / "sample.csv", samples=500, sample_rate=50_000.0)


def test_all_panels_hidden_before_any_import(window) -> None:
    assert window.channel_panel.isHidden()
    assert window.cursor_panel.isHidden()
    assert window.statistics_panel.isHidden()
    assert window.channel_panel_action.isChecked() is False
    assert window.cursor_panel_action.isChecked() is False
    assert window.statistics_panel_action.isChecked() is False


def test_importing_a_file_keeps_panels_hidden(window, qapp, sample_csv) -> None:
    _open_and_wait(window, qapp, sample_csv)

    assert window.channel_panel.isHidden()
    assert window.cursor_panel.isHidden()
    assert window.statistics_panel.isHidden()
    assert window.channel_panel_action.isChecked() is False
    assert window.cursor_panel_action.isChecked() is False
    assert window.statistics_panel_action.isChecked() is False


def test_importing_a_file_keeps_panels_the_user_opened(window, qapp, sample_csv) -> None:
    window.cursor_panel_action.setChecked(True)
    _open_and_wait(window, qapp, sample_csv)

    assert window.cursor_panel.isHidden() is False
    assert window.channel_panel.isHidden()
    assert window.statistics_panel.isHidden()


def test_importing_a_file_builds_a_card_per_channel(window, qapp, sample_csv) -> None:
    _open_and_wait(window, qapp, sample_csv)

    assert len(window.channel_cards) == 4
    for expected_index, card in enumerate(window.channel_cards):
        assert card.index == expected_index
        assert "CH" in card.name_label.text()
        assert card.probe_control.value() > 0
        assert card.offset_control.value() == 0.0


def test_channel_card_color_matches_channel_colors(window, qapp, sample_csv) -> None:
    from osc_app.app.main_window import CHANNEL_COLORS

    _open_and_wait(window, qapp, sample_csv)

    assert window.channel_cards, "se esperaba al menos una tarjeta de canal"
    for index, card in enumerate(window.channel_cards):
        assert CHANNEL_COLORS[index % len(CHANNEL_COLORS)] in card.styleSheet()


def test_importing_a_file_updates_permanent_status_summary(window, qapp, sample_csv) -> None:
    _open_and_wait(window, qapp, sample_csv)

    text = window.info.text()
    assert sample_csv.name in text
    assert "500 muestras" in text
    assert "canales 4/4" in text
    assert "en memoria" in text


def test_hiding_a_channel_updates_active_count_in_summary(window, qapp, sample_csv) -> None:
    _open_and_wait(window, qapp, sample_csv)

    window._channel_checks[0].setChecked(False)

    assert "canales 3/4" in window.info.text()


def test_importing_a_file_adds_it_to_recent_files(window, qapp, sample_csv) -> None:
    assert window._load_recent_files() == []

    _open_and_wait(window, qapp, sample_csv)

    assert window._load_recent_files() == [str(sample_csv)]


def test_recent_files_menu_offers_clear_and_reopen(window, qapp, sample_csv) -> None:
    _open_and_wait(window, qapp, sample_csv)

    window._rebuild_recent_files_menu()
    labels = [action.text() for action in window.recent_files_menu.actions()]

    assert any(label.startswith(f"{sample_csv.name}   —   ") for label in labels)
    assert "Limpiar lista" in labels

    window._clear_recent_files()
    assert window._load_recent_files() == []


def test_toolbar_exposes_frequent_actions(window) -> None:
    toolbars = [child for child in window.children() if child.__class__.__name__ == "QToolBar"]
    assert toolbars, "se esperaba al menos una QToolBar"

    toolbar_actions = [action for action in toolbars[0].actions() if not action.isSeparator()]
    assert window.open_action in toolbar_actions
    assert window.save_image_action in toolbar_actions
    assert window.fft_action in toolbar_actions
    assert window.math_channel_action in toolbar_actions
    assert all(not action.icon().isNull() for action in toolbar_actions)


def test_toolbar_can_be_hidden_from_the_view_menu(window, qapp) -> None:
    window.show()
    qapp.processEvents()
    assert window.main_toolbar.isVisible() is True
    assert window.toolbar_toggle_action.isChecked() is True

    window.toolbar_toggle_action.trigger()
    qapp.processEvents()

    assert window.main_toolbar.isVisible() is False
    assert window.toolbar_toggle_action.isChecked() is False
    assert window.toolbar_toggle_action in window.view_menu.actions()


def test_drop_path_accepts_supported_extension_and_rejects_others(window) -> None:
    accepted = _FakeDropEvent([QUrl.fromLocalFile("/tmp/example.csv")])
    rejected = _FakeDropEvent([QUrl.fromLocalFile("/tmp/example.txt")])

    assert window._acceptable_drop_path(accepted) == Path("/tmp/example.csv")
    assert window._acceptable_drop_path(rejected) is None


def test_draw_style_switches_between_vectors_and_dots(window, qapp, sample_csv) -> None:
    _open_and_wait(window, qapp, sample_csv)
    item = window._plot_items[0]
    line_color = item.opts["pen"].color()
    assert item.opts["symbol"] is None

    window.draw_style.setCurrentIndex(window.draw_style.findData("dots"))
    assert item.opts["symbol"] == "o"
    assert item.opts["pen"].style() == Qt.PenStyle.NoPen
    assert item.opts["symbolBrush"].color() == line_color

    window.draw_style.setCurrentIndex(window.draw_style.findData("vectors"))
    assert item.opts["symbol"] is None
    assert item.opts["pen"].color() == line_color


def test_channel_card_changes_coupling_and_polarity(window, qapp, sample_csv) -> None:
    _open_and_wait(window, qapp, sample_csv)
    card = window.channel_cards[1]

    card.coupling_control.setCurrentIndex(card.coupling_control.findData("ac_mean"))
    card.coupling_control.activated.emit(card.coupling_control.currentIndex())
    assert window._coupling_modes[1] == "ac_mean"

    card.invert_button.setChecked(True)
    assert window._channel_inverted[1] is True


def test_channel_card_probe_presets_set_the_factor(window, qapp, sample_csv) -> None:
    _open_and_wait(window, qapp, sample_csv)
    card = window.channel_cards[0]
    preset = next(
        button for button in card.findChildren(QToolButton) if button.text() == "10X"
    )

    preset.click()

    assert card.probe_control.value() == 10.0
    assert window._applied_probe_factors[0] == 10.0


def test_pressure_settings_open_in_tools_panel(window) -> None:
    window._show_pressure_settings()

    assert window.cursor_panel.isHidden() is False
    assert window.tools_tabs.currentWidget() is window.pressure_tab


def test_enabling_x_then_y_places_both_cursor_pairs(window, qapp, sample_csv) -> None:
    _open_and_wait(window, qapp, sample_csv)
    window.toggle_x_cursors_action.setChecked(True)
    window.toggle_y_cursors_action.setChecked(True)

    assert window._placing_cursor == "x1"
    for x_value in (0.001, 0.002):
        window._place_requested_cursor(x_value, 0.0)
    assert window._placing_cursor == "y1"
    for y_value in (0.5, 1.5):
        window._place_requested_cursor(0.0, y_value)

    assert window._placing_cursor is None
    assert window.cursor_x1.isVisible() and window.cursor_x2.isVisible()
    assert window.cursor_y1.isVisible() and window.cursor_y2.isVisible()
    assert window._cursor_readouts["ΔY"].text() == "1.000 V"


def test_cursor_results_stay_empty_until_cursors_are_placed(window, qapp, sample_csv) -> None:
    _open_and_wait(window, qapp, sample_csv)
    window.toggle_x_cursors_action.setChecked(True)

    assert window._cursor_readouts["Δt"].text() == "—"
    assert window.cursor_values.rowCount() == 0

    window._place_requested_cursor(0.001, 0.0)
    window._place_requested_cursor(0.003, 0.0)

    assert window._cursor_readouts["Δt"].text() == "2.0000 ms"
    assert window.cursor_values.rowCount() == 4


def test_cursor_field_accepts_values_with_si_prefix(window, qapp, sample_csv) -> None:
    _open_and_wait(window, qapp, sample_csv)
    window.toggle_x_cursors_action.setChecked(True)
    window._place_requested_cursor(0.001, 0.0)
    window._place_requested_cursor(0.003, 0.0)

    window.x2_numeric.setText("2.5 ms")
    window.x2_numeric.setModified(True)
    window.x2_numeric.editingFinished.emit()

    assert float(window.cursor_x2.value()) == pytest.approx(0.0025)
    assert window.x2_numeric.text() == "2.50000 ms"

    window.x2_numeric.setText("abc")
    window.x2_numeric.setModified(True)
    window.x2_numeric.editingFinished.emit()
    assert float(window.cursor_x2.value()) == pytest.approx(0.0025)
    assert window.x2_numeric.text() == "2.50000 ms"


def _all_menu_texts(window) -> list[str]:
    texts: list[str] = []

    def collect(menu) -> None:
        for action in menu.actions():
            texts.append(action.text())
            if action.menu() is not None:
                collect(action.menu())

    for top in window.menuBar().actions():
        texts.append(top.text())
        collect(top.menu())
    return texts


def test_menus_do_not_expose_internal_plot_menus(window) -> None:
    texts = _all_menu_texts(window)

    for internal in ("Opciones de trazado", "Navegación y ejes", "3 button", "Transforms"):
        assert internal not in texts
    assert "Ay&uda" in texts


def test_grid_option_toggles_plot_grid(window) -> None:
    assert window.grid_action.isChecked()

    window.grid_action.setChecked(False)

    assert window.plot.getAxis("bottom").grid is False


def test_clear_cycle_is_only_enabled_with_a_cycle(window, qapp, sample_csv) -> None:
    _open_and_wait(window, qapp, sample_csv)
    assert window.clear_cycle_action.isEnabled() is False

    window._begin_cycle_reference()
    window._place_requested_cursor(0.001, 0.0)
    window._place_requested_cursor(0.003, 0.0)
    assert window.clear_cycle_action.isEnabled() is True

    window.clear_cycle_action.trigger()
    assert window.clear_cycle_action.isEnabled() is False


def test_close_acquisition_resets_the_window_and_allows_reopening(
    window, qapp, sample_csv
) -> None:
    _open_and_wait(window, qapp, sample_csv)
    assert window.close_acquisition_action.isEnabled()

    window.close_acquisition_action.trigger()

    assert window._acquisition is None
    assert window.channel_cards == []
    assert window._plot_items == []
    assert window.close_acquisition_action.isEnabled() is False
    assert "Abra una adquisición" in window.info.text()

    _open_and_wait(window, qapp, sample_csv)
    assert len(window.channel_cards) == 4


def test_bring_cursors_into_view_places_them_inside_the_visible_range(
    window, qapp, sample_csv
) -> None:
    _open_and_wait(window, qapp, sample_csv)
    window.toggle_x_cursors_action.setChecked(True)
    window.toggle_y_cursors_action.setChecked(True)
    assert window.bring_cursors_action.isEnabled()

    window.bring_cursors_action.trigger()

    (x_low, x_high), (y_low, y_high) = window.plot.getViewBox().viewRange()
    assert x_low < float(window.cursor_x1.value()) < float(window.cursor_x2.value()) < x_high
    assert y_low < float(window.cursor_y1.value()) < float(window.cursor_y2.value()) < y_high
    assert window._placing_cursor is None
    assert window._cursor_readouts["Δt"].text() != "—"


def test_time_zoom_buttons_step_time_division_in_1_2_5(window, qapp, sample_csv) -> None:
    _open_and_wait(window, qapp, sample_csv)
    window.plot.setXRange(0.0, 14 * 1e-3, padding=0)  # 1 ms/div

    window.zoom_x_in_action.trigger()
    low, high = window.view_box.viewRange()[0]
    assert (high - low) / 14 == pytest.approx(0.5e-3)

    window.zoom_x_out_action.trigger()
    window.zoom_x_out_action.trigger()
    low, high = window.view_box.viewRange()[0]
    assert (high - low) / 14 == pytest.approx(2e-3)
    assert (low + high) / 2 == pytest.approx(7e-3)


def test_view_buttons_share_actions_and_shortcuts(window) -> None:
    assert window._view_buttons["x_in"].defaultAction() is window.zoom_x_in_action
    assert window._view_buttons["full_view"].text() == "Ver todo"
    shortcuts = {
        window.toggle_x_cursors_action: "X",
        window.toggle_y_cursors_action: "Y",
        window.auto_y_action: "A",
        window.zoom_region_action: "Z",
        window.zoom_x_in_action: "+",
        window.zoom_x_out_action: "-",
        window.bring_cursors_action: "C",
    }
    for action, expected in shortcuts.items():
        assert action.shortcut().toString() == expected


def test_open_button_offers_recent_files(window) -> None:
    open_button = window.main_toolbar.widgetForAction(window.open_action)

    assert open_button.menu() is window.recent_files_menu
    assert window.save_image_action.iconText() == "Guardar imagen"


def _menu_texts(menu) -> list[str]:
    return [action.text() for action in menu.actions() if not action.isSeparator()]


def test_zoom_to_region_requires_placed_x_cursors(window, qapp, sample_csv) -> None:
    _open_and_wait(window, qapp, sample_csv)
    before = window.view_box.viewRange()[0]

    assert window.zoom_region_action.isEnabled() is False
    window._zoom_to_region()
    assert window.view_box.viewRange()[0] == before

    window._place_cursor_here("x1", 0.001)
    assert window.zoom_region_action.isEnabled() is True


def test_context_menu_without_acquisition_only_offers_open(window) -> None:
    menu = window._build_plot_context_menu((0.0, 0.0))

    assert [action for action in menu.actions() if not action.isSeparator()] == [
        window.open_action
    ]


def test_context_menu_shows_point_values_and_placement_actions(
    window, qapp, sample_csv
) -> None:
    _open_and_wait(window, qapp, sample_csv)

    texts = _menu_texts(window._build_plot_context_menu((0.002, 1.0)))

    assert texts[0].startswith("t = ") and "CH1" in texts[0]
    assert "Colocar X1 aquí" in texts and "Colocar X2 aquí" in texts
    assert "Colocar Y1 aquí" not in texts  # cursores Y apagados
    assert window.zoom_region_action.text() in texts
    assert "Cancelar colocación" not in texts


def test_place_cursor_here_turns_on_cursors_and_keeps_both_visible(
    window, qapp, sample_csv
) -> None:
    _open_and_wait(window, qapp, sample_csv)

    window._place_cursor_here("x2", 0.003)

    assert window.show_x_cursors.isChecked()
    assert window._placing_cursor is None
    assert float(window.cursor_x2.value()) == pytest.approx(0.003)
    low, high = window.view_box.viewRange()[0]
    assert low <= float(window.cursor_x1.value()) <= high
    assert window._cursor_readouts["Δt"].text() != "—"


def test_cancel_placement_stops_waiting_for_clicks(window, qapp, sample_csv) -> None:
    _open_and_wait(window, qapp, sample_csv)
    window.toggle_x_cursors_action.setChecked(True)
    assert window.cancel_placement_action.isEnabled()
    assert "Cancelar colocación" in _menu_texts(window._build_plot_context_menu((0.0, 0.0)))

    window.cancel_placement_action.trigger()

    assert window._placing_cursor is None
    assert window.show_x_cursors.isChecked() is False


def test_copy_actions_put_tab_separated_tables_on_clipboard(window, qapp, sample_csv) -> None:
    _open_and_wait(window, qapp, sample_csv)
    window._place_cursor_here("x1", 0.001)
    window._place_cursor_here("x2", 0.003)

    window.copy_cursor_measurements_action.trigger()
    text = QApplication.clipboard().text()
    assert "Δt\t0.002\ts" in text
    assert "Canal\tEn X1\tEn X2\tDiferencia\tUnidad" in text

    window._copy_point_values(0.002)
    lines = QApplication.clipboard().text().splitlines()
    assert lines[0] == "Magnitud\tValor\tUnidad"
    assert lines[1].startswith("t\t") and lines[2].startswith("CH1\t")
