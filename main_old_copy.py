# --- 関数定義 ---

""" Arduinoにコマンドを送信し、成功ログを待つ """
def send_command(command_to_send):
    if not (ser and ser.is_open):
        if not is_closing:
            status_label.config(text="Error: Not connected.")
        return False
    
    try:        
        ser.reset_input_buffer() # バッファに残っている古いデータをクリア
        
        ser.write(command_to_send.encode()) # コマンド送信
        print(f"Sent: {command_to_send.strip()}")

        start_time = time.time()
        timeout = 1.0 # デッドラインは1秒

        while (time.time() - start_time) < timeout:
            if ser.in_waiting > 0:
                # データを読み取り、デコードして表示
                line = ser.readline().decode('utf-8', errors='replace').strip()
                
                # "executed"が含まれているかチェック
                if "executed" in line.lower():
                    # print(f"Ack Received: {line}")
                    return True
                
            time.sleep(0.01)

        # タイムアウト
        print(f"Timeout: No 'executed' response for '{command_to_send.strip()}'")
        if not is_closing: # 終了中はエラーを出さない
            status_label.config(text="Communication unstable: No response.")
            messagebox.showwarning("Communication Warning", 
                                   f"Device did not respond (No 'executed' message).\n\nCommand: {command_to_send}")
        return False
    
    except serial.SerialException as e:
        if not is_closing: # 終了中はエラーを出さない
            print(f"\n--- COMMUNICATION ERROR ---\nDetails: {e}\n--------------------\n")
            messagebox.showerror("Communication Error", f"Failed to send command.\nConnection may be lost.\n\nError: {e}")
            status_label.config(text="Disconnected. Please restart the application.")
            disable_all_widgets_on_error()
        return False

"""定期的にHBコマンドを送る"""
def send_heartbeat():
    global ser
    if ser and ser.is_open:
        try:
            ser.write(b"HB\n") # ログを出さない
            window.after(HEARTBEAT_INTERVAL, send_heartbeat) # 次回の予約
        except Exception:
            pass

""" Arduinoからのシリアル入力を監視・表示する """
def check_serial_input():
    if is_closing: return
    if ser and ser.is_open:
        try:
            # 受信データがあるか確認
            while ser.in_waiting > 0:
                line = ser.readline().decode('utf-8', errors='replace').strip()
                if line:
                    print(f"[Arduino] {line}")

                    # 測定終了処理
                    if "MEASUREMENT_END" in line:
                        finish_measurement()
                    
        except Exception as e:
            print(f"Serial Read Error: {e}")
    
    # 100ms後に再実行
    try:
        if window.winfo_exists() and not is_closing:
            window.after(100, check_serial_input)
    except:
        pass

""" 管理下の全デバイス、電極、サーボモータを初期状態(OFF)にする """
def initialize_all_devices():
    if not (ser and ser.is_open): return False

    success = True
    # 電極をすべて切断
    for elec_pin in ELECTRODE_MAP.values():
        if not send_command(f"DO,{elec_pin},0\n"): success = False # DigitalOutput用コマンドは DO,pin,0/1
        time.sleep(0.02)
    # サーボモータをすべてOFF角度へ
    for settings in SERVO_MAP.values():
        servo_pin = settings['pin']
        if servo_pin < 0: continue # ピンが無効ならコマンドを送らない
        off_angle = settings['off_angle']
        if not send_command(f"SV,{servo_pin},{off_angle}\n"): success = False # サーボ用コマンドは SV,pin,angle
        time.sleep(0.05)
    # HZ-ProのDIをすべてHIGHへ（Active Lowにするので待機時はHIGH）
    if DI1_OUTPUT_PIN >= 0:
        if not send_command(f"DO,{DI1_OUTPUT_PIN},1\n"): success = False
    time.sleep(0.05)
    if E_STOP_PIN >= 0:
        if not send_command(f"DO,{E_STOP_PIN},1\n"): success = False

    # GUI更新（終了中は行わない）
    if not is_closing:
        try:
            # チェックボックス等状態更新
            for var in elec_check_vars.values(): var.set(0)
            for var in master_elec_check_vars.values(): var.set(0)
            for var in gas_check_vars.values(): var.set(0)
            if estop_var: estop_var.set(0)

            # UIのロック解除、DI1出力/エマストボタン状態リセット
            toggle_ui_lock(False)
            if di1_output_button: di1_output_button.config(state=tk.NORMAL, relief=tk.RAISED)
            if estop_button:
                estop_button.config(fg="black", font=("Arial", 9, "bold"))

            if 'status_label' in globals() and status_label.winfo_exists():
                status_label.config(text="Device initialization finished.")

        except tk.TclError:
            print("Notice: GUI update skipped (Window closed).")

    print("Device initialization attempt finished.")
    return success

