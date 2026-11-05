#pragma once

#include <stddef.h>
#include <stdint.h>

#include "ui/DisplayManager.h"

namespace SplashScreen {

// A stored start-up picture (PNG or JPEG), drawn centred in the logo area: 320x130 on the
// 170-line screen, 320x184 from the top on screens of 240 lines (the line below is for the hint).
// A 320x184 picture fits both: the 170-line screen shows its middle 130 lines.
struct Logo {
  const uint8_t* data = nullptr;
  size_t size = 0;
  bool png = true;
};

constexpr int kLogoAreaHeight = 130;
constexpr int kTallLogoAreaHeight = 184;
constexpr int kTallScreenHeight = 240;

// Start screen: the logo if there is one (else "MiSTer / <board name>" text), the firmware version
// and `hint` (may be null), a status line such as "Waiting for MiSTer".
void draw(DisplayManager& display, const char* version, const char* hint = nullptr, const Logo* logo = nullptr);

}  // namespace SplashScreen
