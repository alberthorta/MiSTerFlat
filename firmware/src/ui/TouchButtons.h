#pragma once

#include <stdint.h>

#include "ui/DisplayManager.h"

// RESET, OSD and USER as on-screen buttons, plus BLUETOOTH (the pairing menu, which the OSD
// button opens when held), for boards with a touch panel. A tap shows them over the dimmed screen;
// a tap on one reports it to the host (MDSBTN,<name>), whose daemon acts like the MiSTer's own
// buttons. RESET reboots the MiSTer, so it needs a second tap to confirm.
// The buttons fade in and out, and go away after a few seconds, after a tap elsewhere, or when a
// new frame is drawn.
class TouchButtons {
 public:
  explicit TouchButtons(DisplayManager& display) : display_(display) {}

  struct Result {
    bool activity = false;          // any tap: counts as activity (wakes an idle-dark screen)
    const char* pressed = nullptr;  // "reset", "osd", "user", "bt", or "wifi" (see setWifiSlot)
  };
  Result poll(uint32_t nowMs);
  // USER's place shows Wi-Fi set-up instead (in the MiSTer menu, with a Wi-Fi dongle). Takes
  // effect the next time the buttons open.
  void setWifiSlot(bool on) { wifiSlot_ = on; }
  // Test builds: show the buttons with one held (-1 = none) and RESET armed or not.
  void preview(int held, bool resetArmed, uint32_t nowMs);

 private:
  enum Button : int8_t { kNone = -1, kReset = 0, kOsd = 1, kUser = 2, kBluetooth = 3, kCount = 4 };

  enum class Fade : uint8_t { None, In, Out };

  Result release(uint32_t nowMs);
  void show(uint32_t nowMs);
  void hide();
  void stepFade(uint32_t nowMs);
  void finishHide();
  void compose();  // the buttons over the dimmed screen, into the framebuffer
  void draw();
  Button hit(int x, int y) const;

  DisplayManager& display_;
  bool shown_ = false;
  bool resetArmed_ = false;
  bool wifiSlot_ = false;
  bool down_ = false;
  Button held_ = kNone;    // under the finger now: drawn filled
  Button chosen_ = kNone;  // released on: stays filled until the buttons close
  int lastX_ = 0;
  int lastY_ = 0;
  uint32_t lastPollMs_ = 0;
  uint32_t shownAtMs_ = 0;
  uint32_t armedAtMs_ = 0;
  uint32_t closeAtMs_ = 0;  // non-zero: close then, after showing the chosen button
  uint32_t frameCount_ = 0;  // the frame with our buttons on it
  Fade fade_ = Fade::None;
  uint8_t alpha_ = 0;  // 0 = screen under the buttons, 32 = the buttons
  uint32_t nextFadeMs_ = 0;
};
