#pragma once

#include <stdint.h>

#include "ui/DisplayManager.h"

// RESET, OSD and USER as on-screen buttons, plus BLUETOOTH (the pairing menu, which the OSD
// button opens when held), for boards with a touch panel. A tap shows them over the dimmed screen;
// a tap on one reports it to the host (MDSBTN,<name>), whose daemon acts like the MiSTer's own
// buttons. RESET reboots the MiSTer, so it needs a second tap to confirm.
// The buttons fade in and out, and go away after a few seconds, after a tap elsewhere, or when a
// new frame is drawn.
// Below them, two level rows: the MiSTer's global volume (once the host has sent it with MDSVOL)
// and the brightness of this display. Each is an icon, -, a bar of kLevelMax + 1 steps and +; a tap
// on the bar picks that step. These keep the buttons open, so a level can be changed several times.
class TouchButtons {
 public:
  explicit TouchButtons(DisplayManager& display) : display_(display) {}

  static constexpr int kLevelMax = 7;

  struct Result {
    bool activity = false;  // any tap: counts as activity (wakes an idle-dark screen)
    // "reset", "osd", "user", "bt", "wifi" (see setWifiSlot), "voldown", "volup", "vol" (a step
    // picked on the volume bar) or "bright" (any change of the brightness row).
    const char* pressed = nullptr;
    int level = -1;  // "vol" and "bright": the new level
  };
  Result poll(uint32_t nowMs);
  // USER's place shows Wi-Fi set-up instead (in the MiSTer menu, with a Wi-Fi dongle). Takes
  // effect the next time the buttons open.
  void setWifiSlot(bool on) { wifiSlot_ = on; }
  // The MiSTer's global volume: level 0 (quietest) to kLevelMax, as Main's "volume <n>" command.
  void setVolume(int level, bool muted);
  void setBrightness(int level);
  // Test builds: show the buttons with one held (-1 = none) and RESET armed or not.
  void preview(int held, bool resetArmed, uint32_t nowMs);

 private:
  enum Button : int8_t {
    kNone = -1,
    kReset = 0,
    kOsd = 1,
    kUser = 2,
    kBluetooth = 3,
    kCount = 4,  // the main row
    kVolDown = 4,
    kVolUp = 5,
    kVolBar = 6,
    kBrightDown = 7,
    kBrightUp = 8,
    kBrightBar = 9,
    kAll = 10,
  };

  enum class Fade : uint8_t { None, In, Out };

  // Where the parts of a level row go across the screen.
  struct LevelLayout {
    int iconX, downX, upX;
    int barX, barW, seg;
  };

  Result release(uint32_t nowMs);
  void show(uint32_t nowMs);
  void hide();
  void stepFade(uint32_t nowMs);
  void finishHide();
  void compose();  // the buttons over the dimmed screen, into the framebuffer
  void composeLevel(bool volume, int cy, int level, bool greyed);
  void draw();
  bool volumeRow() const { return volume_ >= 0; }
  int rowY() const;  // centre of the main row
  int volumeY() const;
  int brightnessY() const;
  LevelLayout levelLayout() const;
  int levelAt(int x) const;  // the bar step under x
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
  uint32_t closeAtMs_ = 0;    // non-zero: close then, after showing the chosen button
  uint32_t unlightAtMs_ = 0;  // non-zero: a - or + lit by a tap goes back to normal then
  int volume_ = -1;           // -1: not known yet, no volume row
  bool muted_ = false;
  int brightness_ = kLevelMax;
  uint32_t frameCount_ = 0;  // the frame with our buttons on it
  Fade fade_ = Fade::None;
  uint8_t alpha_ = 0;  // 0 = screen under the buttons, 32 = the buttons
  uint32_t nextFadeMs_ = 0;
};
