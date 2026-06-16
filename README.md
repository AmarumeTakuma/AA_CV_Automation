# AA_CV_Automation System

電気化学測定（CV測定など）における電極の切り替えやガスライン制御を自動化するための統合システムです。
PC上のPythonアプリ(`main.py`)からArduinoを経由して、リレー（電極接続）やサーボモーター（ガスライン）を安全に制御します。

## プロジェクト構成

```
AA_CV_Automation/
├── main.py                      # メイン制御アプリケーション (起動・配線のみ)
├── runtime_state.py             # 共有状態管理 (OperationState Enum)
├── ui_utils.py                  # UI・ログ・状態遷移ヘルパー関数
├── selection_manager.py         # 電極・ガスライン・排他制御ロジック
├── measurement_workflow.py      # 測定フロー・E-STOP・初期化処理
├── error_handler.py             # 通信エラー・リカバリ処理
├── device_lifecycle.py          # デバイス接続・ハートビート・watchdog
├── measurement_service.py       # 測定セッション管理 (@dataclass)
├── app_ui.py                    # Tkinter GUI構築とウィジェット管理
├── config_manager.py            # settings.json 読み込み・検証
├── device_controller.py         # Arduino シリアル通信 API
├── pyproject.toml               # uv / Python プロジェクト設定と依存関係定義
├── uv.lock                      # uv が生成するロックファイル（依存バージョン固定）
├── settings.json                # システム全体の設定ファイル (ピン配置、セル構成、サーボ設定)
├── update_config.py             # Arduino用設定ヘッダ(config.h)生成スクリプト
├── requirements.txt             # 依存関係リスト（互換用）
├── README.md                    # 本ドキュメント
├── arduino_firmware/            # Arduino用ファームウェアフォルダ
│   ├── arduino_firmware.ino     # Arduinoメインファームウェア
│   └── config.h                 # update_config.pyによって自動生成される設定ヘッダ（生成後）
├── arduino_tests/               # 診断用・安全確認用のArduinoスケッチ置き場
│   └── pca9685_relay_safe/
│       └── pca9685_relay_safe.ino
```

### スケッチの役割分担

このリポジトリでは、Arduino スケッチを用途ごとに分けて運用します。

- `arduino_firmware/` は本番用です。`main.py` から送られるコマンドを受け取って、実験装置を制御します。
- `arduino_tests/` は診断用です。PCA9685 や配線の動作確認をするための単独スケッチを置きます。
- Arduino IDE では、**1つのスケッチフォルダだけを開いて使う**のが安全です。別フォルダの `.ino` を同じ場所に混在させないでください。
- 本番用スケッチと診断用スケッチは、**役割もフォルダも完全に分離**しておくと、誤アップロードや混在コンパイルを避けやすくなります。

### Python モジュール設計

Pythonアプリは機能別に以下の7つのモジュールに分割されています：

| モジュール | 責務 |
| :--- | :--- |
| `main.py` | アプリ起動・UI構築・コールバック配線のみ |
| `runtime_state.py` | 全体の状態管理（OperationState Enum: IDLE, MEASURING, ESTOP_PENDING, RECOVERING, FAULT, STOPPED） |
| `ui_utils.py` | ログ表示・状態遷移・UI ロック・状態確認ヘルパー |
| `selection_manager.py` | 電極・ガスライン選択・排他制御（再入防止） |
| `measurement_workflow.py` | 測定開始・終了・E-STOP・初期化処理 |
| `error_handler.py` | 通信エラー検出・1回リカバリ・FAULT状態遷移 |
| `device_lifecycle.py` | デバイス接続・ハートビート送信・ watchdog ループ |



## 前提条件

本ドキュメント記載のセットアップを進める前に、以下がインストール済みであることを確認してください。

*   **Python 3.12+**（`uv` 環境を利用した開発用途が前提です）
*   **Arduino IDE**（ファームウェア書き込み用）
*   **Git**（リポジトリ管理用）

