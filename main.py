import tkinter as tk
from tkinter import messagebox
import time
import sys

# 自作モジュール
from config_manager import ConfigManager
from device_controller import ArduinoDevice, DeviceCommunicationError, DeviceTimeoutError
from app_ui import MainUI

# ==========================================
# グローバル変数
# ==========================================

# システム・通信系
config = None
device = None
is_closing = False # アプリ終了中の判定フラグ（Trueのときはエラーなど出さずに終了に専念）
comm_recovery_in_progress = False # 通信異常時の1回リカバリ中フラグ
start_in_progress = False
estop_in_progress = False
last_start_time = 0.0
last_estop_time = 0.0
START_COOLDOWN_SEC = 0.8
ESTOP_COOLDOWN_SEC = 0.5

# GUIの状態管理（IntVar を格納する辞書）
elec_chk_vars = {} # 電極のチェックボックス状態 (0 or 1)
master_chk_vars = {} # セル全体の一括チェックボックス状態 (0 or 1)
gas_chk_vars = {} # ガスラインのチェックボックス状態 (0 or 1)

# 特殊なボタン・ウィジェット本体
di1_btn = None # DI1トリガーボタン (元 start_btn)
estop_btn = None # エマストのチェックボタン本体 (見た目や色を変える用)
estop_var = None # エマストのON/OFF状態 (0 or 1)

# 全ウィジェットのリスト（UIロック用）
all_widgets = []

# ==========================================
# ロジック関数 (GUIから呼ばれる処理)
# ==========================================

def connect_app():
    if is_closing: return
    
    # 接続前にポートの存在チェック
    port_exists, available_ports = device.check_port_available()
    
    if not port_exists:
        ports_str = ", ".join(available_ports) if available_ports else "None"
        warn_msg = (f"Port '{config.serial_port}' is NOT detected on this PC.\n\n"
                    f"Available ports: [{ports_str}]\n\n"
                    f"Do you want to attempt connection anyway?\n"
                    f"(Select 'No' to abort and check your settings.json)")
        attempt_anyway = messagebox.askyesno("Port Not Found", warn_msg) # 単なる警告ではなく、ユーザーに選択させる (Yes/No)
        
        # ユーザーがNoを選んだら、接続処理をやめて待機状態にする
        if not attempt_anyway:
            status_label.config(text="Connection aborted. Please check COM port.")
            return

    # 実際の接続処理（ポートが存在した、またはYesが押された場合）
    try:
        if not device.connect():
            status_label.config(text="Connection failed.")
            return
    except DeviceCommunicationError as e:
        print(f"Connection Error: {e}")
        if not is_closing:
            messagebox.showerror("Connection Error", str(e))
            root.destroy()
        return

    status_label.config(text=f"Connected to {config.serial_port}. Initializing...")
    root.update()
    
    if is_closing: return

    try:
        if device.initialize_devices():
            print("Initialization successful. Connected and Ready.")
            try:
                if root.winfo_exists():
                    status_label.config(text="Connected and Ready.")
                    reset_ui_state()
            except tk.TclError:
                pass
            # 定期タスク開始
            check_incoming_data()
            send_heartbeat_loop()
            comm_watchdog_loop()
        else:
            print("Initialization Error: Device initialization failed.")
            if not is_closing:
                messagebox.showerror("Error", "Initialization failed.")
                root.destroy()
    except (DeviceCommunicationError, DeviceTimeoutError) as e:
        print(f"Initialization Error: {e}")
        if not is_closing:
            messagebox.showerror("Initialization Error", str(e))
            root.destroy()

def send_heartbeat_loop():
    if is_closing: return
    device.send_heartbeat()
    
    # 次回予約（ウィンドウが存在する場合のみ）
    try:
        if root.winfo_exists() and not is_closing:
            root.after(config.heartbeat_interval, send_heartbeat_loop)
    except:
        pass

def comm_watchdog_loop():
    if is_closing:
        return

    try:
        if (device and device.is_connected and not comm_recovery_in_progress
            and not start_in_progress and not estop_in_progress):
            device.probe_communication()
    except (DeviceCommunicationError, DeviceTimeoutError) as e:
        handle_device_comm_error("comm_watchdog", e)
    except Exception as e:
        print(f"Error in comm_watchdog_loop: {e}")

    try:
        if root.winfo_exists() and not is_closing:
            interval_ms = max(1000, int(config.watchdog_timeout / 2))
            root.after(interval_ms, comm_watchdog_loop)
    except:
        pass

def check_incoming_data():
    if is_closing: return
    
    try:
        line = device.read_line()
        while line:
            print(f"[Arduino] {line}")
            if "MEASUREMENT_END" in line:
                finish_measurement_handler()
            line = device.read_line()
    except Exception as e:
        print(f"Serial Read Error: {e}")
    
    # 次回予約（ウィンドウが存在する場合のみ）
    try:
        if root.winfo_exists() and not is_closing:
            root.after(100, check_incoming_data)
    except:
        pass

