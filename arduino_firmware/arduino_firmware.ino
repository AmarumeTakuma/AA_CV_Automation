#include <Servo.h>
#include "config.h"

// 定数定義 (とりあえずここにハードコードして動かす）
const int MAX_SERVOS = 12; 
const int MAX_DIGITAL_PINS = 60; 

// デジタルピン管理（使ったピンを記録）
int activeDigitalPins[MAX_DIGITAL_PINS];
int digitalPinCount = 0;

// サーボ管理
Servo servos[MAX_SERVOS];
int servoPins[MAX_SERVOS];
int servoCount = 0;
int servoOffAngles[MAX_SERVOS];

// 終了信号用（必要であれば使用）
const int DONE_PIN = 19; // A5 (13はLED用に予約)
int lastDoneState = HIGH;

// ウォッチドッグ用
unsigned long lastHeartbeatTime = 0;
bool watchdogActive = false;

void setup() {
  // config.h に BAUDRATE が定義されていればそれを使い、なければ9600
  #ifdef BAUDRATE
    Serial.begin(BAUDRATE);
  #else
    Serial.begin(9600);
  #endif

  // オンボードLEDを出力に設定し、OFFにしておく
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);

  pinMode(DONE_PIN, INPUT_PULLUP);

  // 管理配列の初期化
  for(int i=0; i<MAX_SERVOS; i++) {
    servoPins[i] = -1;
    servoOffAngles[i] = 0;
  }
  for(int i=0; i<MAX_DIGITAL_PINS; i++) {
    activeDigitalPins[i] = -1;
  }

  // configからサーボのデフォルト角度を読み込む
  #ifdef SERVO_COUNT_DEF
    for(int i=0; i<SERVO_COUNT_DEF; i++) {
      int pin = SERVO_DEFAULTS[i][0];
      int angle = SERVO_DEFAULTS[i][1];
      if(pin != -1) {
         int idx = getServoIndex(pin); 
         if(idx != -1) {
             servoOffAngles[idx] = angle;
             servos[idx].write(angle); // 起動時にすぐオフ角度に
         }
      }
    }
  #endif

  // システム制御ピン（Start/Estop）の安全な初期化
  #ifdef PIN_START
    if (PIN_START != -1) {
      digitalWrite(PIN_START, HIGH); // 先にOFF(HIGH)状態にする
      pinMode(PIN_START, OUTPUT);    // その後で出力モードへ
    }
  #endif
  #ifdef PIN_ESTOP
    if (PIN_ESTOP != -1) {
      digitalWrite(PIN_ESTOP, HIGH); // 先にOFF(HIGH)状態にする
      pinMode(PIN_ESTOP, OUTPUT);    // その後で出力モードへ
    }
  #endif

  // オンボードLEDの初期化 (消灯)
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);

  Serial.println("Arduino Ready.");
}

void loop() {
  // コマンド受信
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    parseCommand(command);
  }

  // ウォッチドッグ監視
  if (watchdogActive) {
    if (millis() - lastHeartbeatTime > WATCHDOG_TIMEOUT) {
      forceStopAll(); // 緊急停止
      watchdogActive = false; // 監視を一旦止める（次のHBが来るまで）
    }
  }

  // 測定終了信号の監視 (Active Low: HIGH -> LOW)
  int currentDoneState = digitalRead(DONE_PIN);
  if (lastDoneState == HIGH && currentDoneState == LOW) {
      Serial.println("MEASUREMENT_END");
      delay(50);
  }
  lastDoneState = currentDoneState;
}

// 補助関数

// 緊急停止：全てを初期状態に戻す
void forceStopAll() {
  // デジタルピンを全てOFF
  for(int i=0; i<digitalPinCount; i++) {
    int pin = activeDigitalPins[i];
    if (pin != -1) {
      digitalWrite(pin, LOW); // 強制OFF
    }
  }
  // リストをリセット
  digitalPinCount = 0;
  for(int i=0; i<MAX_DIGITAL_PINS; i++) {
    activeDigitalPins[i] = -1;
  }
  
  // サーボを全て初期角度（OFF位置）に戻す
  for(int i=0; i<MAX_SERVOS; i++) {
    if (servoPins[i] != -1) {
      servos[i].write(servoOffAngles[i]);
    }
  }

  // 緊急停止したらLEDを点灯
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, HIGH);
  
  Serial.println("Error: Watchdog Timeout! System Halted.");
}

// config.h に書かれた使っていいピンかどうかを確認
bool isValidPin(int pin) {
  #ifdef VALID_PIN_COUNT
    for (int i=0; i<VALID_PIN_COUNT; i++) {
      if (VALID_PINS[i] == pin) return true;
    }
    Serial.print("Error: Pin "); Serial.print(pin); Serial.println(" is NOT in whitelist.");
    return false;
  #else
    return true; // configがない場合は全許可（デバッグ用）
  #endif
}

