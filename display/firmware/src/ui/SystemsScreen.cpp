#include "ui/SystemsScreen.h"

#include <Arduino.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

#include "Command.h"
#include "ui/Theme.h"

namespace {

constexpr uint32_t kPollMs = 15;
constexpr uint32_t kFrameMs = 16;
constexpr uint32_t kIdleMs = 10000;

// Covers are kept at this size: the one in the middle is drawn 1:1, the others smaller.
constexpr int kCoverW = 200;
constexpr int kCoverH = 150;
constexpr float kCoverScale = static_cast<float>(kCoverW) / 320;
constexpr int kCentreY = 106;

// Where a cover goes for its distance d from the middle (in covers): the first neighbour at
// kNearX px with kNearScale, then kFarX px more per cover. Side covers are also narrower (kSqueeze),
// as if turned away.
constexpr float kNearX = 118;
constexpr float kFarX = 62;
constexpr float kNearScale = 0.6f;
constexpr float kFarScale = 0.45f;
constexpr float kSqueeze = 0.72f;
constexpr float kMaxDistance = 2.6f;

constexpr int kTapSlop = 10;      // a touch that moves less than this is a tap
constexpr float kRubber = 0.35f;  // dragging past the first or last cover moves this much
constexpr float kFlingMs = 180;   // a quick drag goes on as far as it would in this time
constexpr float kEase = 0.3f;     // per frame, towards the target

// The back button, top left.
constexpr int kBackX = 24;
constexpr int kBackY = 24;
constexpr int kBackR = 17;
constexpr int kBackHit = 58;

constexpr uint16_t kBorder = theme::rgb565(60, 60, 66);
constexpr uint16_t kBorderFront = theme::rgb565(120, 120, 128);
constexpr uint16_t kPlaceholder = theme::rgb565(28, 28, 32);
constexpr uint16_t kDotOff = theme::rgb565(60, 60, 66);

struct Place {
  float x, zoomX, zoomY;
};

Place placeFor(float d) {
  const float a = fabsf(d), sign = d < 0 ? -1.0f : 1.0f;
  Place p;
  float scale, squeeze;
  if (a <= 1) {
    p.x = 160 + sign * a * kNearX;
    scale = 1 + (kNearScale - 1) * a;
    squeeze = 1 + (kSqueeze - 1) * a;
  } else {
    const float f = a - 1 < 1 ? a - 1 : 1;
    p.x = 160 + sign * (kNearX + (a - 1) * kFarX);
    scale = kNearScale + (kFarScale - kNearScale) * f;
    squeeze = kSqueeze;
  }
  p.zoomX = scale * squeeze;
  p.zoomY = scale;
  return p;
}

void drawBack(lgfx::LovyanGFX& g) {
  g.drawCircle(kBackX, kBackY, kBackR, theme::kTextDim);
  g.drawCircle(kBackX, kBackY, kBackR - 1, theme::kTextDim);
  const uint16_t c = theme::kText;
  g.drawWideLine(kBackX + 7, kBackY, kBackX - 7, kBackY, 1.4f, c);
  g.drawWideLine(kBackX - 7, kBackY, kBackX - 1, kBackY - 6, 1.4f, c);
  g.drawWideLine(kBackX - 7, kBackY, kBackX - 1, kBackY + 6, 1.4f, c);
}

// The sprites keep RGB565 byte-swapped, as the panel wants it.
void darken(const LGFX_Sprite& from, LGFX_Sprite& to) {
  const uint16_t* src = static_cast<const uint16_t*>(const_cast<LGFX_Sprite&>(from).getBuffer());
  uint16_t* dst = static_cast<uint16_t*>(to.getBuffer());
  for (int i = 0; i < kCoverW * kCoverH; ++i) {
    const uint16_t v = __builtin_bswap16(src[i]);
    dst[i] = __builtin_bswap16(static_cast<uint16_t>((v >> 1) & 0x7BEF));
  }
}

}  // namespace

void SystemsScreen::onHost(std::string_view args) {
  if (args == "clear") {
    count_ = 0;
    return;
  }
  // item,<i>,<crc32 hex>,<name>
  if (args.substr(0, 5) != "item,") return;
  std::string_view f[3];
  int32_t index = 0;
  if (proto::splitFields(args.substr(5), f, 3) != 3 || !proto::parseInt(f[0], index) || index < 0 ||
      index >= kMaxSystems || index > count_ || f[1].size() != 8) {
    return;
  }
  uint32_t crc = 0;
  for (char c : f[1]) {
    const int v = (c >= '0' && c <= '9') ? c - '0' : (c >= 'a' && c <= 'f') ? c - 'a' + 10 : -1;
    if (v < 0) return;
    crc = crc << 4 | static_cast<uint32_t>(v);
  }
  System& s = systems_[index];
  const size_t n = f[2].size() < sizeof(s.name) - 1 ? f[2].size() : sizeof(s.name) - 1;
  memcpy(s.name, f[2].data(), n);
  s.name[n] = '\0';
  if (s.crc != crc) s.requested = false;
  s.crc = crc;
  if (index == count_) ++count_;
  dirty_ = true;
}