def finish_measurement_handler():
    if is_closing: return
    
    try:
        device.stop_measurement()
    except Exception as e:
        print(f"Error in finish_measurement_handler: {e}")
    finally:
        reset_ui_state()
        try:
            status_label.config(text="Measurement COMPLETED.")
        except tk.TclError:
            pass

def disable_all_widgets_on_error():
    if is_closing: return

    exit_btn = globals().get('btn_exit')

    for widget in all_widgets:
        if widget is exit_btn:
            continue
        if hasattr(widget, 'config'):
            try:
                widget.config(state=tk.DISABLED)
            except tk.TclError:
                pass

    if exit_btn and hasattr(exit_btn, 'config'):
        try:
            exit_btn.config(state=tk.NORMAL)
        except tk.TclError:
            pass

def attempt_one_time_comm_recovery():
    global comm_recovery_in_progress

    if is_closing:
        comm_recovery_in_progress = False
        return

    if not device:
        comm_recovery_in_progress = False
        return

    try:
        # 半断線状態を避けるため、一度ポートを閉じてから再接続を試みる
        if device.ser and device.ser.is_open:
            device.ser.close()
        device.is_connected = False

        if not device.connect():
            raise DeviceCommunicationError("Auto reconnect failed.")
        if not device.initialize_devices():
            raise DeviceCommunicationError("Auto re-initialization failed.")

        reset_ui_state()
        try:
            status_label.config(text="Recovered from communication error. Ready.")
        except tk.TclError:
            pass

        comm_recovery_in_progress = False
    except Exception as recover_err:
        print(f"Auto recovery failed: {recover_err}")
        try:
            device.close()
        except Exception:
            pass
        device.is_connected = False

        try:
            status_label.config(text="Disconnected. Please restart the application.")
        except Exception:
            pass

        try:
            messagebox.showerror(
                "Communication Error",
                f"Auto recovery failed.\n\nDetails: {recover_err}\n\nPlease restart the application."
            )
        except tk.TclError:
            pass

        disable_all_widgets_on_error()
        comm_recovery_in_progress = False

def handle_device_comm_error(context, err):
    global comm_recovery_in_progress

    print(f"Device Communication Error in {context}: {err}")
    if is_closing:
        return

    if comm_recovery_in_progress:
        return

    comm_recovery_in_progress = True

    if device:
        device.is_connected = False

    try:
        status_label.config(text="Communication error detected. Trying auto recovery once...")
    except Exception:
        pass

    disable_all_widgets_on_error()

    for extra_name in ('start_btn', 'di1_btn', 'estop_chk'):
        extra = globals().get(extra_name)
        if extra:
            try:
                extra.config(state=tk.DISABLED)
            except tk.TclError:
                pass

    current_root = globals().get('root')
    if current_root and current_root.winfo_exists():
        try:
            current_root.after(300, attempt_one_time_comm_recovery)
        except tk.TclError:
            comm_recovery_in_progress = False
    else:
        comm_recovery_in_progress = False

def reset_ui_state():
    if is_closing: return
    
    try:
        toggle_ui_lock(False)
        if start_btn: start_btn.config(state=tk.NORMAL, relief=tk.RAISED)
    except tk.TclError:
        pass

def toggle_ui_lock(is_locked):
    if is_closing: return
    
    allowed = [estop_chk]
    try:
        for widget in all_widgets:
            if not hasattr(widget, 'config'):
                continue
            if widget in allowed: continue
            widget.config(state=tk.DISABLED if is_locked else tk.NORMAL)
    except tk.TclError:
        pass

# ==========================================
# ボタン操作イベント
# ==========================================

def on_master_click(cell_name):
    if not device.is_connected or is_closing: return
    
    state = master_chk_vars[cell_name].get()
    
    if state == 0:
        # このセルを全切断
        for ename in config.cells_and_electrodes[cell_name]:
            if elec_chk_vars[ename].get():
                elec_chk_vars[ename].set(0)
                on_elec_click(ename, update_gui=False)
    else:
        # 他セル切断
        for other_cell in config.cells_and_electrodes:
            if other_cell != cell_name:
                master_chk_vars[other_cell].set(0)
                for ename in config.cells_and_electrodes[other_cell]:
                    if elec_chk_vars[ename].get():
                        elec_chk_vars[ename].set(0)
                        on_elec_click(ename, update_gui=False)
        # このセルを全接続
        for ename in config.cells_and_electrodes[cell_name]:
            if not elec_chk_vars[ename].get():
                elec_chk_vars[ename].set(1)
                on_elec_click(ename, update_gui=False)
    
    action_text = "Connected" if state == 1 else "Disconnected"
    status_label.config(text=f"All electrodes in {cell_name} {action_text}.")
    update_master_checkboxes()

