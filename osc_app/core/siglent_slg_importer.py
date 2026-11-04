"""Importador del registro largo SIGLENT ``.slg`` (cabecera ``SPLG``).

Estructura observada en archivos de un SDS1104X-E (firmware 8.2.6.1.37R17):

* ``0x0000``: cabecera de 4 KiB con modelo, número de serie, firmware,
  tasa de muestreo, cantidad de muestras y un bloque de 0x100 bytes por canal.
* ``0x1000``: vista previa decimada 2:1 (no se utiliza; se leen los cuadros
  a resolución completa).
* Desde el desplazamiento indicado en ``0xA8``: cuadros de tamaño fijo, cada
  uno con una cabecera de 0x3C bytes (índice, muestra inicial, muestra final,
  cantidad de muestras) seguida de muestras de 8 bits sin signo.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from osc_app.core.models import Acquisition, Channel

SLG_MAGIC = b"SPLG"
HEADER_SIZE = 0x1000
FRAME_HEADER_SIZE = 0x3C
CHANNEL_BLOCK_OFFSET = 0x280
CHANNEL_BLOCK_SIZE = 0x100
CHANNEL_COUNT = 4


class SlgImportError(ValueError):
    """Error encontrado al importar un registro SIGLENT ``.slg``."""


@dataclass(frozen=True, slots=True)
class SlgImportReport:
    format_name: str
    model: str
    active_channels: tuple[int, ...]
    samples_per_channel: int
    sample_rate: float
    frame_count: int
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SlgImportResult:
    acquisition: Acquisition
    report: SlgImportReport


class SiglentSlgImporter:
    """Decodifica un registro largo ``.slg`` de osciloscopios SIGLENT SDS1000X-E."""

    def load(self, path: str | Path) -> SlgImportResult:
        source = Path(path).resolve()
        if not source.is_file():
            raise SlgImportError(f"No se encontró el archivo: {source}")
        file_size = source.stat().st_size
        if file_size < HEADER_SIZE:
            raise SlgImportError("El archivo es demasiado pequeño para una cabecera SLG.")

        with source.open("rb") as handle:
            header = handle.read(HEADER_SIZE)
        if header[:4] != SLG_MAGIC:
            raise SlgImportError("El archivo no tiene una cabecera SIGLENT SLG (SPLG) válida.")

        version = struct.unpack_from("<I", header, 0x08)[0]
        model = _text(header, 0x0C)
        serial = _text(header, 0x2C)
        firmware = _text(header, 0x4C)
        frame_count = struct.unpack_from("<I", header, 0x84)[0]
        time_division, sample_rate, duration = struct.unpack_from("<3d", header, 0x88)
        declared_total, first_frame, last_frame = struct.unpack_from("<3Q", header, 0xA0)
        year, month, day, hour, minute, second, millisecond = struct.unpack_from(
            "<7I", header, 0xCC
        )

        if frame_count <= 0:
            raise SlgImportError("El registro SLG no contiene cuadros de datos.")
        if not np.isfinite(sample_rate) or sample_rate <= 0:
            raise SlgImportError("La tasa de muestreo no es válida.")
        if first_frame < HEADER_SIZE or last_frame < first_frame:
            raise SlgImportError("Los desplazamientos de los cuadros no son válidos.")
        if frame_count > 1:
            stride, remainder = divmod(last_frame - first_frame, frame_count - 1)
            if remainder:
                raise SlgImportError("Los cuadros del SLG no tienen un tamaño uniforme.")
        else:
            stride = file_size - first_frame
        if stride <= FRAME_HEADER_SIZE or first_frame + stride * frame_count > file_size:
            raise SlgImportError(
                "El archivo SLG está incompleto: los cuadros declarados exceden su tamaño."
            )

        enabled: list[int] = []
        probes: list[float] = []
        offsets: list[float] = []
        volts_per_code: list[float] = []
        center_codes: list[int] = []
        for index in range(CHANNEL_COUNT):
            base = CHANNEL_BLOCK_OFFSET + index * CHANNEL_BLOCK_SIZE
            enabled.append(struct.unpack_from("<I", header, base)[0])
            probe, offset, scale = struct.unpack_from("<3d", header, base + 0x10)
            probes.append(probe if np.isfinite(probe) and probe > 0 else 1.0)
            offsets.append(offset)
            volts_per_code.append(scale)
            center_codes.append(struct.unpack_from("<I", header, base + 0x28)[0])
        active = tuple(index + 1 for index, value in enumerate(enabled) if value == 1)
        if not active:
            raise SlgImportError("El registro SLG no contiene canales activos.")
        for number in active:
            scale = volts_per_code[number - 1]
            if not np.isfinite(scale) or scale <= 0 or not np.isfinite(offsets[number - 1]):
                raise SlgImportError(f"La escala u offset de CH{number} no es válido.")

        capacity = (stride - FRAME_HEADER_SIZE) // len(active)
        frames = np.memmap(
            source,
            dtype=np.uint8,
            mode="r",
            offset=first_frame,
            shape=(frame_count, stride),
        )
        frame_headers = (
            np.ascontiguousarray(frames[:, :32]).view("<u8").reshape(frame_count, 4)
        )
        counts = frame_headers[:, 3].astype(np.int64)
        if not np.array_equal(frame_headers[:, 0], np.arange(frame_count)):
            raise SlgImportError("Los índices de los cuadros SLG no son consecutivos.")
        if np.any(counts > capacity):
            raise SlgImportError("Un cuadro SLG declara más muestras de las que contiene.")
        starts = np.concatenate(([0], np.cumsum(counts)[:-1]))
        if not np.array_equal(frame_headers[:, 1].astype(np.int64), starts):
            raise SlgImportError("Los cuadros SLG no forman un registro continuo.")
        total = int(counts.sum())
        if total == 0:
            raise SlgImportError("El registro SLG no contiene muestras.")

        warnings: list[str] = []
        if total != declared_total:
            warnings.append(
                f"La cabecera declara {declared_total:,} muestras y los cuadros contienen {total:,}."
            )
        if len(active) > 1:
            warnings.append(
                "La distribución multicanal del SLG no ha sido verificada con archivos reales."
            )

        valid = np.arange(capacity) < counts[:, None]
        channels: list[Channel] = []
        for slot, number in enumerate(active):
            start = FRAME_HEADER_SIZE + slot * capacity
            raw = frames[:, start : start + capacity][valid]
            scale = np.float32(volts_per_code[number - 1])
            offset = np.float32(offsets[number - 1])
            probe = np.float32(probes[number - 1])
            center = np.float32(center_codes[number - 1] or 128)
            samples = ((raw.astype(np.float32) - center) * scale - offset) * probe
            channels.append(Channel(name=f"CH{number}", unit="V", samples=samples))

        time = np.arange(total, dtype=np.float64) / sample_rate
        metadata = {
            "Formato": "SIGLENT SLG (registro largo) 8 bits",
            "Versión SLG": str(version),
            "Modelo": model,
            "Número de serie": serial,
            "Firmware": firmware,
            "Fecha": (
                f"{year:04d}-{month:02d}-{day:02d} "
                f"{hour:02d}:{minute:02d}:{second:02d}.{millisecond:03d}"
            ),
            "Sample Rate": f"{sample_rate:.17g}",
            "Record Length": str(total),
            "Duración": f"{duration:.17g}",
            "Time Division": f"{time_division:.17g}",
            "Cuadros": str(frame_count),
            "Active Channels": ",".join(f"CH{number}" for number in active),
        }
        for number in active:
            probe = probes[number - 1]
            metadata[f"CH{number} Probe"] = f"{probe:.17g}"
            metadata[f"CH{number} Scale"] = f"{volts_per_code[number - 1] * 25 * probe:.17g}"
            metadata[f"CH{number} Offset"] = f"{offsets[number - 1] * probe:.17g}"
        acquisition = Acquisition(source, time, tuple(channels), metadata)
        report = SlgImportReport(
            "SIGLENT SLG 8-bit",
            model,
            active,
            total,
            sample_rate,
            frame_count,
            tuple(warnings),
        )
        return SlgImportResult(acquisition, report)


def _text(header: bytes, offset: int, size: int = 0x20) -> str:
    return header[offset : offset + size].split(b"\x00", 1)[0].decode("ascii", "replace")
