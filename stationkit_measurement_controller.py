from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
import time
from typing import Any, Literal

from pydantic import BaseModel, Field
from stationkit import StateError, StationControllerBase

from device_controller import DeviceCommunicationError, DeviceTimeoutError
from measurement_file_service import create_measurement_output_file
from measurement_prestart_automation import run_prestart_automation
from measurement_service import MeasurementSession, collect_selected_electrodes, collect_selected_gas_lines
from runtime_state import OperationState
from ui_utils import can_start_measurement, reset_ui_state, set_operation_state, toggle_ui_lock


class StationChangeTarget(BaseModel):
    kind: Literal["electrode", "gas"]
    name: str
    selected: bool = True


class MeasurementExecuteRequest(BaseModel):
    filename: str
    save_dir: str
    target_cell: str
    protocol_name: str = Field(default="CV")


@dataclass(slots=True)
class StationkitChangeResult:
    kind: str
    name: str
    selected: bool


class MeasurementStationController(StationControllerBase):
    def __init__(self, state, add_log=None, handle_device_comm_error=None) -> None:
        super().__init__()
        self.app_state = state
        self.add_log = add_log
        self.handle_device_comm_error = handle_device_comm_error

    def _log(self, message: str) -> None:
        if self.add_log:
            self.add_log(message)

    async def _do_connect(self, address: str) -> None:
        if not self.app_state.device:
            raise StateError("Device is not initialized")

        self._log(f"Connecting to {address}...")
        await asyncio.to_thread(self.app_state.device.connect)
        self.app_state.status_label.config(text=f"Connected to {address}. Initializing...")
        self._log(f"Connected to {address}. Initializing...")
        self.app_state.root.update()

        ok = await asyncio.to_thread(self.app_state.device.initialize_devices)
        if not ok:
            raise DeviceCommunicationError("Device initialization failed.")

        enabled = bool(getattr(self.app_state, "exclusive_var", None) and self.app_state.exclusive_var.get())
        await asyncio.to_thread(self.app_state.device.set_interlock_enabled, enabled)
        if self.app_state.root.winfo_exists():
            self.app_state.status_label.config(text="Connected and Ready.")
            self._log("Initialization completed. Connected and Ready.")
            reset_ui_state(self.app_state)

    def initialize_all(self) -> None:
        if not self.app_state.device:
            raise StateError("Device is not initialized")

        if not self.app_state.device.initialize_devices():
            raise DeviceCommunicationError("Device initialization failed.")

        enabled = bool(getattr(self.app_state, "exclusive_var", None) and self.app_state.exclusive_var.get())
        self.app_state.device.set_interlock_enabled(enabled)
        if self.app_state.root.winfo_exists():
            self.app_state.status_label.config(text="Initialized.")
            reset_ui_state(self.app_state)

    async def _do_disconnect(self) -> None:
        if not self.app_state.device:
            return
        await asyncio.to_thread(self.app_state.device.close)

    async def _do_change(self, target: StationChangeTarget) -> StationkitChangeResult:
        if not self.app_state.device or not self.app_state.device.is_connected:
            raise StateError("change requires a connected device")
        if self.app_state.is_closing:
            raise StateError("Application is closing")
        if self.app_state.operation_state != OperationState.IDLE:
            raise StateError("change requires IDLE state")

        if target.kind == "electrode":
            channel = self.app_state.config.pca_relay_map.get(target.name)
            if channel is None:
                raise StateError(f"Electrode '{target.name}' is not defined in pca_relay_map")
            await asyncio.to_thread(self.app_state.device.set_pca_relay, channel, 1 if target.selected else 0)
            if self.app_state.status_label:
                self.app_state.status_label.config(text=f"{target.name}: {'ON' if target.selected else 'OFF'}")
            return StationkitChangeResult(kind=target.kind, name=target.name, selected=target.selected)

        if target.kind == "gas":
            servo = self.app_state.config.pca_servo_map.get(target.name)
            if not servo:
                raise StateError(f"Gas line '{target.name}' is not defined in pca_servo_map")
            angle = servo["on_angle"] if target.selected else servo["off_angle"]
            await asyncio.to_thread(self.app_state.device.set_servo, servo["channel"], angle)
            if self.app_state.status_label:
                self.app_state.status_label.config(text=f"Gas line {target.name} {'Opened' if target.selected else 'Closed'}")
            return StationkitChangeResult(kind=target.kind, name=target.name, selected=target.selected)

        raise StateError(f"Unsupported change kind: {target.kind}")

    async def _do_execute(self, params: MeasurementExecuteRequest) -> dict[str, Any]:
        if not can_start_measurement(self.app_state):
            raise StateError("Measurement cannot be started in the current state")

        set_operation_state(self.app_state, OperationState.MEASURING, self._log)
        try:
            self.app_state.current_measurement = MeasurementSession(
                filename=params.filename,
                save_dir=params.save_dir,
                target_cell=params.target_cell,
                protocol_name=params.protocol_name,
                started_at=datetime.now(),
                selected_electrodes=collect_selected_electrodes(self.app_state.elec_chk_vars),
                selected_gas_lines=collect_selected_gas_lines(self.app_state.gas_chk_vars),
                exclusive_interlock_enabled=bool(getattr(self.app_state, "exclusive_var", None) and self.app_state.exclusive_var.get()),
                serial_port=self.app_state.config.serial_port,
            )
            self.app_state.measurement_history.append(self.app_state.current_measurement)
            self._log(f"Measurement start request: {params.target_cell} (save: {params.save_dir}/{params.filename})")

            prestart_result = run_prestart_automation(self.app_state, self.app_state.current_measurement, self._log)
            self.app_state.current_measurement.automation_plan_name = prestart_result.plan_name
            if not prestart_result.success:
                set_operation_state(self.app_state, OperationState.IDLE, self._log)
                return {"ok": False, "reason": "prestart_failed", "plan_name": prestart_result.plan_name}

            started = await asyncio.to_thread(self.app_state.device.start_measurement)
            if not started:
                raise DeviceCommunicationError("Measurement start trigger failed")

            output_path = create_measurement_output_file(
                save_dir=params.save_dir,
                filename=params.filename,
                target_cell=params.target_cell,
                selected_electrodes=self.app_state.current_measurement.selected_electrodes,
                selected_gas_lines=self.app_state.current_measurement.selected_gas_lines,
                exclusive_interlock_enabled=self.app_state.current_measurement.exclusive_interlock_enabled,
                serial_port=self.app_state.current_measurement.serial_port,
            )
            self._log(f"Measurement file created: {output_path}")
            if self.app_state.start_btn:
                self.app_state.start_btn.config(relief="sunken")
            self.app_state.root.update()
            toggle_ui_lock(self.app_state, True)
            self.app_state.status_label.config(text=f"Measurement STARTED: {params.target_cell}")
            self._log("Measurement started.")
            self.app_state.last_start_time = time.monotonic()
            return {"ok": True, "output_path": str(output_path), "target_cell": params.target_cell}
        except Exception:
            set_operation_state(self.app_state, OperationState.IDLE, self._log)
            raise

    async def _do_status(self) -> dict[str, Any]:
        current = None
        if self.app_state.current_measurement:
            current = self.app_state.current_measurement.to_dict()
        return {
            "operation_state": self.app_state.operation_state.value,
            "is_connected": bool(self.app_state.device and self.app_state.device.is_connected),
            "current_measurement": current,
            "selected_electrodes": collect_selected_electrodes(self.app_state.elec_chk_vars),
            "selected_gas_lines": collect_selected_gas_lines(self.app_state.gas_chk_vars),
        }

    def set_interlock(self, enabled: bool) -> None:
        if not self.app_state.device:
            raise StateError("Device is not initialized")
        asyncio.run(asyncio.to_thread(self.app_state.device.set_interlock_enabled, enabled))

