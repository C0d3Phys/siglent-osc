import numpy as np

from osc_app.core.advanced_measurements import (
    calculate_edge_measurements,
    estimate_delay_and_phase,
)


def test_square_wave_edges_and_widths() -> None:
    time = np.arange(0.0, 0.01, 1e-5)
    samples = (np.sin(2 * np.pi * 1000 * time) >= 0).astype(float)
    result = calculate_edge_measurements(time, samples)

    assert result.rising_edges >= 8
    assert result.falling_edges >= 8
    assert result.high_width is not None
    assert np.isclose(result.high_width, 0.0005, atol=2e-5)


def test_delay_and_phase() -> None:
    time = np.arange(0.0, 0.05, 1e-4)
    first = np.sin(2 * np.pi * 100 * time)
    second = np.sin(2 * np.pi * 100 * (time - 0.001))
    delay, phase = estimate_delay_and_phase(time, first, second, 100.0)

    assert delay is not None and np.isclose(delay, 0.001, atol=1e-4)
    assert phase is not None and np.isclose(phase, 36.0, atol=4.0)
