"""Pruebas de humo de la interfaz principal en modo Qt sin pantalla (offscreen).

Cubren el comportamiento nuevo: barra de herramientas (con la opción de
ocultarla), los tres paneles abriéndose al importar, las tarjetas por canal,
el resumen de estado permanente, los archivos recientes y el filtrado de
arrastrar-y-soltar. No sustituyen pruebas manuales de la interfaz, pero
detectan regresiones al instanciar y operar la ventana.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QMimeData, QSettings, QUrl
from PySide6.QtWidgets import QApplication

from osc_app.app.main_window import MainWindow
from osc_app.tools.generate_sample_csv import generate_sample_csv


class _FakeDropEvent:
    """Sustituto mínimo de QDropEvent/QDragEnterEvent para pruebas."""

    def __init__(self, urls: list[QUrl]) -> None:
        self._mime = QMimeData()
        self._mime.setUrls(urls)

    def mimeData(self) -> QMimeData:
        return self._mime


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


def test_importing_a_file_shows_all_panels(window, sample_csv) -> None:
    window.open_file(sample_csv)

    assert window.channel_panel.isHidden() is False
    assert window.cursor_panel.isHidden() is False
    assert window.statistics_panel.isHidden() is False
    assert window.channel_panel_action.isChecked() is True
    assert window.cursor_panel_action.isChecked() is True
    assert window.statistics_panel_action.isChecked() is True


def test_importing_a_file_builds_a_card_per_channel(window, sample_csv) -> None:
    window.open_file(sample_csv)

    assert len(window.channel_cards) == 4
    for expected_index, card in enumerate(window.channel_cards):
        assert card.index == expected_index
        assert "CH" in card.name_label.text()
        assert card.probe_control.value() > 0
        assert card.offset_control.value() == 0.0


def test_channel_card_color_matches_channel_colors(window, sample_csv) -> None:
    from osc_app.app.main_window import CHANNEL_COLORS

    window.open_file(sample_csv)

    for index, card in enumerate(window.channel_cards):
        assert CHANNEL_COLORS[index % len(CHANNEL_COLORS)] in card.styleSheet()


def test_importing_a_file_updates_permanent_status_summary(window, sample_csv) -> None:
    window.open_file(sample_csv)

    text = window.info.text()
    assert sample_csv.name in text
    assert "500 muestras" in text
    assert "canales 4/4" in text
    assert "en memoria" in text


def test_hiding_a_channel_updates_active_count_in_summary(window, sample_csv) -> None:
    window.open_file(sample_csv)

    window._channel_checks[0].setChecked(False)

    assert "canales 3/4" in window.info.text()


def test_importing_a_file_adds_it_to_recent_files(window, sample_csv) -> None:
    assert window._load_recent_files() == []

    window.open_file(sample_csv)

    assert window._load_recent_files() == [str(sample_csv)]


def test_recent_files_menu_offers_clear_and_reopen(window, sample_csv) -> None:
    window.open_file(sample_csv)

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
