#pragma once

#include <stdint.h>

// RGB565 colours. Dark panel look: black background, white text, one warm accent.
namespace theme {

constexpr uint16_t rgb565(uint8_t r, uint8_t g, uint8_t b) {
  return static_cast<uint16_t>(((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3));
}

constexpr uint16_t kBackground = rgb565(0, 0, 0);
constexpr uint16_t kText = rgb565(240, 240, 240);
constexpr uint16_t kTextDim = rgb565(120, 120, 120);
constexpr uint16_t kTextFaint = rgb565(70, 70, 70);
constexpr uint16_t kAccent = rgb565(255, 140, 26);
// Colour of the brightest grey level in tty2oled pictures (they are monochrome/greyscale).
constexpr uint16_t kArtwork = rgb565(255, 255, 255);

}  // namespace theme
