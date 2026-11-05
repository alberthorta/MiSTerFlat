#include "ui/WifiScreen.h"

#include <stdio.h>
#include <string.h>

#include "Command.h"
#include "ui/Theme.h"

namespace {

constexpr uint32_t kPollMs = 20;
constexpr int kDragSlop = 8;  // a touch that moves less than this is a tap
constexpr uint32_t kScanTimeoutMs = 45000;
constexpr uint32_t kJoinTimeoutMs = 60000;
constexpr uint32_t kDotsMs = 400;
constexpr size_t kMinPassword = 8;

constexpr int kHeaderH = 30;
constexpr int kHeaderButton = 44;
constexpr int kRowH = 40;

// Keyboard: 4 rows of 38 px keys (2 px gap) under the password field.
constexpr int kFieldTop = 36;
constexpr int kFieldH = 34;
constexpr int kKeysTop = 80;
constexpr int kKeyPitchY = 40;
constexpr int kKeyH = 38;
constexpr int kKeyW = 32;
constexpr int kWideKey = 48;   // shift, backspace
constexpr int kLayerKey = 64;  // abc / 123
constexpr int kOkKey = 96;

// Key codes returned by keyAt() (>= 0: a character).
constexpr int kNoKey = -1;
constexpr int kShift = -2;
constexpr int kBackspace = -3;
constexpr int kLayerSwitch = -4;
constexpr int kOk = -5;

// Letters, digits and symbols together cover every printable ASCII character.
const char* const kRows[4][3] = {
    {"qwertyuiop", "asdfghjkl", "zxcvbnm"},
    {"QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM"},
    {"1234567890", "-/:;()$&@", ".,?!'\"#"},
    {"[]{}#%^*+=", "_\\|~<>`!?", ".,'\"@$&"},
};

constexpr uint16_t kHeader = theme::rgb565(22, 22, 26);
constexpr uint16_t kKey = theme::rgb565(55, 55, 60);
constexpr uint16_t kKeySpecial = theme::rgb565(38, 38, 42);
constexpr uint16_t kLine = theme::rgb565(40, 40, 44);
constexpr uint16_t kGood = theme::rgb565(80, 200, 120);
constexpr uint16_t kBad = theme::rgb565(235, 70, 60);

int hexValue(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

void appendHex(char*& out, const uint8_t* data, size_t length) {
  static const char kDigits[] = "0123456789abcdef";
  for (size_t i = 0; i < length; ++i) {
    *out++ = kDigits[data[i] >> 4];
    *out++ = kDigits[data[i] & 0xF];
  }
}

// An SSID for the ASCII fonts: each UTF-8 sequence (or other non-ASCII byte) becomes one '?'.
void printable(const uint8_t* ssid, size_t length, char* out, size_t size) {
  size_t n = 0;
  for (size_t i = 0; i < length && n + 1 < size; ++i) {
    const uint8_t c = ssid[i];
    if (c >= 0x80 && c < 0xC0) continue;  // UTF-8 continuation byte
    out[n++] = c >= 0x20 && c < 0x7F ? static_cast<char>(c) : '?';
  }
  out[n] = '\0';
}

// Cuts text from the right with ".." until it fits.
void fit(lgfx::LovyanGFX& g, char* text, int width) {
  size_t n = strlen(text);
  if (g.textWidth(text) <= width) return;
  while (n > 2) {
    --n;
    text[n] = '\0';
    char buf[48];
    snprintf(buf, sizeof(buf), "%s..", text);
    if (g.textWidth(buf) <= width) {
      strcpy(text, buf);
      return;
    }
  }
}

void drawBars(lgfx::LovyanGFX& g, int x, int cy, int signal, uint16_t c, uint16_t off) {
  const int level = signal >= -55 ? 4 : signal >= -65 ? 3 : signal >= -75 ? 2 : 1;
  for (int i = 0; i < 4; ++i) {
    const int h = 4 + i * 3;
    g.fillRect(x + i * 5, cy + 6 - h, 3, h, i < level ? c : off);
  }
}

void drawLock(lgfx::LovyanGFX& g, int x, int cy, uint16_t c) {
  g.drawArc(x + 5, cy - 2, 4, 3, 180, 360, c);
  g.fillRoundRect(x, cy - 2, 11, 8, 2, c);
}

void drawClose(lgfx::LovyanGFX& g, int cx, int cy, uint16_t c) {
  g.drawWideLine(cx - 6, cy - 6, cx + 6, cy + 6, 1.2f, c);
  g.drawWideLine(cx - 6, cy + 6, cx + 6, cy - 6, 1.2f, c);
}

void drawRescan(lgfx::LovyanGFX& g, int cx, int cy, uint16_t c) {
  g.fillArc(cx, cy, 8, 6, 330, 360, c);
  g.fillArc(cx, cy, 8, 6, 0, 270, c);
  g.fillTriangle(cx - 1, cy - 12, cx - 1, cy - 3, cx + 5, cy - 7, c);
}

void drawBack(lgfx::LovyanGFX& g, int cx, int cy, uint16_t c) {
  g.drawWideLine(cx + 4, cy - 7, cx - 3, cy, 1.4f, c);
  g.drawWideLine(cx - 3, cy, cx + 4, cy + 7, 1.4f, c);
}

void drawButton(lgfx::LovyanGFX& g, int x, int y, int w, int h, const char* label, uint16_t face) {
  g.fillRoundRect(x, y, w, h, 8, face);
  g.setFont(&fonts::DejaVu18);
  g.setTextColor(theme::kText);
  g.setTextDatum(lgfx::middle_center);
  g.drawString(label, x + w / 2, y + h / 2);
}

// Buttons of the result screen: OK alone, or Back and Try again.
constexpr int kResultButtonY = 178;
constexpr int kResultButtonH = 40;

}  // namespace

void WifiScreen::open(uint32_t nowMs) {
  passwordLength_ = 0;
  password_[0] = '\0';
  scan(nowMs);
}

void WifiScreen::scan(uint32_t nowMs) {
  netCount_ = 0;
  scroll_ = 0;
  state_ = State::Scanning;
  stateMs_ = lastDotsMs_ = nowMs;
  transport_.write("MDSWIFI,scan\n");
  draw();
}

void WifiScreen::join(uint32_t nowMs) {
  const Net& n = nets_[selected_];
  // "MDSWIFI,join," + 64 + "," + 126 + "\n" fits the host's line reader.
  char line[220];
  char* p = line;
  p += snprintf(line, sizeof(line), "MDSWIFI,join,");
  appendHex(p, n.ssid, n.length);
  *p++ = ',';
  appendHex(p, reinterpret_cast<const uint8_t*>(password_), passwordLength_);
  *p++ = '\n';
  *p = '\0';
  transport_.write(line);
  state_ = State::Connecting;
  stateMs_ = lastDotsMs_ = nowMs;
  draw();
}

void WifiScreen::onHost(std::string_view args, uint32_t nowMs) {
  if (!active()) return;
  std::string_view f[6];
  const size_t n = proto::splitFields(args, f, 6);
  if (n == 0) return;
  if (f[0] == "scanning") {
    netCount_ = 0;
  } else if (f[0] == "net" && n == 5 && state_ == State::Scanning && netCount_ < kMaxNets) {
    int32_t signal, secure, linked;
    if (!proto::parseInt(f[1], signal) || !proto::parseInt(f[2], secure) || !proto::parseInt(f[3], linked)) return;
    Net& net = nets_[netCount_];
    size_t len = 0;
    for (size_t i = 0; i + 1 < f[4].size() && len < sizeof(net.ssid); i += 2) {
      const int hi = hexValue(f[4][i]), lo = hexValue(f[4][i + 1]);
      if (hi < 0 || lo < 0) return;
      net.ssid[len++] = static_cast<uint8_t>(hi << 4 | lo);
    }
    if (len == 0) return;
    net.length = static_cast<uint8_t>(len);
    net.signal = static_cast<int8_t>(signal < -127 ? -127 : signal > 0 ? 0 : signal);
    net.secure = secure != 0;
    net.linked = linked != 0;
    ++netCount_;
  } else if (f[0] == "end" && state_ == State::Scanning) {
    state_ = State::List;
    stateMs_ = nowMs;
    draw();
  } else if (f[0] == "status" && n >= 2 && state_ == State::Connecting) {
    if (f[1] == "connecting") return;
    joinOk_ = f[1] == "ok";
    const std::string_view text = n >= 3 ? f[2] : std::string_view();
    const size_t len = text.size() < sizeof(result_) - 1 ? text.size() : sizeof(result_) - 1;
    memcpy(result_, text.data(), len);
    result_[len] = '\0';
    state_ = State::Done;
    stateMs_ = nowMs;
    draw();
  }
}

WifiScreen::Result WifiScreen::poll(uint32_t nowMs) {
  Result r;
  if (!active()) return r;
  // Timeouts, and the dots of "Scanning..." / "Connecting...".
  if (state_ == State::Scanning && nowMs - stateMs_ >= kScanTimeoutMs) {
    state_ = State::List;
    draw();
  } else if (state_ == State::Connecting && nowMs - stateMs_ >= kJoinTimeoutMs) {
    joinOk_ = false;
    strcpy(result_, "no answer from the MiSTer");
    state_ = State::Done;
    draw();
  } else if ((state_ == State::Scanning || state_ == State::Connecting) && nowMs - lastDotsMs_ >= kDotsMs) {
    lastDotsMs_ = nowMs;
    draw();
  }

  if (nowMs - lastPollMs_ < kPollMs) return r;
  lastPollMs_ = nowMs;
  int x, y;
  if (display_.touched(&x, &y)) {
    r.activity = true;
    if (!down_) {
      down_ = true;
      moved_ = false;
      downX_ = x;
      downY_ = y;
      downScroll_ = scroll_;
    }
    lastX_ = x;
    lastY_ = y;
    if (abs(y - downY_) > kDragSlop || abs(x - downX_) > kDragSlop) moved_ = true;
    if (state_ == State::List && moved_) {
      int s = downScroll_ - (y - downY_);
      s = s < 0 ? 0 : s > maxScroll() ? maxScroll() : s;
      if (s != scroll_) {
        scroll_ = s;
        draw();
      }
    } else if (state_ == State::Keyboard) {
      char c;
      const int key = keyAt(x, y, &c);
      const int held = key == kNoKey ? -1 : key >= 0 ? static_cast<uint8_t>(c) : 256 - key;
      if (held != heldKey_) {
        heldKey_ = held;
        draw();
      }
    }
    return r;
  }
  if (!down_) return r;
  down_ = false;
  r.activity = true;
  const bool wasHeld = heldKey_ != -1;
  heldKey_ = -1;
  if (!moved_ || (state_ == State::Keyboard && wasHeld)) tap(lastX_, lastY_, nowMs);
  else if (wasHeld) draw();
  r.closed = !active();
  return r;
}

void WifiScreen::tap(int x, int y, uint32_t nowMs) {
  const int w = display_.width();
  // Header buttons: close on the right, rescan (list) next to it, back (keyboard) on the left.
  if (y < kHeaderH && state_ != State::Connecting) {
    if (x >= w - kHeaderButton) {
      close();
      return;
    }
    if (state_ == State::List && x >= w - 2 * kHeaderButton) {
      scan(nowMs);
      return;
    }
    if (state_ == State::Keyboard && x < kHeaderButton) {
      state_ = State::List;
      draw();
      return;
    }
  }
  switch (state_) {
    case State::List: tapList(x, y, nowMs); break;
    case State::Keyboard: tapKeyboard(x, y, nowMs); break;
    case State::Done: tapDone(x, y, nowMs); break;
    default: break;
  }
}

void WifiScreen::tapList(int, int y, uint32_t nowMs) {
  if (y < kHeaderH) return;
  const int i = (y - kHeaderH + scroll_) / kRowH;
  if (i < 0 || i >= netCount_) return;
  selected_ = i;
  passwordLength_ = 0;
  password_[0] = '\0';
  layer_ = kLower;
  if (!nets_[i].secure) {
    join(nowMs);
    return;
  }
  state_ = State::Keyboard;
  draw();
}

void WifiScreen::tapKeyboard(int x, int y, uint32_t nowMs) {
  char c;
  const int key = keyAt(x, y, &c);
  if (key >= 0) {
    if (passwordLength_ < kMaxPassword) {
      password_[passwordLength_++] = c;
      password_[passwordLength_] = '\0';
    }
  } else if (key == kBackspace) {
    if (passwordLength_ > 0) password_[--passwordLength_] = '\0';
  } else if (key == kShift) {
    layer_ = layer_ == kLower ? kUpper : layer_ == kUpper ? kLower : layer_ == kDigits ? kSymbols : kDigits;
  } else if (key == kLayerSwitch) {
    layer_ = layer_ == kLower || layer_ == kUpper ? kDigits : kLower;
  } else if (key == kOk && passwordLength_ >= kMinPassword) {
    join(nowMs);
    return;
  }
  draw();
}

void WifiScreen::tapDone(int x, int y, uint32_t nowMs) {
  if (y < kResultButtonY || y > kResultButtonY + kResultButtonH) return;
  const int w = display_.width();
  if (joinOk_) {
    close();
    return;
  }
  if (x < w / 2) {
    state_ = State::List;  // Back
    draw();
  } else {
    state_ = State::Keyboard;  // Try again, with what was typed
    (void)nowMs;
    draw();
  }
}

int WifiScreen::keyAt(int x, int y, char* out) const {
  if (y < kKeysTop) return kNoKey;
  const int row = (y - kKeysTop) / kKeyPitchY;
  const char* const* rows = kRows[layer_];
  switch (row) {
    case 0: {
      const int i = x / kKeyW;
      if (i < 0 || i >= 10) return kNoKey;
      *out = rows[0][i];
      return static_cast<uint8_t>(*out);
    }
    case 1: {
      const int i = (x - kKeyW / 2) / kKeyW;
      if (x < kKeyW / 2 || i >= 9) return kNoKey;
      *out = rows[1][i];
      return static_cast<uint8_t>(*out);
    }
    case 2: {
      if (x < kWideKey) return kShift;
      if (x >= kWideKey + 7 * kKeyW) return kBackspace;
      *out = rows[2][(x - kWideKey) / kKeyW];
      return static_cast<uint8_t>(*out);
    }
    case 3:
      if (x < kLayerKey) return kLayerSwitch;
      if (x >= display_.width() - kOkKey) return kOk;
      *out = ' ';
      return ' ';
    default:
      return kNoKey;
  }
}

int WifiScreen::maxScroll() const {
  const int content = netCount_ * kRowH;
  const int view = display_.height() - kHeaderH;
  return content > view ? content - view : 0;
}

void WifiScreen::draw() {
  switch (state_) {
    case State::Scanning: {
      char dots[16];
      snprintf(dots, sizeof(dots), "Scanning%.*s", static_cast<int>((lastDotsMs_ / kDotsMs) % 4), "...");
      drawMessage(dots, "Looking for Wi-Fi networks", "about 12 seconds");
      break;
    }
    case State::List: drawList(); break;
    case State::Keyboard: drawKeyboard(); break;
    case State::Connecting: {
      char title[16], name[40];
      snprintf(title, sizeof(title), "Connecting%.*s", static_cast<int>((lastDotsMs_ / kDotsMs) % 4), "...");
      printable(nets_[selected_].ssid, nets_[selected_].length, name, sizeof(name));
      drawMessage(title, name, "this can take 30 seconds");
      break;
    }
    case State::Done: drawDone(); break;
    default: break;
  }
}

void WifiScreen::drawHeader(const char* title, bool back, bool rescan) {
  auto& g = display_.canvas();
  const int w = display_.width();
  g.fillRect(0, 0, w, kHeaderH, kHeader);
  g.setFont(&fonts::DejaVu18);
  g.setTextColor(theme::kText);
  g.setTextDatum(lgfx::middle_left);
  char text[48];
  snprintf(text, sizeof(text), "%s", title);
  fit(g, text, w - (back ? kHeaderButton : 12) - 2 * kHeaderButton);
  g.drawString(text, back ? kHeaderButton : 12, kHeaderH / 2);
  if (back) drawBack(g, kHeaderButton / 2, kHeaderH / 2, theme::kText);
  if (rescan) drawRescan(g, w - kHeaderButton - kHeaderButton / 2, kHeaderH / 2, theme::kText);
  drawClose(g, w - kHeaderButton / 2, kHeaderH / 2, theme::kText);
}

void WifiScreen::drawMessage(const char* line1, const char* line2, const char* line3) {
  auto& g = display_.canvas();
  const int w = display_.width();
  const int h = display_.height();
  g.fillScreen(theme::kBackground);
  drawHeader("Wi-Fi", false, false);
  g.setTextDatum(lgfx::middle_center);
  g.setFont(&fonts::DejaVu24);
  g.setTextColor(theme::kText);
  g.drawString(line1, w / 2, h / 2 - 14);
  g.setFont(&fonts::DejaVu12);
  g.setTextColor(theme::kTextDim);
  g.drawString(line2, w / 2, h / 2 + 18);
  g.drawString(line3, w / 2, h / 2 + 36);
  display_.present();
}

void WifiScreen::drawList() {
  auto& g = display_.canvas();
  const int w = display_.width();
  const int h = display_.height();
  g.fillScreen(theme::kBackground);
  if (netCount_ == 0) {
    drawHeader("Wi-Fi", false, true);
    g.setTextDatum(lgfx::middle_center);
    g.setFont(&fonts::DejaVu18);
    g.setTextColor(theme::kTextDim);
    g.drawString("No networks found", w / 2, h / 2);
    display_.present();
    return;
  }
  g.setClipRect(0, kHeaderH, w, h - kHeaderH);
  g.setFont(&fonts::DejaVu18);
  g.setTextDatum(lgfx::middle_left);
  for (int i = 0; i < netCount_; ++i) {
    const int top = kHeaderH + i * kRowH - scroll_;
    if (top + kRowH < kHeaderH || top > h) continue;
    const Net& n = nets_[i];
    const int cy = top + kRowH / 2;
    const uint16_t c = n.linked ? theme::kAccent : theme::kText;
    drawBars(g, 12, cy, n.signal, c, theme::kTextFaint);
    char name[40];
    printable(n.ssid, n.length, name, sizeof(name));
    fit(g, name, w - 44 - 36);
    g.setTextColor(c);
    g.drawString(name, 40, cy);
    if (n.secure) drawLock(g, w - 26, cy, theme::kTextDim);
    g.drawFastHLine(12, top + kRowH - 1, w - 24, kLine);
  }
  g.clearClipRect();
  // Scroll position, when the list is longer than the screen.
  const int max = maxScroll();
  if (max > 0) {
    const int view = h - kHeaderH;
    const int bar = view * view / (view + max);
    g.fillRoundRect(w - 4, kHeaderH + (view - bar) * scroll_ / max, 3, bar, 1, theme::kTextFaint);
  }
  drawHeader("Wi-Fi", false, true);
  display_.present();
}

void WifiScreen::drawKeyboard() {
  auto& g = display_.canvas();
  const int w = display_.width();
  g.fillScreen(theme::kBackground);
  char name[40];
  printable(nets_[selected_].ssid, nets_[selected_].length, name, sizeof(name));
  drawHeader(name, true, false);

  // Password field: shown as typed (the screen is small and typos are easy); the end stays visible.
  g.drawRoundRect(8, kFieldTop, w - 16, kFieldH, 6, theme::kTextFaint);
  g.setFont(&fonts::DejaVu18);
  g.setTextDatum(lgfx::middle_left);
  const char* shown = password_;
  while (*shown && g.textWidth(shown) > w - 40) ++shown;
  if (passwordLength_ == 0) {
    g.setTextColor(theme::kTextFaint);
    g.drawString("Password", 18, kFieldTop + kFieldH / 2);
  } else {
    g.setTextColor(theme::kText);
    g.drawString(shown, 18, kFieldTop + kFieldH / 2);
  }
  const int caretX = 18 + (passwordLength_ ? g.textWidth(shown) : 0) + 1;
  g.fillRect(caretX, kFieldTop + 8, 2, kFieldH - 16, theme::kAccent);

  auto key = [&](int x, int y, int kw, const char* label, int code, uint16_t face, bool small) {
    const bool held = heldKey_ == (code >= 0 ? code : 256 - code);
    g.fillRoundRect(x + 1, y + 1, kw - 2, kKeyH - 2, 5, held ? theme::kAccent : face);
    g.setFont(small ? &fonts::DejaVu12 : &fonts::DejaVu18);
    g.setTextColor(theme::kText);
    g.setTextDatum(lgfx::middle_center);
    g.drawString(label, x + kw / 2, y + kKeyH / 2);
  };
  const char* const* rows = kRows[layer_];
  char label[2] = {};
  for (int i = 0; i < 10; ++i) {
    label[0] = rows[0][i];
    key(i * kKeyW, kKeysTop, kKeyW, label, static_cast<uint8_t>(label[0]), kKey, false);
  }
  for (int i = 0; i < 9; ++i) {
    label[0] = rows[1][i];
    key(kKeyW / 2 + i * kKeyW, kKeysTop + kKeyPitchY, kKeyW, label, static_cast<uint8_t>(label[0]), kKey, false);
  }
  const int y2 = kKeysTop + 2 * kKeyPitchY;
  // Shift shows the layer it switches to.
  const char* shiftLabel = layer_ == kLower ? "ABC" : layer_ == kUpper ? "abc" : layer_ == kDigits ? "#+=" : "123";
  key(0, y2, kWideKey, shiftLabel, kShift, kKeySpecial, true);
  for (int i = 0; i < 7; ++i) {
    label[0] = rows[2][i];
    key(kWideKey + i * kKeyW, y2, kKeyW, label, static_cast<uint8_t>(label[0]), kKey, false);
  }
  key(kWideKey + 7 * kKeyW, y2, kWideKey, "DEL", kBackspace, kKeySpecial, true);
  const int y3 = kKeysTop + 3 * kKeyPitchY;
  key(0, y3, kLayerKey, layer_ == kLower || layer_ == kUpper ? "123" : "abc", kLayerSwitch, kKeySpecial, true);
  key(kLayerKey, y3, w - kLayerKey - kOkKey, "space", ' ', kKey, true);
  const bool ready = passwordLength_ >= kMinPassword;
  key(w - kOkKey, y3, kOkKey, "Connect", kOk, ready ? theme::kAccent : kKeySpecial, true);
  display_.present();
}

void WifiScreen::drawDone() {
  auto& g = display_.canvas();
  const int w = display_.width();
  g.fillScreen(theme::kBackground);
  drawHeader("Wi-Fi", false, false);
  char name[40];
  printable(nets_[selected_].ssid, nets_[selected_].length, name, sizeof(name));
  g.setTextDatum(lgfx::middle_center);
  g.setFont(&fonts::DejaVu24);
  g.setTextColor(joinOk_ ? kGood : kBad);
  g.drawString(joinOk_ ? "Connected" : "Could not connect", w / 2, 76);
  g.setFont(&fonts::DejaVu18);
  g.setTextColor(theme::kText);
  g.drawString(name, w / 2, 112);
  g.setFont(&fonts::DejaVu12);
  g.setTextColor(theme::kTextDim);
  g.drawString(result_, w / 2, 140);
  if (joinOk_) {
    drawButton(g, (w - 120) / 2, kResultButtonY, 120, kResultButtonH, "OK", kKey);
  } else {
    drawButton(g, 16, kResultButtonY, w / 2 - 24, kResultButtonH, "Back", kKey);
    drawButton(g, w / 2 + 8, kResultButtonY, w / 2 - 24, kResultButtonH, "Try again", theme::kAccent);
  }
  display_.present();
}
