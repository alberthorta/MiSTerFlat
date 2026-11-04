#include "hal/PowerSwitch.h"

#include <Arduino.h>
#include <driver/gpio.h>
#include <esp_system.h>

#include "util/Log.h"

void PowerSwitch::begin(bool storedOn, bool autoOn) {
  if (!available()) return;
  const esp_reset_reason_t reason = esp_reset_reason();
  const bool coldStart = reason == ESP_RST_POWERON || reason == ESP_RST_BROWNOUT || reason == ESP_RST_UNKNOWN;
  on_ = coldStart ? autoOn : storedOn;
  LOGF("mister power %s (reset reason %d)", on_ ? "on" : "off", (int)reason);
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
