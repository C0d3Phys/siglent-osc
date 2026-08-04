"""Formato de texto para el resumen permanente de la adquisición activa.

Mantiene el cálculo y el formato fuera de los widgets para poder probarlos
sin levantar una aplicación Qt.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from osc_app.core.models import Acquisition


def format_sample_count(count: int) -> str:
    return f"{count:,}"


def format_sample_rate(sample_rate: float | None) -> str:
    if not sample_rate:
        return "tasa no disponible"
    return f"{sample_rate:,.3f} Sa/s"


def format_memory_bytes(num_bytes: float) -> str:
    """Formatea un tamaño en bytes con la unidad binaria más legible."""
    if num_bytes < 0:
        raise ValueError("num_bytes no puede ser negativo")
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024.0 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} TB"  # pragma: no cover - defensivo, no alcanzable con GB tope


def estimate_acquisition_memory_bytes(acquisition: Acquisition) -> int:
    """Estima la memoria ocupada por el eje temporal y las muestras crudas."""
    total = int(acquisition.time.nbytes)
    for channel in acquisition.channels:
        total += int(channel.samples.nbytes)
    return total


def build_status_summary(
    *,
    file_name: str,
    sample_count: int,
    duration: float,
    sample_rate: float | None,
    active_channels: int,
    total_channels: int,
    memory_bytes: int,
) -> str:
    """Construye la línea de resumen que se muestra de forma permanente."""
    return (
        f"{file_name}  |  {format_sample_count(sample_count)} muestras  |  "
        f"{duration:.6g} s  |  {format_sample_rate(sample_rate)}  |  "
        f"canales {active_channels}/{total_channels}  |  "
        f"{format_memory_bytes(memory_bytes)} en memoria"
    )
