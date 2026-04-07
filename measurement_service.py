"""
Measurement session management and utilities.
Handles measurement data structure and state collection.
"""

import datetime
from dataclasses import dataclass


@dataclass
class MeasurementSession:
    """Captures all measurement metadata and state."""
    filename: str
    save_dir: str
    target_cell: str
    started_at: datetime.datetime
    selected_electrodes: list
    selected_gas_lines: list
    exclusive_interlock_enabled: bool
    serial_port: str
    ended_at: datetime.datetime = None
    status: str = "running"

    def mark_completed(self):
        """Mark measurement as completed and record end time."""
        self.ended_at = datetime.datetime.now()
        self.status = "completed"

    def duration_seconds(self):
        """Return measurement duration in seconds."""
        if self.ended_at is None:
            return (datetime.datetime.now() - self.started_at).total_seconds()
        return (self.ended_at - self.started_at).total_seconds()

    def to_dict(self):
        """Convert session to dictionary for logging/export."""
        return {
            "filename": self.filename,
            "save_dir": self.save_dir,
            "target_cell": self.target_cell,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_sec": self.duration_seconds(),
            "status": self.status,
            "selected_electrodes": self.selected_electrodes,
            "selected_gas_lines": self.selected_gas_lines,
            "exclusive_interlock_enabled": self.exclusive_interlock_enabled,
            "serial_port": self.serial_port,
        }


def collect_selected_electrodes(elec_chk_vars):
    """
    Collect all currently selected electrodes from checkbox state dictionary.
    
    Args:
        elec_chk_vars: Dict[str, IntVar] of electrode checkbox states.
    
    Returns:
        List of selected electrode names.
    """
    selected = []
    for name, var in elec_chk_vars.items():
        if var.get():
            selected.append(name)
    return selected


def collect_selected_gas_lines(gas_chk_vars):
    """
    Collect all currently selected gas lines from checkbox state dictionary.
    
    Args:
        gas_chk_vars: Dict[str, IntVar] of gas line checkbox states.
    
    Returns:
        List of selected gas line names.
    """
    selected = []
    for name, var in gas_chk_vars.items():
        if var.get():
            selected.append(name)
    return selected