def on_elec_click(name, update_gui=True):
    if not device.is_connected or is_closing: return
    
    try:
        state = elec_chk_vars[name].get()
        pin = config.electrode_map.get(name)

        if pin is None:
            error_msg = (f"Config Error:\nElectrode '{name}' is not defined in electrode_map.\nPlease check settings.")
            print(error_msg)
            messagebox.showerror("Configuration Error", error_msg)
            elec_chk_vars[name].set(0)
            return
        
        if state == 1:
            # 排他制御
            ch = config.reverse_elec_exclusive.get(name)
            if not ch:
                error_msg = (f"Config Error:\nElectrode '{name}' is not assigned to any exclusive channel.\nPlease check settings.")
                print(error_msg)
                messagebox.showerror("Configuration Error", error_msg)
                elec_chk_vars[name].set(0)
                return

            for other in config.elec_exclusive_channels.get(ch, []):
                if other != name and other in elec_chk_vars and elec_chk_vars[other].get():
                    other_pin = config.electrode_map.get(other)
                    if other_pin is not None:
                        elec_chk_vars[other].set(0)
                        device.set_digital(other_pin, 0)
                        time.sleep(0.05)
            device.set_digital(pin, 1)
        else:
            device.set_digital(pin, 0)

        if update_gui:
            status_label.config(text=f"{name}: {'ON' if state else 'OFF'}")
            update_master_checkboxes()
    except DeviceCommunicationError as e:
        handle_device_comm_error("on_elec_click", e)
    except DeviceTimeoutError as e:
        print(f"Device Timeout in on_elec_click: {e}")
        if not is_closing:
            messagebox.showerror("Device Error", str(e))
    except Exception as e:
        print(f"Error in on_elec_click: {e}")

def update_master_checkboxes():
    if is_closing: return
    
    try:
        for cell, elecs in config.cells_and_electrodes.items():
            all_on = all(elec_chk_vars[e].get() for e in elecs)
            master_chk_vars[cell].set(1 if all_on else 0)
    except tk.TclError:
        pass

def on_gas_click(name, update_gui=True):
    if not device.is_connected or is_closing: return
    
    try:
        state = gas_chk_vars[name].get()
        s = config.servo_map.get(name)

        if not s:
            error_msg = (f"Config Error:\nGas line '{name}' is not defined in servo_map.\nPlease check settings.")
            print(error_msg)
            messagebox.showerror("Configuration Error", error_msg)
            if name in gas_chk_vars:
                gas_chk_vars[name].set(0)
            return
        
        if state == 1:
            # 排他制御
            ch = config.reverse_gas_exclusive.get(name)
            if ch:
                for other in config.gas_exclusive_channels.get(ch, []):
                    if other != name and other in gas_chk_vars and gas_chk_vars[other].get():
                        gas_chk_vars[other].set(0)
                        other_s = config.servo_map.get(other)
                        if other_s:
                            device.set_servo(other_s['pin'], other_s['off_angle'])
                            time.sleep(0.1)
            device.set_servo(s['pin'], s['on_angle'])
        else:
            device.set_servo(s['pin'], s['off_angle'])

        if update_gui and not is_closing:
            action_text = "Opened" if state == 1 else "Closed"
            status_label.config(text=f"Gas line {name} {action_text}.")
    except DeviceCommunicationError as e:
        handle_device_comm_error("on_gas_click", e)
    except DeviceTimeoutError as e:
        print(f"Device Timeout in on_gas_click: {e}")
        if not is_closing:
            messagebox.showerror("Device Error", str(e))
    except Exception as e:
        print(f"Error in on_gas_click: {e}")

def on_start():
    global start_in_progress, last_start_time

    if not device.is_connected or is_closing: return
    if config.di1_output_pin < 0:
        messagebox.showinfo("Info", "DI1 Output Pin Disabled")
        return

    now = time.monotonic()
    if start_in_progress or (now - last_start_time) < START_COOLDOWN_SEC:
        return

    start_in_progress = True

    try:
        if device.start_measurement():
            print("Measurement STARTED. (UI Locked)")
            start_btn.config(state=tk.DISABLED, relief=tk.SUNKEN)
            toggle_ui_lock(True)
            status_label.config(text="Measurement STARTED.")
            last_start_time = time.monotonic()
    except DeviceCommunicationError as e:
        handle_device_comm_error("on_start", e)
    except DeviceTimeoutError as e:
        print(f"Device Timeout in on_start: {e}")
        if not is_closing:
            messagebox.showerror("Device Error", str(e))
    except Exception as e:
        print(f"Error in on_start: {e}")
    finally:
        start_in_progress = False

