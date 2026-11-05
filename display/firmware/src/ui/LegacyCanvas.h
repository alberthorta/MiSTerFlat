#pragma once

#include <stdint.h>

#include <string_view>

#include "ui/DisplayManager.h"

// Drawing commands written for the 256x64 tty2oled OLED (CMDTXT, CMDGEO, CMDCLST). They draw
// into a 256x64 viewport centered on our 320x170 panel, 1:1, so existing scripts keep their
// layout. Grey levels 0..15 become grey RGB565.
namespace LegacyCanvas {

constexpr int kWidth = 256;
constexpr int kHeight = 64;

int originX(const DisplayManager& display);
int originY(const DisplayManager& display);
uint16_t grey(int level);

// Each returns false for bad parameters (the caller shows the parameter error screen).
// *present tells whether the sketch would update the display now (false in "buffer mode",
// font or figure number >= 100).
bool text(DisplayManager& display, std::string_view args, bool* present);
bool geometry(DisplayManager& display, std::string_view args, bool* present);

void parameterError(DisplayManager& display, std::string_view line);
void testPattern(DisplayManager& display);

}  // namespace LegacyCanvas
