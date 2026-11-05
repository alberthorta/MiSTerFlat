#pragma once

#include <stdint.h>

#include <string_view>

#include "hal/Lgfx.h"
#include "transport/SerialTransport.h"
#include "ui/DisplayManager.h"

// The system picker on touch boards, opened from the Systems button of the menu clock: the covers
// of a few systems side by side (cover flow). Drag to move between them; a tap on a side cover
// brings it to the middle, a tap on the middle one asks the host to load that core
// (MDSSYS,load,<i>). The back button (top left) or 10 s without a touch closes it.
//
// The host owns the list: MDSSYS,clear and MDSSYS,item,<i>,<crc32>,<name> after it sees the
// board. The covers are the host's own pictures (320x240 PNG or JPEG), asked for when the picker
// opens (MDSSYS,img,<i>) and sent back as MDSSYSIMG frames. They are kept in PSRAM, smaller, until
// the host sends a different crc.
class SystemsScreen {
 public:
  SystemsScreen(DisplayManager& display, SerialTransport& transport) : display_(display), transport_(transport) {}

  // At least one system: the menu clock shows the Systems button.
  bool available() const { return count_ > 0; }
  bool active() const { return active_; }
  void open(uint32_t nowMs);
  void close() { active_ = false; }
  // MDSSYS lines from the host (the text after "MDSSYS,").
  void onHost(std::string_view args);
  // A cover (MDSSYSIMG,<bytes>,<crc32>,<png|jpg>,<index>), crc already checked.
  void onCover(int index, uint32_t crc, bool png, const uint8_t* data, size_t length);

  struct Result {
    bool activity = false;  // any touch
    bool closed = false;    // closed by the user or by the timeout: the caller redraws its screen
    bool loading = false;   // a core was asked for: the host sends its picture next
  };
  Result poll(uint32_t nowMs);

  static constexpr int kMaxSystems = 12;

 private:
  struct System {
    char name[32];
    uint32_t crc;      // of the host's picture
    uint32_t haveCrc;  // of the cover we hold (0 = none)
    bool requested;
    LGFX_Sprite* cover;  // full brightness
    LGFX_Sprite* dim;    // darker copy for the side positions
  };

  void requestCovers();
  void tap(int x, int y);
  void draw();
  void drawCover(int i, float d);
  bool makeSprites(System& s);
  float maxPos() const { return count_ > 0 ? count_ - 1 : 0; }

  DisplayManager& display_;
  SerialTransport& transport_;
  System systems_[kMaxSystems] = {};
  int count_ = 0;
  bool active_ = false;
  bool dirty_ = false;

  float pos_ = 0;     // the system in the middle; fractions while moving
  float target_ = 0;  // where pos_ goes after a drag or a tap
  bool down_ = false;
  bool moved_ = false;
  int downX_ = 0;
  int downY_ = 0;
  int lastX_ = 0;
  float downPos_ = 0;
  float velocity_ = 0;  // pixels per ms, smoothed, while dragging
  uint32_t lastMoveMs_ = 0;
  uint32_t lastTouchMs_ = 0;
  uint32_t lastPollMs_ = 0;
  uint32_t lastFrameMs_ = 0;
  int pendingLoad_ = -1;
};