// 排他制御チェック
bool checkInterlock(int targetPin) {
  #ifdef PAIR_COUNT
    for (int i=0; i<PAIR_COUNT; i++) {
      int pinA = EXCLUSIVE_PAIRS[i][0];
      int pinB = EXCLUSIVE_PAIRS[i][1];
      if (pinA == -1) continue;

      // 自分がAで、相方のBが既にONならブロック
      if (targetPin == pinA) {
        if (digitalRead(pinB) == HIGH) {
          Serial.print("BLOCK: Pin "); Serial.print(pinA); Serial.print(" vs ON-Pin "); Serial.println(pinB);
          return false;
        }
      } 
      // 自分がBで、相方のAが既にONならブロック
      else if (targetPin == pinB) {
        if (digitalRead(pinA) == HIGH) {
          Serial.print("BLOCK: Pin "); Serial.print(pinB); Serial.print(" vs ON-Pin "); Serial.println(pinA);
          return false;
        }
      }
    }
  #endif
  return true;
}

int getServoIndex(int pin) {
  // 登録済みならそのインデックスを返す
  for(int i=0; i<servoCount; i++) {
    if (servoPins[i] == pin) return i;
  }
  // 未登録なら空き枠を探す
  if (servoCount < MAX_SERVOS) {
    servos[servoCount].attach(pin); // ここで初めてattach
    servoPins[servoCount] = pin;
    servoCount++;
    return servoCount - 1;
  }
  return -1; // 満員
}

// デジタル出力実行
void setDigitalPin(int pin, int value) {
  if (!isValidPin(pin)) return; // ホワイトリスト
  if (value == 1) {
    if (!checkInterlock(pin)) return; // 排他制御
  }

  // ピン出力実行
  pinMode(pin, OUTPUT); // 念のためモード設定
  digitalWrite(pin, value);
  
  // 使用済みリストに登録（緊急停止機能用）
  bool found = false;
  for(int i=0; i<digitalPinCount; i++) {
    if(activeDigitalPins[i] == pin) {
      found = true;
    }
  }
  if(!found && digitalPinCount < MAX_DIGITAL_PINS) {
    activeDigitalPins[digitalPinCount] = pin;
    digitalPinCount++;
  }
  
  Serial.print("Executed DO Pin:"); Serial.println(pin);
}

// コマンド解析
void parseCommand(String cmd) {
  cmd.trim(); // 前後の空白を削除

  if(cmd.startsWith("HB")) {
    lastHeartbeatTime = millis(); // タイマーリセット
    watchdogActive = true; // 監視有効化（接続されたとみなす）
    digitalWrite(LED_BUILTIN, LOW); // 正常に通信できているのでLEDを消す
    return;
  }
  
  if (cmd.startsWith("DO,")) { 
    // DigitalOutput用コマンド (DO,ピン番号,0/1)
    int firstComma = cmd.indexOf(',');
    int secondComma = cmd.indexOf(',', firstComma + 1);
    
    if (firstComma > 0 && secondComma > 0) {
      int pin = cmd.substring(firstComma + 1, secondComma).toInt(); // ピン番号
      int value = cmd.substring(secondComma + 1).toInt(); // 値 (0 or 1)
       
      setDigitalPin(pin, value);
    } else { 
      Serial.println("Error: DO format (expected DO,pin,val)."); 
    }

  } else if (cmd.startsWith("SV,")) { 
    // サーボ制御コマンド (SV,ピン番号,角度)
    int firstComma = cmd.indexOf(',');
    int secondComma = cmd.indexOf(',', firstComma + 1);
    
    if (firstComma > 0 && secondComma > 0) {
      int pin = cmd.substring(firstComma + 1, secondComma).toInt(); // ピン番号
      int angle = cmd.substring(secondComma + 1).toInt(); // 角度
      
      // 安全のためこちら側でも角度を0-180に制限
      angle = constrain(angle, 0, 180); 
      
      // ホワイトリスト確認
      if (!isValidPin(pin)) return; 

      // 配列からサーボを探して動かす
      int idx = getServoIndex(pin);
      if (idx != -1) {
        servos[idx].write(angle);
        Serial.print("Executed SV Pin:"); Serial.print(pin);
        Serial.print(", Angle:"); Serial.println(angle);
      } else {
        Serial.println("Error: Servo limit reached.");
      }

    } else { 
      Serial.println("Error: SV format (expected SV,pin,angle)."); 
    }
    
  } else {
    if (cmd.length() > 0) {
        Serial.println("Error: Unknown command prefix.");
    }
  }
}