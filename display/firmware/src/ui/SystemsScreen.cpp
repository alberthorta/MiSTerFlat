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

// Systems: the host's 320x240 core pictures. Games: MiSTerManager's 240x320 box covers.
constexpr float kSystemScale = 200.0f / 320;
constexpr float kGameScale = 126.0f / 240;

// Side covers get smaller and narrower (as if turned away) up to the first neighbour, then only
// smaller.
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

constexpr int kLabelY = 206;
constexpr int kDotsY = 228;
constexpr int kDotGap = 11;

constexpr uint16_t kBorder = theme::rgb565(60, 60, 66);
constexpr uint16_t kBorderFront = theme::rgb565(120, 120, 128);
constexpr uint16_t kPlaceholder = theme::rgb565(28, 28, 32);
constexpr uint16_t kDotOff = theme::rgb565(60, 60, 66);

struct Place {
  float x, zoomX, zoomY;
};

void drawBack(lgfx::LovyanGFX& g) {
  g.drawCircle(kBackX, kBackY, kBackR, theme::kTextDim);
  g.drawCircle(kBackX, kBackY, kBackR - 1, theme::kTextDim);
  const uint16_t c = theme::kText;
  g.drawWideLine(kBackX + 7, kBackY, kBackX - 7, kBackY, 1.4f, c);
  g.drawWideLine(kBackX - 7, kBackY, kBackX - 1, kBackY - 6, 1.4f, c);
  g.drawWideLine(kBackX - 7, kBackY, kBackX - 1, kBackY + 6, 1.4f, c);
}

// The sprites keep RGB565 byte-swapped, as the panel wants it.
void darken(LGFX_Sprite& from, LGFX_Sprite& to, int pixels) {
  const uint16_t* src = static_cast<const uint16_t*>(from.getBuffer());
  uint16_t* dst = static_cast<uint16_t*>(to.getBuffer());
  for (int i = 0; i < pixels; ++i) {
    const uint16_t v = __builtin_bswap16(src[i]);
    dst[i] = __builtin_bswap16(static_cast<uint16_t>((v >> 1) & 0x7BEF));
  }
}

bool parseHex32(std::string_view hex, uint32_t& out) {
  if (hex.size() != 8) return false;
  out = 0;
  for (char c : hex) {
    const int v = (c >= '0' && c <= '9') ? c - '0' : (c >= 'a' && c <= 'f') ? c - 'a' + 10 : -1;
    if (v < 0) return false;
    out = out << 4 | static_cast<uint32_t>(v);
  }
  return true;
}

// The name in the large font, or the small one, or cut with "..." to fit.
void drawFitted(lgfx::LovyanGFX& g, const char* text, int x, int y, int maxW) {
  g.setFont(&fonts::DejaVu18);
  if (g.textWidth(text) > maxW) g.setFont(&fonts::DejaVu12);
  if (g.textWidth(text) <= maxW) {
    g.drawString(text, x, y);
    return;
  }
  char cut[48];
  size_t n = strlen(text) < sizeof(cut) - 4 ? strlen(text) : sizeof(cut) - 4;
  for (; n > 0; --n) {
    memcpy(cut, text, n);
    strcpy(cut + n, "...");
    if (g.textWidth(cut) <= maxW) break;
  }
  g.drawString(cut, x, y);
}

}  // namespace

const SystemsScreen::Geometry& SystemsScreen::geometry() const {
  static const Geometry kSystems = {200, 150, 106, 118, 62, kSystemScale};
  static const Geometry kGames = {126, 168, 108, 104, 52, kGameScale};
  return level_ == Level::Systems ? kSystems : kGames;
}

bool SystemsScreen::parseItem(std::string_view crcHex, std::string_view name, Item& item) {
  uint32_t crc = 0;
  if (!parseHex32(crcHex, crc)) return false;
  const size_t n = name.size() < sizeof(item.name) - 1 ? name.size() : sizeof(item.name) - 1;
  memcpy(item.name, name.data(), n);
  item.name[n] = '\0';
  if (item.crc != crc) item.requested = false;
  item.crc = crc;
  return true;
}

