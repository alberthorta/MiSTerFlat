#include "Presence.h"

namespace presence {

void Presence::start(uint32_t nowMs) {
  startMs_ = nowMs;
  lastActivityMs_ = nowMs;
}

void Presence::onTraffic(uint32_t nowMs) {
  (void)nowMs;
  anyTraffic_ = true;
}

Event Presence::onActivity(uint32_t nowMs) {
  anyTraffic_ = true;
  lastActivityMs_ = nowMs;
  if (sleeping_) {
    sleeping_ = false;
    return Event::Wake;
  }
  return Event::None;
}

Event Presence::onHeartbeat(uint32_t nowMs) {
  anyTraffic_ = true;
  heartbeatSeen_ = true;
  lastHeartbeatMs_ = nowMs;
  if (hostLost_) {
    hostLost_ = false;
    return Event::HostBack;
  }
  return Event::None;
}

Event Presence::update(uint32_t nowMs) {
  if (heartbeatSeen_ && !hostLost_ && nowMs - lastHeartbeatMs_ >= config_.hostLostMs) {
    hostLost_ = true;
    return Event::HostLost;
  }
  if (!sleeping_ && config_.idleTimeoutMs > 0 && nowMs - lastActivityMs_ >= config_.idleTimeoutMs) {
    sleeping_ = true;
    return Event::IdleSleep;
  }
  if (!anyTraffic_ && !splashHintShown_ && nowMs - startMs_ >= config_.splashWaitMs) {
    splashHintShown_ = true;
    return Event::SplashWaiting;
  }
  return Event::None;
}

}  // namespace presence
