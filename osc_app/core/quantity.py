"""Formato y lectura de magnitudes con prefijos SI (ms, µs, mV, kHz…).

Independiente de Qt para poder probarlo sin interfaz. Los prefijos solo se
aplican a unidades del SI de uso habitual en el osciloscopio; otras unidades
(PSI, unidades libres de canales matemáticos) se muestran sin escalar.
"""

from __future__ import annotations

import math
import re

SI_UNITS = frozenset({"s", "V", "A", "Hz", "W", "Ω"})
_PREFIXES = (
    (1e9, "G"),
    (1e6, "M"),
    (1e3, "k"),
    (1.0, ""),
    (1e-3, "m"),
    (1e-6, "µ"),
    (1e-9, "n"),
    (1e-12, "p"),
)
_PREFIX_FACTORS = {
    "G": 1e9,
    "M": 1e6,
    "k": 1e3,
    "": 1.0,
    "m": 1e-3,
    "u": 1e-6,
    "µ": 1e-6,
    "μ": 1e-6,
    "n": 1e-9,
    "p": 1e-12,
}
_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"


def format_quantity(value: float, unit: str, digits: int = 4) -> str:
    """Devuelve ``value`` con ``digits`` cifras significativas y prefijo SI.

    Siempre muestra el mismo número de cifras (``3.000 V``, ``49.99 ms``) para
    que las columnas se lean alineadas. Valores no finitos se muestran como
    ``—``.
    """
    if not math.isfinite(value):
        return "—"
    if unit not in SI_UNITS:
        return f"{_fixed_significant(value, digits)} {unit}".rstrip()
    absolute = abs(value)
    factor, prefix = 1.0, ""
    if absolute > 0:
        for candidate, candidate_prefix in _PREFIXES:
            # El redondeo puede llevar 999.96 a "1000": se compara ya redondeado.
            if abs(float(_fixed_significant(absolute / candidate, digits))) >= 1.0:
                factor, prefix = candidate, candidate_prefix
                break
        else:
            factor, prefix = _PREFIXES[-1]
    scaled = value / factor
    text = _fixed_significant(scaled, digits)
    if abs(float(text)) >= 1000 and prefix != "G":
        index = [item[1] for item in _PREFIXES].index(prefix)
        factor, prefix = _PREFIXES[index - 1]
        text = _fixed_significant(value / factor, digits)
    return f"{text} {prefix}{unit}"


def parse_quantity(text: str, unit: str) -> float:
    """Interpreta texto como ``12.5 ms``, ``-3u``, ``0,25 V`` o ``1e-3``.

    El prefijo y la unidad son opcionales; se acepta coma decimal. Lanza
    ``ValueError`` si el texto no es una magnitud válida.
    """
    cleaned = text.strip().replace("−", "-")
    if "," in cleaned and "." not in cleaned:
        cleaned = cleaned.replace(",", ".")
    unit_pattern = re.escape(unit) if unit else ""
    match = re.fullmatch(
        rf"({_NUMBER})\s*([GMkmuµμnp]?)\s*(?:{unit_pattern})?" if unit_pattern
        else rf"({_NUMBER})\s*([GMkmuµμnp]?)",
        cleaned,
    )
    if match is None:
        raise ValueError(f"Valor no válido: {text!r}")
    value = float(match.group(1)) * _PREFIX_FACTORS[match.group(2)]
    if not math.isfinite(value):
        raise ValueError(f"Valor no válido: {text!r}")
    return value


def _fixed_significant(value: float, digits: int) -> str:
    """Formatea con ``digits`` cifras significativas sin notación científica."""
    if value == 0:
        return f"{0:.{max(digits - 1, 0)}f}"
    magnitude = math.floor(math.log10(abs(value)))
    # 0.9999 con 3 cifras redondea a 1.00: la magnitud se toma ya redondeada.
    rounded = round(value, digits - 1 - magnitude)
    if rounded != 0:
        magnitude = math.floor(math.log10(abs(rounded)))
    decimals = max(digits - 1 - magnitude, 0)
    return f"{value:.{decimals}f}"
