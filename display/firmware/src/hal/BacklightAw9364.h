#pragma once

#include <Arduino.h>
#include <LovyanGFX.hpp>

// The T-Display-S3 backlight goes through an AW9364 LED driver, not a plain MOSFET. It has 16
// levels and is set by pulses on its enable pin: high after off = level 16, each low pulse =
// one level down (1 wraps to 16), low for more than 2.5 ms = off. Sequence from LILYGO's
// examples/factory/factory.ino setBrightness().
//
// We used LovyanGFX Light_PWM before: the chip counted every duty change of a fade as pulses and
// ended on a random, often dim, level. Going up a level means wrapping through all the others,
// but 15 pulses take a few tens of microseconds, which the eye does not see.
class BacklightAw9364 : public lgfx::ILight {
 public:
  explicit BacklightAw9364(int pin) : pin_(pin) {}

  bool init(uint8_t brightness) override {
    pinMode(pin_, OUTPUT);
    digitalWrite(pin_, LOW);
    delay(kOffMs);
    level_ = 0;
    setBrightness(brightness);
    return true;
  }

  // 0 = off, 1..255 = level 1..16.
  void setBrightness(uint8_t brightness) override {
    const int target = brightness == 0 ? 0 : 1 + (brightness - 1) * (kLevels - 1) / 254;
    if (target == level_) return;
    if (target == 0) {
      digitalWrite(pin_, LOW);
      delay(kOffMs);
      level_ = 0;
      return;
    }
    if (level_ == 0) {
      digitalWrite(pin_, HIGH);
      delayMicroseconds(kStartUs);
      level_ = kLevels;
    }
    const int pulses = (level_ - target + kLevels) % kLevels;
    for (int i = 0; i < pulses; ++i) {
      // The datasheet asks for at least 0.5 us low and high; digitalWrite alone can be shorter.
      digitalWrite(pin_, LOW);
      delayMicroseconds(1);
      digitalWrite(pin_, HIGH);
      delayMicroseconds(1);
    }
    level_ = target;
  }

 private:
  static constexpr int kLevels = 16;
  static constexpr uint32_t kOffMs = 3;
  static constexpr uint32_t kStartUs = 30;
  const int pin_;
  int level_ = 0;
};
