#include "ui/TouchButtons.h"

#include <Arduino.h>

#include "ui/Theme.h"

namespace {

constexpr uint32_t kPollMs = 20;
constexpr uint32_t kShownMs = 5000;
constexpr uint32_t kConfirmMs = 3000;
// The chosen button stays lit this long, so the tap visibly did something.
constexpr uint32_t kChosenMs = 180;
// Fade in and out: 4 blended frames. Each frame is a full push (about 30 ms on the SPI panel), so
// the whole fade takes about 150 ms.
constexpr uint8_t kAlphaStep = 8;
constexpr uint32_t kFadeFrameMs = 15;

// One row of round buttons, centred on the screen. Only an armed RESET gets a line of text below.
constexpr int kRadius = 28;
constexpr int kHeldGrow = 3;
constexpr int kRing = 3;
constexpr int kSpacing = 74;  // centre to centre
constexpr int kCaptionGap = 16;

struct Style {
  const char* name;
  uint16_t colour;
};

const Style kStyles[] = {
    {"reset", theme::rgb565(235, 70, 60)},
    {"osd", theme::kAccent},
    {"user", theme::rgb565(80, 200, 120)},
    {"bt", theme::rgb565(60, 140, 255)},
};
// In the MiSTer menu there is no core to reset: USER becomes Wi-Fi set-up when there is a dongle.
const Style kWifiStyle = {"wifi", theme::rgb565(0, 190, 200)};
constexpr int kWifiIcon = 4;
constexpr int kUserSlot = 2;

const Style& styleFor(int i, bool wifiSlot) { return i == kUserSlot && wifiSlot ? kWifiStyle : kStyles[i]; }

constexpr uint16_t kFace = theme::rgb565(28, 28, 32);

int centreX(int w, int i) { return w / 2 + (2 * i - 3) * kSpacing / 2; }
int centreY(int h) { return h / 2; }

// Icons, drawn with primitives, about 30 px across. fillArc angles: 0 = 3 o'clock, clockwise.
void drawPower(lgfx::LovyanGFX& g, int cx, int cy, uint16_t c) {
  g.fillArc(cx, cy + 2, 13, 10, 300, 360, c);
  g.fillArc(cx, cy + 2, 13, 10, 0, 240, c);
  g.fillRoundRect(cx - 2, cy - 14, 4, 15, 2, c);
}

void drawMenu(lgfx::LovyanGFX& g, int cx, int cy, uint16_t c) {
  for (int k = -1; k <= 1; ++k) g.fillRoundRect(cx - 13, cy - 2 + k * 8, 26, 4, 2, c);
}

void drawRestart(lgfx::LovyanGFX& g, int cx, int cy, uint16_t c) {
  g.fillArc(cx, cy, 13, 10, 330, 360, c);
  g.fillArc(cx, cy, 13, 10, 0, 270, c);
  // Arrow head at the top end of the arc, pointing right (clockwise).
  g.fillTriangle(cx - 1, cy - 19, cx - 1, cy - 4, cx + 8, cy - 11, c);
}

void drawBluetooth(lgfx::LovyanGFX& g, int cx, int cy, uint16_t c) {
  const float r = 1.4f;
  g.drawWideLine(cx - 1, cy - 14, cx - 1, cy + 14, r, c);
  g.drawWideLine(cx - 1, cy - 14, cx + 7, cy - 7, r, c);
  g.drawWideLine(cx + 7, cy - 7, cx - 8, cy + 7, r, c);
  g.drawWideLine(cx - 1, cy + 14, cx + 7, cy + 7, r, c);
  g.drawWideLine(cx + 7, cy + 7, cx - 8, cy - 7, r, c);
}

void drawWifi(lgfx::LovyanGFX& g, int cx, int cy, uint16_t c) {
  g.fillCircle(cx, cy + 8, 3, c);
  g.fillArc(cx, cy + 10, 11, 8, 225, 315, c);
  g.fillArc(cx, cy + 10, 18, 15, 225, 315, c);
}

void drawIcon(lgfx::LovyanGFX& g, int i, int cx, int cy, uint16_t c) {
  switch (i) {
    case 0: drawPower(g, cx, cy, c); break;
    case 1: drawMenu(g, cx, cy, c); break;
    case 2: drawRestart(g, cx, cy, c); break;
    case kWifiIcon: drawWifi(g, cx, cy, c); break;
    default: drawBluetooth(g, cx, cy, c); break;
  }
}

}  // namespace

TouchButtons::Result TouchButtons::poll(uint32_t nowMs) {
  Result r;
  // Someone else drew a frame: our buttons are gone with the old one.
  if (shown_ && display_.frameCount() != frameCount_) {
    shown_ = false;
    resetArmed_ = false;
    closeAtMs_ = 0;
    fade_ = Fade::None;
  }
  if (fade_ != Fade::None) {
    stepFade(nowMs);
    return r;
  }
  if (shown_ && closeAtMs_ && static_cast<int32_t>(nowMs - closeAtMs_) >= 0) hide();
  if (shown_ && resetArmed_ && nowMs - armedAtMs_ >= kConfirmMs) {
    resetArmed_ = false;
    draw();
  }
  if (shown_ && !down_ && nowMs - shownAtMs_ >= kShownMs) hide();

  if (nowMs - lastPollMs_ < kPollMs) return r;
  lastPollMs_ = nowMs;
  int x, y;
  if (display_.touched(&x, &y)) {
    down_ = true;
    lastX_ = x;
    lastY_ = y;
    // Light the button under the finger while it is held.
    const Button b = shown_ && !closeAtMs_ ? hit(x, y) : kNone;
    if (b != held_) {
      held_ = b;
      draw();
    }
    return r;
  }
  if (!down_) return r;
  // The finger left the glass: that is the tap, at the last point it touched.
  down_ = false;
  return release(nowMs);
}

