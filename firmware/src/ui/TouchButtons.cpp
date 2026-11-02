#include "ui/TouchButtons.h"

#include <Arduino.h>
#include <math.h>

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

// Level rows (volume, brightness) under the main row: icon, small -, bar, small +. The icon sits
// under RESET and + under BLUETOOTH. All rows together are centred on the screen.
constexpr int kMainToLevel = 76;  // centre of the main row to centre of the first level row
constexpr int kLevelGap = 52;     // centre to centre of two level rows
constexpr int kSmallRadius = 18;
constexpr int kIconToDown = 44;
constexpr int kSegments = TouchButtons::kLevelMax + 1;
constexpr int kSegmentGap = 4;
constexpr int kSegmentHeight = 14;
constexpr int kBarMargin = 10;  // between the bar and the - and + buttons
constexpr uint16_t kVolColour = theme::rgb565(190, 120, 255);
constexpr uint16_t kBrightColour = theme::rgb565(240, 190, 40);
constexpr uint16_t kSegmentOff = theme::rgb565(60, 60, 66);

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

void drawMinus(lgfx::LovyanGFX& g, int cx, int cy, uint16_t c) { g.fillRoundRect(cx - 8, cy - 2, 16, 4, 2, c); }

void drawPlus(lgfx::LovyanGFX& g, int cx, int cy, uint16_t c) {
  drawMinus(g, cx, cy, c);
  g.fillRoundRect(cx - 2, cy - 8, 4, 16, 2, c);
}

void drawSpeaker(lgfx::LovyanGFX& g, int cx, int cy, uint16_t c) {
  g.fillRect(cx - 11, cy - 4, 6, 8, c);
  g.fillTriangle(cx - 6, cy - 4, cx + 1, cy - 11, cx + 1, cy + 11, c);
  g.fillTriangle(cx - 6, cy - 4, cx - 6, cy + 4, cx + 1, cy + 11, c);
  for (int r : {9, 15}) {
    g.fillArc(cx + 1, cy, r, r - 2, 315, 360, c);
    g.fillArc(cx + 1, cy, r, r - 2, 0, 45, c);
  }
}

