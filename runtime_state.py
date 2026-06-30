from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Protocol, Any


if TYPE_CHECKING:
    from stationkit_measurement_controller import MeasurementExecuteRequest, StationChangeTarget


class StationkitControllerProtocol(Protocol):
    def connect(self, address: str) -> None: ...
    def change(self, target: StationChangeTarget) -> Any: ...
    def execute(self, params: MeasurementExecuteRequest) -> Any: ...
    def status(self) -> dict[str, Any]: ...
    def initialize_all(self) -> None: ...
    def disconnect_now(self) -> None: ...
    def set_interlock(self, enabled: bool) -> None: ...
    def stop_measurement(self) -> None: ...


class OperationState(Enum):
    """Application operation state machine."""
    IDLE = "idle"
    MEASURING = "measuring"
    ESTOP_PENDING = "estop_pending"
    RECOVERING = "recovering"
    FAULT = "fault"
    STOPPED = "stopped"


@dataclass
class RuntimeState:
    config: object = None
    device: object = None
    root: object = None
    stationkit_controller: StationkitControllerProtocol | None = None

    is_closing: bool = False
    operation_state: OperationState = OperationState.IDLE

    last_start_time: float = 0.0
    last_estop_time: float = 0.0

    start_cooldown_sec: float = 0.8
    estop_cooldown_sec: float = 0.5
    estop_pulse_duration_sec: float = 0.5

    elec_chk_vars: dict = field(default_factory=dict)
    master_chk_vars: dict = field(default_factory=dict)
    gas_chk_vars: dict = field(default_factory=dict)

    all_widgets: list = field(default_factory=list)

    start_btn: object = None
    di1_btn: object = None
    estop_chk: object = None
    estop_btn: object = None
    btn_exit: object = None
    exclusive_var: object = None
    estop_var: object = None
    status_label: object = None
    log_combo: object = None

    current_measurement: object = None
    measurement_history: list = field(default_factory=list)
