#include "ui/CoreScreen.h"

#include "CoreNames.h"
#include "ui/LegacyAssetRenderer.h"
#include "ui/TextRenderer.h"
#include "ui/Theme.h"

namespace CoreScreen {

namespace {

constexpr int kMargin = 12;
constexpr int kNameTop = 30;
constexpr int kNameHeight = 80;
constexpr int kAccentWidth = 64;
constexpr int kAccentHeight = 3;
constexpr int kAccentGap = 10;

// tty2oled pictures are 256x64 (4:1). Scaled to the full screen width (1.25x, 320x80) and
// centered vertically; the logo carries the name, so no text is drawn.
constexpr int kArtWidth = 320;
constexpr int kArtHeight = 80;

bool sameIgnoringCase(std::string_view a, std::string_view b) {
  if (a.size() != b.size()) return false;
  for (size_t i = 0; i < a.size(); ++i) {
    char x = a[i], y = b[i];
    if (x >= 'a' && x <= 'z') x = static_cast<char>(x - 'a' + 'A');
    if (y >= 'a' && y <= 'z') y = static_cast<char>(y - 'a' + 'A');
    if (x != y) return false;
  }
  return true;
}

// The real core name, small, when the big name is a different (friendly) one.
void drawCoreNameFootnote(lgfx::LovyanGFX& g, std::string_view name, std::string_view coreName, int w, int h) {
  if (sameIgnoringCase(name, coreName)) return;
  // drawString needs a terminated string; core names are short.
  char raw[64];
  const size_t n = coreName.size() < sizeof(raw) - 1 ? coreName.size() : sizeof(raw) - 1;
  for (size_t i = 0; i < n; ++i) raw[i] = coreName[i];
  raw[n] = '\0';
  g.setFont(&fonts::Font2);
  g.setTextSize(1);
  g.setTextColor(theme::kTextFaint);
  g.setTextDatum(lgfx::bottom_center);
  g.drawString(raw, w / 2, h - 6);
}

}  // namespace

void drawNameOnly(DisplayManager& display, std::string_view coreName) {
  auto& g = display.canvas();
  const int w = display.width();
  const int h = display.height();
  g.fillScreen(theme::kBackground);

  const std::string_view name = coreinfo::displayName(coreName);
  const TextRenderer::Box box{kMargin, display.layoutTop() + kNameTop, w - 2 * kMargin, kNameHeight};
  const int bottom = TextRenderer::drawFittedC64(g, name, box, theme::kText);

  const int accentY = bottom + kAccentGap;
  g.fillRect((w - kAccentWidth) / 2, accentY, kAccentWidth, kAccentHeight, theme::kAccent);

  drawCoreNameFootnote(g, name, coreName, w, h);
  display.present();
}

void drawWithArtwork(DisplayManager& display, std::string_view coreName, proto::ImageFormat format,
                     const uint8_t* data, size_t length) {
  auto& g = display.canvas();
  const int w = display.width();
  const int h = display.height();
  g.fillScreen(theme::kBackground);

  if (!LegacyAssetRenderer::draw(g, format, data, length, (w - kArtWidth) / 2, (h - kArtHeight) / 2, kArtWidth,
                                 kArtHeight, theme::kArtwork, theme::kBackground)) {
    drawNameOnly(display, coreName);
    return;
  }
  display.present();
}

bool drawAsset(DisplayManager& display, AssetFormat format, const uint8_t* data, size_t length) {
  auto& g = display.canvas();
  const int w = display.width();
  const int h = display.height();
  g.fillScreen(theme::kBackground);
  // The datum places the picture inside the (0, 0, w, h) box: middle_center centers it.
  const bool ok = format == AssetFormat::Png
                      ? g.drawPng(data, length, 0, 0, w, h, 0, 0, 1.0f, 0.0f, lgfx::middle_center)
                      : g.drawJpg(data, length, 0, 0, w, h, 0, 0, 1.0f, 0.0f, lgfx::middle_center);
  if (ok) display.present();
  return ok;
}

}  // namespace CoreScreen
