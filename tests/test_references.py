import numpy as np

from osc_app.core.references import reference_time_shift, transform_reference


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
