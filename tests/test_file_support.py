from pathlib import Path

from osc_app.core.file_support import is_supported_acquisition_file


def test_accepts_known_extensions_case_insensitively() -> None:
    assert is_supported_acquisition_file(Path("capture.csv"))
    assert is_supported_acquisition_file(Path("capture.CSV"))
    assert is_supported_acquisition_file(Path("capture.bin"))
    assert is_supported_acquisition_file(Path("capture.LWF"))


def test_rejects_unrelated_extensions() -> None:
    assert not is_supported_acquisition_file(Path("notes.txt"))
    assert not is_supported_acquisition_file(Path("archive.zip"))
    assert not is_supported_acquisition_file(Path("no_extension"))


def test_accepts_plain_string_paths() -> None:
    assert is_supported_acquisition_file("C:/captures/example.bin")