void SystemsScreen::onHost(std::string_view args) {
  std::string_view f[4];
  int32_t a = 0, b = 0;
  if (args == "clear") {
    systemCount_ = 0;
    gamesOf_ = -1;
    gameCount_ = 0;
    gamesExpected_ = -1;
    if (active_) {
      active_ = false;
      closedByHost_ = true;
    }
    return;
  }
  if (args.substr(0, 5) == "item,") {
    // item,<i>,<crc32>,<name>
    if (proto::splitFields(args.substr(5), f, 3) == 3 && proto::parseInt(f[0], a) && a >= 0 && a < kMaxSystems &&
        a <= systemCount_ && parseItem(f[1], f[2], systems_[a])) {
      if (a == systemCount_) ++systemCount_;
      dirty_ = true;
    }
    return;
  }
  if (args.substr(0, 6) == "games,") {
    // games,<i>,<n>: the list of system i follows
    if (proto::splitFields(args.substr(6), f, 2) == 2 && proto::parseInt(f[0], a) && proto::parseInt(f[1], b) &&
        a == gamesOf_ && gamesExpected_ != -1) {
      gameCount_ = 0;
      gamesExpected_ = b < 0 ? 0 : b > kMaxGames ? kMaxGames : b;
      if (gamesExpected_ == 0) gamesExpected_ = -1;
      dirty_ = true;
    }
    return;
  }
  if (args.substr(0, 5) == "game,") {
    // game,<i>,<j>,<crc32>,<name>
    if (proto::splitFields(args.substr(5), f, 4) == 4 && proto::parseInt(f[0], a) && proto::parseInt(f[1], b) &&
        a == gamesOf_ && gamesExpected_ > 0 && b == gameCount_ && parseItem(f[2], f[3], games_[b])) {
      ++gameCount_;
      if (gameCount_ == gamesExpected_) {
        gamesExpected_ = -1;
        if (active_ && level_ == Level::Games) requestCovers();
      }
      dirty_ = true;
    }
  }
}

bool SystemsScreen::makeSprites(Item& item, const Geometry& g) {
  for (LGFX_Sprite** p : {&item.cover, &item.dim}) {
    if (*p) continue;
    auto* sprite = new LGFX_Sprite();
    sprite->setColorDepth(16);
    sprite->setPsram(true);
    if (!sprite->createSprite(g.w, g.h)) {
      delete sprite;
      return false;
    }
    *p = sprite;
  }
  return true;
}

void SystemsScreen::setCover(Item& item, const Geometry& geo, uint32_t crc, bool png, const uint8_t* data,
                             size_t length) {
  if (!makeSprites(item, geo)) return;
  item.cover->fillScreen(TFT_BLACK);
  // Centred in the cover, whatever the picture's size.
  const bool ok = png ? item.cover->drawPng(data, length, 0, 0, geo.w, geo.h, 0, 0, geo.scale, geo.scale,
                                            lgfx::middle_center)
                      : item.cover->drawJpg(data, length, 0, 0, geo.w, geo.h, 0, 0, geo.scale, geo.scale,
                                            lgfx::middle_center);
  if (!ok) return;
  darken(*item.cover, *item.dim, geo.w * geo.h);
  item.haveCrc = crc;
  dirty_ = true;
}

void SystemsScreen::onCover(int system, int game, uint32_t crc, bool png, const uint8_t* data, size_t length) {
  const Level was = level_;
  if (game < 0 && system >= 0 && system < systemCount_) {
    level_ = Level::Systems;
    setCover(systems_[system], geometry(), crc, png, data, length);
  } else if (game >= 0 && system == gamesOf_ && game < gameCount_) {
    level_ = Level::Games;
    setCover(games_[game], geometry(), crc, png, data, length);
  }
  level_ = was;
}

