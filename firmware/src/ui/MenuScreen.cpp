#include "ui/MenuScreen.h"

#include <stdio.h>
#include <string.h>

#include <string_view>

#include "config.h"
#include "ui/Theme.h"

namespace MenuScreen {

namespace {

const char* const kWeekdays[] = {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"};
const char* const kMonths[] = {"Jan", "Feb", "Mar", "Apr", "May", "Jun",
                               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"};

// The screen is a column, centred vertically: title, time, date, then one line per network.
// Heights are those of the fonts; the gaps shrink when the column does not fit (two networks on
// the 170-pixel T-Display-S3).
constexpr int kTitleScale = 2;  // retro 8x8 font
constexpr int kTimeScale = 7;   // 56 px digits, "HH:MM" 280 px wide
constexpr int kNetScale = 2;
constexpr int kTitleH = 8 * kTitleScale;
constexpr int kTimeH = 8 * kTimeScale;
constexpr int kDateH = 18;
constexpr int kNetH = 8 * kNetScale;
constexpr int kGapTitle = 14;  // below the title
constexpr int kGapTime = 16;   // below the time
constexpr int kGapDate = 24;   // below the date
constexpr int kGapNet = 8;     // between network lines
constexpr int kMargin = 4;     // kept free at the top and bottom
constexpr int kIconWidth = 18;
constexpr int kIconGap = 8;

// MDSNET text: "eth=<ip> wifi=<ip>" from our daemon, one or both, or a bare address from an older
// daemon (no icon then). Ethernet comes first.
enum class NetKind : uint8_t { Unknown, Ethernet, WiFi };
struct NetEntry {
  NetKind kind;
  char ip[24];
};
constexpr int kMaxEntries = 2;

int parseNet(std::string_view text, NetEntry* out) {
  int n = 0;
  while (!text.empty() && n < kMaxEntries) {
    const size_t space = text.find(' ');
    std::string_view token = text.substr(0, space);
    text = space == std::string_view::npos ? std::string_view() : text.substr(space + 1);
    if (token.empty()) continue;
    NetKind kind = NetKind::Unknown;
    if (token.substr(0, 4) == "eth=") {
      kind = NetKind::Ethernet;
      token = token.substr(4);
    } else if (token.substr(0, 5) == "wifi=") {
      kind = NetKind::WiFi;
      token = token.substr(5);
    }
    NetEntry& e = out[n++];
    e.kind = kind;
    const size_t len = token.size() < sizeof(e.ip) - 1 ? token.size() : sizeof(e.ip) - 1;
    memcpy(e.ip, token.data(), len);
    e.ip[len] = '\0';
  }
  if (n == 2 && out[1].kind == NetKind::Ethernet) {
    const NetEntry first = out[0];
    out[0] = out[1];
    out[1] = first;
  }
  return n;
}

// Icons about 16 px high, in an 18 px wide box starting at x, centred on y.
void drawEthernet(lgfx::LovyanGFX& g, int x, int y, uint16_t c) {
  // An RJ45 socket seen from the front: the body, four contacts and the latch slot below.
  g.drawRect(x + 1, y - 7, 16, 11, c);
  g.drawRect(x + 2, y - 6, 14, 9, c);
  for (int k = 0; k < 4; ++k) g.fillRect(x + 5 + k * 2, y - 4, 1, 4, c);
  g.fillRect(x + 6, y + 4, 6, 4, c);
}

void drawWiFi(lgfx::LovyanGFX& g, int x, int y, uint16_t c) {
  const int cx = x + 9;
  const int cy = y + 7;
  g.fillCircle(cx, cy - 2, 2, c);
  g.fillArc(cx, cy, 8, 6, 225, 315, c);
  g.fillArc(cx, cy, 13, 11, 225, 315, c);
}

}  // namespace

void draw(DisplayManager& display, const wallclock::DateTime& t, const char* ip, bool dimmed) {
  auto& g = display.canvas();
  const int w = display.width();
  const int h = display.height();
  const uint16_t timeColor = dimmed ? theme::rgb565(90, 90, 90) : theme::kText;
  const uint16_t accent = dimmed ? theme::rgb565(90, 50, 10) : theme::kAccent;
  const uint16_t dim = dimmed ? theme::rgb565(55, 55, 55) : theme::kTextDim;

  NetEntry nets[kMaxEntries];
  const int n = ip ? parseNet(ip, nets) : 0;

  // Column height, gaps shrunk if needed.
  const int heights = kTitleH + kTimeH + kDateH + n * kNetH;
  int gaps[3 + kMaxEntries] = {kGapTitle, kGapTime, n ? kGapDate : 0, kGapNet, 0};
  int gapSum = gaps[0] + gaps[1] + gaps[2] + (n > 1 ? gaps[3] : 0);
  const int room = h - 2 * kMargin - heights;
  if (gapSum > room && gapSum > 0) {
    for (int& gap : gaps) gap = gap * (room > 0 ? room : 0) / gapSum;
    gapSum = gaps[0] + gaps[1] + gaps[2] + (n > 1 ? gaps[3] : 0);
  }
  int y = (h - heights - gapSum) / 2;

  g.fillScreen(theme::kBackground);
  g.setTextDatum(lgfx::middle_center);

  g.setFont(&fonts::Font8x8C64);
  g.setTextSize(kTitleScale);
  g.setTextColor(accent);
  g.drawString("MiSTer", w / 2, y + kTitleH / 2);
  y += kTitleH + gaps[0];

  char buf[32];
  snprintf(buf, sizeof(buf), "%02d:%02d", t.hour, t.minute);
  g.setTextSize(kTimeScale);
  g.setTextColor(timeColor);
  g.drawString(buf, w / 2, y + kTimeH / 2);
  y += kTimeH + gaps[1];

  const int wd = (t.weekday >= 0 && t.weekday < 7) ? t.weekday : 0;
  const int mo = (t.month >= 1 && t.month <= 12) ? t.month - 1 : 0;
  snprintf(buf, sizeof(buf), "%s %d %s %d", kWeekdays[wd], t.day, kMonths[mo], t.year);
  g.setFont(&fonts::DejaVu18);
  g.setTextSize(1);
  g.setTextColor(dim);
  g.drawString(buf, w / 2, y + kDateH / 2);
  y += kDateH + gaps[2];

  // Networks: one per line, icons in one column, the block centred on the widest line.
  g.setFont(&fonts::Font8x8C64);
  g.setTextSize(kNetScale);
  g.setTextColor(dim);
  int widest = 0;
  for (int i = 0; i < n; ++i) {
    const int lw = (nets[i].kind == NetKind::Unknown ? 0 : kIconWidth + kIconGap) + g.textWidth(nets[i].ip);
    if (lw > widest) widest = lw;
  }
  const bool anyIcon = n > 0 && (nets[0].kind != NetKind::Unknown || (n > 1 && nets[1].kind != NetKind::Unknown));
  const int x0 = (w - widest) / 2;
  g.setTextDatum(lgfx::middle_left);
  for (int i = 0; i < n; ++i) {
    const int cy = y + kNetH / 2;
    int x = x0;
    if (nets[i].kind == NetKind::Ethernet) drawEthernet(g, x, cy, dim);
    if (nets[i].kind == NetKind::WiFi) drawWiFi(g, x, cy, dim);
    if (anyIcon) x += kIconWidth + kIconGap;
    g.drawString(nets[i].ip, x, cy);
    y += kNetH + gaps[3];
  }
  // The firmware version, small in the top-right corner, as on the start screen.
  g.setFont(&fonts::Font2);
  g.setTextSize(1);
  g.setTextDatum(lgfx::top_right);
  g.setTextColor(dimmed ? theme::rgb565(35, 35, 35) : theme::kTextFaint);
  g.drawString("v" MDS_FW_VERSION, w - 4, 2);
  g.setTextDatum(lgfx::middle_center);
  display.present();
}

}  // namespace MenuScreen