## 動作環境
*   **OS**: Windows (推奨)
*   **Python 3.12+**
    *   `tkinter` (標準ライブラリ)
    *   その他、`requirements.txt` に記載のライブラリ (`pyserial` 等)
*   **Arduino IDE** (ファームウェア書き込み用)

## セットアップと使用方法（uv推奨）

本システムは、`settings.json` を編集するだけでPCアプリとArduinoファームウェアの両方の設定が同期される仕組みになっています。

### ⚠️ ハードウェア接続の重要事項
詳細な配線図は省略しますが、トラブル防止のため以下の点だけは必ず守ってください。

*   **GNDの共通化 (Common Ground)**
    *   Arduinoの **GND** ピンと、測定器(HZ-Pro)の制御端子側の **COM (GND)** は必ず接続してください。
    *   ここが接続されていないと信号の基準レベルが定まらず、誤動作や機器故障の原因になります。
*   **サーボモータの電源 (Power Supply)**
    *   複数のサーボを一斉に動かすと大電流が流れ、Arduinoがリセット（通信切断）されることがあります。
    *   可能な限り、サーボ用電源は外部5V電源を用意し、GNDのみArduinoと共通化することを推奨します。
*   **ノイズ対策 (Noise Reduction)**
    *   サーボやリレーの制御線と、電気化学測定用のケーブル（特にWE/RE）は、束ねたり平行に這わせたりせず、できるだけ物理的に離して配線してください。

### Step 0: ライブラリのインストール（uv推奨）
ターミナルで以下のコマンドを実行し、必要なライブラリをインストールしてください。

`uv` 環境を利用する場合:

```bash
uv sync
```

`requirements.txt` から依存関係を `pyproject.toml` に取り込みたい場合（初回移行・更新時のみ）:

```bash
uv add -r requirements.txt
```

`pip` を使う場合（代替）:

```bash
pip install -r requirements.txt
```

### Step 1: 構成の設定 (`settings.json`)
`settings.json` を開き、実験環境に合わせてピン配置を変更してください。
*   **connection**: PCとの通信設定（COMポート、ボーレート）
*   **pins**: システム制御ピン (Start triggers, Emergency Stop)
  *   `pins`: システム制御ピン (測定器との DI/DO, E-STOP 等)
      - `di1_output`: 測定開始トリガー (HZ-Pro の **DI-1** へ接続、Active‑Low パルス)
      - `di2_output`: 追加の測定トリガ出力（現状は下地実装、将来の拡張用）
      - `cell_open_in`: HZ-Pro の **CELL-OPEN-IN**（E-STOP/セルオープン入力）。`estop` は本設定に吸収されています。
      - `do1_input`: HZ-Pro の **DO-1**（測定完了入力）。`done` は本設定に吸収されています。DO1 の立下りで `MEASUREMENT_END` を送信します。
      - `do2_input`: 追加のデジタル入力（下地実装、イベント通知あり）
      - `hw_err_in`: ハードウェア異常検出入力（Hz‑Pro が異常検出時に 200ms 間 HIGH を出力します。基準は ISO‑GND）。

      参考: このリポジトリのデフォルト割当例（`settings.json` に記載）:

      - `di1_output`: 2
      - `di2_output`: 3
      - `cell_open_in`: 4
      - `do1_input` (done): 5
      - `do2_input`: 6
      - `hw_err_in`: 7

      注: ピン番号はボードごとに異なるため、使用するボードのデジタルピン番号で指定してください。変更後は必ず `python update_config.py` を実行して `arduino_firmware/config.h` を再生成し、スケッチを再アップロードしてください。