TouchButtons::Result TouchButtons::release(uint32_t nowMs) {
  Result r;
  r.activity = true;
  const Button b = held_;
  held_ = kNone;
  // The first tap on a dark (idle) screen only wakes it.
  if (!display_.lightOn() || closeAtMs_) return r;
  if (!shown_) {
    show(nowMs);
    return r;
  }
  shownAtMs_ = nowMs;
  if (b == kNone) {
    hide();
    return r;
  }
  if (b == kReset && !resetArmed_) {
    resetArmed_ = true;
    armedAtMs_ = nowMs;
    draw();
    return r;
  }
  r.pressed = styleFor(b, wifiSlot_).name;
  chosen_ = b;
  closeAtMs_ = nowMs + kChosenMs;
  if (closeAtMs_ == 0) closeAtMs_ = 1;
  draw();
  return r;
}

void TouchButtons::preview(int held, bool resetArmed, uint32_t nowMs) {
  if (!shown_) show(nowMs);
  fade_ = Fade::None;  // screenshots want the final frame at once
  held_ = held >= 0 && held < kCount ? static_cast<Button>(held) : kNone;
  resetArmed_ = resetArmed;
  armedAtMs_ = shownAtMs_ = nowMs;
  draw();
}

void TouchButtons::show(uint32_t nowMs) {
  // Without a framebuffer there is nothing to put back.
  if (!display_.saveFrame(DisplayManager::kUnder)) return;
  shown_ = true;
  resetArmed_ = false;
  held_ = chosen_ = kNone;
  closeAtMs_ = 0;
  shownAtMs_ = nowMs;
  compose();
  if (!display_.saveFrame(DisplayManager::kOver)) {
    draw();
    return;
  }
  fade_ = Fade::In;
  alpha_ = 0;
  nextFadeMs_ = nowMs;
  stepFade(nowMs);
}

void TouchButtons::stepFade(uint32_t nowMs) {
  if (static_cast<int32_t>(nowMs - nextFadeMs_) < 0) return;
  nextFadeMs_ = nowMs + kFadeFrameMs;
  if (fade_ == Fade::In) {
    alpha_ = alpha_ + kAlphaStep >= 32 ? 32 : alpha_ + kAlphaStep;
    if (alpha_ == 32) fade_ = Fade::None;
  } else {
    alpha_ = alpha_ <= kAlphaStep ? 0 : alpha_ - kAlphaStep;
    if (alpha_ == 0) {
      fade_ = Fade::None;
      finishHide();
      return;
    }
  }
  display_.blendSaved(alpha_);
  display_.present();
  frameCount_ = display_.frameCount();
}

void TouchButtons::hide() {
  if (!shown_ || fade_ == Fade::Out) return;
  closeAtMs_ = 0;
  // Fade out from what is on screen now (a lit button, an armed RESET).
  if (fade_ == Fade::None) {
    if (!display_.saveFrame(DisplayManager::kOver)) {
      finishHide();
      return;
    }
    alpha_ = 32;
  }
  fade_ = Fade::Out;
  nextFadeMs_ = millis();
}

void TouchButtons::finishHide() {
  shown_ = false;
  resetArmed_ = false;
  held_ = chosen_ = kNone;
  display_.restoreFrame(DisplayManager::kUnder);
  display_.present();
}

void TouchButtons::draw() {
  if (!shown_) return;
  compose();
  display_.present();
  frameCount_ = display_.frameCount();
}

void TouchButtons::compose() {
  display_.restoreFrame(DisplayManager::kUnder);
  display_.dimFrame();
  auto& g = display_.canvas();
  const int w = display_.width();
  const int cy = centreY(display_.height());

  g.setTextDatum(lgfx::middle_center);
  g.setTextSize(1);
  g.setFont(&fonts::DejaVu12);
  for (int i = 0; i < kCount; ++i) {
    const Style& s = styleFor(i, wifiSlot_);
    const int cx = centreX(w, i);
    const bool armed = i == kReset && resetArmed_;
    const bool lit = i == held_ || i == chosen_ || armed;
    const int r = kRadius + (i == held_ || i == chosen_ ? kHeldGrow : 0);
    if (lit) {
      g.fillCircle(cx, cy, r, s.colour);
      drawIcon(g, &s == &kWifiStyle ? kWifiIcon : i, cx, cy, theme::kText);
    } else {
      g.fillCircle(cx, cy, r, s.colour);
      g.fillCircle(cx, cy, r - kRing, kFace);
      drawIcon(g, &s == &kWifiStyle ? kWifiIcon : i, cx, cy, s.colour);
    }
    if (armed) {
      g.setTextColor(s.colour);
      g.drawString("Tap again", cx, cy + kRadius + kCaptionGap);
    }
  }
}

TouchButtons::Button TouchButtons::hit(int x, int y) const {
  const int w = display_.width();
  const int cy = centreY(display_.height());
  // A little larger than the circle: half the spacing across, a margin above and below.
  for (int i = 0; i < kCount; ++i) {
    const int dx = x - centreX(w, i);
    if (dx * dx < (kSpacing / 2) * (kSpacing / 2) && y > cy - kRadius - 12 && y < cy + kRadius + 12) {
      return static_cast<Button>(i);
    }
  }
  return kNone;
}