bool SystemsScreen::makeSprites(System& s) {
  for (LGFX_Sprite** p : {&s.cover, &s.dim}) {
    if (*p) continue;
    auto* sprite = new LGFX_Sprite();
    sprite->setColorDepth(16);
    sprite->setPsram(true);
    if (!sprite->createSprite(kCoverW, kCoverH)) {
      delete sprite;
      return false;
    }
    *p = sprite;
  }
  return true;
}

void SystemsScreen::onCover(int index, uint32_t crc, bool png, const uint8_t* data, size_t length) {
  if (index < 0 || index >= count_) return;
  System& s = systems_[index];
  if (!makeSprites(s)) return;
  s.cover->fillScreen(TFT_BLACK);
  // Centred in the cover, whatever its size (320x170 pictures from the T-Display get bands).
  const bool ok = png ? s.cover->drawPng(data, length, 0, 0, kCoverW, kCoverH, 0, 0, kCoverScale, kCoverScale,
                                         lgfx::middle_center)
                      : s.cover->drawJpg(data, length, 0, 0, kCoverW, kCoverH, 0, 0, kCoverScale, kCoverScale,
                                         lgfx::middle_center);
  if (!ok) return;
  darken(*s.cover, *s.dim);
  s.haveCrc = crc;
  dirty_ = true;
}

void SystemsScreen::open(uint32_t nowMs) {
  if (count_ == 0) return;
  active_ = true;
  down_ = false;
  pendingLoad_ = -1;
  if (pos_ > maxPos()) pos_ = maxPos();
  target_ = pos_ = roundf(pos_);
  lastTouchMs_ = nowMs;
  requestCovers();
  draw();
}

void SystemsScreen::requestCovers() {
  for (int i = 0; i < count_; ++i) {
    System& s = systems_[i];
    if (s.haveCrc == s.crc || s.requested || s.crc == 0) continue;
    char line[24];
    snprintf(line, sizeof(line), "MDSSYS,img,%d\n", i);
    if (transport_.write(line)) s.requested = true;
  }
}

SystemsScreen::Result SystemsScreen::poll(uint32_t nowMs) {
  Result r;
  if (!active_) return r;
  if (nowMs - lastPollMs_ >= kPollMs) {
    lastPollMs_ = nowMs;
    int x, y;
    if (display_.touched(&x, &y)) {
      r.activity = true;
      lastTouchMs_ = nowMs;
      if (!down_) {
        down_ = moved_ = false;
        down_ = true;
        downX_ = lastX_ = x;
        downY_ = y;
        downPos_ = pos_;
        velocity_ = 0;
        lastMoveMs_ = nowMs;
      }
      if (abs(x - downX_) > kTapSlop || abs(y - downY_) > kTapSlop) moved_ = true;
      if (moved_) {
        float p = downPos_ - (x - downX_) / kNearX;
        if (p < 0) p *= kRubber;
        if (p > maxPos()) p = maxPos() + (p - maxPos()) * kRubber;
        const uint32_t dt = nowMs - lastMoveMs_;
        if (dt > 0) velocity_ = 0.6f * velocity_ + 0.4f * (x - lastX_) / dt;
        lastMoveMs_ = nowMs;
        lastX_ = x;
        if (p != pos_) {
          pos_ = target_ = p;
          dirty_ = true;
        }
      }
    } else if (down_) {
      down_ = false;
      r.activity = true;
      lastTouchMs_ = nowMs;
      if (!moved_) {
        tap(downX_, downY_);
      } else {
        // A finger that stopped before letting go does not fling.
        if (nowMs - lastMoveMs_ > 80) velocity_ = 0;
        float t = roundf(pos_ - velocity_ * kFlingMs / kNearX);
        const float from = roundf(downPos_);
        if (t > from + 2) t = from + 2;
        if (t < from - 2) t = from - 2;
        target_ = t < 0 ? 0 : t > maxPos() ? maxPos() : t;
      }
      if (!active_) {
        r.closed = pendingLoad_ < 0;
        r.loading = pendingLoad_ >= 0;
        return r;
      }
    }
  }
  if (!down_ && pos_ != target_ && nowMs - lastFrameMs_ >= kFrameMs) {
    pos_ += (target_ - pos_) * kEase;
    if (fabsf(target_ - pos_) < 0.004f) pos_ = target_;
    dirty_ = true;
  }
  if (dirty_ && nowMs - lastFrameMs_ >= kFrameMs) {
    lastFrameMs_ = nowMs;
    draw();
  }
  if (!down_ && pos_ == target_ && nowMs - lastTouchMs_ >= kIdleMs) {
    active_ = false;
    r.closed = true;
  }
  return r;
}

