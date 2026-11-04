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

    assert sample_csv.name in labels
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
