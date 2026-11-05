#pragma once

#include "WallClock.h"
#include "ui/DisplayManager.h"

// The MiSTer is switched off (power relay open). Two screens:
// - idle: the MiSTer logo and the time (if this board knows it), under a dimmed backlight;
// - prompt, after a tap: the power symbol and "Tap to power on", at full brightness, for a few
//   seconds; a second tap switches the MiSTer on. Two taps, so a brush against the glass does not.
// boardIp: this board's own address, bottom right as on the menu screen ("" for none).
namespace StandbyScreen {

void drawIdle(DisplayManager& display, const wallclock::DateTime* now, const char* boardIp = "");
void drawPrompt(DisplayManager& display, const char* boardIp = "");

}  // namespace StandbyScreen
