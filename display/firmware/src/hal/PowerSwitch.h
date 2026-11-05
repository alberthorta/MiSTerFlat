#pragma once

#include "config.h"

// The relay that switches the MiSTer's 5 V (boards with cfg::pin::kMisterPower). The display sits
// on the always-on 5 V, so it can switch the MiSTer on and off.
//
// The pad is held (gpio_hold_en) after every change. A reset of this board (watchdog, ESP.restart,
// a firmware flash from the MiSTer) would otherwise leave the pin floating for a few hundred ms,
// the relay would open and the MiSTer would lose power, in the middle of the flash too.
class PowerSwitch {
 public:
  static constexpr bool available() { return cfg::pin::kMisterPower >= 0; }

  // storedOn: the state saved before the reset. After a power-on reset the relay cannot have
  // been on, so autoOn decides.
  void begin(bool storedOn, bool autoOn);
  bool on() const { return on_; }
  void set(bool on);

 private:
  void drive();
  bool on_ = false;
};
