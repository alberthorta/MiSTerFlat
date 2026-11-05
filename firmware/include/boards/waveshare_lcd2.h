#pragma once

#include <stdint.h>

// Waveshare ESP32-S3-Touch-LCD-2: ST7789T3 240x320 on SPI, backlight through a MOSFET on a PWM
// pin, CST816D touch panel on I2C. Same ESP32-S3R8 (16 MB flash, 8 MB PSRAM) and native USB as
// the T-Display-S3. The IMU, microSD and camera socket are not used.
#define MDS_BOARD_ID "HWWSTLCD2"
#define MDS_BOARD_NAME "Waveshare LCD 2"
#define MDS_BOARD_WAVESHARE_LCD2 1
#define MDS_HAS_TOUCH 1
// Its own Wi-Fi (set from MiSTerManager) and the virtual display web page: docs/virtual-display.md.
#define MDS_HAS_STATION 1

namespace cfg {

// From the board schematic (ESP32-S3-Touch-LCD-2-SchDoc.pdf), checked on a real board in the
// gizmo project. Waveshare's own demo leaves LCD reset unconnected (-1); the schematic has IO0.
namespace pin {
constexpr int kPowerOn = -1;  // no switched peripheral rail
constexpr int kLcdBacklight = 1;
constexpr int kLcdReset = 0;
constexpr int kLcdCs = 45;
constexpr int kLcdDc = 42;
constexpr int kLcdSclk = 39;
constexpr int kLcdMosi = 38;
constexpr int kLcdMiso = 40;  // shared with the microSD slot
constexpr int kTouchSda = 48;  // I2C shared with the IMU
constexpr int kTouchScl = 47;
constexpr int kTouchInt = 46;
// MiSTer power relay on header P1 (silkscreen "18"): a free camera pin, not a strapping pin.
// A 5 V relay module with a high-level input switches the MiSTer's 5 V; see docs/power.md.
constexpr int kMisterPower = 18;
constexpr int kMisterPowerOnLevel = 1;
}  // namespace pin

namespace lcd {
constexpr int kNativeWidth = 240;
constexpr int kNativeHeight = 320;
constexpr uint32_t kWriteClockHz = 40000000;
constexpr uint32_t kBacklightPwmHz = 20000;
}  // namespace lcd

constexpr int kScreenWidth = 320;
constexpr int kScreenHeight = 240;

// Landscape. 0 reads correctly (checked on the board); 2 is turned 180 degrees (CMDROT,1).
constexpr uint8_t kRotationNormal = 0;
constexpr uint8_t kRotationFlipped = 2;

}  // namespace cfg
