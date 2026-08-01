from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from osc_app.core.models import Acquisition, Channel

HEADER_SIZE = 0x800
HORIZONTAL_DIVISIONS = 14


class BinImportError(ValueError):
    """Error encontrado al importar una adquisición BIN de SIGLENT."""


@dataclass(frozen=True, slots=True)
class BinImportReport:
    format_name: str
    header_size: int
    data_width_bits: int
    active_channels: tuple[int, ...]
    samples_per_channel: int
    sample_rate: float
    time_division: float
    trigger_delay: float
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BinImportResult:
    acquisition: Acquisition
    report: BinImportReport


class SiglentBinImporter:
    """Importa el formato BIN moderno documentado para SDS1xx4X-E/U."""

    def load(self, path: str | Path) -> BinImportResult:
        source = Path(path).resolve()
        if not source.is_file():
            raise BinImportError(f"No se encontró el archivo: {source}")
        if source.stat().st_size < HEADER_SIZE:
            raise BinImportError("El archivo es demasiado pequeño para una cabecera SIGLENT.")

        with source.open("rb") as handle:
            header = handle.read(HEADER_SIZE)
        enabled = struct.unpack_from("<4I", header, 0x00)
        if any(value not in (0, 1) for value in enabled) or not any(enabled):
            raise BinImportError("La cabecera no corresponde al formato BIN moderno reconocido.")
        if header[0x260] != 0:
            raise BinImportError("El BIN usa 16 bits; esta versión admite únicamente 8 bits.")

        length = struct.unpack_from("<I", header, 0xF4)[0]
        sample_rate = struct.unpack_from("<d", header, 0xF8)[0]
        time_division = struct.unpack_from("<d", header, 0xD4)[0]
        trigger_delay = struct.unpack_from("<d", header, 0xE4)[0]
        scales = tuple(
            struct.unpack_from("<d", header, 0x10 + index * 0x10)[0] for index in range(4)
        )
        offsets = tuple(
            struct.unpack_from("<d", header, 0x50 + index * 0x10)[0] for index in range(4)
        )
        stored_probes = tuple(struct.unpack_from("<d", header, 0x240 + index * 8)[0] for index in range(4))
        probes = tuple(value if np.isfinite(value) and value > 0 else 1.0 for value in stored_probes)
        active = tuple(index + 1 for index, value in enumerate(enabled) if value)
        self._validate(length, sample_rate, time_division, trigger_delay, scales, offsets, active)

        expected_size = HEADER_SIZE + length * len(active)
        actual_size = source.stat().st_size
        if actual_size != expected_size:
            raise BinImportError(
                f"Tamaño BIN inconsistente: se esperaban {expected_size:,} bytes y "
                f"se encontraron {actual_size:,}."
            )

        raw = np.memmap(
            source,
            dtype=np.uint8,
            mode="r",
            offset=HEADER_SIZE,
            shape=(length * len(active),),
        )
        channels: list[Channel] = []
        for slot, channel_number in enumerate(active):
            raw_channel = raw[slot * length : (slot + 1) * length]
            scale = np.float32(scales[channel_number - 1] / 25.0)
            offset = np.float32(offsets[channel_number - 1])
            probe = np.float32(probes[channel_number - 1])
            samples = ((raw_channel.astype(np.float32) - 128.0) * scale - offset) * probe
            channels.append(Channel(name=f"CH{channel_number}", unit="V", samples=samples))

        start_time = trigger_delay - time_division * HORIZONTAL_DIVISIONS / 2.0
        time = start_time + np.arange(length, dtype=np.float64) / sample_rate
        metadata = {
            "Format": "SIGLENT BIN modern 8-bit",
            "Header Size": str(HEADER_SIZE),
            "Sample Rate": f"{sample_rate:.17g}",
            "Record Length": str(length),
            "Time Division": f"{time_division:.17g}",
            "Trigger Delay": f"{trigger_delay:.17g}",
            "Active Channels": ",".join(f"CH{number}" for number in active),
        }
        for channel_number in active:
            metadata[f"CH{channel_number} Probe"] = f"{probes[channel_number - 1]:.17g}"
            metadata[f"CH{channel_number} Scale"] = (
                f"{scales[channel_number - 1] * probes[channel_number - 1]:.17g}"
            )
            metadata[f"CH{channel_number} Offset"] = (
                f"{offsets[channel_number - 1] * probes[channel_number - 1]:.17g}"
            )
        acquisition = Acquisition(source, time, tuple(channels), metadata)
        report = BinImportReport(
            "SIGLENT BIN modern 8-bit",
            HEADER_SIZE,
            8,
            active,
            length,
            sample_rate,
            time_division,
            trigger_delay,
            (),
        )
        return BinImportResult(acquisition, report)

    @staticmethod
    def _validate(
        length: int,
        sample_rate: float,
        time_division: float,
        trigger_delay: float,
        scales: tuple[float, ...],
        offsets: tuple[float, ...],
        active: tuple[int, ...],
    ) -> None:
        if length <= 0:
            raise BinImportError("La longitud de adquisición no es válida.")
        if not np.isfinite(sample_rate) or sample_rate <= 0:
            raise BinImportError("La tasa de muestreo no es válida.")
        if not np.isfinite(time_division) or time_division <= 0:
            raise BinImportError("La base temporal no es válida.")
        if not np.isfinite(trigger_delay):
            raise BinImportError("El retraso de trigger no es válido.")
        for channel_number in active:
            scale = scales[channel_number - 1]
            offset = offsets[channel_number - 1]
            if not np.isfinite(scale) or scale <= 0 or not np.isfinite(offset):
                raise BinImportError(f"La escala u offset de CH{channel_number} no es válido.")
