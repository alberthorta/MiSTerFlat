#include "ui/StandbyScreen.h"

#include <stdio.h>

#include "ui/Logos.h"
#include "ui/Theme.h"

namespace StandbyScreen {

namespace {

constexpr uint16_t kTimeColour = theme::rgb565(90, 90, 96);
// The prompt shows at full brightness, so it can use the colours as they are.
constexpr uint16_t kPromptIconColour = theme::rgb565(245, 120, 35);
constexpr uint16_t kPromptHintColour = theme::rgb565(200, 200, 206);

// This board's own address, small in the bottom-right corner as on the menu screen.
void drawBoardIp(lgfx::LovyanGFX& g, int w, int h, const char* boardIp) {
  if (!boardIp || !boardIp[0]) return;
  g.setFont(&fonts::Font2);
  g.setTextSize(1);
  g.setTextDatum(lgfx::bottom_right);
  g.setTextColor(theme::kTextFaint);
  g.drawString(boardIp, w - 4, h - 2);
  g.setTextDatum(lgfx::middle_center);
}

void drawPower(lgfx::LovyanGFX& g, int cx, int cy, uint16_t c) {
  // The same symbol as the RESET touch button, twice the size. fillArc: 0 = 3 o'clock, clockwise.
  g.fillArc(cx, cy + 4, 27, 21, 300, 360, c);
  g.fillArc(cx, cy + 4, 27, 21, 0, 240, c);
  g.fillRoundRect(cx - 4, cy - 28, 8, 30, 4, c);
}

}  // namespace

void drawIdle(DisplayManager& display, const wallclock::DateTime* now, const char* boardIp) {
  auto& g = display.canvas();
  const int w = display.width();
  const int h = display.height();
  g.fillScreen(theme::kBackground);
  // Logo and time as one column in the middle; without the time, the logo alone.
  const int column = now ? kLogoHeight + 70 : kLogoHeight;
  const int top = (h - column) / 2;
  g.drawPng(kLogoPng, sizeof(kLogoPng), (w - kLogoWidth) / 2, top);
  if (now) {
    char buf[8];
    snprintf(buf, sizeof(buf), "%02d:%02d", now->hour, now->minute);
    g.setTextDatum(lgfx::middle_center);
    g.setTextSize(1);
    g.setFont(&fonts::FreeSansBold24pt7b);
    g.setTextColor(kTimeColour);
    g.drawString(buf, w / 2, top + kLogoHeight + 46);
  }
  drawBoardIp(g, w, h, boardIp);
  display.present();
}

void drawPrompt(DisplayManager& display, const char* boardIp) {
  auto& g = display.canvas();
  const int w = display.width();
  const int h = display.height();
  g.fillScreen(theme::kBackground);
  g.setTextDatum(lgfx::middle_center);
  g.setTextSize(1);
  const int top = (h - 110) / 2;
  drawPower(g, w / 2, top + 32, kPromptIconColour);
  g.setFont(&fonts::DejaVu18);
  g.setTextColor(kPromptHintColour);
  g.drawString("Tap to power on", w / 2, top + 95);
  drawBoardIp(g, w, h, boardIp);
  display.present();
}

}  // namespace StandbyScreen