# ... existing code ...
    def stop_measurement(self) -> None:
        if not self.app_state.device:
            return
        asyncio.run(asyncio.to_thread(self.app_state.device.stop_measurement))

    def disconnect_now(self) -> None:
        asyncio.run(self._do_disconnect())

    # ▼▼▼ 追加：対象セルの排他制御をハードウェアに送信するメソッド ▼▼▼
    def apply_exclusive_routing(self, target_cell: str) -> None:
        if not self.app_state.device:
            raise StateError("Device is not initialized")
        # デバイス通信で画面がフリーズしないよう、別スレッドで安全に実行
        asyncio.run(asyncio.to_thread(self._apply_exclusive_routing_sync, target_cell))

    # ▼▼▼ 追加：ガス名から対象のセル名を推測するロジック ▼▼▼
    def _infer_cell_for_gas(self, gas_name: str) -> str | None:
        upper_name = gas_name.upper().replace("-", " ")
        
        # 1. 完全なセル名が含まれているか
        for cell_name in self.app_state.config.cells_and_electrodes.keys():
            if cell_name.upper() in upper_name:
                return cell_name
                
        # 2. 末尾のアルファベット（A, Bなど）でマッチするか
        tokens = upper_name.split()
        suffix = None
        for token in reversed(tokens):
            if len(token) == 1 and token.isalpha():
                suffix = token
                break
                
        if suffix:
            for cell_name in self.app_state.config.cells_and_electrodes.keys():
                cell_tokens = cell_name.upper().replace("-", " ").split()
                if cell_tokens and cell_tokens[-1] == suffix:
                    return cell_name
                    
        return None
    # ▲▲▲ 追加ここまで ▲▲▲

    def _apply_exclusive_routing_sync(self, target_cell: str) -> None:
        target_electrodes = self.app_state.config.cells_and_electrodes.get(target_cell, [])
        
        # 1. 電極の排他処理
        for elec_name in self.app_state.elec_chk_vars.keys():
            is_target = (elec_name in target_electrodes)
            channel = self.app_state.config.pca_relay_map.get(elec_name)
            if channel is not None:
                self.app_state.device.set_pca_relay(channel, 1 if is_target else 0)
                
        # 2. ガスの排他処理
        for gas_name in self.app_state.gas_chk_vars.keys():
            # ▼▼▼ 変更：推測ロジックを使って対象ガスかどうか判定する ▼▼▼
            inferred_cell = self._infer_cell_for_gas(gas_name)
            
            if inferred_cell:
                is_target = (inferred_cell == target_cell)
            else:
                is_target = (gas_name == target_cell) # 推測できなければ完全一致でフォールバック
            # ▲▲▲ 変更ここまで ▲▲▲
                
            servo = self.app_state.config.pca_servo_map.get(gas_name)
            if servo:
                angle = servo["on_angle"] if is_target else servo["off_angle"]
                self.app_state.device.set_servo(servo["channel"], angle)

    def force_hardware_all_off(self) -> None:
        """エマスト発動時などに呼び出し、全リレーとサーボを物理的にOFFにする"""
        if not self.app_state.device or not self.app_state.device.is_connected:
            return
        
        # 画面をフリーズさせないよう別スレッドで安全に実行
        asyncio.run(asyncio.to_thread(self._force_hardware_all_off_sync))

    def _force_hardware_all_off_sync(self) -> None:
        import time
        try:
            # 1. 最優先：測定器の出力を止める（トリガーOFF）
            self.app_state.device.stop_measurement()
            if hasattr(self.app_state.device, "stop_di2"):
                self.app_state.device.stop_di2()
            self._log("[E-STOP Sequence] 1. Measurement triggers stopped.")
            
            # 測定器からの電流が完全に落ちるまで待機（サージ・アーク防止のため1秒待機）
            time.sleep(1.0)
            
            # 2. 電流が落ちてから、電極リレーを少しずつ時間差でOFFにする
            self._log("[E-STOP Sequence] 2. Disconnecting electrodes...")
            for channel in self.app_state.config.pca_relay_map.values():
                self.app_state.device.set_pca_relay(channel, 0)
                time.sleep(0.1)  # リレー同時遮断によるノイズと負荷を分散
                
            time.sleep(0.5)
            
            # 3. ガスサーボをOFF角度にする
            self._log("[E-STOP Sequence] 3. Closing gas lines...")
            for servo in self.app_state.config.pca_servo_map.values():
                self.app_state.device.set_servo(servo["channel"], servo["off_angle"])
                time.sleep(0.1)  # サーボの同時駆動による電源電圧降下を防ぐ
                
            # 4. 最後にArduino側の全体初期化を呼び、完全な安全状態を確定
            self._log("[E-STOP Sequence] 4. Finalizing device states (SYS,INIT)...")
            self.app_state.device.initialize_devices()
                
            self._log("[System] Hardware shutdown sequence completed safely.")
        except Exception as e:
            self._log(f"[Device Error] Failed to complete safe shutdown: {e}")