void drawSun(lgfx::LovyanGFX& g, int cx, int cy, uint16_t c) {
  g.fillCircle(cx, cy, 5, c);
  for (int k = 0; k < 8; ++k) {
    const float a = k * static_cast<float>(M_PI) / 4;
    const float dx = cosf(a), dy = sinf(a);
    g.drawWideLine(cx + dx * 8.5f, cy + dy * 8.5f, cx + dx * 12.5f, cy + dy * 12.5f, 1.2f, c);
  }
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
  if (shown_ && unlightAtMs_ && static_cast<int32_t>(nowMs - unlightAtMs_) >= 0) {
    unlightAtMs_ = 0;
    chosen_ = kNone;
    draw();
  }
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
  if (b >= kCount) {
    // Shown at once; the host confirms the volume with MDSVOL.
    const int step = b == kVolUp || b == kBrightUp ? 1 : -1;
    if (b == kVolDown || b == kVolUp) {
      // Like Main's volume keys: the first step out of mute only unmutes.
      if (muted_) {
        muted_ = false;
      } else {
        volume_ = constrain(volume_ + step, 0, kLevelMax);
      }
      r.pressed = step > 0 ? "volup" : "voldown";
    } else if (b == kVolBar) {
      volume_ = r.level = levelAt(lastX_);
      muted_ = false;
      r.pressed = "vol";
    } else {
      brightness_ = b == kBrightBar ? levelAt(lastX_) : constrain(brightness_ + step, 0, kLevelMax);
      r.level = brightness_;
      r.pressed = "bright";
    }
    if (b != kVolBar && b != kBrightBar) {
      chosen_ = b;
      unlightAtMs_ = nowMs + kChosenMs;
      if (unlightAtMs_ == 0) unlightAtMs_ = 1;
    }
    draw();
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
  const bool volumeButton = held == kVolDown || held == kVolUp || held == kVolBar;
  held_ = held >= 0 && held < kAll && (!volumeButton || volumeRow()) ? static_cast<Button>(held) : kNone;
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
  closeAtMs_ = unlightAtMs_ = 0;
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
  unlightAtMs_ = 0;
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
  const int cy = rowY();

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
  if (volumeRow()) composeLevel(true, volumeY(), volume_, muted_);
  composeLevel(false, brightnessY(), brightness_, false);
}

TouchButtons::LevelLayout TouchButtons::levelLayout() const {
  const int w = display_.width();
  LevelLayout l;
  l.iconX = centreX(w, 0);
  l.downX = l.iconX + kIconToDown;
  l.upX = centreX(w, kCount - 1);
  const int edge = kSmallRadius + kHeldGrow + kBarMargin;
  const int space = l.upX - l.downX - 2 * edge;
  l.seg = (space - (kSegments - 1) * kSegmentGap) / kSegments;
  l.barW = kSegments * l.seg + (kSegments - 1) * kSegmentGap;
  l.barX = (l.downX + l.upX - l.barW) / 2;
  return l;
}

int TouchButtons::levelAt(int x) const {
  const LevelLayout l = levelLayout();
  return constrain((x - l.barX + kSegmentGap / 2) / (l.seg + kSegmentGap), 0, kLevelMax);
}

void TouchButtons::composeLevel(bool volume, int cy, int level, bool greyed) {
  auto& g = display_.canvas();
  const LevelLayout l = levelLayout();
  const uint16_t colour = volume ? kVolColour : kBrightColour;
  const Button down = volume ? kVolDown : kBrightDown;
  const Button up = volume ? kVolUp : kBrightUp;

  const uint16_t iconColour = greyed ? theme::kTextDim : colour;
  if (volume) {
    drawSpeaker(g, l.iconX, cy, iconColour);
  } else {
    drawSun(g, l.iconX, cy, iconColour);
  }
  for (const Button b : {down, up}) {
    const int cx = b == down ? l.downX : l.upX;
    const bool lit = b == held_ || b == chosen_;
    const int r = kSmallRadius + (lit ? kHeldGrow : 0);
    g.fillCircle(cx, cy, r, colour);
    if (!lit) g.fillCircle(cx, cy, r - kRing, kFace);
    const uint16_t icon = lit ? theme::kText : colour;
    if (b == down) {
      drawMinus(g, cx, cy, icon);
    } else {
      drawPlus(g, cx, cy, icon);
    }
  }
  // Main's own volume bar has 8 steps as well: level n lights n + 1 of them.
  const uint16_t on = greyed ? theme::kTextDim : colour;
  for (int i = 0; i < kSegments; ++i) {
    g.fillRoundRect(l.barX + i * (l.seg + kSegmentGap), cy - kSegmentHeight / 2, l.seg, kSegmentHeight, 3,
                    i <= level ? on : kSegmentOff);
  }
  if (greyed) {
    g.setTextColor(theme::kTextDim);
    g.drawString("Muted", l.barX + l.barW / 2, cy + kSegmentHeight / 2 + kCaptionGap - 4);
  }
}

void TouchButtons::setVolume(int level, bool muted) {
  level = constrain(level, 0, kLevelMax);
  if (level == volume_ && muted == muted_) return;
  volume_ = level;
  muted_ = muted;
  if (shown_ && fade_ == Fade::None && !closeAtMs_) draw();
}

void TouchButtons::setBrightness(int level) {
  level = constrain(level, 0, kLevelMax);
  if (level == brightness_) return;
  brightness_ = level;
  if (shown_ && fade_ == Fade::None && !closeAtMs_) draw();
}

int TouchButtons::rowY() const {
  const int levelRows = volumeRow() ? 2 : 1;
  const int total = kRadius + kMainToLevel + (levelRows - 1) * kLevelGap + kSmallRadius;
  return (display_.height() - total) / 2 + kRadius;
}

int TouchButtons::volumeY() const { return rowY() + kMainToLevel; }

int TouchButtons::brightnessY() const { return rowY() + kMainToLevel + (volumeRow() ? kLevelGap : 0); }

TouchButtons::Button TouchButtons::hit(int x, int y) const {
  const int w = display_.width();
  const int cy = rowY();
  // A little larger than the circle: half the spacing across, a margin above and below.
  for (int i = 0; i < kCount; ++i) {
    const int dx = x - centreX(w, i);
    if (dx * dx < (kSpacing / 2) * (kSpacing / 2) && y > cy - kRadius - 12 && y < cy + kRadius + 12) {
      return static_cast<Button>(i);
    }
  }
  // Level rows: the whole band of the row counts. Left of the bar (the icon too) is -, right is +.
  const LevelLayout l = levelLayout();
  for (const bool volume : {true, false}) {
    if (volume && !volumeRow()) continue;
    const int ry = volume ? volumeY() : brightnessY();
    if (y <= ry - kLevelGap / 2 || y >= ry + kLevelGap / 2) continue;
    if (x < l.iconX - kSpacing / 2 || x > l.upX + kSpacing / 2) return kNone;
    if (x < l.barX - kBarMargin / 2) return volume ? kVolDown : kBrightDown;
    if (x > l.barX + l.barW + kBarMargin / 2) return volume ? kVolUp : kBrightUp;
    return volume ? kVolBar : kBrightBar;
  }
  return kNone;
}
