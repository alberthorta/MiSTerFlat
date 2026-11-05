#pragma once

// tty2oled pictures (256x64) decoded and resampled to any size. Pure C++, unit-tested natively.
//
// Formats, as the tty2oled sketch reads them:
// - XBM: 1 bpp, 32 bytes per row, least significant bit = leftmost pixel.
// - GSC: 4 bpp, 128 bytes per row, high nibble = left pixel, 0 = black .. 15 = full.

#include <stddef.h>
#include <stdint.h>

namespace legacyart {

constexpr int kWidth = 256;
constexpr int kHeight = 64;
constexpr size_t kXbmBytes = 2048;
constexpr size_t kGscBytes = 8192;

enum class Format : uint8_t { Xbm, Gsc };

// Intensity 0..255 of source pixel (x, y).
uint8_t sourceIntensity(Format format, const uint8_t* data, int x, int y);

// Area-average resampling to outWidth x outHeight intensities (0..255, row-major) in `out`.
// Every output pixel is the exact area-weighted mean of the source pixels it covers, so a
// non-integer scale like 1.25x gives soft edges instead of uneven pixel columns.
// Output sizes from half to 4x the source. Returns false if the data length does not match the
// format or a size is out of range.
bool resample(Format format, const uint8_t* data, size_t length, int outWidth, int outHeight, uint8_t* out);

}  // namespace legacyart