void SystemsScreen::open(uint32_t nowMs) {
  if (systemCount_ == 0) return;
  active_ = true;
  closedByHost_ = false;
  down_ = false;
  playing_ = -1;
  level_ = Level::Systems;
  pos_ = systemPos_;
  if (pos_ > maxPos()) pos_ = maxPos();
  target_ = pos_ = roundf(pos_);
  lastTouchMs_ = nowMs;
  requestCovers();
  draw();
}

void SystemsScreen::openGames(int system) {
  if (system != gamesOf_) {
    // Another system: the covers we hold belong to the old one.
    for (Item& g : games_) {
      g.haveCrc = g.crc = 0;
      g.requested = false;
    }
    gamesOf_ = system;
  }
  gameCount_ = 0;
  gamesExpected_ = -2;
  char line[24];
  snprintf(line, sizeof(line), "MDSSYS,games,%d\n", system);
  transport_.write(line);
  systemPos_ = pos_;
  level_ = Level::Games;
  pos_ = target_ = 0;
  dirty_ = true;
}

void SystemsScreen::backToSystems() {
  level_ = Level::Systems;
  gamesExpected_ = -1;
  pos_ = target_ = systemPos_;
  dirty_ = true;
}

void SystemsScreen::requestCovers() {
  Item* list = items();
  for (int i = 0; i < count(); ++i) {
    Item& s = list[i];
    if (s.haveCrc == s.crc || s.requested || s.crc == 0) continue;
    char line[32];
    if (level_ == Level::Systems) {
      snprintf(line, sizeof(line), "MDSSYS,img,%d\n", i);
    } else {
      snprintf(line, sizeof(line), "MDSSYS,gimg,%d,%d\n", gamesOf_, i);
    }
    if (transport_.write(line)) s.requested = true;
  }
}

