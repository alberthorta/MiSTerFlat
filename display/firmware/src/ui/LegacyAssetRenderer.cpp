#include "ui/LegacyAssetRenderer.h"

#include <esp_heap_caps.h>

#include "LegacyArt.h"
#include "config.h"

namespace LegacyAssetRenderer {

namespace {

constexpr size_t kMaxPixels = static_cast<size_t>(cfg::kScreenWidth) * cfg::kScreenHeight;

uint16_t blend565(uint16_t from, uint16_t to, int amount /* 0..255 */) {
  const int r0 = (from >> 11) & 0x1F, g0 = (from >> 5) & 0x3F, b0 = from & 0x1F;
  const int r1 = (to >> 11) & 0x1F, g1 = (to >> 5) & 0x3F, b1 = to & 0x1F;
  const int r = r0 + ((r1 - r0) * amount + 127) / 255;
  const int g = g0 + ((g1 - g0) * amount + 127) / 255;
  const int b = b0 + ((b1 - b0) * amount + 127) / 255;
  return static_cast<uint16_t>((r << 11) | (g << 5) | b);
}

// Intensity buffer for one resampled picture, in PSRAM, allocated on first use.
uint8_t* intensityBuffer() {
  static uint8_t* buffer = static_cast<uint8_t*>(heap_caps_malloc(kMaxPixels, MALLOC_CAP_SPIRAM));
  return buffer;
}

}  // namespace

bool draw(lgfx::LovyanGFX& g, proto::ImageFormat format, const uint8_t* data, size_t length, int x, int y,
          int width, int height, uint16_t foreground, uint16_t background) {
  if (format == proto::ImageFormat::None) return false;
  if (width <= 0 || height <= 0 || static_cast<size_t>(width) * height > kMaxPixels) return false;
  uint8_t* levels = intensityBuffer();
  if (!levels) return false;
  const legacyart::Format f = format == proto::ImageFormat::Xbm ? legacyart::Format::Xbm : legacyart::Format::Gsc;
  if (!legacyart::resample(f, data, length, width, height, levels)) return false;

  uint16_t palette[256];
  for (int i = 0; i < 256; ++i) palette[i] = blend565(background, foreground, i);

  g.startWrite();
  for (int row = 0; row < height; ++row) {
    const uint8_t* src = levels + row * width;
    for (int col = 0; col < width; ++col) g.writePixel(x + col, y + row, palette[src[col]]);
  }
  g.endWrite();
  return true;
}

}  // namespace LegacyAssetRenderer
