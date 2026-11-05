#include "app/Settings.h"

#include <Preferences.h>

#include "util/Log.h"

namespace {

constexpr const char* kNamespace = "mds";
constexpr const char* kContrastKey = "con";
constexpr const char* kRotatedKey = "rot";
constexpr const char* kIdleKey = "idle";
constexpr const char* kFadeKey = "fade";
constexpr const char* kIdleClockKey = "iclk";
constexpr const char* kScreenBrightnessKey = "sbl";
constexpr const char* kClockFontKey = "cfont";
constexpr const char* kPowerOnKey = "pwr";
constexpr const char* kAutoOnKey = "aon";
constexpr uint8_t kMinBacklight = 40;

void put(const char* key, uint32_t value) {
  Preferences p;
  if (!p.begin(kNamespace, false)) return;
  p.putUInt(key, value);
  p.end();
}

}  // namespace

void Settings::load() {
  Preferences p;
  if (!p.begin(kNamespace, true)) return;  // first boot: nothing stored yet, keep defaults
  const uint32_t con = p.getUInt(kContrastKey, kDefaultContrast);
  const uint32_t rot = p.getUInt(kRotatedKey, 0);
  const uint32_t idle = p.getUInt(kIdleKey, 0);
  const uint32_t fade = p.getUInt(kFadeKey, 1);
  const uint32_t idleClock = p.getUInt(kIdleClockKey, 0);
  const uint32_t screenBrightness = p.getUInt(kScreenBrightnessKey, 0);
  const uint32_t clockFont = p.getUInt(kClockFontKey, 0);
  const uint32_t powerOn = p.getUInt(kPowerOnKey, 0);
  const uint32_t autoOn = p.getUInt(kAutoOnKey, 0);
  p.end();
  clockFont_ = clockFont <= 255 ? static_cast<uint8_t>(clockFont) : 0;  // MenuScreen checks the range
  screenBrightness_ = screenBrightness == 1;
  powerOn_ = powerOn == 1;
  autoOn_ = autoOn == 1;
  fade_ = fade != 0;
  idleClock_ = idleClock == 1;
  // Stored values are trusted only within range.
  contrast_ = con <= 255 ? static_cast<uint8_t>(con) : kDefaultContrast;
  rotated_ = rot == 1;
  idleMinutes_ = idle <= kMaxIdleMinutes ? static_cast<uint16_t>(idle) : 0;
  LOGF("settings: contrast %u rotated %d idle %u min", contrast_, rotated_, idleMinutes_);
}

void Settings::setContrast(uint8_t v) {
  if (v == contrast_) return;
  contrast_ = v;
  put(kContrastKey, v);
}

void Settings::setRotated(bool v) {
  if (v == rotated_) return;
  rotated_ = v;
  put(kRotatedKey, v ? 1 : 0);
}

void Settings::setIdleMinutes(uint16_t v) {
  if (v > kMaxIdleMinutes) v = kMaxIdleMinutes;
  if (v == idleMinutes_) return;
  idleMinutes_ = v;
  put(kIdleKey, v);
}

void Settings::setFade(bool v) {
  if (v == fade_) return;
  fade_ = v;
  put(kFadeKey, v ? 1 : 0);
}

void Settings::setIdleClock(bool v) {
  if (v == idleClock_) return;
  idleClock_ = v;
  put(kIdleClockKey, v ? 1 : 0);
}

void Settings::setScreenBrightness(bool v) {
  if (v == screenBrightness_) return;
  screenBrightness_ = v;
  put(kScreenBrightnessKey, v ? 1 : 0);
}

void Settings::setClockFont(uint8_t v) {
  if (v == clockFont_) return;
  clockFont_ = v;
  put(kClockFontKey, v);
}

void Settings::setPowerOn(bool v) {
  if (v == powerOn_) return;
  powerOn_ = v;
  put(kPowerOnKey, v ? 1 : 0);
}

void Settings::setAutoOn(bool v) {
  if (v == autoOn_) return;
  autoOn_ = v;
  put(kAutoOnKey, v ? 1 : 0);
}

void Settings::resetToDefaults() {
  setContrast(kDefaultContrast);
  setRotated(false);
  setIdleMinutes(0);
  setFade(true);
  setIdleClock(false);
  setScreenBrightness(false);
  setClockFont(0);
  setAutoOn(false);
}

uint8_t Settings::backlightFor(uint8_t contrast) {
  return static_cast<uint8_t>(kMinBacklight + contrast * (255 - kMinBacklight) / 255);
}
