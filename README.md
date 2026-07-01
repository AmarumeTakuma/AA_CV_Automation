# AA_CV_Automation

電気化学測定の前処理と装置切り替えを、PC 上の Python アプリと Arduino ファームウェアで連携して自動化するためのプロジェクトです。

このリポジトリでは、GUI から次の操作をまとめて扱えます。

- 電極セルの選択と排他制御
- ガスラインの切り替え
- 測定開始トリガーの送出
- 緊急停止 E-STOP
- 測定開始前の外部アプリ操作の自動化
- 測定ファイルの即時作成とメタデータ記録

設定の中心は `settings.json` です。PC 側の Python アプリと Arduino 側の設定は、この 1 ファイルを元に同期させます。

## まず全体像

1. `settings.json` を実験環境に合わせて編集します。
2. `update_config.py` を実行して Arduino 用の `arduino_firmware/config.h` を生成します。
3. Arduino IDE で `arduino_firmware/arduino_firmware.ino` を書き込みます。
4. `main.py` を起動して GUI から装置を操作します。

## リポジトリ構成

```text
AA_CV_Automation/
├── main.py
├── app_ui.py
├── config_manager.py
├── device_controller.py
├── device_lifecycle.py
├── error_handler.py
├── measurement_workflow.py
├── measurement_prestart_automation.py
├── measurement_start_dialog.py
├── measurement_service.py
├── measurement_automation_models.py
├── stationkit_measurement_controller.py
├── runtime_state.py
├── selection_manager.py
├── system_actions.py
├── ui_utils.py
├── update_config.py
├── settings.json
├── pyproject.toml
├── uv.lock
├── README.md
├── arduino_firmware/
│   ├── arduino_firmware.ino
│   └── config.h            # 自動生成
├── tests_arduino/
│   ├── pca9685_relay_safe/
│   │   └── pca9685_relay_safe.ino
│   └── pca9685_servo_sweep/
│       └── pca9685_servo_sweep.ino
├── mock/
│   └── mock_hoktnet.py
├── start_btn.png
├── start_btn_dummy.png
└── selection_manager.py.bak
```

補足:

- `arduino_firmware/config.h` は生成物です。手で編集しないでください。
- `tests_arduino/` は診断用スケッチです。本番用の `arduino_firmware/` とは分けて運用してください。
- `start_btn_dummy.png` は、開始前の自動操作で使われる画像認識用の素材です。

## 役割ごとの概要

- `main.py`: アプリ起動、GUI 構築、状態管理の起点。
- `app_ui.py`: Tkinter で画面を組み立てる UI 実装。
- `config_manager.py`: `settings.json` の読込、検証、内部マップ生成。
- `device_controller.py`: Arduino へのシリアル通信と各種コマンド送信。
- `stationkit_measurement_controller.py`: StationKit 経由の測定開始、停止、状態確認。
- `measurement_workflow.py`: 測定開始・終了の制御。
- `measurement_prestart_automation.py`: 測定直前の GUI 自動操作。
- `measurement_start_dialog.py`: ファイル名、保存先、対象セルの選択ダイアログ。
- `selection_manager.py`: 電極とガスラインの個別操作、排他制御。
- `system_actions.py`: E-STOP、初期化、終了処理。
- `ui_utils.py`: 状態遷移、UI ロック、ログ更新の共通処理。
- `update_config.py`: `settings.json` から Arduino 用設定ヘッダを生成。

## 必要なもの

- Windows
- Python 3.12 以上
- Arduino IDE
- Arduino 本体と接続機器一式
- `stationkit` が利用できる Python 環境
- `pyserial`, `pyautogui`, `keyboard`, `opencv-python`, `pywin32` などの依存パッケージ

推奨は `uv` を使う方法です。`pyproject.toml` と `uv.lock` が用意されています。

## 初回セットアップ

### 1. 依存関係の導入

```powershell
uv sync
```

`uv` を使わない場合は、通常の Python 環境に対して依存関係を入れてください。

```powershell
pip install keyboard opencv-python pyautogui pyperclip pyserial pywin32 typer "stationkit @ git+https://github.com/Nu424/stationkit.git"
```

### 2. `settings.json` を編集する

接続先の COM ポート、ピン割り当て、セル構成、サーボ角度を実験環境に合わせて修正します。

### 3. Arduino 用設定を生成する

`settings.json` を変更したら、必ず Arduino 側の設定ファイルを再生成します。

```powershell
uv run python update_config.py
```

`uv` を使わない場合は次でも構いません。

```powershell
python update_config.py
```

### 4. Arduino IDE でスケッチを書き込む

`arduino_firmware/arduino_firmware.ino` を Arduino IDE で開き、ボードとポートを選んで書き込みます。

### 5. PC アプリを起動する

```powershell
uv run python main.py
```

`uv` を使わない場合は次です。

```powershell
python main.py
```

## 操作の流れ

1. アプリ起動後、`settings.json` が読み込まれます。
2. GUI で `START` を押します。
3. 測定ダイアログでファイル名、保存先、対象セルを選びます。
4. 必要に応じて開始前の自動操作を実行します。
5. Arduino に DI1 の開始トリガーが送られます。
6. 指定した名前と保存先は測定セッション情報として保持され、実際の保存は下流の測定ソフト側で行われます。
7. 測定完了信号を受けると、停止処理が走って待機状態に戻ります。

`E-STOP` は画面上のボタンに加えて、`Esc` キーでも発動できます。

## 画面の見方

- `START`: 測定開始ダイアログを開きます。
- `E-STOP [Esc]`: 緊急停止を実行します。
- `Individual Controls`: 電極とガスラインの個別操作を開閉します。
- `Exclusive Interlock`: セル選択時の排他制御を有効・無効にします。通常は有効のまま使います。
- `Initialize All`: 全デバイスを安全な初期状態に戻します。
- `Exit`: アプリを終了します。

