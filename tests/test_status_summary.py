from pathlib import Path

import numpy as np
import pytest

from osc_app.core.models import Acquisition, Channel
from osc_app.core.status_summary import (
    build_status_summary,
    estimate_acquisition_memory_bytes,
    format_memory_bytes,
    format_sample_count,
    format_sample_rate,
)


def _sample_acquisition(samples: int = 1000) -> Acquisition:
    time = np.arange(samples, dtype=np.float64) / 1000.0
    channels = tuple(
        Channel(name=f"C{i + 1}", unit="V", samples=np.zeros(samples, dtype=np.float32))
        for i in range(4)
    )
    return Acquisition(source_file=Path("demo.csv"), time=time, channels=channels, metadata={})


def test_format_sample_count_uses_thousands_separator() -> None:
    assert format_sample_count(1_234_567) == "1,234,567"


def test_format_sample_rate_handles_missing_value() -> None:
    assert format_sample_rate(None) == "tasa no disponible"
    assert format_sample_rate(0) == "tasa no disponible"


def test_format_sample_rate_formats_with_thousands_and_precision() -> None:
    assert format_sample_rate(1_000_000) == "1,000,000.000 Sa/s"


@pytest.mark.parametrize(
    ("num_bytes", "expected"),
    [
        (0, "0 B"),
        (512, "512 B"),
        (2048, "2.0 KB"),
        (5 * 1024 * 1024, "5.0 MB"),
        (3 * 1024 * 1024 * 1024, "3.0 GB"),
    ],
)
def test_format_memory_bytes(num_bytes: int, expected: str) -> None:
    assert format_memory_bytes(num_bytes) == expected


def test_format_memory_bytes_rejects_negative_values() -> None:
    with pytest.raises(ValueError):
        format_memory_bytes(-1)


def test_estimate_acquisition_memory_bytes_sums_time_and_channels() -> None:
    acquisition = _sample_acquisition(samples=1000)

    total = estimate_acquisition_memory_bytes(acquisition)

    expected = acquisition.time.nbytes + sum(c.samples.nbytes for c in acquisition.channels)
    assert total == expected


def test_build_status_summary_contains_all_fields() -> None:
    summary = build_status_summary(
        file_name="demo.csv",
        sample_count=1000,
        duration=0.999,
        sample_rate=1000.0,
        active_channels=2,
        total_channels=4,
        memory_bytes=2048,
    )

    assert "demo.csv" in summary
    assert "1,000 muestras" in summary
    assert "1,000.000 Sa/s" in summary
    assert "canales 2/4" in summary
    assert "2.0 KB en memoria" in summary
