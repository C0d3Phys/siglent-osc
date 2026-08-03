import numpy as np

from osc_app.core.math_channels import calculate_math_channel


def test_fixed_math_operations() -> None:
    time = np.array([0.0, 1.0, 2.0])
    first = np.array([1.0, 2.0, 4.0])
    second = np.array([1.0, 0.0, 2.0])

    np.testing.assert_allclose(calculate_math_channel(time, first, "add", second), [2, 2, 6])
    divided = calculate_math_channel(time, first, "divide", second)
    assert np.isnan(divided[1])
    np.testing.assert_allclose(calculate_math_channel(time, first, "integral"), [0, 1.5, 4.5])
