#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

Adafruit_PWMServoDriver pwm(0x40);
const uint16_t PWM_FULL_ON = 4095;
const uint16_t PWM_FULL_OFF = 0;
const uint8_t RELAY_CH = 0;

void setup() {
  Serial.begin(115200);
  delay(500);
  pwm.begin();
  pwm.setOscillatorFrequency(27000000);
  pwm.setPWMFreq(50);
  pwm.setPWM(RELAY_CH, 0, PWM_FULL_OFF);
  Serial.println("Safe relay test start");
}

void loop() {
  Serial.println("Relay ON");
  pwm.setPWM(RELAY_CH, 0, PWM_FULL_ON);
  delay(3000);
  Serial.println("Relay OFF");
  pwm.setPWM(RELAY_CH, 0, PWM_FULL_OFF);
  delay(3000);
}