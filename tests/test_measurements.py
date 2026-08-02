import numpy as np
import pytest

from osc_app.core.measurements import (
    calculate_pulse_measurements,
    calculate_statistics,
    inclusive_region_indices,
    nearest_index,
)


def test_statistics_ignore_non_finite_values() -> None:
    samples = np.array([1.0, 2.0, 3.0, np.nan, np.inf])

    result = calculate_statistics(samples)

    assert result.count_total == 5
    assert result.count_valid == 3
    assert result.minimum == 1
    assert result.maximum == 3
    assert result.mean == 2
    assert result.rms == pytest.approx(np.sqrt(14 / 3))
    assert result.peak_to_peak == 2


def test_nearest_index_chooses_closest_sample_and_clamps() -> None:
    time = np.array([0.0, 0.1, 0.2, 0.3])

    assert nearest_index(time, -10) == 0
    assert nearest_index(time, 0.16) == 2
    assert nearest_index(time, 10) == 3


def test_region_indices_include_both_ends() -> None:
    time = np.array([0.0, 0.1, 0.2, 0.3, 0.4])

    assert inclusive_region_indices(time, 0.3, 0.1) == (1, 4)


def test_pulse_measurements_calculate_frequency_and_positive_duty() -> None:
    time = np.arange(0.0, 0.01, 1e-5)
    samples = np.where((time % 0.001) < 0.00025, 5.0, 0.0)

    result = calculate_pulse_measurements(time, samples)

    assert result.frequency == pytest.approx(1000.0, rel=0.01)
    assert result.duty_positive == pytest.approx(25.0, abs=0.2)
    assert result.threshold == pytest.approx(2.5)


def test_pulse_measurements_reject_flat_signal() -> None:
    result = calculate_pulse_measurements(np.arange(5.0), np.ones(5))

    assert result.frequency is None
    assert result.duty_positive is None