""" UIをロックする処理 """
def toggle_ui_lock(is_locked): # True：ロック、False：解除
    if is_closing: return

    # エマストのみ操作可能
    allowed_widgets = [estop_button]

    for widget in all_widgets:
        if widget in allowed_widgets:
            continue
            
        if is_locked:
            widget.config(state=tk.DISABLED)
        else:
            widget.config(state=tk.NORMAL)

""" 一括操作チェックボックスがクリックされたときの処理 """
def on_master_checkbox_click(cell_name):
    if not (ser and ser.is_open) or is_closing: return

    state = master_elec_check_vars[cell_name].get()
    electrodes_in_cell = CELLS_AND_ELECTRODES[cell_name]
    if state == 0:
        #このセルをすべて切断する
        for elec_name in electrodes_in_cell:
            if elec_check_vars[elec_name].get() == 1:
                elec_check_vars[elec_name].set(0)
                on_check_click(elec_name, update_gui=False)

    else:
        # 他のセルをすべて切断する
        for other_cell_name in CELLS_AND_ELECTRODES:
            if other_cell_name != cell_name:
                for elec_name in CELLS_AND_ELECTRODES[other_cell_name]:
                    if elec_check_vars[elec_name].get() == 1:
                        elec_check_vars[elec_name].set(0)
                        on_check_click(elec_name, update_gui=False)
        # このセルをすべて接続する
        for elec_name in electrodes_in_cell:
            if elec_check_vars[elec_name].get() == 0:
                elec_check_vars[elec_name].set(1)
                on_check_click(elec_name, update_gui=False)
    
    # ログを表示
    action_text = "Connected" if state == 1 else "Disconnected"
    status_label.config(text=f"All electrodes in {cell_name} {action_text}.")
    update_all_master_checkboxes()

""" 電極チェックボックスがクリックされたときの処理 """
def on_check_click(clicked_elec_name, update_gui=True):
    if not (ser and ser.is_open) or is_closing: return

    new_state = elec_check_vars[clicked_elec_name].get()
    pin_number = ELECTRODE_MAP.get(clicked_elec_name)

    # ピン番号が未定義であった場合
    if not pin_number:
        error_msg = (f"Config Error:\nElectrode '{clicked_elec_name}' is not defined in ELECTRODE_MAP.\nPlease check the spelling.")
        print(error_msg)
        messagebox.showerror("Configuration Error", error_msg)
        if clicked_elec_name in elec_check_vars:
             elec_check_vars[clicked_elec_name].set(0)
        return
    
    if new_state == 0:
        # この電極を切断する
        send_command(f"DO,{pin_number},0\n")

    else:
        channel_name = REVERSE_ELEC_EXCLUSIVE_CHANNELS.get(clicked_elec_name)
        # 接続したい電極が排他チャンネルに入っていなかった場合
        if not channel_name:
            error_msg = (f"Config Error:\nElectrode '{clicked_elec_name}' is not assigned to any EXCLUSIVE_CHANNELS.\nPlease add it to the correct channel.")
            print(error_msg)
            messagebox.showerror("Configuration Error", error_msg)
            elec_check_vars[clicked_elec_name].set(0)
            return
        # 他セルの同種の電極を切断する
        for elec_name_in_channel in ELEC_EXCLUSIVE_CHANNELS[channel_name]:
            if elec_name_in_channel != clicked_elec_name and elec_name_in_channel in elec_check_vars and elec_check_vars[elec_name_in_channel].get() == 1:
                elec_check_vars[elec_name_in_channel].set(0)
                pin_to_disconnect = ELECTRODE_MAP[elec_name_in_channel]
                send_command(f"DO,{pin_to_disconnect},0\n")
                time.sleep(0.05)
        # この電極を接続する
        send_command(f"DO,{pin_number},1\n")

    # 一括操作以外の場合ではログを表示
    if update_gui and not is_closing:
        action_text = "Connected" if new_state == 1 else "Disconnected"
        status_label.config(text=f"{action_text} {clicked_elec_name}.")
        update_all_master_checkboxes()

""" 親チェックボックスの状態を矛盾がないように更新する """
def update_all_master_checkboxes():
    if is_closing: return
    for cell_name, electrodes_in_cell in CELLS_AND_ELECTRODES.items():
        are_all_electrodes_connected = all(elec_check_vars[elec_name].get() == 1 for elec_name in electrodes_in_cell)
        master_elec_check_vars[cell_name].set(1 if are_all_electrodes_connected else 0)

