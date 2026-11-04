import math

import pytest

from osc_app.core.quantity import format_quantity, parse_quantity


@pytest.mark.parametrize(
    ("value", "unit", "digits", "expected"),
    [
        (3.228514828, "V", 4, "3.229 V"),
        (-0.114691, "V", 4, "-114.7 mV"),
        (5.0, "V", 4, "5.000 V"),
        (0.0, "V", 4, "0.000 V"),
        (0.04999, "s", 4, "49.99 ms"),
        (-0.05, "s", 6, "-50.0000 ms"),
        (2.5e-6, "s", 4, "2.500 µs"),
        (10.001, "Hz", 4, "10.00 Hz"),
        (0.0009999, "s", 3, "1.00 ms"),
        (1236.0, "Hz", 4, "1.236 kHz"),
        (999.96, "V", 4, "1.000 kV"),
        (500.0, "PSI", 4, "500.0 PSI"),
    ],
)
def test_format_quantity(value: float, unit: str, digits: int, expected: str) -> None:
    assert format_quantity(value, unit, digits) == expected


def test_format_non_finite_is_dash() -> None:
    assert format_quantity(math.nan, "V") == "—"


@pytest.mark.parametrize(
    ("text", "unit", "expected"),
    [
        ("12.5 ms", "s", 0.0125),
        ("12.5ms", "s", 0.0125),
        ("-3u", "s", -3e-6),
        ("-3 µs", "s", -3e-6),
        ("0,25 V", "V", 0.25),
        ("250 mV", "V", 0.25),
        ("1e-3", "s", 1e-3),
        ("2", "s", 2.0),
        ("−50.0000 ms", "s", -0.05),
    ],
)
def test_parse_quantity(text: str, unit: str, expected: float) -> None:
    assert parse_quantity(text, unit) == pytest.approx(expected)


@pytest.mark.parametrize("text", ["", "abc", "5 V", "1..2 s"])
def test_parse_quantity_rejects_invalid_text(text: str) -> None:
    with pytest.raises(ValueError):
        parse_quantity(text, "s")


def test_format_and_parse_round_trip() -> None:
    for value in (55.158, -0.05, 2.5e-6, 165.47396):
        assert parse_quantity(format_quantity(value, "s", 6), "s") == pytest.approx(
            value, rel=1e-5
        )
