from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import correlate, correlation_lags

from osc_app.core.measurements import calculate_pulse_measurements


@dataclass(frozen=True)
class ReferenceComparison:
    samples: int
    mae: float
    rmse: float
    maximum_error: float
    correlation: float | None
    gain: float | None
    offset: float | None
    residual_delay: float | None
    actual_frequency: float | None
    reference_frequency: float | None
    frequency_difference: float | None
    duty_difference: float | None
    time_scale: float | None
    time: np.ndarray
    error: np.ndarray


def reference_time_shift(
    reference_time: np.ndarray,
    reference_samples: np.ndarray,
    mode: str,
    *,
    active_x1: float,
    region: tuple[float, float] | None = None,
) -> float:
    """Return the time offset needed to align a reference trace."""
    if reference_time.size == 0 or reference_samples.size == 0:
        return 0.0
    if mode == "original":
        return 0.0
    if mode == "x1":
        return float(active_x1 - reference_time[0])
    if mode != "peak":
        raise ValueError(f"Modo de alineación desconocido: {mode}")

    mask = np.isfinite(reference_samples)
    if region is not None:
        start, end = sorted(region)
        mask &= (reference_time >= start) & (reference_time <= end)
    indices = np.flatnonzero(mask)
    if indices.size == 0:
        return 0.0
    peak_index = int(indices[np.argmax(np.abs(reference_samples[indices]))])
    target = active_x1 if region is None else min(region)
    return float(target - reference_time[peak_index])


def transform_reference(
    samples: np.ndarray, *, gain: float, offset: float
) -> np.ndarray:
    """Apply display-only gain and offset to a reference signal."""
    return np.asarray(samples * gain + offset, dtype=np.float32)


def compare_reference(
    actual_time: np.ndarray,
    actual_samples: np.ndarray,
    reference_time: np.ndarray,
    reference_samples: np.ndarray,
) -> ReferenceComparison:
    """Compare an active signal against an interpolated reference."""
    actual_time = np.asarray(actual_time, dtype=np.float64)
    actual_samples = np.asarray(actual_samples, dtype=np.float64)
    reference_time = np.asarray(reference_time, dtype=np.float64)
    reference_samples = np.asarray(reference_samples, dtype=np.float64)
    if actual_time.size < 3 or reference_time.size < 3:
        raise ValueError("Se necesitan al menos tres muestras en ambas señales")
    reference_order = np.argsort(reference_time)
    reference_time = reference_time[reference_order]
    reference_samples = reference_samples[reference_order]
    overlap = (
        np.isfinite(actual_time)
        & np.isfinite(actual_samples)
        & (actual_time >= reference_time[0])
        & (actual_time <= reference_time[-1])
    )
    comparison_time = actual_time[overlap]
    actual = actual_samples[overlap]
    if comparison_time.size < 3:
        raise ValueError("Las señales no tienen una región temporal común")
    interpolated = np.interp(comparison_time, reference_time, reference_samples)
    finite = np.isfinite(actual) & np.isfinite(interpolated)
    comparison_time = comparison_time[finite]
    actual = actual[finite]
    interpolated = interpolated[finite]
    if comparison_time.size < 3:
        raise ValueError("No hay suficientes valores válidos para comparar")
    error = actual - interpolated
    mae = float(np.mean(np.abs(error), dtype=np.float64))
    rmse = float(np.sqrt(np.mean(np.square(error), dtype=np.float64)))
    maximum_error = float(np.max(np.abs(error)))
    actual_std = float(np.std(actual))
    reference_std = float(np.std(interpolated))
    correlation_value = None
    gain = None
    offset = None
    if actual_std > np.finfo(float).eps and reference_std > np.finfo(float).eps:
        actual_mean = float(np.mean(actual))
        reference_mean = float(np.mean(interpolated))
        covariance = float(
            np.mean((actual - actual_mean) * (interpolated - reference_mean))
        )
        correlation_value = float(
            np.clip(covariance / (actual_std * reference_std), -1.0, 1.0)
        )
        gain = covariance / (reference_std**2)
        offset = actual_mean - gain * reference_mean

    step = max(1, comparison_time.size // 100_000)
    reduced_actual = actual[::step] - np.mean(actual[::step])
    reduced_reference = interpolated[::step] - np.mean(interpolated[::step])
    residual_delay = None
    if not np.allclose(reduced_actual, 0.0) and not np.allclose(reduced_reference, 0.0):
        cross = correlate(reduced_actual, reduced_reference, mode="full", method="fft")
        lags = correlation_lags(
            reduced_actual.size, reduced_reference.size, mode="full"
        )
        lag = int(lags[int(np.argmax(cross))])
        residual_delay = float(lag * np.median(np.diff(comparison_time[::step])))

    actual_pulse = calculate_pulse_measurements(comparison_time, actual)
    reference_pulse = calculate_pulse_measurements(comparison_time, interpolated)
    frequency_difference = (
        actual_pulse.frequency - reference_pulse.frequency
        if actual_pulse.frequency is not None and reference_pulse.frequency is not None
        else None
    )
    duty_difference = (
        actual_pulse.duty_positive - reference_pulse.duty_positive
        if actual_pulse.duty_positive is not None
        and reference_pulse.duty_positive is not None
        else None
    )
    time_scale = (
        reference_pulse.frequency / actual_pulse.frequency
        if actual_pulse.frequency is not None
        and reference_pulse.frequency is not None
        and actual_pulse.frequency > 0
        else None
    )
    return ReferenceComparison(
        samples=int(comparison_time.size),
        mae=mae,
        rmse=rmse,
        maximum_error=maximum_error,
        correlation=correlation_value,
        gain=gain,
        offset=offset,
        residual_delay=residual_delay,
        actual_frequency=actual_pulse.frequency,
        reference_frequency=reference_pulse.frequency,
        frequency_difference=frequency_difference,
        duty_difference=duty_difference,
        time_scale=time_scale,
        time=comparison_time,
        error=np.asarray(error, dtype=np.float32),
    )
