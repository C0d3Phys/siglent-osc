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

