"""Lógica pura para la lista de archivos recientes (sin dependencias de Qt)."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from pathlib import PurePosixPath, PureWindowsPath

MAX_RECENT_FILES = 8


def path_identity(path: str) -> str:
    """Clave para comparar rutas: resuelve nombres cortos de Windows
    (``ING_CE~1``) y enlaces, e ignora mayúsculas donde el sistema lo hace."""
    return os.path.normcase(os.path.realpath(path))


def push_recent_file(
    existing: Iterable[str],
    new_path: str,
    limit: int = MAX_RECENT_FILES,
    key: Callable[[str], str] = lambda path: path,
) -> list[str]:
    """Devuelve una nueva lista con ``new_path`` primero, sin duplicados.

    El orden refleja el uso más reciente primero. ``existing`` no se modifica.
    Dos rutas son la misma entrada si ``key`` les da el mismo valor.
    """
    if limit < 1:
        raise ValueError("limit debe ser al menos 1")
    return dedupe_paths([new_path, *existing], key)[:limit]


def dedupe_paths(paths: Iterable[str], key: Callable[[str], str] = lambda path: path) -> list[str]:
    """Quita rutas repetidas (según ``key``) conservando la primera aparición."""
    seen: set[str] = set()
    unique: list[str] = []
    for path in paths:
        identity = key(path)
        if identity not in seen:
            seen.add(identity)
            unique.append(path)
    return unique


def filter_existing_paths(
    paths: Iterable[str], exists: Callable[[str], bool]
) -> list[str]:
    """Filtra rutas que ya no existen en disco, conservando el orden."""
    return [path for path in paths if exists(path)]


def recent_file_label(path: str, max_folder_parts: int = 2) -> str:
    """Texto del menú: nombre del archivo y la carpeta que lo contiene.

    La carpeta se acorta a sus últimos ``max_folder_parts`` niveles para que
    dos archivos con el mismo nombre se distingan sin ocupar todo el menú.
    """
    windows = "\\" in path
    pure = PureWindowsPath(path) if windows else PurePosixPath(path)
    parent = pure.parent
    if len(parent.parts) > max_folder_parts + 1:
        separator = "\\" if windows else "/"
        folder = "…" + separator + separator.join(parent.parts[-max_folder_parts:])
    else:
        folder = str(parent)
    return f"{pure.name}   —   {folder}"
