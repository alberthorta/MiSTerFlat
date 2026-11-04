#include "hal/PowerSwitch.h"

#include <Arduino.h>
#include <driver/gpio.h>
#include <esp_system.h>

#include "util/Log.h"

void PowerSwitch::begin(bool storedOn, bool autoOn) {
  if (!available()) return;
  const esp_reset_reason_t reason = esp_reset_reason();
  const bool coldStart = reason == ESP_RST_POWERON || reason == ESP_RST_BROWNOUT || reason == ESP_RST_UNKNOWN;
  // After a cold start no hold is left, so the pin can be read. A resistor from the MiSTer's own
  // 3.3 V to the relay input (docs/power.md) keeps the relay closed while the MiSTer runs: a high
  // pin here means it is on. A brownout during its start-up must not switch it off again.
  // Without that resistor the relay input pulls the floating pin low.
  bool latched = false;
  if (coldStart) {
    pinMode(cfg::pin::kMisterPower, INPUT);
    delayMicroseconds(100);
    latched = digitalRead(cfg::pin::kMisterPower) == cfg::pin::kMisterPowerOnLevel;
  }
  on_ = coldStart ? (latched || autoOn) : storedOn;
  LOGF("mister power %s (reset reason %d, latched %d)", on_ ? "on" : "off", (int)reason, latched);
  drive();
}

void PowerSwitch::set(bool on) {
  if (!available() || on == on_) return;
  on_ = on;
  LOGF("mister power %s", on_ ? "on" : "off");
  drive();
}

void PowerSwitch::drive() {
  const gpio_num_t pin = static_cast<gpio_num_t>(cfg::pin::kMisterPower);
  const int level = on_ ? cfg::pin::kMisterPowerOnLevel : !cfg::pin::kMisterPowerOnLevel;
  // A pad still held from before a reset ignores these until the hold is released, and then takes
  // the new values at once: when the level is the same, the relay never sees a gap.
  gpio_set_level(pin, level);
  pinMode(cfg::pin::kMisterPower, OUTPUT);
  gpio_set_level(pin, level);
  gpio_hold_dis(pin);
  gpio_set_level(pin, level);
  gpio_hold_en(pin);
}
