from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.floating]


@dataclass(frozen=True, slots=True)
class Channel:
    """Canal original importado de una adquisición."""

    name: str
    unit: str
    samples: FloatArray

    def __post_init__(self) -> None:
        values = np.ascontiguousarray(self.samples)
        if values.dtype not in (np.dtype(np.float32), np.dtype(np.float64)):
            values = values.astype(np.float32)
        values.setflags(write=False)
        object.__setattr__(self, "samples", values)


@dataclass(frozen=True, slots=True)
class Acquisition:
    """Adquisición normalizada con un eje temporal explícito."""

    source_file: Path
    time: FloatArray
    channels: tuple[Channel, ...]
    metadata: Mapping[str, str]

    def __post_init__(self) -> None:
        time = np.ascontiguousarray(self.time, dtype=np.float64)
        time.setflags(write=False)
        if time.ndim != 1 or time.size == 0:
            raise ValueError("El eje temporal debe ser un arreglo no vacío.")
        if not np.all(np.isfinite(time)):
            raise ValueError("El eje temporal contiene valores no finitos.")
        if time.size > 1 and not np.all(np.diff(time) > 0):
            raise ValueError("El eje temporal debe ser estrictamente creciente.")
        if not self.channels:
            raise ValueError("La adquisición debe contener al menos un canal.")
        if any(channel.samples.size != time.size for channel in self.channels):
            raise ValueError("Todos los canales deben tener la misma longitud que el tiempo.")
        object.__setattr__(self, "time", time)
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @property
    def sample_count(self) -> int:
        return int(self.time.size)

    @property
    def duration(self) -> float:
        return float(self.time[-1] - self.time[0]) if self.time.size > 1 else 0.0

    @property
    def sample_rate(self) -> float | None:
        if self.time.size < 2:
            return None
        interval = float(np.median(np.diff(self.time)))
        return 1.0 / interval if interval > 0 else None
