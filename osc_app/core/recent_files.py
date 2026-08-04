"""Lógica pura para la lista de archivos recientes (sin dependencias de Qt)."""

from __future__ import annotations

from collections.abc import Callable, Iterable

MAX_RECENT_FILES = 8


def push_recent_file(
    existing: Iterable[str], new_path: str, limit: int = MAX_RECENT_FILES
) -> list[str]:
    """Devuelve una nueva lista con ``new_path`` primero, sin duplicados.

    El orden refleja el uso más reciente primero. ``existing`` no se modifica.
    """
    if limit < 1:
        raise ValueError("limit debe ser al menos 1")
    updated = [new_path] + [path for path in existing if path != new_path]
    return updated[:limit]


def filter_existing_paths(
    paths: Iterable[str], exists: Callable[[str], bool]
) -> list[str]:
    """Filtra rutas que ya no existen en disco, conservando el orden."""
    return [path for path in paths if exists(path)]
