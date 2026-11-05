#pragma once

#include <stddef.h>
#include <stdint.h>

#include "ProtocolParser.h"
#include "hal/Lgfx.h"

// Draws a tty2oled picture (256x64, XBM or GSC) resampled to width x height (see
// legacyart::resample). Intensity is blended from `background` to `foreground`, so a tint
// colour also works.
namespace LegacyAssetRenderer {

// False (and nothing drawn) if the format/length pair is not a valid picture or the size is
// not supported.
bool draw(lgfx::LovyanGFX& g, proto::ImageFormat format, const uint8_t* data, size_t length, int x, int y,
          int width, int height, uint16_t foreground, uint16_t background);

}  // namespace LegacyAssetRenderer