*   **cells**: 各セル（Cell A, Cell B...）と電極(WE, CE, RE)のArduinoピン番号
*   **servos**: ガスライン制御用サーボモーターのピン番号と角度設定
*   **safety**: 安全設定・禁止ピン設定
    *   **prohibited_pins**: 以下の理由により、使用を禁止するピンを指定します。
        *   `0`, `1`: Arduinoのシリアル通信(USB)で使用するため使用禁止
        *   `13`: 緊急停止(Watchdog Timeout)時の警告LED表示に使用するため使用禁止

> **Tips: アナログピンのデジタル利用について**
> Arduinoのアナログ入力ピン（A0〜A5など）は、通常のデジタルピン（入出力）としても使用可能です。
> 足りない場合はこれらを利用することを検討してください。 `settings.json` に記述する際は、以下の対応表（Arduino Uno/Nanoの場合）を参考に**デジタルピン番号**で指定してください。
>
> | アナログピン | デジタルピン番号 |
> | :--- | :--- |
> | A0 | 14 |
> | A1 | 15 |
> | A2 | 16 |
> | A3 | 17 |
> | A4 | 18 |
> | A5 | 19 |

## main.py を実行すると何が起きるか（簡潔な実行フロー）

- 起動時に `settings.json` を `ConfigManager` が読み込み・検証します。設定エラーがあればダイアログを表示して終了します。
- Tkinter ウィンドウを作成し、`MainUI` によって GUI ウィジェットを構築します。
- `ArduinoDevice` を `ConfigManager` と共に初期化し、100ms 後に `connect_app` が呼ばれて以下を実行します:
  - シリアルポートの存在確認（ユーザに接続継続の可否を確認するプロンプトを表示する場合あり）
  - Arduino への接続を確立し、`initialize_devices()` によって全ピンを安全側に初期化
  - ファームウェア側の排他設定（インターロック）の有効化
- 接続成功後、以下の定期処理が `root.after` で開始されます:
  - ハートビート送信（ウォッチドッグ維持）
  - 通信ウォッチドッグ（通信健全性監視）
  - シリアル受信チェック（`MEASUREMENT_END` 等のイベント検知）
- UI 操作例:
  - `START` → 測定ダイアログを表示 → Arduinoへ DI1 パルス送信（測定開始） → UIロック → シリアルから `MEASUREMENT_END` を受信すると測定終了処理
  - `E-STOP`（Esc or ボタン）→ Arduinoへ E-STOP パルス送信 → UIとデバイスを安全にリセット
- 終了時は `on_close` でデバイス初期化とシリアルクローズを行い、アプリケーションを終了します。

## 測定開始ロジック（現状の詳細）

`START` 押下時の処理は、現在次の順序で動作します。

1. `app_ui.py` の `START` ボタンが `on_start` コールバックを呼びます。
2. `measurement_workflow.on_start()` で開始前ガードを実施します。
  - デバイス未接続、またはアプリ終了中なら何もしません。
  - `di1_output_pin < 0`（無効設定）の場合は情報ダイアログを表示して終了します。
3. `measurement_prestart_automation.show_start_dialog()` が表示され、以下の入力を受け取ります。
  - ファイル名（拡張子 `.act` は内部で付与）
  - 保存フォルダ
  - ターゲットセル
4. ダイアログの `Start` 確定後、`measurement_workflow.execute_start_measurement()` が実行されます。
  - `can_start_measurement()` により「IDLE かつ接続済みかつ終了中でないこと」を確認。
  - 状態を `MEASURING` に遷移。
  - `MeasurementSession` を生成し、選択済み電極/ガスライン、排他設定、COMポート等をスナップショット保存。
  - `run_prestart_automation()` を実行（`settings.json` の `measurement_prestart.steps` ベース）。
  - prestart が失敗した場合は `IDLE` に戻して終了。
5. prestart 成功後、`device.start_measurement()` で DI1 パルス（Active-Low）を Arduino に送信します。
6. DI1 トリガ送信成功時のみ、`measurement_file_service.create_measurement_output_file()` で act を即時作成します。
  - `measurement_start`, `target_cell`, `save_dir` などのメタデータ行を書き込み。
