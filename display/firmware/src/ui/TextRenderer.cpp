#include "ui/TextRenderer.h"

#include <string.h>

namespace TextRenderer {

namespace {

constexpr int kGlyph = 8;  // Font8x8C64 cell
constexpr int kLineGap = 4;
constexpr size_t kMaxText = 63;

struct Line {
  char text[kMaxText + 1];
  size_t length;
};

void upperCopy(std::string_view in, Line& out, size_t maxLength) {
  out.length = in.size() < maxLength ? in.size() : maxLength;
  for (size_t i = 0; i < out.length; ++i) {
    const char c = in[i];
    out.text[i] = (c >= 'a' && c <= 'z') ? static_cast<char>(c - 'a' + 'A') : c;
  }
  out.text[out.length] = '\0';
}

// Splits at the last space that keeps the first line within `perLine`, else hard at `perLine`.
size_t splitPoint(std::string_view text, size_t perLine) {
  const size_t space = text.substr(0, perLine + 1).rfind(' ');
  return (space != std::string_view::npos && space > 0) ? space : perLine;
}

int drawLines(lgfx::LovyanGFX& g, const Line* lines, int count, int scale, const Box& box, uint16_t color) {
  g.setFont(&fonts::Font8x8C64);
  g.setTextSize(scale);
  g.setTextColor(color);
  g.setTextDatum(lgfx::top_center);
  const int lineHeight = kGlyph * scale;
  const int total = count * lineHeight + (count - 1) * kLineGap;
  int y = box.y + (box.h - total) / 2;
  for (int i = 0; i < count; ++i) {
    g.drawString(lines[i].text, box.x + box.w / 2, y);
    y += lineHeight + kLineGap;
  }
  g.setTextSize(1);
  return y - kLineGap;
}

bool tryOneLine(lgfx::LovyanGFX& g, std::string_view text, int scale, const Box& box, uint16_t color, int* bottom) {
  const size_t perLine = static_cast<size_t>(box.w / (kGlyph * scale));
  if (text.size() > perLine || kGlyph * scale > box.h) return false;
  Line line;
  upperCopy(text, line, perLine);
  *bottom = drawLines(g, &line, 1, scale, box, color);
  return true;
}

// Two lines; with wordsOnly the break must be at a space (no split inside a word).
bool tryTwoLines(lgfx::LovyanGFX& g, std::string_view text, int scale, bool wordsOnly, const Box& box,
                 uint16_t color, int* bottom) {
  const size_t perLine = static_cast<size_t>(box.w / (kGlyph * scale));
  if (2 * kGlyph * scale + kLineGap > box.h || text.size() > 2 * perLine + 1) return false;
  const size_t cut = splitPoint(text, perLine);
  const bool atSpace = cut < text.size() && text[cut] == ' ';
  if (wordsOnly && !atSpace) return false;
  std::string_view second = text.substr(cut);
  if (atSpace) second.remove_prefix(1);
  if (second.empty() || second.size() > perLine) return false;
  Line lines[2];
  upperCopy(text.substr(0, cut), lines[0], perLine);
  upperCopy(second, lines[1], perLine);
  *bottom = drawLines(g, lines, 2, scale, box, color);
  return true;
}

}  // namespace

int drawFittedC64(lgfx::LovyanGFX& g, std::string_view text, const Box& box, uint16_t color, int maxScale) {
  if (text.size() > kMaxText) text = text.substr(0, kMaxText);
  int bottom = box.y;
  // Largest first. Two lines at 3x read better than one line at 2x ("SUPER / NINTENDO").
  if (maxScale >= 4 && tryOneLine(g, text, 4, box, color, &bottom)) return bottom;
  if (maxScale >= 3 && tryOneLine(g, text, 3, box, color, &bottom)) return bottom;
  if (maxScale >= 3 && tryTwoLines(g, text, 3, true, box, color, &bottom)) return bottom;
  if (maxScale >= 2 && tryOneLine(g, text, 2, box, color, &bottom)) return bottom;
  if (maxScale >= 2 && tryTwoLines(g, text, 2, false, box, color, &bottom)) return bottom;
  if (tryTwoLines(g, text, 1, false, box, color, &bottom)) return bottom;

  // Still too long: one line at 1x, cut with "..".
  const size_t perLine = static_cast<size_t>(box.w / kGlyph);
  Line line;
  upperCopy(text, line, perLine);
  if (text.size() > perLine && perLine >= 2) {
    line.text[perLine - 2] = '.';
    line.text[perLine - 1] = '.';
  }
  return drawLines(g, &line, 1, 1, box, color);
}

}  // namespace TextRenderer
