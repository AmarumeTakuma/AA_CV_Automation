from dataclasses import dataclass, field


@dataclass
class RuntimeState:
    config: object = None
    device: object = None
    root: object = None

    is_closing: bool = False
    comm_recovery_in_progress: bool = False
    start_in_progress: bool = False
    estop_in_progress: bool = False
    exclusive_toggle_in_progress: bool = False

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