def on_estop():
    global estop_in_progress, last_estop_time

    if not device.is_connected or is_closing: return
    if config.estop_pin < 0:
        estop_var.set(0)
        reset_ui_state()
        return

    now = time.monotonic()
    if estop_in_progress or (now - last_estop_time) < ESTOP_COOLDOWN_SEC:
        estop_var.set(0)
        return

    estop_in_progress = True

    try:
        if estop_var.get():
            print("!!! EMERGENCY STOP ACTIVATED !!!")
            device.trigger_estop() # 緊急停止パルス送信 & 測定停止
            estop_chk.config(fg="white", bg="red")
            status_label.config(text="E-STOP ACTIVATED!")
            
            # GUIリセット
            root.update()
            reset_ui_state()
            estop_var.set(0)
            
            # 全体リセット(変数を戻す)
            init_gui_vars()
            estop_chk.config(fg="black", bg="#ffcccc")
            print("E-Stop Released. System Reset.")
            status_label.config(text="E-STOP Released.")
            last_estop_time = time.monotonic()
        else:
            # 万が一OFF操作されたらHighに戻す
            device.set_digital(config.estop_pin, 1)
    except DeviceCommunicationError as e:
        handle_device_comm_error("on_estop", e)
    except DeviceTimeoutError as e:
        print(f"Device Timeout in on_estop: {e}")
        if not is_closing:
            messagebox.showerror("Device Error", str(e))
    except Exception as e:
        print(f"Error in on_estop: {e}")
    finally:
        estop_in_progress = False

def on_init_btn():
    print("Manual initialization requested.")
    try:
        if device.initialize_devices():
            try:
                # チェックボックス等をリセット
                init_gui_vars()
                
                # ボタン・ウィジェットの見た目をリセット
                if root.winfo_exists():
                    if start_btn:
                        start_btn.config(state=tk.NORMAL, relief=tk.RAISED)
                    if di1_btn:
                        di1_btn.config(state=tk.NORMAL, relief=tk.RAISED)
                    if estop_btn:
                        estop_btn.config(fg="black", bg="#ffcccc")
                    estop_var.set(0)
                    status_label.config(text="Initialized.")
                
                # UI ロック解除
                reset_ui_state()
            except tk.TclError:
                pass
        else:
            if not is_closing:
                messagebox.showerror("Error", "Initialization failed.")
    except DeviceCommunicationError as e:
        handle_device_comm_error("on_init_btn", e)
    except DeviceTimeoutError as e:
        print(f"Initialization Timeout: {e}")
        if not is_closing:
            messagebox.showerror("Initialization Error", str(e))

def init_gui_vars():
    for v in elec_chk_vars.values(): v.set(0)
    for v in master_chk_vars.values(): v.set(0)
    for v in gas_chk_vars.values(): v.set(0)

def on_close():
    global is_closing
    print("Application closing...")
    is_closing = True
    device.close()
    root.destroy()

# ==========================================
# メイン実行 (GUI構築と初期化)
# ==========================================

if __name__ == '__main__':
    # Tkinterの土台を先に作る（エラーのポップアップを安全に出すため）
    root = tk.Tk()
    root.title("Electrode Controller")

    # 設定の読み込みとデバイスの準備
    try:
        config = ConfigManager("settings.json") # 設定読み込み
        err = config.validate()
        if err:
            print(f"[Config Error] {err}")
            messagebox.showerror("Config Error", err)
            sys.exit(1)
        print("Configuration loaded and validated.")
        device = ArduinoDevice(config) # デバイス管理クラスの作成
    except Exception as e:
        print(f"[Fatal Error] {e}")
        messagebox.showerror("Initialization Error", str(e))
        sys.exit(1)

    ui = MainUI(
        root,
        config,
        {
            "on_master_click": on_master_click,
            "on_elec_click": on_elec_click,
            "on_gas_click": on_gas_click,
            "on_start": on_start,
            "on_estop": on_estop,
            "on_init_btn": on_init_btn,
            "on_close": on_close,
        },
    )
    ui.build()

    elec_chk_vars = ui.elec_chk_vars
    master_chk_vars = ui.master_chk_vars
    gas_chk_vars = ui.gas_chk_vars
    all_widgets = ui.lockable_widgets
    start_btn = ui.start_btn
    di1_btn = ui.start_btn
    estop_var = ui.estop_var
    estop_chk = ui.estop_chk
    estop_btn = ui.estop_chk
    btn_exit = ui.btn_exit
    status_label = ui.status_label

    # イベントバインド
    root.protocol("WM_DELETE_WINDOW", on_close)
    root.bind('<Escape>', lambda e: (estop_var.set(1), on_estop()))
    root.after(100, connect_app)

    root.mainloop()