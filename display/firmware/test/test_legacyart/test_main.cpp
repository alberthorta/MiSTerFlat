#include <unity.h>

#include <string.h>

#include <vector>

#include "../fixtures.h"
#include "LegacyArt.h"

using namespace legacyart;

void setUp() {}
void tearDown() {}

namespace {

constexpr size_t kCorLine = 18;  // "CMDCOR,MDSTEST,-1\n" in the captures

std::vector<uint8_t> xbm(uint8_t fill) { return std::vector<uint8_t>(kXbmBytes, fill); }

}  // namespace

void test_source_bit_and_nibble_order() {
  std::vector<uint8_t> x = xbm(0);
  x[0] = 0x01;  // LSB = leftmost pixel
  TEST_ASSERT_EQUAL(255, sourceIntensity(Format::Xbm, x.data(), 0, 0));
  TEST_ASSERT_EQUAL(0, sourceIntensity(Format::Xbm, x.data(), 1, 0));

  std::vector<uint8_t> g(kGscBytes, 0);
  g[0] = 0xF3;  // high nibble = left pixel
  TEST_ASSERT_EQUAL(255, sourceIntensity(Format::Gsc, g.data(), 0, 0));
  TEST_ASSERT_EQUAL(51, sourceIntensity(Format::Gsc, g.data(), 1, 0));
}

void test_identity_size_is_exact() {
  const uint8_t* gsc = kCapture_gsc + kCorLine;
  std::vector<uint8_t> out(kWidth * kHeight);
  TEST_ASSERT_TRUE(resample(Format::Gsc, gsc, kGscBytes, kWidth, kHeight, out.data()));
  for (int y = 0; y < kHeight; ++y)
    for (int x = 0; x < kWidth; ++x)
      TEST_ASSERT_EQUAL(sourceIntensity(Format::Gsc, gsc, x, y), out[y * kWidth + x]);
}

void test_solid_colours_stay_solid_at_125() {
  std::vector<uint8_t> out(320 * 80);
  std::vector<uint8_t> white = xbm(0xFF), black = xbm(0x00);
  TEST_ASSERT_TRUE(resample(Format::Xbm, white.data(), kXbmBytes, 320, 80, out.data()));
  for (uint8_t v : out) TEST_ASSERT_EQUAL(255, v);
  TEST_ASSERT_TRUE(resample(Format::Xbm, black.data(), kXbmBytes, 320, 80, out.data()));
  for (uint8_t v : out) TEST_ASSERT_EQUAL(0, v);
}

void test_edge_gets_an_intermediate_grey() {
  // Left 4 columns white. At 1.25x output column 4 covers source [3.2, 4.0): all white;
  // output column 5 covers [4.0, 4.8): all black. Column 3 covers [2.4, 3.2): white.
  // Left 3 columns white instead: output 3 covers [2.4, 3.2) = 0.6 white + 0.2 black -> 75%.
  std::vector<uint8_t> x = xbm(0);
  for (int y = 0; y < kHeight; ++y) x[y * 32] = 0x07;
  std::vector<uint8_t> out(320 * 80);
  TEST_ASSERT_TRUE(resample(Format::Xbm, x.data(), kXbmBytes, 320, 80, out.data()));
  TEST_ASSERT_EQUAL(255, out[2]);
  TEST_ASSERT_EQUAL(191, out[3]);  // round(255 * 0.75)
  TEST_ASSERT_EQUAL(0, out[4]);
}

void test_weights_preserve_average_brightness() {
  const uint8_t* xb = kCapture_xbm + kCorLine;
  uint64_t srcSum = 0;
  for (int y = 0; y < kHeight; ++y)
    for (int x = 0; x < kWidth; ++x) srcSum += sourceIntensity(Format::Xbm, xb, x, y);
  std::vector<uint8_t> out(320 * 80);
  TEST_ASSERT_TRUE(resample(Format::Xbm, xb, kXbmBytes, 320, 80, out.data()));
  uint64_t outSum = 0;
  for (uint8_t v : out) outSum += v;
  // Means in hundredths; resampling may only move them by rounding.
  const int srcMean = static_cast<int>(srcSum * 100 / (kWidth * kHeight));
  const int outMean = static_cast<int>(outSum * 100 / out.size());
  TEST_ASSERT_INT_WITHIN(50, srcMean, outMean);
}

void test_bad_input_is_rejected() {
  std::vector<uint8_t> out(1024 * 1024);
  std::vector<uint8_t> x = xbm(0);
  TEST_ASSERT_FALSE(resample(Format::Xbm, x.data(), 2047, 320, 80, out.data()));
  TEST_ASSERT_FALSE(resample(Format::Gsc, x.data(), kXbmBytes, 320, 80, out.data()));
  TEST_ASSERT_FALSE(resample(Format::Xbm, x.data(), kXbmBytes, 127, 80, out.data()));
  TEST_ASSERT_FALSE(resample(Format::Xbm, x.data(), kXbmBytes, 2000, 80, out.data()));
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_source_bit_and_nibble_order);
  RUN_TEST(test_identity_size_is_exact);
  RUN_TEST(test_solid_colours_stay_solid_at_125);
  RUN_TEST(test_edge_gets_an_intermediate_grey);
  RUN_TEST(test_weights_preserve_average_brightness);
  RUN_TEST(test_bad_input_is_rejected);
  return UNITY_END();
}
