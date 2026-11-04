import struct
from pathlib import Path

import numpy as np
import pytest

from osc_app.core.siglent_slg_importer import SiglentSlgImporter, SlgImportError

FIRST_FRAME = 0x1000
FRAME_CAPACITY = 4
FRAME_STRIDE = 0x3C + FRAME_CAPACITY


def make_slg(path: Path, samples: np.ndarray, sample_rate: float = 1000.0) -> Path:
    samples = np.asarray(samples, dtype=np.uint8)
    frames = [samples[i : i + FRAME_CAPACITY] for i in range(0, samples.size, FRAME_CAPACITY)]
    header = bytearray(FIRST_FRAME)
    header[:4] = b"SPLG"
    struct.pack_into("<I", header, 0x08, 1)
    header[0x0C : 0x0C + 10] = b"SDS1104X-E"
    struct.pack_into("<I", header, 0x84, len(frames))
    struct.pack_into("<3d", header, 0x88, 0.05, sample_rate, samples.size / sample_rate)
    struct.pack_into(
        "<3Q", header, 0xA0, samples.size, FIRST_FRAME, FIRST_FRAME + FRAME_STRIDE * (len(frames) - 1)
    )
    struct.pack_into("<7I", header, 0xCC, 2026, 11, 4, 8, 6, 11, 592)
    for index in range(4):
        base = 0x280 + index * 0x100
        struct.pack_into("<I", header, base, int(index == 0))
        struct.pack_into("<3d", header, base + 0x10, 1.0, 0.12, 0.04)
        struct.pack_into("<I", header, base + 0x28, 128)
    body = bytearray()
    start = 0
    for index, frame in enumerate(frames):
        block = bytearray(FRAME_STRIDE)
        struct.pack_into("<4Q", block, 0, index, start, start + frame.size, frame.size)
        block[0x3C : 0x3C + frame.size] = frame.tobytes()
        body += block
        start += frame.size
    path.write_bytes(bytes(header) + bytes(body))
    return path


def test_imports_frames_and_skips_unused_tail(tmp_path: Path) -> None:
    raw = np.array([131, 131, 206, 206, 131, 206], dtype=np.uint8)
    result = SiglentSlgImporter().load(make_slg(tmp_path / "rec.slg", raw))

    assert result.report.active_channels == (1,)
    assert result.report.samples_per_channel == 6
    assert result.report.frame_count == 2
    assert result.acquisition.sample_rate == pytest.approx(1000.0)
    assert result.acquisition.time[0] == 0.0
    assert result.acquisition.channels[0].samples.tolist() == pytest.approx(
        [0.0, 0.0, 3.0, 3.0, 0.0, 3.0], abs=1e-6
    )
    assert result.acquisition.metadata["Modelo"] == "SDS1104X-E"
    assert result.report.warnings == ()


def test_rejects_wrong_magic(tmp_path: Path) -> None:
    path = make_slg(tmp_path / "bad.slg", np.full(4, 128))
    content = bytearray(path.read_bytes())
    content[:4] = b"XXXX"
    path.write_bytes(content)

    with pytest.raises(SlgImportError, match="SPLG"):
        SiglentSlgImporter().load(path)


def test_rejects_truncated_file(tmp_path: Path) -> None:
    path = make_slg(tmp_path / "short.slg", np.full(12, 128))
    path.write_bytes(path.read_bytes()[:-10])

    with pytest.raises(SlgImportError, match="incompleto"):
        SiglentSlgImporter().load(path)


SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "splg0001.slg"


@pytest.mark.skipif(not SAMPLE.is_file(), reason="archivo de ejemplo no disponible")
def test_imports_real_sds1104xe_recording() -> None:
    result = SiglentSlgImporter().load(SAMPLE)

    assert result.report.samples_per_channel == 5_515_800
    assert result.acquisition.sample_rate == pytest.approx(25_000.0)
    samples = result.acquisition.channels[0].samples
    assert np.percentile(samples, 5) == pytest.approx(0.0, abs=0.05)
    assert np.percentile(samples, 95) == pytest.approx(2.92, abs=0.05)
