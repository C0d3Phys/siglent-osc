from __future__ import annotations

import numpy as np


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
