from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import get_window


@dataclass(frozen=True)
class SpectrumResult:
    frequency: np.ndarray
    amplitude: np.ndarray
    dominant_frequency: float | None
    dominant_amplitude: float | None


def calculate_spectrum(
    samples: np.ndarray,
    sample_rate: float,
    *,
    window: str = "hann",
    remove_dc: bool = True,
) -> SpectrumResult:
    """Return a single-sided amplitude spectrum."""
    samples = np.asarray(samples, dtype=np.float64)
    samples = samples[np.isfinite(samples)]
    if samples.size < 2 or sample_rate <= 0:
        return SpectrumResult(np.empty(0), np.empty(0), None, None)
    if remove_dc:
        samples = samples - np.mean(samples)
    window_values = get_window(window, samples.size, fftbins=True)
    scale = float(np.sum(window_values))
    transformed = np.fft.rfft(samples * window_values)
    amplitude = 2.0 * np.abs(transformed) / scale
    amplitude[0] *= 0.5
    if samples.size % 2 == 0:
        amplitude[-1] *= 0.5
    frequency = np.fft.rfftfreq(samples.size, d=1.0 / sample_rate)
    start = 1 if remove_dc and amplitude.size > 1 else 0
    if amplitude.size <= start:
        return SpectrumResult(frequency, amplitude, None, None)
    peak = start + int(np.argmax(amplitude[start:]))
    return SpectrumResult(
        frequency,
        amplitude,
        float(frequency[peak]),
        float(amplitude[peak]),
    )
