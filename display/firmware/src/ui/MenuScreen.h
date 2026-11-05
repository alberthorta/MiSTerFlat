#pragma once

#include "WallClock.h"
#include "ui/DisplayManager.h"

// Built-in screen for the MiSTer menu (core "MENU") and the idle clock: time, date, and the
// MiSTer's IP address when the daemon sent one. `dimmed` draws in dark greys for the idle clock.
// boardIp: this board's own address (its Wi-Fi, for the virtual display), small in the top-left
// corner like the version in the top-right one; empty for none.
namespace MenuScreen {

// Fonts for the time, chosen with MDSCFG,clockfont,<index>. Index 0 is the default.
constexpr int kClockFontCount = 8;
const char* clockFontName(int index);

// systems: the Systems button at the bottom (touch boards, when the host sent a list of systems).
void draw(DisplayManager& display, const wallclock::DateTime& now, const char* ip, bool dimmed, int clockFont = 0,
          const char* boardIp = "", bool systems = false);

// Where the Systems button is, for the tap.
struct Rect {
  int x, y, w, h;
};
Rect systemsButton(const DisplayManager& display);

}  // namespace MenuScreen