個別操作では、セルごとに次の項目を扱います。

- 電極の `All` と `WE` / `CE` / `RE`
- ガスラインの個別選択

## `settings.json` の見方

このファイルが最重要です。大きく分けて以下の項目があります。

### `connection`

- `port`: Arduino が接続される COM ポート名です。例: `COM5`
- `baudrate`: シリアル通信速度です。Arduino 側と一致させてください。

### `gpio_pins`

Arduino のデジタルピン割り当てです。

- `di1_output`: 測定開始トリガー出力
- `di2_output`: 予備のトリガー出力
- `cell_open_in`: E-STOP またはセルオープン入力
- `do1_input`: 測定完了入力
- `do2_input`: 予備入力
- `hw_err_in`: ハードウェア異常入力
- `physical_estop`: 物理 E-STOP 用のピン

注意:

- `di1_output` と `cell_open_in` は Active Low 前提です。
- 0 / 1 番ピンはシリアル通信で使うため避けてください。
- 13 番ピンは警告 LED として使われることがあるため避けるのが安全です。

### `pca9685`

PCA9685 のアドレスと周波数です。

- `address`: I2C アドレス
- `frequency`: サーボ駆動周波数

### `pca_relays`

セルごとの電極マップです。

例:

```json
"pca_relays": {
  "Cell A": {"WE": 0, "CE": 1, "RE": 2},
  "Cell B": {"WE": 4, "CE": 5, "RE": 6}
}
```

各セルに `WE`, `CE`, `RE` が必要です。1 つでも欠けると設定検証で止まります。

### `pca_servos`

ガスライン用サーボの設定です。

- `channel`: PCA9685 のチャネル番号
- `on_angle`: 開状態の角度
- `off_angle`: 閉状態の角度
- `group`: 同一グループとして排他制御したい場合に使います

`on_angle` と `off_angle` の差が小さすぎると不安定になるため、十分な差を持たせてください。

### `safety`

- `watchdog_timeout_ms`: ハートビートが途切れたときに安全停止へ入るまでの時間
- `min_angle_diff`: サーボ角度差の最小値
- `prohibited_pca_channels`: 使わない PCA チャネルを明示したい場合の予約欄

### `validation`

- `required_electrodes`: 各セルに必須の電極タイプです。通常は `WE`, `CE`, `RE` です。

### `system_limits`

- `max_pca_channels`: 使える PCA チャネル上限
- `max_servos`: サーボ数上限
- `allowed_baudrates`: 許可する通信速度の一覧

### `measurement_prestart`

測定開始前に行う GUI 自動操作の定義です。

- `plan_name`: 手順セットの名前
- `steps`: 実行手順の配列

対応する代表的なアクションには、`focus_window`, `wait`, `click`, `locate_and_click`, `press`, `hotkey`, `write_text`, `paste_text` があります。

`START` ダイアログで `Change Settings` や `Configure DIO` を選ぶと、設定された手順に応じた開始前自動化が走ります。どちらもオフの場合は、簡易ルートで開始ボタン画像を探して操作します。

## 測定ファイル

測定開始時には、指定したファイル名と保存先が測定セッション情報として扱われます。このアプリ側では新しいファイルを作成しません。

セッションには次の情報が保持されます。

- 対象セル
- 保存先
- シリアルポート
- 排他インターロックの有効状態
- 選択中の電極
- 選択中のガスライン

保存先は前回値が `.last_save_dir` に記憶されます。

## 安全上の注意

- Arduino と測定器の GND は共通化してください。
- サーボ電源は可能なら外部 5V を使い、GND のみ Arduino と共通にしてください。
- リレー制御線と測定ケーブルはできるだけ離してください。
- Arduino IDE では、本番用スケッチと診断用スケッチを同じフォルダに混在させないでください。

## 診断用スケッチ

`tests_arduino/` には、配線確認や単体動作確認用のスケッチがあります。

- `tests_arduino/pca9685_relay_safe/pca9685_relay_safe.ino`
- `tests_arduino/pca9685_servo_sweep/pca9685_servo_sweep.ino`

本番投入前の配線確認に使うと安全です。

## よくある問題

### Arduino に接続できない

- `settings.json` の `connection.port` が正しいか確認してください。
- Arduino IDE のシリアルモニタが開いたままになっていないか確認してください。
- ボーレートが一致しているか確認してください。

### `Config Error` で起動できない

- `settings.json` に JSON の書式ミスがないか確認してください。
- `connection.port` が空になっていないか確認してください。
- 各セルの `WE` / `CE` / `RE` が揃っているか確認してください。

### 設定変更が反映されない

- `update_config.py` を実行し直してください。
- 生成された `arduino_firmware/config.h` を Arduino IDE に再書き込みしてください。

### START しても動かない

- `gpio_pins.di1_output` が無効になっていないか確認してください。
- 画面のログに `DI1 Output Pin Disabled` が出ていないか確認してください。

### 開始前自動化が失敗する

- `start_btn_dummy.png` が存在するか確認してください。
- 対象アプリのウィンドウタイトルが設定と合っているか確認してください。
- 画像認識に使う座標や素材が現状画面に合っているか確認してください。

## 開発メモ

- 状態管理は `OperationState` を中心に動きます。
- 測定開始は StationKit 経由で実行されます。
- ハートビートが止まるとウォッチドッグで安全停止に入ります。
- E-STOP は UI とハードウェアの両方を安全側に倒します。

必要に応じて `settings.json` を編集し、`update_config.py` と Arduino への再書き込みを忘れないことが、このプロジェクトで最も重要です。