from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from osc_app.core.models import Acquisition, Channel

TIME_NAMES = {"time", "time(s)", "seconds", "second", "timestamp", "x"}
CHANNEL_PATTERN = re.compile(r"^(?:ch|c|channel)\s*([1-4])(?:\s*\([^)]*\))?$", re.IGNORECASE)
UNIT_PATTERN = re.compile(r"\(([^)]+)\)\s*$")


class CsvImportError(ValueError):
    """Error comprensible encontrado al inspeccionar o importar un CSV."""


@dataclass(frozen=True, slots=True)
class ImportReport:
    delimiter: str
    encoding: str
    rows_read: int
    rows_accepted: int
    rows_rejected: int
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ImportResult:
    acquisition: Acquisition
    report: ImportReport


class GenericCsvImporter:
    """Importador inicial para CSV con tiempo explícito y hasta cuatro canales."""

    def load(self, path: str | Path) -> ImportResult:
        source = Path(path).resolve()
        if not source.is_file():
            raise CsvImportError(f"No se encontró el archivo: {source}")

        encoding = self._detect_encoding(source)
        metadata, table_lines = self._read_lines(source, encoding)
        if len(table_lines) < 2:
            raise CsvImportError("No se encontró una tabla con encabezado y datos.")

        delimiter = self._detect_delimiter(table_lines[:10])
        rows = list(csv.reader(table_lines, delimiter=delimiter))
        header = [cell.strip() for cell in rows[0]]
        time_index, channel_indices = self._map_columns(header)

        time_values: list[float] = []
        channel_values: list[list[float]] = [[] for _ in channel_indices]
        rejected = 0
        warnings: list[str] = []

        for line_number, row in enumerate(rows[1:], start=2):
            if not row or all(not cell.strip() for cell in row):
                rejected += 1
                continue
            try:
                time_value = self._number(row[time_index])
            except (IndexError, ValueError):
                rejected += 1
                warnings.append(f"Fila {line_number}: tiempo inválido; fila omitida.")
                continue

            parsed_channels: list[float] = []
            for index in channel_indices:
                try:
                    parsed_channels.append(self._number(row[index]))
                except (IndexError, ValueError):
                    parsed_channels.append(float("nan"))
                    warnings.append(f"Fila {line_number}: muestra inválida convertida a NaN.")

            time_values.append(time_value)
            for values, value in zip(channel_values, parsed_channels, strict=True):
                values.append(value)

        if not time_values:
            raise CsvImportError("No se encontraron filas de datos válidas.")

        channels = tuple(
            Channel(
                name=self._channel_name(header[index]),
                unit=self._unit(header[index], default="V"),
                samples=np.asarray(values, dtype=np.float64),
            )
            for index, values in zip(channel_indices, channel_values, strict=True)
        )
        try:
            acquisition = Acquisition(
                source_file=source,
                time=np.asarray(time_values, dtype=np.float64),
                channels=channels,
                metadata=metadata,
            )
        except ValueError as exc:
            raise CsvImportError(str(exc)) from exc

        report = ImportReport(
            delimiter=delimiter,
            encoding=encoding,
            rows_read=len(rows) - 1,
            rows_accepted=len(time_values),
            rows_rejected=rejected,
            warnings=tuple(warnings),
        )
        return ImportResult(acquisition=acquisition, report=report)

    @staticmethod
    def _detect_encoding(path: Path) -> str:
        raw = path.read_bytes()[:65536]
        for encoding in ("utf-8-sig", "cp1252"):
            try:
                raw.decode(encoding)
                return encoding
            except UnicodeDecodeError:
                continue
        raise CsvImportError("No se pudo reconocer la codificación del archivo.")

    @staticmethod
    def _read_lines(path: Path, encoding: str) -> tuple[dict[str, str], list[str]]:
        metadata: dict[str, str] = {}
        table_lines: list[str] = []
        with path.open("r", encoding=encoding, newline="") as handle:
            for raw_line in handle:
                stripped = raw_line.strip()
                if not stripped:
                    continue
                if stripped.startswith("#"):
                    content = stripped[1:].strip()
                    key, separator, value = content.partition(":")
                    if separator:
                        metadata[key.strip()] = value.strip()
                    continue
                table_lines.append(raw_line)
        return metadata, table_lines

    @staticmethod
    def _detect_delimiter(lines: list[str]) -> str:
        sample = "".join(lines)
        try:
            return csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
        except csv.Error as exc:
            raise CsvImportError("No se pudo detectar el delimitador del CSV.") from exc

    @staticmethod
    def _map_columns(header: list[str]) -> tuple[int, list[int]]:
        normalized = [value.strip().lower() for value in header]
        time_candidates = [index for index, name in enumerate(normalized) if name in TIME_NAMES]
        if len(time_candidates) != 1:
            raise CsvImportError("Debe existir exactamente una columna de tiempo reconocible.")
        channel_indices = [
            index for index, name in enumerate(header) if CHANNEL_PATTERN.match(name.strip())
        ]
        if not channel_indices:
            raise CsvImportError("No se encontró ninguna columna CH1–CH4 reconocible.")
        return time_candidates[0], channel_indices

    @staticmethod
    def _number(value: str) -> float:
        number = float(value.strip())
        if not np.isfinite(number):
            raise ValueError("valor no finito")
        return number

    @staticmethod
    def _channel_name(header: str) -> str:
        match = CHANNEL_PATTERN.match(header.strip())
        return f"CH{match.group(1)}" if match else header.strip()

    @staticmethod
    def _unit(header: str, default: str) -> str:
        match = UNIT_PATTERN.search(header)
        return match.group(1).strip() if match else default

