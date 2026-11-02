#include "ui/SplashScreen.h"

#include "config.h"
#include "ui/Theme.h"

namespace SplashScreen {

namespace {

// The hint uses an anti-aliased font (a scaled bitmap font looked blocky). It fills most of the
// line below the logo, so the version moved to the top-right corner, which the logo area leaves free.
constexpr int kHintY = 140;
constexpr int kTallHintY = 210;  // on 240 lines: centred in the 56 lines under the logo area

bool drawLogo(lgfx::LovyanGFX& g, int w, int top, int h, const Logo& logo) {
  if (!logo.data || logo.size == 0) return false;
  // The datum centres the picture in the (0, top, w, h) box; larger ones are cropped.
  return logo.png ? g.drawPng(logo.data, logo.size, 0, top, w, h, 0, 0, 1.0f, 0.0f, lgfx::middle_center)
                  : g.drawJpg(logo.data, logo.size, 0, top, w, h, 0, 0, 1.0f, 0.0f, lgfx::middle_center);
}

void drawTextTitle(lgfx::LovyanGFX& g, int w, int top) {
  g.setTextDatum(lgfx::middle_center);
  g.setTextColor(theme::kText);
  g.setFont(&fonts::FreeSansBold24pt7b);
  g.drawString("MiSTer", w / 2, top + 62);

  g.fillRect(w / 2 - 50, top + 92, 100, 3, theme::kAccent);

  g.setTextColor(theme::kTextDim);
  g.setFont(&fonts::FreeSans12pt7b);
  g.drawString(MDS_BOARD_NAME, w / 2, top + 118);
}

}  // namespace

void draw(DisplayManager& display, const char* version, const char* hint, const Logo* logo) {
  auto& g = display.canvas();
  const int w = display.width();
  const bool tall = display.height() >= kTallScreenHeight;
  const int top = tall ? 0 : display.layoutTop();
  const int areaHeight = tall ? kTallLogoAreaHeight : kLogoAreaHeight;

  g.fillScreen(theme::kBackground);
  g.setTextSize(1);
  if (!logo || !drawLogo(g, w, top, areaHeight, *logo)) {
    g.fillScreen(theme::kBackground);  // a failed decode may have drawn part of the picture
    drawTextTitle(g, w, top + (areaHeight - kLogoAreaHeight) / 2);
  }

  g.setTextDatum(lgfx::top_right);
  g.setTextColor(theme::kTextFaint);
  g.setFont(&fonts::Font2);
  g.drawString(version, w - 4, 2);

  if (hint) {
    g.setTextDatum(lgfx::middle_center);
    g.setTextColor(theme::kAccent, theme::kBackground);
    g.setFont(&fonts::DejaVu24);
    g.drawString(hint, w / 2, tall ? kTallHintY : top + kHintY);
  }

  display.present();
}

}  // namespace SplashScreen
