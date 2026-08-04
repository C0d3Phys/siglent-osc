from pathlib import Path

import numpy as np
import pytest

from osc_app.core.csv_importer import CsvImportError, GenericCsvImporter
from osc_app.tools.generate_sample_csv import generate_sample_csv


def test_generated_csv_imports_four_channels(tmp_path: Path) -> None:
    path = generate_sample_csv(tmp_path / "capture.csv", samples=1_001, sample_rate=50_000)

    result = GenericCsvImporter().load(path)

    assert result.acquisition.sample_count == 1_001
    assert [channel.name for channel in result.acquisition.channels] == [
        "CH1",
        "CH2",
        "CH3",
        "CH4",
    ]
    assert result.acquisition.sample_rate == pytest.approx(50_000)
    assert result.report.rows_accepted == 1_001
    assert result.report.rows_rejected == 0
    assert result.acquisition.metadata["Record Length"] == "1001"


def test_imported_arrays_are_read_only(tmp_path: Path) -> None:
    path = generate_sample_csv(tmp_path / "capture.csv", samples=10)
    acquisition = GenericCsvImporter().load(path).acquisition

    with pytest.raises(ValueError):
        acquisition.time[0] = 10
    with pytest.raises(ValueError):
        acquisition.channels[0].samples[0] = 10


def test_rejects_non_monotonic_time(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("Time(s),CH1(V)\n0,1\n0,2\n", encoding="utf-8")

    with pytest.raises(CsvImportError, match="estrictamente creciente"):
        GenericCsvImporter().load(path)


def test_signal_values_are_finite_except_explicit_bad_cells(tmp_path: Path) -> None:
    path = tmp_path / "nan.csv"
    path.write_text("Time(s),CH1(V)\n0,1\n0.1,bad\n", encoding="utf-8")

    result = GenericCsvImporter().load(path)

    assert np.isnan(result.acquisition.channels[0].samples[1])
    assert result.report.warnings


def test_accepts_hantek_square_bracket_headers(tmp_path: Path) -> None:
    path = tmp_path / "hantek.csv"
    path.write_text("Time [s],CH1 [V]\n0,0.1\n0.001,0.2\n", encoding="utf-8")

    acquisition = GenericCsvImporter().load(path).acquisition

    assert acquisition.channels[0].name == "CH1"
    assert acquisition.channels[0].unit == "V"
    assert acquisition.sample_rate == pytest.approx(1_000)


def test_accepts_hantek_trailing_delimiters(tmp_path: Path) -> None:
    path = tmp_path / "hantek.csv"
    path.write_text(
        "Time [s],CH1 [V]\n0,0.1,\n0.001,0.2,\n0.002,0.3,\n",
        encoding="utf-8",
    )

    acquisition = GenericCsvImporter().load(path).acquisition

    assert acquisition.sample_count == 3
