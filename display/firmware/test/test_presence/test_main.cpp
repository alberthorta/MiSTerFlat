#include <unity.h>

#include "Presence.h"

using namespace presence;

void setUp() {}
void tearDown() {}

namespace {

Config cfg(uint32_t idleMs) {
  Config c;
  c.hostLostMs = 15000;
  c.idleTimeoutMs = idleMs;
  c.splashWaitMs = 10000;
  return c;
}

// Runs update() every 100 ms from `from` to `to`; returns the first event other than None.
Event runUntil(Presence& p, uint32_t from, uint32_t to) {
  for (uint32_t t = from; t <= to; t += 100) {
    const Event e = p.update(t);
    if (e != Event::None) return e;
  }
  return Event::None;
}

}  // namespace

void test_no_heartbeat_never_loses_host() {  // stock tty2oled daemon: no pings
  Presence p(cfg(0));
  p.start(0);
  p.onActivity(1000);
  TEST_ASSERT_EQUAL(Event::None, runUntil(p, 1100, 600000));
  TEST_ASSERT_FALSE(p.hostLost());
}

void test_host_lost_and_back() {
  Presence p(cfg(0));
  p.start(0);
  p.onHeartbeat(1000);
  TEST_ASSERT_EQUAL(Event::None, runUntil(p, 1100, 15900));
  TEST_ASSERT_EQUAL(Event::HostLost, p.update(16000));
  TEST_ASSERT_TRUE(p.hostLost());
  TEST_ASSERT_EQUAL(Event::None, runUntil(p, 16100, 60000));  // reported once
  TEST_ASSERT_EQUAL(Event::HostBack, p.onHeartbeat(61000));
  TEST_ASSERT_FALSE(p.hostLost());
}

void test_regular_heartbeats_keep_host() {
  Presence p(cfg(0));
  p.start(0);
  for (uint32_t t = 0; t < 120000; t += 5000) {
    p.onHeartbeat(t);
    TEST_ASSERT_EQUAL(Event::None, runUntil(p, t + 100, t + 4900));
  }
}

void test_idle_sleep_and_wake() {
  Presence p(cfg(60000));
  p.start(0);
  p.onActivity(1000);
  TEST_ASSERT_EQUAL(Event::None, runUntil(p, 1100, 60900));
  TEST_ASSERT_EQUAL(Event::IdleSleep, p.update(61000));
  TEST_ASSERT_TRUE(p.idleSleeping());
  TEST_ASSERT_EQUAL(Event::None, runUntil(p, 61100, 200000));
  TEST_ASSERT_EQUAL(Event::Wake, p.onActivity(200100));
  TEST_ASSERT_FALSE(p.idleSleeping());
  TEST_ASSERT_EQUAL(Event::None, p.onActivity(200200));
}

void test_heartbeat_is_not_activity() {
  Presence p(cfg(60000));
  p.start(0);
  p.onActivity(0);
  for (uint32_t t = 5000; t < 60000; t += 5000) {
    TEST_ASSERT_EQUAL(Event::None, runUntil(p, t - 4900, t - 100));
    p.onHeartbeat(t);
  }
  TEST_ASSERT_EQUAL(Event::IdleSleep, runUntil(p, 55100, 60100));
  TEST_ASSERT_EQUAL(Event::None, p.onHeartbeat(61000));
  TEST_ASSERT_TRUE(p.idleSleeping());
}

void test_idle_zero_never_sleeps() {
  Presence p(cfg(0));
  p.start(0);
  p.onActivity(0);
  TEST_ASSERT_EQUAL(Event::None, runUntil(p, 100, 3600000));
}

void test_splash_hint_only_without_traffic() {
  Presence p(cfg(0));
  p.start(0);
  TEST_ASSERT_EQUAL(Event::None, runUntil(p, 100, 9900));
  TEST_ASSERT_EQUAL(Event::SplashWaiting, p.update(10000));
  TEST_ASSERT_EQUAL(Event::None, runUntil(p, 10100, 30000));

  Presence q(cfg(0));
  q.start(0);
  q.onTraffic(500);  // tty2oled startup commands count
  TEST_ASSERT_EQUAL(Event::None, runUntil(q, 600, 30000));
}

void test_timer_wraparound() {
  Presence p(cfg(0));
  const uint32_t t0 = 0xFFFFF000u;
  p.start(t0);
  p.onHeartbeat(t0);
  TEST_ASSERT_EQUAL(Event::None, p.update(t0 + 14000));
  TEST_ASSERT_EQUAL(Event::HostLost, p.update(t0 + 15000));
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_no_heartbeat_never_loses_host);
  RUN_TEST(test_host_lost_and_back);
  RUN_TEST(test_regular_heartbeats_keep_host);
  RUN_TEST(test_idle_sleep_and_wake);
  RUN_TEST(test_heartbeat_is_not_activity);
  RUN_TEST(test_idle_zero_never_sleeps);
  RUN_TEST(test_splash_hint_only_without_traffic);
  RUN_TEST(test_timer_wraparound);
  return UNITY_END();
}
