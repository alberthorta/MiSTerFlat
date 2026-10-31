#pragma once

#include <LovyanGFX.hpp>

#include "config.h"

#if defined(MDS_BOARD_WAVESHARE_LCD2)

// ST7789T3 on SPI2, as wired on the Waveshare ESP32-S3-Touch-LCD-2. Panel settings match the
// gizmo project and Waveshare's demo (IPS: colours inverted, no offsets).
class Lgfx : public lgfx::LGFX_Device {
 public:
  Lgfx() {
    {
      auto c = bus_.config();
      c.spi_host = SPI2_HOST;
      c.spi_mode = 0;
      c.freq_write = cfg::lcd::kWriteClockHz;
      c.pin_sclk = cfg::pin::kLcdSclk;
      c.pin_mosi = cfg::pin::kLcdMosi;
      c.pin_miso = cfg::pin::kLcdMiso;
      c.pin_dc = cfg::pin::kLcdDc;
      c.dma_channel = SPI_DMA_CH_AUTO;
      bus_.config(c);
      panel_.setBus(&bus_);
    }
    {
      auto c = panel_.config();
      c.pin_cs = cfg::pin::kLcdCs;
      c.pin_rst = cfg::pin::kLcdReset;
      c.pin_busy = -1;
      c.panel_width = cfg::lcd::kNativeWidth;
      c.panel_height = cfg::lcd::kNativeHeight;
      c.offset_x = 0;
      c.offset_y = 0;
      c.offset_rotation = 1;  // so that setRotation(0) is landscape
      c.readable = false;
      c.invert = true;
      c.rgb_order = false;
      c.dlen_16bit = false;
      c.bus_shared = false;
      panel_.config(c);
    }
    {
      auto c = light_.config();
      c.pin_bl = cfg::pin::kLcdBacklight;
      c.freq = cfg::lcd::kBacklightPwmHz;
      c.pwm_channel = 7;
      c.invert = false;
      light_.config(c);
      panel_.setLight(&light_);
    }
    {
      // Raw points come in the panel's native portrait frame; getTouch() turns them with the
      // screen rotation, so they match what is drawn.
      auto c = touch_.config();
      c.x_min = 0;
      c.x_max = cfg::lcd::kNativeWidth - 1;
      c.y_min = 0;
      c.y_max = cfg::lcd::kNativeHeight - 1;
      c.pin_int = cfg::pin::kTouchInt;
      c.pin_rst = -1;
      c.bus_shared = false;
      c.offset_rotation = 0;
      c.i2c_port = 0;
      c.pin_sda = cfg::pin::kTouchSda;
      c.pin_scl = cfg::pin::kTouchScl;
      c.freq = 400000;
      touch_.config(c);
      panel_.setTouch(&touch_);
    }
    setPanel(&panel_);
  }

 private:
  lgfx::Bus_SPI bus_;
  lgfx::Panel_ST7789 panel_;
  lgfx::Light_PWM light_;
  lgfx::Touch_CST816S touch_;
};

#else

#include "hal/BacklightAw9364.h"

// ST7789 on the ESP32-S3 i80 (8-bit parallel) bus, as wired on the T-Display-S3.
// Values follow LILYGO's own LovyanGFX examples (examples/T-Display-S3-Queue).
class Lgfx : public lgfx::LGFX_Device {
 public:
  Lgfx() {
    {
      auto c = bus_.config();
      c.freq_write = cfg::lcd::kWriteClockHz;
      c.pin_wr = cfg::pin::kLcdWr;
      c.pin_rd = cfg::pin::kLcdRd;
      c.pin_rs = cfg::pin::kLcdDc;
      c.pin_d0 = cfg::pin::kLcdD0;
      c.pin_d1 = cfg::pin::kLcdD1;
      c.pin_d2 = cfg::pin::kLcdD2;
      c.pin_d3 = cfg::pin::kLcdD3;
      c.pin_d4 = cfg::pin::kLcdD4;
      c.pin_d5 = cfg::pin::kLcdD5;
      c.pin_d6 = cfg::pin::kLcdD6;
      c.pin_d7 = cfg::pin::kLcdD7;
      bus_.config(c);
      panel_.setBus(&bus_);
    }
    {
      auto c = panel_.config();
      c.pin_cs = cfg::pin::kLcdCs;
      c.pin_rst = cfg::pin::kLcdReset;
      c.pin_busy = -1;
      c.panel_width = cfg::lcd::kNativeWidth;
      c.panel_height = cfg::lcd::kNativeHeight;
      c.offset_x = cfg::lcd::kColumnOffset;
      c.offset_y = 0;
      c.offset_rotation = 1;  // so that setRotation(0) is landscape
      c.readable = false;
      c.invert = true;
      c.rgb_order = false;
      c.dlen_16bit = false;
      c.bus_shared = false;
      panel_.config(c);
    }
    panel_.setLight(&light_);
    setPanel(&panel_);
  }

 private:
  lgfx::Bus_Parallel8 bus_;
  lgfx::Panel_ST7789 panel_;
  BacklightAw9364 light_{cfg::pin::kLcdBacklight};
};

#endif
