from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class UartFrame:
    time: float
    value: int
    valid_stop: bool


def decode_uart(
    time: np.ndarray,
    samples: np.ndarray,
    *,
    baud_rate: float,
    threshold: float,
    inverted: bool = False,
) -> list[UartFrame]:
    """Decode basic 8-N-1 UART frames from an already captured analog signal."""
    if baud_rate <= 0:
        raise ValueError("El baud rate debe ser positivo")
    time = np.asarray(time, dtype=np.float64)
    samples = np.asarray(samples, dtype=np.float64)
    valid = np.isfinite(time) & np.isfinite(samples)
    time = time[valid]
    logic = samples[valid] >= threshold
    if inverted:
        logic = ~logic
    if time.size < 3:
        return []
    starts = np.flatnonzero(logic[:-1] & ~logic[1:]) + 1
    bit_time = 1.0 / baud_rate
    frames: list[UartFrame] = []
    next_allowed_time = -np.inf
    for start_index in starts:
        start_time = float(time[start_index])
        if start_time < next_allowed_time:
            continue
        sample_times = start_time + bit_time * (1.5 + np.arange(8))
        stop_time = start_time + bit_time * 9.5
        indices = np.searchsorted(time, np.append(sample_times, stop_time))
        if np.any(indices >= time.size):
            break
        bits = logic[indices[:8]]
        value = sum(int(bit) << position for position, bit in enumerate(bits))
        frames.append(UartFrame(start_time, value, bool(logic[indices[8]])))
        next_allowed_time = start_time + bit_time * 10.0
    return frames
