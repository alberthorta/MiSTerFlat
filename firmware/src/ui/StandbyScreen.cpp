#include "ui/StandbyScreen.h"

#include <stdio.h>

#include "ui/Theme.h"

namespace StandbyScreen {

namespace {

constexpr uint16_t kIconColour = theme::rgb565(150, 70, 30);
constexpr uint16_t kTimeColour = theme::rgb565(90, 90, 96);
constexpr uint16_t kHintColour = theme::rgb565(110, 110, 116);

void drawPower(lgfx::LovyanGFX& g, int cx, int cy, uint16_t c) {
  // The same symbol as the RESET touch button, twice the size. fillArc: 0 = 3 o'clock, clockwise.
  g.fillArc(cx, cy + 4, 27, 21, 300, 360, c);
  g.fillArc(cx, cy + 4, 27, 21, 0, 240, c);
  g.fillRoundRect(cx - 4, cy - 28, 8, 30, 4, c);
}

}  // namespace

void draw(DisplayManager& display, const wallclock::DateTime* now, const char* boardIp) {
  auto& g = display.canvas();
  const int w = display.width();
  const int h = display.height();
  g.fillScreen(theme::kBackground);
  g.setTextDatum(lgfx::middle_center);
  g.setTextSize(1);

  // Icon, time and hint as one column in the middle; without the time the column is shorter.
  const int column = now ? 170 : 110;
  int y = (h - column) / 2;
  drawPower(g, w / 2, y + 32, kIconColour);
  y += 80;
  if (now) {
    char buf[8];
    snprintf(buf, sizeof(buf), "%02d:%02d", now->hour, now->minute);
    g.setFont(&fonts::FreeSansBold24pt7b);
    g.setTextColor(kTimeColour);
    g.drawString(buf, w / 2, y + 22);
    y += 60;
  }
  g.setFont(&fonts::DejaVu18);
  g.setTextColor(kHintColour);
  g.drawString("Tap to power on", w / 2, y + 15);

  if (boardIp && boardIp[0]) {
    g.setFont(&fonts::Font2);
    g.setTextDatum(lgfx::bottom_right);
    g.setTextColor(theme::kTextFaint);
    g.drawString(boardIp, w - 4, h - 2);
    g.setTextDatum(lgfx::middle_center);
  }

  display.present();
}

}  // namespace StandbyScreen