SystemsScreen::Result SystemsScreen::poll(uint32_t nowMs) {
  Result r;
  if (closedByHost_) {
    closedByHost_ = false;
    r.closed = true;
    return r;
  }
  if (!active_) return r;
  if (nowMs - lastPollMs_ >= kPollMs) {
    lastPollMs_ = nowMs;
    int x, y;
    if (display_.touched(&x, &y)) {
      r.activity = true;
      lastTouchMs_ = nowMs;
      if (!down_) {
        down_ = true;
        moved_ = false;
        downX_ = lastX_ = x;
        downY_ = y;
        downPos_ = pos_;
        velocity_ = 0;
        lastMoveMs_ = nowMs;
      }
      if (abs(x - downX_) > kTapSlop || abs(y - downY_) > kTapSlop) moved_ = true;
      if (moved_ && count() > 0) {
        const float step = geometry().nearX;
        float p = downPos_ - (x - downX_) / step;
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
        float t = roundf(pos_ - velocity_ * kFlingMs / geometry().nearX);
        const float from = roundf(downPos_);
        if (t > from + 2) t = from + 2;
        if (t < from - 2) t = from - 2;
        target_ = t < 0 ? 0 : t > maxPos() ? maxPos() : t;
      }
      if (!active_) {
        r.loading = playing_ >= 0;
        r.closed = !r.loading;
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
    if (level_ == Level::Games) {
      backToSystems();
    } else {
      active_ = false;
    }
    return;
  }
  // The front-most cover under the finger.
  const Geometry& geo = geometry();
  int best = -1;
  float bestDistance = 99;
  for (int i = 0; i < count(); ++i) {
    const float d = i - pos_, a = fabsf(d);
    if (a > kMaxDistance) continue;
    const float scale = a <= 1 ? 1 + (kNearScale - 1) * a : kNearScale + (kFarScale - kNearScale) * (a - 1 < 1 ? a - 1 : 1);
    const float squeeze = a <= 1 ? 1 + (kSqueeze - 1) * a : kSqueeze;
    const float cx = 160 + (d < 0 ? -1 : 1) * (a <= 1 ? a * geo.nearX : geo.nearX + (a - 1) * geo.farX);
    if (fabsf(x - cx) <= geo.w * scale * squeeze / 2 && fabsf(y - geo.centreY) <= geo.h * scale / 2 && a < bestDistance) {
      best = i;
      bestDistance = a;
    }
  }
  if (best < 0) return;
  if (best != static_cast<int>(roundf(pos_))) {
    target_ = best;
    return;
  }
  if (level_ == Level::Systems) {
    openGames(best);
    return;
  }
  char line[32];
  snprintf(line, sizeof(line), "MDSSYS,play,%d,%d\n", gamesOf_, best);
  transport_.write(line);
  playing_ = best;
  target_ = pos_ = best;
  draw();
  active_ = false;
}

void SystemsScreen::drawCover(const Item& item, float d) {
  auto& g = display_.canvas();
  const Geometry& geo = geometry();
  const float a = fabsf(d);
  float x, scale, squeeze;
  if (a <= 1) {
    x = 160 + (d < 0 ? -1 : 1) * a * geo.nearX;
    scale = 1 + (kNearScale - 1) * a;
    squeeze = 1 + (kSqueeze - 1) * a;
  } else {
    x = 160 + (d < 0 ? -1 : 1) * (geo.nearX + (a - 1) * geo.farX);
    scale = kNearScale + (kFarScale - kNearScale) * (a - 1 < 1 ? a - 1 : 1);
    squeeze = kSqueeze;
  }
  const float zoomX = scale * squeeze, zoomY = scale;
  const int w = lroundf(geo.w * zoomX), h = lroundf(geo.h * zoomY);
  const int x0 = lroundf(x) - w / 2, y0 = geo.centreY - h / 2;
  const bool front = a < 0.5f;
  if (item.haveCrc && item.cover) {
    LGFX_Sprite* sprite = front ? item.cover : item.dim;
    if (d == 0) {
      sprite->pushSprite(&g, x0, y0);
    } else {
      sprite->pushRotateZoom(&g, x, geo.centreY, 0, zoomX, zoomY);
    }
  } else {
    g.fillRect(x0, y0, w, h, kPlaceholder);
    if (front) {
      g.setTextColor(theme::kTextDim);
      drawFitted(g, item.name, lroundf(x), geo.centreY, w - 8);
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
  const Item* list = items();
  const int n = count();

  if (level_ == Level::Games) {
    g.setFont(&fonts::DejaVu12);
    g.setTextColor(theme::kTextDim);
    if (gamesOf_ >= 0 && gamesOf_ < systemCount_) g.drawString(systems_[gamesOf_].name, 160, 11);
    if (gamesExpected_ != -1 || n == 0) {
      g.setFont(&fonts::DejaVu18);
      g.drawString(gamesExpected_ != -1 ? "Loading..." : "No games", 160, 110);
      drawBack(g);
      display_.present();
      return;
    }
  }

  // Back to front: the farthest covers first, the middle one last.
  bool drawn[kMaxGames] = {};
  for (int k = 0; k < n; ++k) {
    int pick = -1;
    float far = -1;
    for (int i = 0; i < n; ++i) {
      const float a = fabsf(i - pos_);
      if (!drawn[i] && a > far) {
        far = a;
        pick = i;
      }
    }
    drawn[pick] = true;
    if (far <= kMaxDistance) drawCover(list[pick], pick - pos_);
  }

  int current = static_cast<int>(roundf(pos_));
  if (current < 0) current = 0;
  if (current > n - 1) current = n - 1;
  if (playing_ >= 0) {
    char text[56];
    snprintf(text, sizeof(text), "Starting %s", list[playing_].name);
    g.setTextColor(theme::kAccent);
    drawFitted(g, text, 160, kLabelY, 300);
  } else {
    g.setTextColor(theme::kText);
    drawFitted(g, list[current].name, 160, kLabelY, 300);
  }
  const int dotsX = 160 - (n - 1) * kDotGap / 2;
  for (int i = 0; i < n; ++i) {
    g.fillCircle(dotsX + i * kDotGap, kDotsY, 3, i == current ? theme::kAccent : kDotOff);
  }
  drawBack(g);
  display_.present();
}
