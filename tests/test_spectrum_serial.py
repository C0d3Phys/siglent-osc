import numpy as np

from osc_app.core.serial_decoding import decode_uart
from osc_app.core.spectrum import calculate_spectrum


def test_spectrum_finds_tone() -> None:
    sample_rate = 10_000.0
    time = np.arange(10_000) / sample_rate
    samples = 2.0 * np.sin(2 * np.pi * 321.0 * time)
    result = calculate_spectrum(samples, sample_rate, window="hann")

    assert result.dominant_frequency is not None
    assert np.isclose(result.dominant_frequency, 321.0, atol=1.0)
    assert result.dominant_amplitude is not None
    assert np.isclose(result.dominant_amplitude, 2.0, atol=0.05)


def test_uart_decodes_8n1_byte() -> None:
    baud = 1000.0
    sample_rate = 100_000.0
    value = 0x55
    bits = [1, 1, 0] + [(value >> index) & 1 for index in range(8)] + [1, 1]
    samples_per_bit = int(sample_rate / baud)
    logic = np.repeat(bits, samples_per_bit).astype(float)
    time = np.arange(logic.size) / sample_rate

    frames = decode_uart(time, logic, baud_rate=baud, threshold=0.5)

    assert frames
    assert frames[0].value == value
    assert frames[0].valid_stop