""" ガスチェックボックスがクリックされたときの処理 """
def on_gas_check_click(clicked_gasline_name, update_gui=True):
    if not (ser and ser.is_open) or is_closing: return

    new_state = gas_check_vars[clicked_gasline_name].get()
    servo_info = SERVO_MAP.get(clicked_gasline_name)

    # ガスラインの情報がなかった場合
    if not servo_info:
        error_msg = (f"Config Error:\nGas line '{clicked_gasline_name}' is not defined in SERVO_MAP.\nPlease check the spelling.")
        print(error_msg)
        messagebox.showerror("Configuration Error", error_msg)
        if clicked_gasline_name in gas_check_vars:
            gas_check_vars[clicked_gasline_name].set(0)
        return

    if new_state == 0:
        # このガスラインを閉じる
        send_command(f"SV,{servo_info['pin']},{servo_info['off_angle']}\n")
    else:
        channel_name = REVERSE_GAS_EXCLUSIVE_CHANNELS.get(clicked_gasline_name)
        # パージ以外のガスラインで真
        if channel_name:
            # 他ガスラインを閉じる
            for gasline_name_in_channel in GAS_EXCLUSIVE_CHANNELS[channel_name]:
                if gasline_name_in_channel != clicked_gasline_name and gasline_name_in_channel in gas_check_vars and gas_check_vars[gasline_name_in_channel].get() == 1:
                    gas_check_vars[gasline_name_in_channel].set(0)
                    servo_info_to_close = SERVO_MAP[gasline_name_in_channel]
                    send_command(f"SV,{servo_info_to_close['pin']},{servo_info_to_close['off_angle']}\n")
                    time.sleep(0.1)
        # このガスラインを開く
        send_command(f"SV,{servo_info['pin']},{servo_info['on_angle']}\n")

    # ログを表示（現時点では常にTrue）
    if update_gui and not is_closing:
        action_text = "Opened" if new_state == 1 else "Closed"
        status_label.config(text=f"Gas line {clicked_gasline_name} {action_text}.")

""" DI1 Outputボタンが押されたときの処理 """
def trigger_di1_output():
    if not (ser and ser.is_open) or is_closing: return

    # DI1_OUTPUT_PINが無効なら何もしない（メッセージを出す）
    if DI1_OUTPUT_PIN < 0:
        messagebox.showinfo("Info", "DI1 Output Pin is disabled in settings.")
        return
    
    toggle_ui_lock(True)

    # Active Lowでパルス出力 (0.5秒間 LOW)
    try:
        send_command(f"DO,{DI1_OUTPUT_PIN},0\n")
        status_label.config(text="DI1 Output Triggered (Pulse).")
        window.update() # GUIを強制更新して表示を反映
        time.sleep(0.5)   
        send_command(f"DO,{DI1_OUTPUT_PIN},1\n")

    finally:
        toggle_ui_lock(False)

""" 正常に測定が終了したときの処理（Arduinoからの信号でトリガー） """
def finish_measurement():
    if is_closing: return

    # 測定終了信号を受信した際のログ表示のみ行う
    print("Measurement finished signal received.")
    status_label.config(text="Signal: MEASUREMENT_END received.")

""" エマストボタンが押されたときの処理 """
def on_estop_click():
    if not (ser and ser.is_open) or is_closing: return
    
    # ピンが無効ならUIリセットだけ
    if E_STOP_PIN < 0:
        estop_var.set(0)
        return
    
    # ユーザーが押してONにしたときのみ動作
    if estop_var.get() == 1:
        # Active Lowでパルス送信
        send_command(f"DO,{E_STOP_PIN},0\n")
        estop_button.config(fg="white", font=("Arial", 9, "bold"))
        status_label.config(text="Measurement ABORTED via E-STOP. Device Reset.")
        window.update() # GUIを強制更新して表示を反映
        time.sleep(0.5)
        send_command(f"DO,{E_STOP_PIN},1\n") 
        
        # 固有のUIリセット
        estop_var.set(0)
        estop_button.config(fg="black", font=("Arial", 9, "bold"))
        status_label.config(text="E-STOP Released. Ready for next measurement.")
    else:
        # 万が一OFF操作された場合も安全のためHIGHを送っておく
        send_command(f"DO,{E_STOP_PIN},1\n")

""" プログラム進行中、エラーの際にGUI上の全ウィジェットを無効化する """
def disable_all_widgets_on_error():
    if is_closing: return
    for widget in all_widgets:
        widget.config(state=tk.DISABLED)
    if di1_output_button: di1_output_button.config(state=tk.DISABLED)

""" 正常にプログラムを終了する """
def on_closing():
    global is_closing

    print("\n--- Closing Application ---")
    is_closing = True

    if ser and ser.is_open:
        print("Resetting devices...")
        initialize_all_devices()

        ser.close()
        print("Serial port closed.")

    window.destroy()
    print("Application closed.")

# --- メインの実行部分 ---

