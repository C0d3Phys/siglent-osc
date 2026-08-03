import numpy as np

from osc_app.core.references import (
    compare_reference,
    reference_time_shift,
    transform_reference,
)


def test_reference_alignment_and_transform_do_not_mutate_source() -> None:
    time = np.array([0.0, 1.0, 2.0])
    samples = np.array([0.0, -3.0, 1.0], dtype=np.float32)
    original = samples.copy()

    assert reference_time_shift(
        time, samples, "x1", active_x1=4.0
    ) == 4.0
    assert reference_time_shift(
        time, samples, "peak", active_x1=5.0
    ) == 4.0
    transformed = transform_reference(samples, gain=2.0, offset=1.0)

    np.testing.assert_array_equal(samples, original)
    np.testing.assert_allclose(transformed, [1.0, -5.0, 3.0])


def test_reference_comparison_recovers_gain_offset_and_error() -> None:
    time = np.arange(0.0, 0.1, 1e-4)
    reference = np.sin(2 * np.pi * 100 * time)
    actual = 1.5 * reference + 0.25

    result = compare_reference(time, actual, time, reference)

    assert result.correlation is not None and result.correlation > 0.999
    assert result.gain is not None and np.isclose(result.gain, 1.5, atol=1e-3)
    assert result.offset is not None and np.isclose(result.offset, 0.25, atol=1e-3)
    assert result.rmse > 0
    np.testing.assert_allclose(result.error, actual - reference, atol=1e-6)