7. UIを測定中表示に切り替えます。
  - STARTボタンを押下状態へ変更。
  - E-STOP 以外をロック。
  - ステータス更新とログ追記。
8. 以後、`device_lifecycle.check_incoming_data()` がシリアル受信を監視し、`MEASUREMENT_END` を受信したら `finish_measurement_handler()` を呼びます。
9. `finish_measurement_handler()` は測定終了処理を実施します。
  - `device.stop_measurement()` で DI1 を待機状態（HIGH）へ戻す。
  - 測定セッションを completed に更新。
  - 状態を `IDLE` に戻し、UIロック解除。

補足:

- `RuntimeState` に `start_cooldown_sec` はありますが、現行の `START` 経路ではクールダウン判定には使っていません。
- actファイルは「測定トリガ成功後」に作成されるため、prestart 失敗時や DI1 送信失敗時には作成されません。

## 各ファイルの短い説明（補足）

- `main.py`: アプリ起動、GUI 配線、グローバルな `RuntimeState` の初期化とイベントループ開始。
- `app_ui.py`: `MainUI` クラス。Tkinter ウィジェットの構築と UI のレイアウト管理。
- `config_manager.py`: `settings.json` の読み込み・検証・内部マップ（electrode_map, servo_map 等）生成。
- `device_controller.py`: `ArduinoDevice` クラス。シリアル通信、コマンド送信、ハートビート、デバイス初期化。
- `device_lifecycle.py`: 接続処理、ハートビートループ、受信チェック、初期化シーケンスの起動。
- `error_handler.py`: 一度だけの自動リカバリ試行、リカバリ失敗時の FAULT 遷移と UI ロック。
- `measurement_service.py`: `MeasurementSession` データ構造と選択収集ユーティリティ。
- `measurement_workflow.py`: 測定の開始／終了フロー、測定ダイアログ、E-STOP と初期化のハンドラ。
- `runtime_state.py`: `RuntimeState` と `OperationState` 列挙の定義。アプリ全体の共有状態を保持。
- `selection_manager.py`: 電極 / ガスライン選択ロジック、排他制御、マスター選択処理。
- `ui_utils.py`: ログ追加、UI のロック制御、状態遷移ユーティリティ群。
- `update_config.py`: `settings.json` から `arduino_firmware/config.h` を生成するスクリプト（Arduino 側のホワイトリスト／インターロック生成）。
- `arduino_firmware/arduino_firmware.ino`: Arduino 側ファームウェア。PC からのコマンド (`DO,SV,IL,HB`) を受け取り、ピン制御／サーボ制御／ウォッチドッグを実行。
- `arduino_firmware/config.h`: `update_config.py` によって自動生成される Arduino 用設定ヘッダ（ピンのホワイトリスト／排他ペア／デフォルト角など）。
- `settings.json`: ユーザが編集する主要な構成ファイル（COMポート、ピン割り当て、サーボ角、セーフティ設定など）。
- `requirements.txt` / `pyproject.toml`: 依存パッケージ定義（`pyserial` など）。

---

## 実行例：はじめてアプリを起動する手順

以下は本リポジトリをクローンし、PC と Arduino を接続したあとに行う基本的な手順です。まずは仮想環境を有効化し、依存パッケージをインストールしてください。

```powershell
# 仮想環境を有効化済みであることを想定
pip install -r requirements.txt
```

1. `settings.json` を編集して、使用する `port`（例: COM3）やピン割り当てを環境に合わせて修正してください。
2. Arduino 設定ヘッダを生成します（`arduino_firmware/config.h` が作成されます）。

```powershell
python update_config.py
```

3. `arduino_firmware/arduino_firmware.ino` を Arduino IDE で開き、ボード/ポートを選択してアップロードします。
4. PC と Arduino を USB 接続してからアプリを起動します。

```powershell
python main.py
```

