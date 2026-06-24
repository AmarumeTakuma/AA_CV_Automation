import json
import os
import sys

FIRMWARE_DIR_NAME = "arduino_firmware"


def print_post_generate_checklist(firmware_dir, header_filename):
    """Print a short reminder checklist to prevent missing Arduino upload."""
    ino_path = os.path.join(firmware_dir, "arduino_firmware.ino")
    test_path = os.path.join(os.path.dirname(firmware_dir), "arduino_tests", "pca9685_relay_safe", "pca9685_relay_safe.ino")
    header_path = os.path.join(firmware_dir, header_filename)

    print("\n=== Next Step Checklist ===")
    print("1) Open Arduino IDE and load:")
    print(f"   - {ino_path}")
    print("   - If you are testing wiring only, use:")
    print(f"     * {test_path}")
    print("2) Confirm generated header is present:")
    print(f"   - {header_path}")
    print("3) Verify board/port selection matches your target device.")
    print("4) Install Adafruit_PWMServoDriver library if not already installed.")
    print("5) Upload sketch to Arduino.")
    print("6) Start the desktop app after upload completes.")
    print("===========================\n")

def generate_arduino_header(json_filename="settings.json", header_filename="config.h"):
    # 実行ファイル（main.pyまたはexe）と同じ場所にあるJSONを探す
    if getattr(sys, 'frozen', False):
        application_path = os.path.dirname(sys.executable) # .exe
    else:
        application_path = os.path.dirname(os.path.abspath(__file__)) # .py
    
    json_path = os.path.join(application_path, json_filename)

    firmware_dir = os.path.join(application_path, FIRMWARE_DIR_NAME)

    # ディレクトリがなければ作る
    if not os.path.exists(firmware_dir):
        try:
            os.makedirs(firmware_dir)
            print(f"[Info] Created directory: {firmware_dir}")
        except OSError as e:
            print(f"[Error] Could not create directory '{firmware_dir}': {e}")
            return

    header_path = os.path.join(firmware_dir, header_filename)

    # ファイルの存在確認
    if not os.path.exists(json_path):
        print(f"[Error] Configuration file not found: {json_path}")
        return

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"[Error] Invalid JSON format in {json_path}:\n{e}")
        return

    # データの抽出
    conn_conf = data.get("connection", {})
    baudrate = conn_conf.get("baudrate", 9600)

    # GPIO ピン
    gpio_conf = data.get("gpio_pins", {})
    pin_di1_output = gpio_conf.get("di1_output", -1)
    pin_di2_output = gpio_conf.get("di2_output", -1)
    pin_estop = gpio_conf.get("estop", -1)
    pin_cell_open = gpio_conf.get("cell_open_in", pin_estop)
    # Absorb estop into cell_open_in
    if pin_cell_open >= 0:
        pin_estop = pin_cell_open
    pin_do1 = gpio_conf.get("do1_input", -1)
    pin_do2 = gpio_conf.get("do2_input", -1)
    pin_hw_err = gpio_conf.get("hw_err_in", -1)
    pin_done = gpio_conf.get("done", -1)
    # ▼▼▼ 追加：物理エマストピンの読み込み ▼▼▼
    pin_physical_estop = gpio_conf.get("physical_estop", -1)

    # PCA9685 ピン
    pca_conf = data.get("pca_relays", {})
    pca_servos = data.get("pca_servos", {})
    
    safety = data.get("safety", {})
    wd_timeout = safety.get("watchdog_timeout_ms", 3000)

    sys_limits = data.get("system_limits", {})
    max_pca_channels = sys_limits.get("max_pca_channels", 16)
    max_servos = sys_limits.get("max_servos", 12)

    # GPIO ホワイトリスト（DI1, ESTOP, DONE のみ許可）
    valid_gpio_pins = set()
    if pin_di1_output >= 0:
        valid_gpio_pins.add(pin_di1_output)
    if pin_di2_output >= 0:
        valid_gpio_pins.add(pin_di2_output)
    if pin_estop >= 0:
        valid_gpio_pins.add(pin_estop)
    if pin_cell_open >= 0:
        valid_gpio_pins.add(pin_cell_open)
    if pin_do1 >= 0:
        valid_gpio_pins.add(pin_do1)
    if pin_do2 >= 0:
        valid_gpio_pins.add(pin_do2)
    if pin_hw_err >= 0:
        valid_gpio_pins.add(pin_hw_err)
    if pin_done >= 0:
        valid_gpio_pins.add(pin_done)
    # ▼▼▼ 追加：物理エマストをホワイトリストに登録 ▼▼▼
    if pin_physical_estop >= 0:
        valid_gpio_pins.add(pin_physical_estop)

    valid_gpio_list = sorted(list(valid_gpio_pins))

    # PCA 排他ペア（リレーのみ対象、同種の電極は同時オン禁止）
    exclusive_pairs = []
    relays_by_type = {}
    for cell_name, pins in pca_conf.items():
        for elec_type, channel in pins.items():
            if channel < 0:
                continue
            if elec_type not in relays_by_type:
                relays_by_type[elec_type] = []
            relays_by_type[elec_type].append(channel)

    # 総当たりでペア生成
    for elec_type, channels in relays_by_type.items():
        channels_sorted = sorted(list(set(channels)))
        for i in range(len(channels_sorted)):
            for j in range(i + 1, len(channels_sorted)):
                exclusive_pairs.append((channels_sorted[i], channels_sorted[j]))

    # サーボのデフォルト角度（PCA チャネル + 角度）
    servo_defaults = []
    for name, settings in pca_servos.items():
        channel = settings.get("channel")
        off_angle = settings.get("off_angle", 0)
        if channel is not None and isinstance(channel, int) and channel >= 0:
            servo_defaults.append((channel, off_angle))

    # C++ヘッダー書き出し
    lines = []
    lines.append("// This file is auto-generated by update_config.py")
    lines.append("// DO NOT EDIT THIS FILE MANUALLY")
    lines.append(f"// Source: {json_filename}")
    lines.append("")
    lines.append("#ifndef CONFIG_H")
    lines.append("#define CONFIG_H")
    lines.append("")

    # ボーレート
    lines.append(f"#define BAUDRATE {baudrate}")
    lines.append("")

    # メモリ制限
    lines.append("// --- Firmware Limits (Memory Allocation) ---")
    lines.append(f"const int MAX_GPIO_PINS = 10;")
    lines.append(f"const int MAX_PCA_CHANNELS = {max_pca_channels};")
    lines.append(f"const int MAX_SERVOS = {max_servos};")
    lines.append("")

    # GPIO ピン
    lines.append("// --- GPIO Control Pins (Hardware Assignment) ---")
    lines.append(f"const int DI1_OUTPUT_PIN = {pin_di1_output};")
    lines.append(f"const int DI2_OUTPUT_PIN = {pin_di2_output};")
    lines.append(f"const int ESTOP_PIN = {pin_estop};")
    lines.append(f"// cell open input (alias to ESTOP by default)")
    lines.append(f"const int CELL_OPEN_PIN = {pin_cell_open};")
    lines.append(f"const int DONE_PIN = {pin_done};")
    lines.append(f"const int DO1_PIN = {pin_do1};")
    lines.append(f"const int DO2_PIN = {pin_do2};")
    lines.append(f"const int HW_ERR_PIN = {pin_hw_err};")
    # ▼▼▼ 追加：C++側に定数として書き出し ▼▼▼
    lines.append(f"const int PHYSICAL_ESTOP_PIN = {pin_physical_estop};")
    lines.append("")

    # GPIO ホワイトリスト
    lines.append("// --- Valid GPIO Pins (Whitelist) ---")
    lines.append(f"const int VALID_GPIO_COUNT = {len(valid_gpio_list)};")
    if len(valid_gpio_list) > 0:
        pins_str = ", ".join(map(str, valid_gpio_list))
        lines.append(f"const int VALID_GPIO_PINS[] = {{ {pins_str} }};")
    else:
        lines.append("const int VALID_GPIO_PINS[] = { -1 };")
    lines.append("")

    # PCA9685 排他ペア
    lines.append("// --- PCA9685 Relay Interlock Pairs (Exclusive) ---")
    lines.append(f"const int PCA_PAIR_COUNT = {len(exclusive_pairs)};")
    if len(exclusive_pairs) > 0:
        lines.append("const int PCA_EXCLUSIVE_PAIRS[][2] = {")
        for i, (p1, p2) in enumerate(exclusive_pairs):
            suffix = "," if i < len(exclusive_pairs) - 1 else ""
            lines.append(f"  {{ {p1}, {p2} }}{suffix} // Pair {i+1}")
        lines.append("};")
    else:
        lines.append("const int PCA_EXCLUSIVE_PAIRS[1][2] = {{ -1, -1 }};")
    lines.append("")

    # サーボ デフォルト角度
    lines.append("// --- PCA9685 Servo Default Angles ---")
    lines.append(f"const int SERVO_COUNT_DEF = {len(servo_defaults)};")
    if len(servo_defaults) > 0:
        lines.append("const int SERVO_DEFAULTS[][2] = {")
        for i, (ch, angle) in enumerate(servo_defaults):
            suffix = "," if i < len(servo_defaults) - 1 else ""
            lines.append(f"  {{ {ch}, {angle} }}{suffix} // Channel {ch} -> {angle} deg")
        lines.append("};")
    else:
        lines.append("const int SERVO_DEFAULTS[1][2] = {{ -1, 0 }};")
    lines.append("")

    # ウォッチドッグ
    lines.append("// --- Safety Settings ---")
    lines.append(f"const long WATCHDOG_TIMEOUT = {wd_timeout};")
    lines.append("")

    lines.append("#endif // CONFIG_H")

    # 書き込み
    try:
        with open(header_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))
        print(f"[Success] Generated '{header_filename}' from '{json_filename}'")
        print(f" - Path: {header_path}")
        print(f" - GPIO Pins: {len(valid_gpio_list)}")
        print(f" - PCA Relay Pairs: {len(exclusive_pairs)}")
        print("Please review and upload this config to Arduino now.")
        print_post_generate_checklist(firmware_dir, header_filename)
        
    except Exception as e:
        print(f"[Error] Failed to write header file:\n{e}")

if __name__ == "__main__":
    generate_arduino_header()