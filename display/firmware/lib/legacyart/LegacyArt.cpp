#include "LegacyArt.h"

namespace legacyart {

namespace {

constexpr int kMaxOut = 1024;

// Source pixels covering output index i along one axis, with integer weights.
// In units of 1/out of a source pixel, output i spans [i*src, (i+1)*src) and source s spans
// [s*out, (s+1)*out); the weight is the overlap, and the weights of one output pixel sum to src.
// With output >= half the source size, one output pixel covers at most 2 source pixels and
// touches at most 3.
struct Span {
  int first;
  int count;
  int weight[3];
};

Span span(int i, int src, int out) {
  Span s{};
  const int lo = i * src, hi = (i + 1) * src;
  s.first = lo / out;
  for (int k = 0; k < 3; ++k) {
    const int p = s.first + k;
    if (p >= src) break;
    const int a = p * out > lo ? p * out : lo;
    const int b = (p + 1) * out < hi ? (p + 1) * out : hi;
    if (b <= a) break;
    s.weight[k] = b - a;
    s.count = k + 1;
  }
  return s;
}

}  // namespace

uint8_t sourceIntensity(Format format, const uint8_t* data, int x, int y) {
  if (format == Format::Xbm) {
    const uint8_t b = data[y * (kWidth / 8) + (x >> 3)];
    return ((b >> (x & 7)) & 1) ? 255 : 0;
  }
  const uint8_t b = data[y * (kWidth / 2) + (x >> 1)];
  const uint8_t level = (x & 1) ? (b & 0x0F) : (b >> 4);
  return static_cast<uint8_t>(level * 17);
}

bool resample(Format format, const uint8_t* data, size_t length, int outWidth, int outHeight, uint8_t* out) {
  if (length != (format == Format::Xbm ? kXbmBytes : kGscBytes)) return false;
  if (outWidth * 2 < kWidth || outHeight * 2 < kHeight || outWidth > kMaxOut || outHeight > kMaxOut) {
    return false;
  }
  const uint32_t total = static_cast<uint32_t>(kWidth) * kHeight;  // sum of weights per output pixel
  for (int oy = 0; oy < outHeight; ++oy) {
    const Span sy = span(oy, kHeight, outHeight);
    for (int ox = 0; ox < outWidth; ++ox) {
      const Span sx = span(ox, kWidth, outWidth);
      uint32_t acc = 0;
      for (int j = 0; j < sy.count; ++j) {
        for (int k = 0; k < sx.count; ++k) {
          acc += static_cast<uint32_t>(sy.weight[j]) * sx.weight[k] *
                 sourceIntensity(format, data, sx.first + k, sy.first + j);
        }
      }
      out[oy * outWidth + ox] = static_cast<uint8_t>((acc + total / 2) / total);
    }
  }
  return true;
}

}  // namespace legacyart