void SystemsScreen::tap(int x, int y) {
  if (x < kBackHit && y < kBackHit) {
    active_ = false;
    return;
  }
  // The front-most cover under the finger.
  int best = -1;
  float bestDistance = 99;
  for (int i = 0; i < count_; ++i) {
    const float d = i - pos_;
    if (fabsf(d) > kMaxDistance) continue;
    const Place p = placeFor(d);
    const float halfW = kCoverW * p.zoomX / 2, halfH = kCoverH * p.zoomY / 2;
    if (fabsf(x - p.x) <= halfW && fabsf(y - kCentreY) <= halfH && fabsf(d) < bestDistance) {
      best = i;
      bestDistance = fabsf(d);
    }
  }
  if (best < 0) return;
  if (best != static_cast<int>(roundf(pos_))) {
    target_ = best;
    return;
  }
  char line[24];
  snprintf(line, sizeof(line), "MDSSYS,load,%d\n", best);
  transport_.write(line);
  pendingLoad_ = best;
  target_ = pos_ = best;
  draw();
  active_ = false;
}

void SystemsScreen::drawCover(int i, float d) {
  auto& g = display_.canvas();
  const System& s = systems_[i];
  const Place p = placeFor(d);
  const int w = lroundf(kCoverW * p.zoomX), h = lroundf(kCoverH * p.zoomY);
  const int x0 = lroundf(p.x) - w / 2, y0 = kCentreY - h / 2;
  const bool front = fabsf(d) < 0.5f;
  if (s.haveCrc && s.cover) {
    LGFX_Sprite* sprite = front ? s.cover : s.dim;
    if (d == 0) {
      sprite->pushSprite(&g, x0, y0);
    } else {
      sprite->pushRotateZoom(&g, p.x, kCentreY, 0, p.zoomX, p.zoomY);
    }
  } else {
    g.fillRect(x0, y0, w, h, kPlaceholder);
    if (front) {
      g.setFont(&fonts::DejaVu12);
      g.setTextColor(theme::kTextDim);
      g.drawString(s.name, p.x, kCentreY);
    }
  }
  g.drawRect(x0, y0, w, h, front ? kBorderFront : kBorder);
}

void SystemsScreen::draw() {
  dirty_ = false;
  auto& g = display_.canvas();
  g.fillScreen(theme::kBackground);
  g.setTextDatum(lgfx::middle_center);
  g.setTextSize(1);

  // Back to front: the farthest covers first, the middle one last.
  bool drawn[kMaxSystems] = {};
  for (int k = 0; k < count_; ++k) {
    int pick = -1;
    float far = -1;
    for (int i = 0; i < count_; ++i) {
      const float a = fabsf(i - pos_);
      if (!drawn[i] && a > far) {
        far = a;
        pick = i;
      }
    }
    drawn[pick] = true;
    if (far <= kMaxDistance) drawCover(pick, pick - pos_);
  }

  int current = static_cast<int>(roundf(pos_));
  if (current < 0) current = 0;
  if (current > count_ - 1) current = count_ - 1;
  g.setFont(&fonts::DejaVu18);
  if (pendingLoad_ >= 0) {
    char text[48];
    snprintf(text, sizeof(text), "Loading %s...", systems_[pendingLoad_].name);
    g.setTextColor(theme::kAccent);
    g.drawString(text, 160, 202);
  } else {
    g.setTextColor(theme::kText);
    g.drawString(systems_[current].name, 160, 202);
  }
  // One dot per system.
  constexpr int kDotGap = 12;
  const int dotsX = 160 - (count_ - 1) * kDotGap / 2;
  for (int i = 0; i < count_; ++i) {
    g.fillCircle(dotsX + i * kDotGap, 226, 3, i == current ? theme::kAccent : kDotOff);
  }
  drawBack(g);
  display_.present();
}
