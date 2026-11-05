#pragma once

#include "WallClock.h"
#include "ui/DisplayManager.h"

// The MiSTer is switched off (power relay open): a power symbol, the time if this board knows it,
// and "Tap to power on". Drawn in dark colours; the backlight is turned down as well.
namespace StandbyScreen {

// boardIp: this board's own address, bottom right as on the menu screen ("" for none).
void draw(DisplayManager& display, const wallclock::DateTime* now, const char* boardIp = "");

}  // namespace StandbyScreen
