from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np


def generate_sample_csv(
    output: str | Path,
    *,
    samples: int = 20_000,
    sample_rate: float = 100_000.0,
) -> Path:
    """Genera una captura determinista y representativa de cuatro canales."""
    if samples < 2:
        raise ValueError("Se requieren al menos dos muestras.")
    if sample_rate <= 0:
        raise ValueError("La tasa de muestreo debe ser positiva.")

    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    time = np.arange(samples, dtype=np.float64) / sample_rate - (samples / sample_rate) / 2
    rng = np.random.default_rng(1104)

    ch1 = 2.0 * np.sin(2 * np.pi * 1_000 * time) + rng.normal(0, 0.025, samples)
    ch2 = np.where(np.sin(2 * np.pi * 200 * time) >= 0, 3.3, 0.0)
    phase = np.mod(time * 600, 1.0)
    ch3 = np.where(phase < 0.45, 5.0, 0.0)
    missing_tooth = np.mod(np.floor(time * 600), 36) == 0
    ch3[missing_tooth] = 0.0
    ch4 = 1.25 + 0.7 * np.sin(2 * np.pi * 25 * time) + 0.15 * np.sin(2 * np.pi * 50 * time)

    with destination.open("w", encoding="utf-8", newline="") as handle:
        handle.write("# Format: Synthetic SIGLENT-like CSV\n")
        handle.write("# Instrument Model: SIGLENT SDS1104X-E (synthetic)\n")
        handle.write(f"# Sample Rate: {sample_rate:.12g} Sa/s\n")
        handle.write(f"# Record Length: {samples}\n")
        handle.write("# Trigger Time: 0 s\n")
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["Time(s)", "CH1(V)", "CH2(V)", "CH3(V)", "CH4(V)"])
        writer.writerows(zip(time, ch1, ch2, ch3, ch4, strict=True))
    return destination


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Genera un CSV sintético para OSC App.")
    parser.add_argument("output", nargs="?", default="examples/siglent_fake_4ch.csv")
    parser.add_argument("--samples", type=int, default=20_000)
    parser.add_argument("--sample-rate", type=float, default=100_000.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    path = generate_sample_csv(args.output, samples=args.samples, sample_rate=args.sample_rate)
    print(f"CSV generado: {path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

