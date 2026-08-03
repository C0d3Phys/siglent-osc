from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import correlate, correlation_lags


@dataclass(frozen=True)
class EdgeMeasurements:
    rising_edges: int
    falling_edges: int
    high_width: float | None
    low_width: float | None
    rise_time: float | None
    fall_time: float | None
    overshoot: float | None
    undershoot: float | None


def _crossing_time(time: np.ndarray, samples: np.ndarray, index: int, level: float) -> float:
    x0 = float(samples[index])
    x1 = float(samples[index + 1])
    if np.isclose(x1, x0):
        return float(time[index])
    fraction = (level - x0) / (x1 - x0)
    return float(time[index] + fraction * (time[index + 1] - time[index]))


def calculate_edge_measurements(time: np.ndarray, samples: np.ndarray) -> EdgeMeasurements:
    """Measure edges and pulse timing using robust 10/40/60/90 percent levels."""
    valid = np.isfinite(time) & np.isfinite(samples)
    time = np.asarray(time[valid], dtype=np.float64)
    samples = np.asarray(samples[valid], dtype=np.float64)
    if samples.size < 3:
        return EdgeMeasurements(0, 0, None, None, None, None, None, None)
    low, high = np.percentile(samples, (5.0, 95.0))
    span = float(high - low)
    if not np.isfinite(span) or span <= np.finfo(float).eps:
        return EdgeMeasurements(0, 0, None, None, None, None, 0.0, 0.0)
    levels = {fraction: float(low + span * fraction) for fraction in (0.1, 0.4, 0.5, 0.6, 0.9)}
    rising = np.flatnonzero((samples[:-1] < levels[0.4]) & (samples[1:] >= levels[0.6]))
    falling = np.flatnonzero((samples[:-1] > levels[0.6]) & (samples[1:] <= levels[0.4]))
    mid_rising = np.flatnonzero((samples[:-1] < levels[0.5]) & (samples[1:] >= levels[0.5]))
    mid_falling = np.flatnonzero((samples[:-1] > levels[0.5]) & (samples[1:] <= levels[0.5]))

    def paired_widths(first: np.ndarray, second: np.ndarray) -> list[float]:
        if first.size == 0 or second.size == 0:
            return []
        positions = np.searchsorted(second, first, side="right")
        valid_positions = positions < second.size
        paired_first = first[valid_positions]
        paired_second = second[positions[valid_positions]]
        return list(np.asarray(time[paired_second] - time[paired_first], dtype=float))

    high_widths = paired_widths(mid_rising, mid_falling)
    low_widths = paired_widths(mid_falling, mid_rising)

    low_rise = np.flatnonzero(
        (samples[:-1] < levels[0.1]) & (samples[1:] >= levels[0.1])
    )
    high_rise = np.flatnonzero(
        (samples[:-1] < levels[0.9]) & (samples[1:] >= levels[0.9])
    )
    rise_times: list[float] = []
    rise_positions = np.searchsorted(high_rise, low_rise, side="left")
    for low_index, position in zip(low_rise, rise_positions, strict=True):
        if position < high_rise.size:
            high_index = int(high_rise[position])
            if high_index >= low_index:
                rise_times.append(
                    _crossing_time(time, samples, high_index, levels[0.9])
                    - _crossing_time(time, samples, int(low_index), levels[0.1])
                )

    high_fall = np.flatnonzero(
        (samples[:-1] > levels[0.9]) & (samples[1:] <= levels[0.9])
    )
    low_fall = np.flatnonzero(
        (samples[:-1] > levels[0.1]) & (samples[1:] <= levels[0.1])
    )
    fall_times: list[float] = []
    fall_positions = np.searchsorted(low_fall, high_fall, side="left")
    for high_index, position in zip(high_fall, fall_positions, strict=True):
        if position < low_fall.size:
            low_index = int(low_fall[position])
            if low_index >= high_index:
                fall_times.append(
                    _crossing_time(time, samples, low_index, levels[0.1])
                    - _crossing_time(time, samples, int(high_index), levels[0.9])
                )

    return EdgeMeasurements(
        rising_edges=int(rising.size),
        falling_edges=int(falling.size),
        high_width=float(np.mean(high_widths)) if high_widths else None,
        low_width=float(np.mean(low_widths)) if low_widths else None,
        rise_time=float(np.mean(rise_times)) if rise_times else None,
        fall_time=float(np.mean(fall_times)) if fall_times else None,
        overshoot=max(float(np.max(samples) - high), 0.0),
        undershoot=max(float(low - np.min(samples)), 0.0),
    )


def estimate_delay_and_phase(
    time: np.ndarray, first: np.ndarray, second: np.ndarray, frequency: float | None
) -> tuple[float | None, float | None]:
    """Estimate inter-channel delay by normalized cross-correlation."""
    valid = np.isfinite(time) & np.isfinite(first) & np.isfinite(second)
    time = np.asarray(time[valid], dtype=np.float64)
    first = np.asarray(first[valid], dtype=np.float64)
    second = np.asarray(second[valid], dtype=np.float64)
    if time.size < 3:
        return None, None
    step = max(1, time.size // 100_000)
    time = time[::step]
    first = first[::step] - np.mean(first[::step])
    second = second[::step] - np.mean(second[::step])
    if np.allclose(first, 0.0) or np.allclose(second, 0.0):
        return None, None
    correlation = correlate(second, first, mode="full", method="fft")
    lags = correlation_lags(second.size, first.size, mode="full")
    lag = int(lags[int(np.argmax(correlation))])
    sample_interval = float(np.median(np.diff(time)))
    delay = lag * sample_interval
    phase = ((delay * frequency * 360.0 + 180.0) % 360.0) - 180.0 if frequency else None
    return delay, phase
