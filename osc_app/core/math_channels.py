from __future__ import annotations

import numpy as np
from scipy.integrate import cumulative_trapezoid
from scipy.signal import butter, sosfiltfilt

BINARY_OPERATIONS = {"add", "subtract", "multiply", "divide"}


def calculate_math_channel(
    time: np.ndarray,
    first: np.ndarray,
    operation: str,
    second: np.ndarray | None = None,
    *,
    sample_rate: float | None = None,
    cutoff_hz: float | None = None,
) -> np.ndarray:
    """Calculate one of OSC App's fixed, safe math-channel operations."""
    time = np.asarray(time, dtype=np.float64)
    first = np.asarray(first, dtype=np.float64)
    if operation in BINARY_OPERATIONS:
        if second is None or len(second) != len(first):
            raise ValueError("La operación requiere dos canales compatibles")
        second = np.asarray(second, dtype=np.float64)
        if operation == "add":
            result = first + second
        elif operation == "subtract":
            result = first - second
        elif operation == "multiply":
            result = first * second
        else:
            tolerance = np.finfo(float).eps * np.maximum(np.abs(second), 1.0)
            result = np.full_like(first, np.nan)
            np.divide(first, second, out=result, where=np.abs(second) > tolerance)
    elif operation == "invert":
        result = -first
    elif operation == "absolute":
        result = np.abs(first)
    elif operation == "derivative":
        if time.size != first.size or time.size < 2:
            raise ValueError("La derivada requiere un eje temporal válido")
        result = np.gradient(first, time)
    elif operation == "integral":
        if time.size != first.size or time.size < 2:
            raise ValueError("La integral requiere un eje temporal válido")
        result = cumulative_trapezoid(first, time, initial=0.0)
    elif operation in {"lowpass", "highpass"}:
        if sample_rate is None or sample_rate <= 0 or cutoff_hz is None:
            raise ValueError("El filtro requiere tasa de muestreo y frecuencia de corte")
        if not 0 < cutoff_hz < sample_rate / 2.0:
            raise ValueError("La frecuencia de corte debe ser menor que Nyquist")
        sos = butter(4, cutoff_hz, btype="low" if operation == "lowpass" else "high", fs=sample_rate, output="sos")
        finite = np.isfinite(first)
        replacement = float(np.mean(first[finite])) if np.any(finite) else 0.0
        working = np.where(finite, first, replacement)
        result = sosfiltfilt(sos, working)
        result[~finite] = np.nan
    else:
        raise ValueError(f"Operación matemática desconocida: {operation}")
    return np.asarray(result, dtype=np.float32)
