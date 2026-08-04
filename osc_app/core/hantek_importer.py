from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from osc_app.core.models import Acquisition, Channel

LWF_MAGIC = b"lwf\x00"
LWF_FOOTER = b"\x78\x56\x34\x12"
CHANNEL_OFFSET = 72
CHANNEL_SIZE = 40
CHANNEL_COUNT = 4
CHANNEL_STRUCT = struct.Struct("<HBBIIIdIIiI")
VOLTS_PER_DIV = {
    0: 500e-6,
    1: 1e-3,
    2: 2e-3,
    3: 5e-3,
    4: 10e-3,
    5: 20e-3,
    6: 50e-3,
    7: 100e-3,
    8: 200e-3,
    9: 500e-3,
    10: 1.0,
    11: 2.0,
    12: 5.0,
    13: 10.0,
}


class HantekImportError(ValueError):
    """Error comprensible al decodificar un binario LWF de Hantek."""


@dataclass(frozen=True, slots=True)
class HantekChannelHeader:
    enabled: bool
    timebase_code: int
    sampling_depth: int
    sample_count: int
    sample_rate: float
    vertical_offset_ticks: int
    volts_per_div_code: int


@dataclass(frozen=True, slots=True)
class HantekImportReport:
    version: int
    samples_per_channel: int
    enabled_channels: tuple[int, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HantekImportResult:
    acquisition: Acquisition
    report: HantekImportReport


class HantekLwfImporter:
    """Decodifica directamente una adquisición binaria Hantek `.lwf`."""

    def load(self, path: str | Path) -> HantekImportResult:
        source = Path(path).resolve()
        if not source.is_file():
            raise HantekImportError(f"No se encontró el archivo: {source}")
        if source.suffix.lower() != ".lwf":
            raise HantekImportError("Seleccione un archivo binario Hantek .lwf.")

        raw_file = source.read_bytes()
        minimum_size = CHANNEL_OFFSET + CHANNEL_COUNT * CHANNEL_SIZE + len(LWF_FOOTER)
        if len(raw_file) < minimum_size or raw_file[:4] != LWF_MAGIC:
            raise HantekImportError("El archivo no tiene una cabecera LWF válida.")
        if raw_file[-4:] != LWF_FOOTER:
            raise HantekImportError("El archivo LWF está incompleto o no tiene el cierre esperado.")

        version = struct.unpack_from("<I", raw_file, 4)[0]
        headers = tuple(self._read_channel_header(raw_file, index) for index in range(4))
        active = tuple(index for index, header in enumerate(headers) if header.enabled)
        if not active:
            raise HantekImportError("El LWF no contiene canales activos.")

        sample_rates = {headers[index].sample_rate for index in active}
        sample_counts = {headers[index].sample_count for index in active}
        if len(sample_rates) != 1 or not all(np.isfinite(rate) and rate > 0 for rate in sample_rates):
            raise HantekImportError("Los canales activos no comparten una tasa de muestreo válida.")
        if len(sample_counts) != 1 or next(iter(sample_counts)) <= 0:
            raise HantekImportError("Los canales activos no comparten una longitud válida.")

        total_samples = sum(headers[index].sample_count for index in active)
        payload_size = total_samples * 2
        payload_start = len(raw_file) - len(LWF_FOOTER) - payload_size
        header_end = CHANNEL_OFFSET + CHANNEL_COUNT * CHANNEL_SIZE
        if payload_start < header_end:
            raise HantekImportError("La longitud declarada de las muestras excede el archivo LWF.")

        payload = np.frombuffer(
            raw_file, dtype="<i2", count=total_samples, offset=payload_start
        )
        channels: list[Channel] = []
        cursor = 0
        for index in active:
            header = headers[index]
            values = payload[cursor : cursor + header.sample_count].astype(np.float64)
            cursor += header.sample_count
            volts_per_div = VOLTS_PER_DIV.get(header.volts_per_div_code)
            if volts_per_div is None:
                raise HantekImportError(
                    f"CH{index + 1} usa un código V/div desconocido: "
                    f"{header.volts_per_div_code}."
                )
            # Hantek representa cada división vertical mediante 25 cuentas ADC.
            samples = (values - header.vertical_offset_ticks) * (volts_per_div / 25.0)
            channels.append(Channel(name=f"CH{index + 1}", unit="V", samples=samples))

        sample_rate = next(iter(sample_rates))
        sample_count = next(iter(sample_counts))
        trigger_index = sample_count // 2 - (1 if sample_count % 2 == 0 else 0)
        time = (np.arange(sample_count, dtype=np.float64) - trigger_index) / sample_rate
        metadata = {
            "Formato": "Hantek LWF binario",
            "Versión LWF": str(version),
            "Tasa de muestreo": f"{sample_rate:.12g} Sa/s",
            "Canales activos": ", ".join(f"CH{index + 1}" for index in active),
        }
        acquisition = Acquisition(
            source_file=source,
            time=time,
            channels=tuple(channels),
            metadata=metadata,
        )
        report = HantekImportReport(
            version=version,
            samples_per_channel=sample_count,
            enabled_channels=tuple(index + 1 for index in active),
            warnings=(),
        )
        return HantekImportResult(acquisition=acquisition, report=report)

    @staticmethod
    def _read_channel_header(raw_file: bytes, index: int) -> HantekChannelHeader:
        offset = CHANNEL_OFFSET + index * CHANNEL_SIZE
        (
            _acquisition_mode,
            enabled,
            timebase_code,
            sampling_depth,
            sample_count,
            _unknown,
            sample_rate,
            _trigger_type,
            _trigger_channel,
            vertical_offset_ticks,
            packed_vertical_settings,
        ) = CHANNEL_STRUCT.unpack_from(raw_file, offset)
        return HantekChannelHeader(
            enabled=bool(enabled),
            timebase_code=timebase_code,
            sampling_depth=sampling_depth,
            sample_count=sample_count,
            sample_rate=sample_rate,
            vertical_offset_ticks=vertical_offset_ticks,
            volts_per_div_code=packed_vertical_settings & 0xFF,
        )


# Nombre anterior conservado para no romper integraciones que ya lo importaban.
HantekBundleImporter = HantekLwfImporter
