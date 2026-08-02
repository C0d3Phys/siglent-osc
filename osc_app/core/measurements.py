from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True, slots=True)
class Statistics:
    count_total: int
    count_valid: int
    minimum: float
    maximum: float
    mean: float
    rms: float
    peak_to_peak: float


@dataclass(frozen=True, slots=True)
class PulseMeasurements:
    frequency: float | None
    duty_positive: float | None
    threshold: float | None


def calculate_statistics(samples: NDArray[np.float64]) -> Statistics:
    """Calcula estadísticas en float64 ignorando valores no finitos."""
    values = np.asarray(samples, dtype=np.float64)
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        nan = float("nan")
        return Statistics(values.size, 0, nan, nan, nan, nan, nan)

    minimum = float(np.min(finite))
    maximum = float(np.max(finite))
    return Statistics(
        count_total=int(values.size),
        count_valid=int(finite.size),
        minimum=minimum,
        maximum=maximum,
        mean=float(np.mean(finite, dtype=np.float64)),
        rms=float(np.sqrt(np.mean(np.square(finite), dtype=np.float64))),
        peak_to_peak=maximum - minimum,
    )


def calculate_pulse_measurements(
    time: NDArray[np.float64], samples: NDArray[np.float64]
) -> PulseMeasurements:
    """Calcula frecuencia y Duty+ con nivel medio e histéresis 40/60 %."""
    time_values = np.asarray(time, dtype=np.float64)
    sample_values = np.asarray(samples, dtype=np.float64)
    valid = np.isfinite(time_values) & np.isfinite(sample_values)
    time_values = time_values[valid]
    sample_values = sample_values[valid]
    if time_values.size < 2:
        return PulseMeasurements(None, None, None)

    minimum = float(np.min(sample_values))
    maximum = float(np.max(sample_values))
    amplitude = maximum - minimum
    if amplitude <= np.finfo(float).eps * max(abs(minimum), abs(maximum), 1.0):
        return PulseMeasurements(None, None, None)

    threshold = (minimum + maximum) / 2.0
    duty_positive = float(np.mean(sample_values >= threshold) * 100.0)

    low_threshold = minimum + amplitude * 0.4
    high_threshold = minimum + amplitude * 0.6
    upward = np.flatnonzero(
        (sample_values[:-1] < high_threshold) & (sample_values[1:] >= high_threshold)
    ) + 1
    downward = np.flatnonzero(
        (sample_values[:-1] > low_threshold) & (sample_values[1:] <= low_threshold)
    ) + 1
    event_indices = np.concatenate((upward, downward))
    event_types = np.concatenate(
        (np.ones(upward.size, dtype=np.int8), np.zeros(downward.size, dtype=np.int8))
    )
    order = np.argsort(event_indices, kind="stable")
    high = bool(sample_values[0] >= threshold)
    accepted_rising: list[int] = []
    for event_index, event_type in zip(event_indices[order], event_types[order], strict=True):
        if event_type and not high:
            accepted_rising.append(int(event_index))
            high = True
        elif not event_type and high:
            high = False
    rising_indices = np.asarray(accepted_rising, dtype=np.int64)
    if rising_indices.size < 2:
        frequency = None
    else:
        previous_indices = rising_indices - 1
        previous = sample_values[previous_indices]
        current = sample_values[rising_indices]
        delta = current - previous
        fractions = np.divide(
            high_threshold - previous,
            delta,
            out=np.ones_like(delta),
            where=delta != 0,
        )
        fractions = np.clip(fractions, 0.0, 1.0)
        rising_times = time_values[previous_indices] + fractions * (
            time_values[rising_indices] - time_values[previous_indices]
        )
        periods = np.diff(rising_times)
        positive_periods = periods[periods > 0]
        frequency = float(1.0 / np.median(positive_periods)) if positive_periods.size else None
    return PulseMeasurements(frequency, duty_positive, threshold)


def nearest_index(time: NDArray[np.float64], position: float) -> int:
    """Devuelve el índice de la muestra temporal más cercana."""
    values = np.asarray(time, dtype=np.float64)
    if values.size == 0:
        raise ValueError("El eje temporal está vacío.")
    insertion = int(np.searchsorted(values, position, side="left"))
    if insertion <= 0:
        return 0
    if insertion >= values.size:
        return int(values.size - 1)
    before = insertion - 1
    return before if abs(position - values[before]) <= abs(values[insertion] - position) else insertion


def inclusive_region_indices(
    time: NDArray[np.float64], start: float, end: float
) -> tuple[int, int]:
    """Devuelve límites de corte Python que incluyen ambos extremos seleccionados."""
    values = np.asarray(time, dtype=np.float64)
    low, high = sorted((start, end))
    first = int(np.searchsorted(values, low, side="left"))
    last = int(np.searchsorted(values, high, side="right"))
    first = min(max(first, 0), values.size)
    last = min(max(last, first), values.size)
    return first, last
