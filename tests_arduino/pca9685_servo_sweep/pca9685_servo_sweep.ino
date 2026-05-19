#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

Adafruit_PWMServoDriver pwm(0x40);

const uint8_t SERVO_CHANNELS[] = {9, 10, 11};
const uint16_t SERVO_MIN_US = 900;
const uint16_t SERVO_MAX_US = 2100;
const uint16_t SERVO_FREQ_HZ = 50;
const uint8_t SERVO_OFF_ANGLE = 0;
const uint8_t SERVO_ON_ANGLE = 90;
const uint16_t STATE_HOLD_MS = 3000;

uint16_t usToPwm(uint16_t pulseUs) {
  const uint32_t periodUs = 1000000UL / SERVO_FREQ_HZ;
  const uint32_t pulse = constrain(pulseUs, SERVO_MIN_US, SERVO_MAX_US);
  return (uint16_t)((pulse * 4096UL) / periodUs);
}

void setServoAngle(uint8_t channel, uint8_t angle) {
  angle = constrain(angle, 0, 180);
  const uint16_t pulseUs = map(angle, 0, 180, SERVO_MIN_US, SERVO_MAX_US);
  pwm.setPWM(channel, 0, usToPwm(pulseUs));
}

void setServoState(uint8_t channel, bool on) {
  setServoAngle(channel, on ? SERVO_ON_ANGLE : SERVO_OFF_ANGLE);
}

void allServosOff() {
  for (uint8_t i = 0; i < sizeof(SERVO_CHANNELS) / sizeof(SERVO_CHANNELS[0]); i++) {
    setServoState(SERVO_CHANNELS[i], false);
  }
}

void setExclusiveState(uint8_t offIndex, uint8_t onIndex) {
  const uint8_t offChannel = SERVO_CHANNELS[offIndex];
  const uint8_t onChannel = SERVO_CHANNELS[onIndex];

  Serial.print("Servo ch");
  Serial.print(offChannel);
  Serial.print(" OFF -> Servo ch");
  Serial.print(onChannel);
  Serial.println(" ON");

  setServoState(offChannel, false);
  setServoState(onChannel, true);
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  Wire.begin();
  pwm.begin();
  pwm.setOscillatorFrequency(27000000);
  pwm.setPWMFreq(SERVO_FREQ_HZ);
  delay(10);

  allServosOff();
  Serial.println("PCA9685 servo exclusive test start");
}

void loop() {
  const uint8_t channelCount = sizeof(SERVO_CHANNELS) / sizeof(SERVO_CHANNELS[0]);

  if (channelCount == 0) {
    return;
  }

  allServosOff();
  setServoState(SERVO_CHANNELS[0], true);
  Serial.print("Servo ch");
  Serial.print(SERVO_CHANNELS[0]);
  Serial.println(" ON");
  delay(STATE_HOLD_MS);

  for (uint8_t i = 0; i < channelCount; i++) {
    const uint8_t nextIndex = (i + 1) % channelCount;
    setExclusiveState(i, nextIndex);
    delay(STATE_HOLD_MS);
  }
}