起動後はウィンドウ上の `START` / `E-STOP` や個別の電極・ガスラインチェックボックスを操作して機器を制御します。

## `settings.json` の各項目の説明（例と注意点）

このプロジェクトの動作は主に `settings.json` の内容によって決まります。以下に主要フィールドの意味と注意点をわかりやすくまとめます。

- `connection`:
  - `port`: Arduino が接続されるホスト側のポート名（Windows では `COM3` など）。正しくないと接続確認ダイアログが表示されます。
  - `baudrate`: シリアル通信のボーレート。プロジェクトはデフォルトで `9600` を想定します。

 - `pins`:
  - `pins`: システム制御ピン (測定器との DI/DO, E-STOP 等)
     - `di1_output`: 測定開始トリガー (HZ-Pro の DI-1 へ接続、Active‑Low パルス)
     - `di2_output`: 追加の測定トリガ出力（現状は下地実装、将来の拡張用）
     - `cell_open_in`: HZ-Pro の CELL-OPEN-IN（E-STOP/セルオープン入力）。`estop` は本設定に吸収されています。
     - `do1_input`: HZ-Pro の DO-1（測定完了入力）。`done` は本設定に吸収されています。DO1 の立下りで `MEASUREMENT_END` を送信します。
     - `do2_input`: 追加のデジタル入力（下地実装、イベント通知あり）
     - `hw_err_in`: ハードウェア異常検出入力（Hz‑Pro が異常検出時に 200ms 間 HIGH を出力します。基準は ISO‑GND）。

     参考: このリポジトリのデフォルト割当例（`settings.json` に記載）:

     - `di1_output`: 2
     - `di2_output`: 3
     - `cell_open_in`: 4
     - `do1_input` (done): 5
     - `do2_input`: 6
     - `hw_err_in`: 7

     注: ピン番号はボードごとに異なるため、使用するボードのデジタルピン番号で指定してください。変更後は必ず `python update_config.py` を実行して `arduino_firmware/config.h` を再生成し、スケッチを再アップロードしてください。

- `cells`:
  - 各セルごとに必要な電極ピンを指定します。例: `"Cell A": {"WE": 2, "CE": 3, "RE": 4}`。
  - `validation.required_electrodes`（デフォルトは `WE, CE, RE`）で必須電極を定義しています。欠落があると起動時にエラーとなります。

- `servos`:
  - 各ガスラインに対して `pin`, `on_angle`, `off_angle` を指定します。`group` を与えると同一グループ内での排他制御が働きます。
  - `on_angle` と `off_angle` の差が小さすぎると物理的に切替が不安定になるので、`safety.min_angle_diff` を確認してください。

- `safety`:
  - `watchdog_timeout_ms`: ハートビートが途絶えたときに Arduino が強制停止するミリ秒値（デフォルト3000ms）。
  - `prohibited_pins`: ファームウェアが使用を禁止するピン（例: 0/1 はシリアル、13 は LED）を列挙します。

- `validation`:
  - `required_electrodes`: 各セルに必須とする電極タイプ（例: `WE, CE, RE`）。設定ミスによる安全上の問題をここで検出します。

- `measurement_prestart`:
  - 測定開始前に pyautogui で操作する手順を設定する拡張ポイントです。
  - `plan_name`: 手順セットの名前。
  - `steps`: `hotkey` / `press` / `write_text` / `paste_text` / `click` / `wait` / `focus_window` / `open_path` などのステップ配列。
  - まだ具体化されていない操作は `enabled: false` のまま置いておき、座標やホットキーが確定したら設定側で埋める運用にします。

- `system_limits`:
  - `max_pin_number`, `max_servos`, `allowed_baudrates` 等、動作上の上限や許容値を指定します。

注意: `settings.json` を変更したら必ず `python update_config.py` を実行して `arduino_firmware/config.h` を再生成し、Arduino スケッチを再アップロードしてください。ファームウェア側はホワイトリスト方式で安全ピンしか操作しないため、この同期が重要です。

