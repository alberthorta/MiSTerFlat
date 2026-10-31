#include "ui/MenuScreen.h"

#include <stdio.h>

#include "ui/Theme.h"

namespace MenuScreen {

namespace {

const char* const kWeekdays[] = {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"};
const char* const kMonths[] = {"Jan", "Feb", "Mar", "Apr", "May", "Jun",
                               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"};

constexpr int kTitleY = 16;
constexpr int kTimeY = 74;
// The retro 8x8 font of the core names, 7x: 56 px digits, "HH:MM" 280 px wide.
constexpr int kTimeScale = 7;
constexpr int kDateY = 128;
constexpr int kIpY = 156;

}  // namespace

void draw(DisplayManager& display, const wallclock::DateTime& t, const char* ip, bool dimmed) {
  auto& g = display.canvas();
  const int w = display.width();
  const int top = display.layoutTop();
  const uint16_t timeColor = dimmed ? theme::rgb565(90, 90, 90) : theme::kText;
  const uint16_t accent = dimmed ? theme::rgb565(90, 50, 10) : theme::kAccent;
  const uint16_t dim = dimmed ? theme::rgb565(55, 55, 55) : theme::kTextDim;

  g.fillScreen(theme::kBackground);
  g.setTextDatum(lgfx::middle_center);

  g.setFont(&fonts::DejaVu18);
  g.setTextSize(1);
  g.setTextColor(accent);
  g.drawString("MiSTer", w / 2, top + kTitleY);

  char buf[32];
  snprintf(buf, sizeof(buf), "%02d:%02d", t.hour, t.minute);
  g.setFont(&fonts::Font8x8C64);
  g.setTextSize(kTimeScale);
  g.setTextColor(timeColor);
  g.drawString(buf, w / 2, top + kTimeY);
  g.setTextSize(1);

  const int wd = (t.weekday >= 0 && t.weekday < 7) ? t.weekday : 0;
  const int mo = (t.month >= 1 && t.month <= 12) ? t.month - 1 : 0;
  snprintf(buf, sizeof(buf), "%s %d %s %d", kWeekdays[wd], t.day, kMonths[mo], t.year);
  g.setFont(&fonts::DejaVu18);
  g.setTextColor(dim);
  g.drawString(buf, w / 2, top + kDateY);

  if (ip && ip[0]) {
    g.setFont(&fonts::Font2);
    g.setTextColor(dimmed ? theme::rgb565(45, 45, 45) : theme::kTextFaint);
    g.drawString(ip, w / 2, top + kIpY);
  }
  display.present();
}

}  // namespace MenuScreen
