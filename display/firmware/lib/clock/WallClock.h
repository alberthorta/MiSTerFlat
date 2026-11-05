#pragma once

// Wall clock kept from CMDSETTIME and the millisecond counter (the board has no RTC battery).
// tty2oled sends *local* time as if it were a UTC epoch (`date -d "now <offset> hour" +%s`), so the
// broken-down fields below are the local time directly. Pure C++, unit-tested natively.

#include <stdint.h>

namespace wallclock {

struct DateTime {
  int year, month, day;  // month 1..12
  int hour, minute, second;
  int weekday;  // 0 = Monday
};

// Days since 1970-01-01 to a civil date (Howard Hinnant's algorithm; no libc time zone involved).
DateTime fromEpoch(int64_t epochSeconds);

class WallClock {
 public:
  void set(int64_t epochSeconds, uint32_t nowMs);
  bool valid() const { return valid_; }
  int64_t now(uint32_t nowMs) const;
  DateTime local(uint32_t nowMs) const { return fromEpoch(now(nowMs)); }
  // Minutes since the epoch: changes once a minute, for redrawing a clock.
  int64_t minuteStamp(uint32_t nowMs) const { return now(nowMs) / 60; }

 private:
  bool valid_ = false;
  int64_t epochAtSet_ = 0;
  uint32_t msAtSet_ = 0;
};

}  // namespace wallclock
