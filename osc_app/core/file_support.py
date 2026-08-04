"""Utilidades independientes de Qt para reconocer archivos de adquisición."""

from __future__ import annotations

from pathlib import Path

SUPPORTED_ACQUISITION_SUFFIXES = frozenset({".csv", ".bin", ".lwf"})


def is_supported_acquisition_file(path: str | Path) -> bool:
    """Indica si la ruta tiene una extensión de adquisición reconocida.

    No verifica que el archivo exista ni que su contenido sea válido; solo
    filtra por extensión para decisiones rápidas de interfaz (por ejemplo,
    arrastrar y soltar).
    """
    return Path(path).suffix.lower() in SUPPORTED_ACQUISITION_SUFFIXES
