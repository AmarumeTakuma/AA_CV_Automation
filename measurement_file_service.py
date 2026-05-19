"""Helpers for creating measurement output files.

This module keeps the start flow simple: once the user selects a file name
and save directory, the app can create the target CSV file immediately.
"""

from __future__ import annotations

import csv
from pathlib import Path


def build_measurement_output_path(save_dir: str, filename: str) -> Path:
    """Return the absolute path for the measurement output file."""
    return Path(save_dir) / filename


def create_measurement_output_file(
    save_dir: str,
    filename: str,
    target_cell: str,
    *,
    selected_electrodes: list[str] | None = None,
    selected_gas_lines: list[str] | None = None,
    exclusive_interlock_enabled: bool | None = None,
    serial_port: str | None = None,
) -> Path:
    """Create the measurement CSV file with a small metadata header.

    The file is created immediately so the chosen name and folder exist
    as soon as the measurement starts.
    """
    output_path = build_measurement_output_path(save_dir, filename)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["measurement_start"])
        writer.writerow(["target_cell", target_cell])
        writer.writerow(["filename", filename])
        writer.writerow(["save_dir", str(output_path.parent)])
        if serial_port is not None:
            writer.writerow(["serial_port", serial_port])
        if exclusive_interlock_enabled is not None:
            writer.writerow(["exclusive_interlock_enabled", str(exclusive_interlock_enabled)])
        if selected_electrodes is not None:
            writer.writerow(["selected_electrodes", ";".join(selected_electrodes)])
        if selected_gas_lines is not None:
            writer.writerow(["selected_gas_lines", ";".join(selected_gas_lines)])

    return output_path
