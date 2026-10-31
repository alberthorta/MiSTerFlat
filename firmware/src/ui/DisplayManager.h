#pragma once

#include <stdint.h>

#include "hal/Lgfx.h"

// Owns the panel and a full-screen RGB565 framebuffer. Screens draw into canvas() and call
// present(), which pushes the whole frame in one transfer (no visible partial redraws).
class DisplayManager {
 public:
  bool begin(uint8_t rotation);

  lgfx::LovyanGFX& canvas();
  void present();
  // Like present(), but dips the backlight: down, swap the frame, up again. Runs from tick();
  // nothing waits. Falls back to present() when the light is off anyway.
  void presentFaded(uint32_t nowMs);
  void tick(uint32_t nowMs);
  bool fading() const { return fade_ != Fade::None; }
  // The next present() fades (screens call present() themselves). Cleared after that call or by
  // disarmFade() if the screen did not present after all.
  void armFade(uint32_t nowMs) {
    fadeArmed_ = true;
    fadeArmedMs_ = nowMs;
  }
  void disarmFade() { fadeArmed_ = false; }

  // Remembered while asleep: wake() restores it.
  void setBrightness(uint8_t level);
  void setRotation(uint8_t rotation);
  void sleep();
  void wake();
  bool awake() const { return awake_; }
  // Idle sleep: backlight only, independent of sleep()/wake() (CMDDOFF/CMDDON), which it never
  // overrides. The panel keeps running, so the next frame is ready when the light comes back.
  void setBacklightOn(bool on);

  bool lightOn() const { return awake_ && backlightOn_; }
  // A point on the screen (in drawing coordinates) while a finger is on it. Always false on
  // boards without a touch panel.
  bool touched(int* x, int* y);
  // Counts present() calls, so an overlay can tell whether its frame is still the one shown.
  uint32_t frameCount() const { return frameCount_; }
  // Copies of the framebuffer (in PSRAM) for an overlay: kUnder is what it covers, kOver the
  // overlay itself. blendSaved() mixes them into the framebuffer for a fade.
  enum Slot : uint8_t { kUnder = 0, kOver = 1 };
  bool saveFrame(Slot slot = kUnder);
  void restoreFrame(Slot slot = kUnder);
  // alpha 0 = kUnder, 32 = kOver.
  void blendSaved(uint8_t alpha);
  // Darkens the framebuffer to a quarter, as a backdrop for an overlay.
  void dimFrame();

  int width() const;
  int height() const;
  // The fixed layouts (start screen, menu clock, core name) were drawn for the 170-pixel
  // T-Display-S3. Taller screens shift them down by this much, so they stay centred.
  static constexpr int kLayoutHeight = 170;
  int layoutTop() const { return (height() - kLayoutHeight) / 2; }
  bool hasFramebuffer() const { return framebufferOk_; }
  // Raw framebuffer: RGB565, big-endian per pixel (LovyanGFX sprite layout), row-major.
  const uint8_t* framebufferBytes() const;
  size_t framebufferSize() const;

 private:
  Lgfx lcd_;
  LGFX_Sprite frame_{&lcd_};
  bool framebufferOk_ = false;
  uint8_t* saved_[2] = {};
  uint32_t frameCount_ = 0;
  bool awake_ = true;
  bool backlightOn_ = true;
  uint8_t brightness_ = 0;

  enum class Fade : uint8_t { None, Out, In };
  void finishFade();
  Fade fade_ = Fade::None;
  bool fadeArmed_ = false;
  uint32_t fadeArmedMs_ = 0;
  uint32_t fadeStartMs_ = 0;
  uint8_t fadeFrom_ = 0;   // backlight level when the fade-out started
  uint8_t level_ = 0;      // backlight level being shown during a fade
};
