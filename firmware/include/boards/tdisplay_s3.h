#pragma once

#include <stdint.h>

// LILYGO T-Display-S3: ST7789 170x320 on the 8-bit parallel bus, AW9364 backlight driver.
// The id is 9 characters, as tty2oled's installer.sh expects (${BLA:0:9}), and unknown to its
// flasher.
#define MDS_BOARD_ID "HWTDISPS3"
#define MDS_BOARD_NAME "T-Display-S3"
#define MDS_BOARD_TDISPLAY_S3 1
#define MDS_HAS_TOUCH 0

namespace cfg {

// Pins verified against LILYGO T-Display-S3 commit ec889e7
// (Setup206_LilyGo_T_Display_S3.h and examples/*/pin_config.h). See docs/research.md.
namespace pin {
constexpr int kPowerOn = 15;  // Peripheral/LCD power enable, needed on battery
constexpr int kLcdBacklight = 38;
constexpr int kLcdReset = 5;
constexpr int kLcdCs = 6;
constexpr int kLcdDc = 7;
constexpr int kLcdWr = 8;
constexpr int kLcdRd = 9;
constexpr int kLcdD0 = 39;
constexpr int kLcdD1 = 40;
constexpr int kLcdD2 = 41;
constexpr int kLcdD3 = 42;
constexpr int kLcdD4 = 45;
constexpr int kLcdD5 = 46;
constexpr int kLcdD6 = 47;
constexpr int kLcdD7 = 48;
constexpr int kButtonBoot = 0;
constexpr int kButtonKey = 14;
}  // namespace pin

namespace lcd {
constexpr int kNativeWidth = 170;
constexpr int kNativeHeight = 320;
// The ST7789 has 240 columns; the 170-pixel glass starts at column 35.
constexpr int kColumnOffset = 35;
constexpr uint32_t kWriteClockHz = 16000000;
}  // namespace lcd

constexpr int kScreenWidth = 320;
constexpr int kScreenHeight = 170;

// LovyanGFX rotation for landscape. 0 reads correctly with the USB-C socket on the right
// (checked on the board). 2 is the same landscape turned 180 degrees (CMDROT,1).
constexpr uint8_t kRotationNormal = 0;
constexpr uint8_t kRotationFlipped = 2;

}  // namespace cfg
