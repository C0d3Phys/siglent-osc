import struct
from pathlib import Path

import numpy as np
import pytest

from osc_app.core.siglent_bin_importer import BinImportError, SiglentBinImporter


def make_modern_bin(path: Path, channels: tuple[np.ndarray, ...]) -> Path:
    header = bytearray(0x800)
    for index in range(4):
        struct.pack_into("<I", header, index * 4, int(index < len(channels)))
        struct.pack_into("<d", header, 0x10 + index * 0x10, 0.05)
        struct.pack_into("<d", header, 0x50 + index * 0x10, -0.1)
    struct.pack_into("<d", header, 0xD4, 0.001)
    struct.pack_into("<d", header, 0xE4, 0.0)
    struct.pack_into("<I", header, 0xF4, channels[0].size)
    struct.pack_into("<d", header, 0xF8, 100_000.0)
    header[0x260] = 0
    with path.open("wb") as handle:
        handle.write(header)
        for channel in channels:
            handle.write(np.asarray(channel, dtype=np.uint8).tobytes())
    return path


def test_imports_modern_two_channel_bin(tmp_path: Path) -> None:
    path = make_modern_bin(
        tmp_path / "capture.bin",
        (
            np.array([128, 129, 130], dtype=np.uint8),
            np.array([100, 110, 120], dtype=np.uint8),
        ),
    )

    result = SiglentBinImporter().load(path)

    assert result.report.active_channels == (1, 2)
    assert result.report.samples_per_channel == 3
    assert result.acquisition.sample_rate == pytest.approx(100_000)
    assert result.acquisition.time[0] == pytest.approx(-0.007)
    assert result.acquisition.channels[0].samples.dtype == np.float32
    assert result.acquisition.channels[0].samples.tolist() == pytest.approx(
        [0.1, 0.102, 0.104]
    )


def test_applies_probe_factor_and_vertical_offset_sign(tmp_path: Path) -> None:
    path = make_modern_bin(tmp_path / "probe.bin", (np.array([54, 130], dtype=np.uint8),))
    content = bytearray(path.read_bytes())
    struct.pack_into("<d", content, 0x10, 0.1)
    struct.pack_into("<d", content, 0x50, -0.296)
    struct.pack_into("<d", content, 0x240, 10.0)
    path.write_bytes(content)

    result = SiglentBinImporter().load(path)

    assert result.acquisition.channels[0].samples.tolist() == pytest.approx([0.0, 3.04])
    assert result.acquisition.metadata["CH1 Probe"] == "10"
    assert result.acquisition.metadata["CH1 Scale"] == "1"


def test_rejects_inconsistent_file_size(tmp_path: Path) -> None:
    path = make_modern_bin(tmp_path / "bad.bin", (np.array([128, 129], dtype=np.uint8),))
    with path.open("ab") as handle:
        handle.write(b"extra")

    with pytest.raises(BinImportError, match="Tamaño BIN inconsistente"):
        SiglentBinImporter().load(path)


def test_rejects_unknown_header(tmp_path: Path) -> None:
    path = tmp_path / "unknown.bin"
    path.write_bytes(bytes(0x800))

    with pytest.raises(BinImportError, match="formato BIN moderno"):
        SiglentBinImporter().load(path)
