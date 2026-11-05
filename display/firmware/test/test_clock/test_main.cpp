#include <unity.h>

#include "WallClock.h"

using namespace wallclock;

void setUp() {}
void tearDown() {}

void test_epoch_zero() {
  DateTime t = fromEpoch(0);
  TEST_ASSERT_EQUAL(1970, t.year);
  TEST_ASSERT_EQUAL(1, t.month);
  TEST_ASSERT_EQUAL(1, t.day);
  TEST_ASSERT_EQUAL(0, t.hour);
  TEST_ASSERT_EQUAL(3, t.weekday);  // Thursday
}

void test_known_dates() {
  // 2026-10-08 21:05:09 (a Thursday), checked with `date -u -r 1791493509` on macOS.
  DateTime t = fromEpoch(1791493509);
  TEST_ASSERT_EQUAL(2026, t.year);
  TEST_ASSERT_EQUAL(10, t.month);
  TEST_ASSERT_EQUAL(8, t.day);
  TEST_ASSERT_EQUAL(21, t.hour);
  TEST_ASSERT_EQUAL(5, t.minute);
  TEST_ASSERT_EQUAL(9, t.second);
  TEST_ASSERT_EQUAL(3, t.weekday);

  t = fromEpoch(951782400);  // 2000-02-29 00:00:00, leap day
  TEST_ASSERT_EQUAL(2000, t.year);
  TEST_ASSERT_EQUAL(2, t.month);
  TEST_ASSERT_EQUAL(29, t.day);

  t = fromEpoch(4102444799LL);  // 2099-12-31 23:59:59
  TEST_ASSERT_EQUAL(2099, t.year);
  TEST_ASSERT_EQUAL(12, t.month);
  TEST_ASSERT_EQUAL(31, t.day);
  TEST_ASSERT_EQUAL(23, t.hour);
  TEST_ASSERT_EQUAL(59, t.second);
}

void test_clock_runs_from_millis() {
  WallClock c;
  TEST_ASSERT_FALSE(c.valid());
  c.set(1791493509, 5000);
  TEST_ASSERT_TRUE(c.valid());
  TEST_ASSERT_EQUAL_INT64(1791493509, c.now(5999));
  TEST_ASSERT_EQUAL_INT64(1791493510, c.now(6000));
  TEST_ASSERT_EQUAL_INT64(1791493509 + 3600, c.now(5000 + 3600000));
}

void test_minute_stamp_changes_once_a_minute() {
  WallClock c;
  c.set(60 * 1000 + 59, 0);  // hh:mm:59
  const int64_t m = c.minuteStamp(0);
  TEST_ASSERT_EQUAL_INT64(m, c.minuteStamp(999));
  TEST_ASSERT_EQUAL_INT64(m + 1, c.minuteStamp(1000));
}

void test_millis_wraparound() {
  WallClock c;
  c.set(1000000, 0xFFFFFC18u);  // 1 s before the 32-bit wrap
  TEST_ASSERT_EQUAL_INT64(1000002, c.now(1000u));
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_epoch_zero);
  RUN_TEST(test_known_dates);
  RUN_TEST(test_clock_runs_from_millis);
  RUN_TEST(test_minute_stamp_changes_once_a_minute);
  RUN_TEST(test_millis_wraparound);
  return UNITY_END();
}
