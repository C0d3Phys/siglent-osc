"""Configuración compartida de pruebas.

Fuerza la plataforma Qt ``offscreen`` por defecto para que la suite pueda
correr en un entorno sin servidor gráfico (CI, contenedores). Si el
desarrollador ya definió ``QT_QPA_PLATFORM``, se respeta su valor.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
