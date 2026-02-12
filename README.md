# AA_CV_Automation System

電気化学測定（CV測定など）における電極の切り替えやガスライン制御を自動化するための統合システムです。
PC上のPythonアプリ(`main.py`)からArduinoを経由して、リレー（電極接続）やサーボモーター（ガスライン）を安全に制御します。

## プロジェクト構成

```
AA_CV_Automation/
├── main.py                 # メイン制御アプリケーション (GUI: config読み込み、操作パネル)
├── settings.json           # システム全体の設定ファイル (ピン配置、セル構成、サーボ設定)
├── update_config.py        # Arduino用設定ヘッダ(config.h)生成スクリプト
├── requirements.txt        # 必要なPythonライブラリ一覧
├── README.md               # 本ドキュメント
└── arduino_firmware/       # Arduino用ファームウェアフォルダ
    ├── arduino_firmware.ino # Arduinoメインファームウェア
    └── config.h            # update_config.pyによって自動生成される設定ヘッダ
```

## 動作環境
*   **OS**: Windows (推奨)
*   **Python 3.x**
    *   `tkinter` (標準ライブラリ)
    *   その他、`requirements.txt` に記載のライブラリ (`pyserial` 等)
*   **Arduino IDE** (ファームウェア書き込み用)

## セットアップと使用方法

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

### Step 0: ライブラリのインストール
ターミナルで以下のコマンドを実行し、必要なライブラリをインストールしてください。

```bash
pip install -r requirements.txt
```

### Step 1: 構成の設定 (`settings.json`)
`settings.json` を開き、実験環境に合わせてピン配置を変更してください。
*   **connection**: PCとの通信設定（COMポート、ボーレート）
*   **pins**: システム制御ピン (Start triggers, Emergency Stop)
    *   `start`: 測定開始トリガー (HZ-Proの **DI-1** へ接続)
    *   `estop`: 緊急停止トリガー (HZ-Proの **CELL-OPEN-IN** へ接続)
    *   `done`: 測定完了信号 (HZ-Proの **DO-1** から接続)
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

### Step 2: Arduino設定ファイルの生成 (`update_config.py`)
`settings.json` の変更をArduino側に反映させるため、以下のスクリプトを実行します。

```bash
python update_config.py
```
これにより `arduino_firmware/config.h` が自動生成されます。
> **注意**: `arduino_firmware/config.h` は手動で編集しないでください。常に `update_config.py` 経由で更新します。

### Step 3: Arduinoへの書き込み
Arduino IDEを使用し、書き込みを行います。
1.  `arduino_firmware/arduino_firmware.ino` を開きます。
2.  ボードに書き込みます。この際、自動生成された `config.h` が読み込まれ、許可されたピンのみが操作可能になります（ホワイトリスト方式）。

### Step 4: アプリケーションの起動
PCとArduinoをUSB接続し、アプリを起動します。

```bash
python main.py
```

## 主な機能と安全機構

1.  **電極切り替え (Relay Control)**
    *   指定したセルの電極(WE/CE/RE)のみを回路に接続します。
    *   **排他制御**: 同じ役割の電極が同時にONにならないよう、ソフトウェアおよびファームウェアレベルで二重に保護されています。

2.  **ガスライン制御 (Servo Control)**
    *   サーボモーターを指定角度に動かし、ガスの流路を切り替えます。
    *   不感帯対策や初期化時の突入電流防止ロジックが含まれています。

3.  **安全な信号出力 (Active Low Safety)**
    *   Start/EstopなどのActive Lowピンに対し、Arduino起動時の意図しないLow出力（誤トリガー）を防ぐため、`digitalWrite(HIGH)` してから `pinMode(OUTPUT)` に設定する安全な初期化順序を実装しています。

4.  **ウォッチドッグタイマー (Watchdog Timer)**
    *   PCアプリからのハートビート信号（通信）が途絶えた場合（アプリのクラッシュやUSBケーブル断線時など）、設定された時間（デフォルト3000ms）経過後に自動的に緊急停止（全ピンOFF、サーボ初期化）を発動します。

5.  **設定の一元管理**
    *   すべてのハードウェア設定は `settings.json` に集約されており、PythonアプリとArduinoファームウェア間の設定不整合を防ぎます。