---

### Step 2: Arduino設定ファイルの生成（uv推奨） (`update_config.py`)
`settings.json` の変更をArduino側に反映させるため、以下のスクリプトを実行します。

`uv` 環境を利用する場合:

```bash
uv run python update_config.py
```

`pip` / 通常の Python 実行の場合（代替）:

```bash
python update_config.py
```

これにより `arduino_firmware/config.h` が自動生成されます。
> **注意**: `arduino_firmware/config.h` は手動で編集しないでください。常に `update_config.py` 経由で更新します。

### Step 3: Arduinoへの書き込み
Arduino IDEを使用し、書き込みを行います。
1.  `arduino_firmware/arduino_firmware.ino` を開きます。
2.  ボードに書き込みます。この際、自動生成された `config.h` が読み込まれ、許可されたピンのみが操作可能になります（ホワイトリスト方式）。

### Step 4: アプリケーションの起動（uv推奨）
PCとArduinoをUSB接続し、アプリを起動します。

`uv` 環境を利用する場合:

```bash
uv run python main.py
```

`pip` / 通常の Python 実行の場合（代替）:

```bash
python main.py
```

## 主な機能と安全機構

### 1. 操作状態の統一管理（状態機械）
すべての操作は `OperationState` Enum による状態機械で管理され、各操作は**現在の状態のみで判定**されます：

```
IDLE (待機)
  ├─ START → MEASURING
  ├─ E-STOP → ESTOP_PENDING → IDLE (0.5秒後)
  ├─ 通信エラー → RECOVERING
  └─ 電極切り替え / ガスライン制御 / 排他制御など
     各操作は IDLE 状態でのみ実行可能

MEASURING (測定中)
  ├─ 測定完了イベント → IDLE
  ├─ 通信エラー → RECOVERING
  └─ E-STOP は実行可能 → ESTOP_PENDING

RECOVERING (通信リカバリ中)
  ├─ リカバリ成功 → IDLE
  └─ リカバリ失敗 → FAULT

FAULT (致命的エラー)
  └─ アプリ再起動まで操作不可
```

### 2. 電極切り替え (Relay Control)
指定したセルの電極(WE/CE/RE)のみを回路に接続します。
- **排他制御**: 同じ役割の電極が同時にONにならないよう、ソフトウェアおよびファームウェアレベルで二重に保護されています。
- 操作は `operation_state == IDLE` かつ `device.is_connected` の場合のみ許可
- 電極リレーの出力は **active-high** 前提です。`DO,pin,1` で ON、`DO,pin,0` で OFF になります。

### 3. ガスライン制御 (Servo Control)
サーボモーターを指定角度に動かし、ガスの流路を切り替えます。
- 不感帯対策や初期化時の突入電流防止ロジックが含まれています。
- 操作は `operation_state == IDLE` かつ `device.is_connected` の場合のみ許可

### 4. 安全な信号出力 (Active Low Safety)
Start/Estopなどのシステム信号ピンの初期化時における安全性を確保します。
- DI1 と E-STOP は **active-low** 前提です。
- Arduino起動時の意図しないLow出力（誤トリガー）を防ぐため、`digitalWrite(HIGH)` してから `pinMode(OUTPUT)` に設定する安全な初期化順序を実装

### 5. ウォッチドッグタイマー (Watchdog Timer)
PCアプリからのハートビート信号（通信）が途絶えた場合に自動的に緊急停止を発動します。
- アプリのクラッシュやUSBケーブル断線時など、設定された時間（デフォルト3000ms）経過後に全ピンOFF、サーボ初期化を実行

### 6. 設定管理 (Config Management)
すべてのハードウェア設定は `settings.json` に集約されており、PythonアプリとArduinoファームウェア間の設定不整合を防ぎます。
- `update_config.py` を実行して `arduino_firmware/config.h` を自動生成
