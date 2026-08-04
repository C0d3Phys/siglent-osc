import struct
from pathlib import Path

import numpy as np
import pytest

from osc_app.core.hantek_importer import (
    CHANNEL_OFFSET,
    CHANNEL_SIZE,
    HantekImportError,
    HantekLwfImporter,
)


def _write_lwf(tmp_path: Path, *, footer: bytes = b"\x78\x56\x34\x12") -> Path:
    raw = bytearray(CHANNEL_OFFSET + 4 * CHANNEL_SIZE)
    raw[:4] = b"lwf\x00"
    struct.pack_into("<I", raw, 4, 2001)
    struct.pack_into(
        "<HBBIIIdIIiI",
        raw,
        CHANNEL_OFFSET,
        0,
        1,
        21,
        4,
        4,
        0,
        1_000.0,
        0,
        0,
        -10,
        6,
    )
    raw.extend(np.asarray([-10, -9, -8, -7], dtype="<i2").tobytes())
    raw.extend(footer)
    path = tmp_path / "capture.lwf"
    path.write_bytes(raw)
    return path


def test_lwf_opens_without_csv_or_ref(tmp_path: Path) -> None:
    result = HantekLwfImporter().load(_write_lwf(tmp_path))

    assert result.acquisition.sample_count == 4
    assert result.acquisition.sample_rate == pytest.approx(1_000)
    assert result.acquisition.time.tolist() == pytest.approx([-0.001, 0, 0.001, 0.002])
    assert result.acquisition.channels[0].samples.tolist() == pytest.approx(
        [0, 0.002, 0.004, 0.006]
    )
    assert result.report.enabled_channels == (1,)


def test_rejects_invalid_footer(tmp_path: Path) -> None:
    path = _write_lwf(tmp_path, footer=b"bad!")

    with pytest.raises(HantekImportError, match="cierre esperado"):
        HantekLwfImporter().load(path)


def test_rejects_non_lwf_file(tmp_path: Path) -> None:
    path = tmp_path / "capture.csv"
    path.write_text("irrelevant", encoding="utf-8")

    with pytest.raises(HantekImportError, match="archivo binario Hantek"):
        HantekLwfImporter().load(path)
