#include "ui/LegacyCanvas.h"

#include "Command.h"
#include "ui/Theme.h"

namespace LegacyCanvas {

namespace {

constexpr int kBufferModeOffset = 100;
constexpr int kMaxLevel = 15;

// tty2oled font numbers (oled_setfont) mapped to the closest LovyanGFX font.
const lgfx::IFont* fontFor(int f) {
  switch (f) {
    case 0: return &fonts::Font0;          // u8g2 5x7
    case 1: return &fonts::DejaVu12;       // luBS08
    case 2: return &fonts::DejaVu12;       // luBS10
    case 3: return &fonts::DejaVu18;       // luBS14
    case 4: return &fonts::DejaVu24;       // luBS18
    case 5: return &fonts::DejaVu24;       // luBS24
    case 8: return &fonts::Font7;          // 7-segment digits
    case 9:
    case 10: return &fonts::Font8x8C64;    // commodore64 / 8bitclassic
    default: return &fonts::DejaVu12;      // 6, 7 and unknown
  }
}

bool inRange(int32_t v, int32_t lo, int32_t hi) { return v >= lo && v <= hi; }

}  // namespace

int originX(const DisplayManager& display) { return (display.width() - kWidth) / 2; }

int originY(const DisplayManager& display) { return (display.height() - kHeight) / 2; }

uint16_t grey(int level) {
  if (level < 0) level = 0;
  if (level > kMaxLevel) level = kMaxLevel;
  const uint8_t v = static_cast<uint8_t>(level * 17);
  return theme::rgb565(v, v, v);
}

bool text(DisplayManager& display, std::string_view args, bool* present) {
  std::string_view f[6];
  if (proto::splitFields(args, f, 6) != 6) return false;
  int32_t font, fg, bg, x, y;
  if (!proto::parseInt(f[0], font) || !proto::parseInt(f[1], fg) || !proto::parseInt(f[2], bg) ||
      !proto::parseInt(f[3], x) || !proto::parseInt(f[4], y)) {
    return false;
  }
  if (font < 0 || !inRange(fg, 0, kMaxLevel) || !inRange(bg, 0, kMaxLevel) || !inRange(x, 0, kWidth - 1) ||
      !inRange(y, 0, kHeight - 1)) {
    return false;
  }
  *present = font < kBufferModeOffset;
  if (!*present) font -= kBufferModeOffset;

  char buf[128];
  const size_t n = f[5].size() < sizeof(buf) - 1 ? f[5].size() : sizeof(buf) - 1;
  for (size_t i = 0; i < n; ++i) buf[i] = f[5][i];
  buf[n] = '\0';

  auto& g = display.canvas();
  g.setFont(fontFor(font));
  g.setTextSize(1);
  g.setTextColor(grey(fg), grey(bg));
  g.setTextDatum(lgfx::baseline_left);  // u8g2 setCursor() is the baseline
  g.drawString(buf, originX(display) + x, originY(display) + y);
  return true;
}

bool geometry(DisplayManager& display, std::string_view args, bool* present) {
  std::string_view f[8];
  if (proto::splitFields(args, f, 8) != 8) return false;
  int32_t v[8];
  for (int i = 0; i < 8; ++i) {
    if (!proto::parseInt(f[i], v[i])) return false;
  }
  int32_t figure = v[0];
  *present = figure < kBufferModeOffset;
  if (!*present) figure -= kBufferModeOffset;
  if (!inRange(v[1], 0, kMaxLevel)) return false;

  auto& g = display.canvas();
  const uint16_t c = grey(v[1]);
  const int ox = originX(display), oy = originY(display);
  const int x = ox + v[2], y = oy + v[3];
  const int i = v[4], j = v[5], k = v[6], l = v[7];
  // Clip to the legacy viewport so a script cannot draw over the rest of the screen.
  g.setClipRect(ox, oy, kWidth, kHeight);
  switch (figure) {
    case 1: g.drawPixel(x, y, c); break;
    case 2: g.drawLine(x, y, ox + i, oy + j, c); break;
    case 3: g.drawRect(x, y, i, j, c); break;
    case 4: g.fillRect(x, y, i, j, c); break;
    case 5: g.drawCircle(x, y, i, c); break;
    case 6: g.fillCircle(x, y, i, c); break;
    case 7: g.drawRoundRect(x, y, i, j, k, c); break;
    case 8: g.fillRoundRect(x, y, i, j, k, c); break;
    case 9: g.drawTriangle(x, y, ox + i, oy + j, ox + k, oy + l, c); break;
    case 10: g.fillTriangle(x, y, ox + i, oy + j, ox + k, oy + l, c); break;
    default:
      g.clearClipRect();
      return false;
  }
  g.clearClipRect();
  return true;
}

void parameterError(DisplayManager& display, std::string_view line) {
  auto& g = display.canvas();
  g.fillScreen(theme::kBackground);
  g.setTextSize(1);
  g.setTextDatum(lgfx::middle_center);
  g.setTextColor(theme::kAccent);
  g.setFont(&fonts::DejaVu18);
  g.drawString("Parameter Error", display.width() / 2, 60);

  char buf[64];
  const size_t n = line.size() < sizeof(buf) - 1 ? line.size() : sizeof(buf) - 1;
  for (size_t i = 0; i < n; ++i) buf[i] = line[i];
  buf[n] = '\0';
  g.setTextColor(theme::kTextDim);
  g.setFont(&fonts::DejaVu12);
  g.drawString(buf, display.width() / 2, 100);
  display.present();
}

void testPattern(DisplayManager& display) {
  auto& g = display.canvas();
  const int w = display.width(), h = display.height();
  static const uint16_t kBars[] = {
      theme::rgb565(255, 255, 255), theme::rgb565(255, 255, 0), theme::rgb565(0, 255, 255),
      theme::rgb565(0, 255, 0),     theme::rgb565(255, 0, 255), theme::rgb565(255, 0, 0),
      theme::rgb565(0, 0, 255),     theme::rgb565(0, 0, 0),
  };
  const int n = sizeof(kBars) / sizeof(kBars[0]);
  const int barsHeight = h * 2 / 3;
  for (int i = 0; i < n; ++i) g.fillRect(i * w / n, 0, (i + 1) * w / n - i * w / n, barsHeight, kBars[i]);
  for (int level = 0; level <= kMaxLevel; ++level) {
    const int x0 = level * w / (kMaxLevel + 1), x1 = (level + 1) * w / (kMaxLevel + 1);
    g.fillRect(x0, barsHeight, x1 - x0, h - barsHeight, grey(level));
  }
  // One-pixel frame: shows whether the panel offsets are right (all four edges visible).
  g.drawRect(0, 0, w, h, theme::rgb565(255, 0, 0));
  display.present();
}

}  // namespace LegacyCanvas