if __name__ == '__main__':
    load_settings()
    generate_maps()

    window = tk.Tk()
    window.title("Electrode Controller")

    # 辞書の整合性チェック
    config_error = validate_configuration()
    if config_error:
        print(f"\n--- CONFIGURATION ERROR ---\n{config_error}\n---------------------------\n")
        messagebox.showerror("Configuration Error", config_error)
        window.destroy()

    else:
        # GUI作成
        main_container = tk.Frame(window)
        main_container.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

        # 左側：電極制御
        elec_frame = tk.LabelFrame(main_container, text="Electrode Control", padx=10, pady=5)
        elec_frame.pack(side=tk.LEFT, padx=5, fill=tk.Y, anchor=tk.N)

        groups_container_frame = tk.Frame(elec_frame)
        groups_container_frame.pack()

        for cell_name, electrodes_in_cell in CELLS_AND_ELECTRODES.items():
            # セルごとのフレーム
            cell_frame = tk.LabelFrame(groups_container_frame, text=cell_name, padx=10, pady=5, font=("Helvetica", 11, "bold"))
            cell_frame.pack(side=tk.LEFT, padx=10, pady=5, fill=tk.Y, anchor=tk.N)
            
            # 親チェックボックス
            var_master = tk.IntVar()
            chk_master = tk.Checkbutton(cell_frame, text="Connect / Disconnect All", variable=var_master, command=lambda g=cell_name: on_master_checkbox_click(g))
            chk_master.pack(anchor=tk.W)
            master_elec_check_vars[cell_name] = var_master
            all_widgets.append(chk_master)

            # 子チェックボックス
            for elec_name in electrodes_in_cell:
                electrode_type = elec_name.split('-')[1]
                var = tk.IntVar(value=0)
                checkbox = tk.Checkbutton(cell_frame, text=electrode_type, variable=var, command=lambda a=elec_name: on_check_click(a))
                checkbox.pack(anchor=tk.W, padx=10)
                elec_check_vars[elec_name] = var
                all_widgets.append(checkbox)

        # 右側：ガス制御、HZ-Pro制御
        right_container = tk.Frame(main_container)
        right_container.pack(side=tk.LEFT, padx=5, fill=tk.Y, anchor=tk.N)

        # ガス
        gas_frame = tk.LabelFrame(right_container, text="Gas Control (Servo)", padx=10, pady=10)
        gas_frame.pack(fill=tk.X, anchor=tk.N, pady=(0, 10))

        for gas_name, settings in SERVO_MAP.items():
            if settings.get('pin', -1) < 0: continue # ピンが無効ならGUIに表示しない

            var = tk.IntVar(value=0)
            checkbox = tk.Checkbutton(gas_frame, text=gas_name, variable=var, command=lambda gn=gas_name: on_gas_check_click(gn))
            checkbox.pack(anchor=tk.W)
            gas_check_vars[gas_name] = var
            all_widgets.append(checkbox)

        # HZ-Pro
        measurement_frame = tk.LabelFrame(right_container, text="HZ-Pro Control (Active Low)", padx=10, pady=10)
        measurement_frame.pack(fill=tk.X, anchor=tk.N, pady=(0, 10))

        # DI1 Output ボタン
        di1_output_button = tk.Button(measurement_frame, text="Trigger DI1 Output", bg="#ccffcc", 
                                 width=20, height=2, command=trigger_di1_output)
        di1_output_button.pack(pady=5)
        all_widgets.append(di1_output_button)

        # E-STOP ボタン
        estop_var = tk.IntVar(value=0)
        estop_button = tk.Checkbutton(measurement_frame, text="E-STOP [Esc]", bg="#ffcccc", variable=estop_var, 
                             indicatoron=0, selectcolor="red", 
                             width=20, height=2, fg="black", font=("Arial", 9, "bold"),
                             command=on_estop_click)
        estop_button.pack(pady=2)
        all_widgets.append(estop_button)

        # リセット関係
        bottom_frame = tk.Frame(window)
        bottom_frame.pack(side=tk.BOTTOM, pady=10, fill=tk.X, padx=10)

        # 初期化ボタン
        initialize_button = tk.Button(bottom_frame, text="Initialize All Devices", command=initialize_all_devices,
                                      width=20, height=2)
        initialize_button.pack(side=tk.LEFT, padx=20)
        all_widgets.append(initialize_button)

        # 終了ボタン
        quit_button = tk.Button(bottom_frame, text="Exit Application", command=on_closing, 
                                width=20, height=2)
        quit_button.pack(side=tk.RIGHT, padx=20)
        all_widgets.append(quit_button)

        # ログ表示のためのラベル
        status_label = tk.Label(window, text="Connecting...", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        status_label.pack(side=tk.BOTTOM, fill=tk.X)
        
        window.protocol("WM_DELETE_WINDOW", on_closing)
        window.after(100, connect_to_arduino)

        window.bind('<Escape>', lambda e: (estop_var.set(1), on_estop_click()))
        
        window.mainloop()