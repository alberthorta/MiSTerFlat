#pragma once

#include "WallClock.h"
#include "ui/DisplayManager.h"

// Built-in screen for the MiSTer menu (core "MENU") and the idle clock: time, date, and the
// MiSTer's IP address when the daemon sent one. `dimmed` draws in dark greys for the idle clock.
namespace MenuScreen {

// Fonts for the time, chosen with MDSCFG,clockfont,<index>. Index 0 is the default.
constexpr int kClockFontCount = 8;
const char* clockFontName(int index);

void draw(DisplayManager& display, const wallclock::DateTime& now, const char* ip, bool dimmed, int clockFont = 0);

}  // namespace MenuScreen
