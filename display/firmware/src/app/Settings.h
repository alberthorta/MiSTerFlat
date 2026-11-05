#pragma once

#include <stdint.h>

// Display settings kept in NVS across power cycles, so the first frame after boot already has the
// right brightness and rotation. Written only when a value changes: tty2oled sends CMDCON and
// CMDROT every time its daemon starts.
class Settings {
 public:
  static constexpr uint8_t kDefaultContrast = 255;
  static constexpr uint16_t kMaxIdleMinutes = 1440;

  void load();

  uint8_t contrast() const { return contrast_; }  // CMDCON scale 0..255
  bool rotated() const { return rotated_; }       // CMDROT,1
  uint16_t idleMinutes() const { return idleMinutes_; }  // 0 = never sleep
  bool fade() const { return fade_; }            // backlight dip on core changes
  bool idleClock() const { return idleClock_; }  // idle: dim clock instead of backlight off
  // The brightness was picked on the touch screen: from then on CMDCON from the host is ignored,
  // since the daemon sends its configured contrast every time it connects.
  bool screenBrightness() const { return screenBrightness_; }
  uint8_t clockFont() const { return clockFont_; }  // MenuScreen::kClockFonts index
  // The MiSTer power relay: its state, so a reset of this board keeps it, and whether the MiSTer
  // starts by itself when the whole box gets power (else it waits in standby for a tap).
  bool powerOn() const { return powerOn_; }
  bool autoOn() const { return autoOn_; }

  void setContrast(uint8_t v);
  void setRotated(bool v);
  void setIdleMinutes(uint16_t v);
  void setFade(bool v);
  void setIdleClock(bool v);
  void setScreenBrightness(bool v);
  void setClockFont(uint8_t v);
  void setPowerOn(bool v);
  void setAutoOn(bool v);
  void resetToDefaults();

  // CMDCON is OLED contrast (tty2oled default 100). On a backlit TFT 0 must not mean "black",
  // so 0..255 maps onto a usable backlight range.
  static uint8_t backlightFor(uint8_t contrast);

 private:
  uint8_t contrast_ = kDefaultContrast;
  bool rotated_ = false;
  uint16_t idleMinutes_ = 0;
  bool fade_ = true;
  bool idleClock_ = false;
  bool screenBrightness_ = false;
  uint8_t clockFont_ = 0;
  bool powerOn_ = false;
  bool autoOn_ = false;
};
