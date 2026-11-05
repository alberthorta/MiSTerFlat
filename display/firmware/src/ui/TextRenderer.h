#pragma once

#include <stdint.h>

#include <string_view>

#include "hal/Lgfx.h"

namespace TextRenderer {

struct Box {
  int x, y, w, h;
};

// Draws `text` upper-cased in the Commodore 64 font (what tty2oled uses for core names), as
// large as fits in `box`: one line at 4x, 3x or 2x, else two lines at 2x or 1x, else truncated.
// Integer scales only, so the pixels stay sharp; `maxScale` caps the size. Returns the bottom y
// of the drawn text.
int drawFittedC64(lgfx::LovyanGFX& g, std::string_view text, const Box& box, uint16_t color, int maxScale = 4);

}  // namespace TextRenderer
