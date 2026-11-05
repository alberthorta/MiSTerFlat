#include "WallClock.h"

namespace wallclock {

DateTime fromEpoch(int64_t epochSeconds) {
  DateTime t{};
  int64_t days = epochSeconds / 86400;
  int64_t secs = epochSeconds % 86400;
  if (secs < 0) {
    secs += 86400;
    days -= 1;
  }
  t.hour = static_cast<int>(secs / 3600);
  t.minute = static_cast<int>((secs % 3600) / 60);
  t.second = static_cast<int>(secs % 60);
  // 1970-01-01 was a Thursday (Monday = 0 -> Thursday = 3).
  t.weekday = static_cast<int>(((days % 7) + 7 + 3) % 7);

  const int64_t z = days + 719468;
  const int64_t era = (z >= 0 ? z : z - 146096) / 146097;
  const int64_t doe = z - era * 146097;
  const int64_t yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
  const int64_t doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
  const int64_t mp = (5 * doy + 2) / 153;
  t.day = static_cast<int>(doy - (153 * mp + 2) / 5 + 1);
  t.month = static_cast<int>(mp < 10 ? mp + 3 : mp - 9);
  t.year = static_cast<int>(yoe + era * 400 + (t.month <= 2 ? 1 : 0));
  return t;
}

void WallClock::set(int64_t epochSeconds, uint32_t nowMs) {
  epochAtSet_ = epochSeconds;
  msAtSet_ = nowMs;
  valid_ = true;
}

int64_t WallClock::now(uint32_t nowMs) const {
  // Unsigned difference survives the 49-day millis() wrap.
  return epochAtSet_ + static_cast<int64_t>(static_cast<uint32_t>(nowMs - msAtSet_) / 1000);
}

}  // namespace wallclock
