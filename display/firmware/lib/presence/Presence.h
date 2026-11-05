#pragma once

// Time-based display states, kept apart from drawing so they run in the native unit tests.
// Time is passed in, never read.
//
// - Host heartbeat: our daemon sends MDSPING every few seconds. Once one has been seen, a long
//   silence means the MiSTer side is gone (daemon stopped, MiSTer off or rebooting): the display
//   shows "Waiting for MiSTer". The stock tty2oled daemon never pings, so in that mode this state
//   is never entered.
// - Idle sleep: no core change or display command for idleTimeoutMs -> backlight off. Pings are
//   not activity. Any activity wakes it. 0 = never.
// - Splash waiting: nothing at all received for a while after boot -> a hint on the start screen.

#include <stdint.h>

namespace presence {

struct Config {
  uint32_t hostLostMs = 15000;       // 3 missed pings at the daemon's 5 s period
  uint32_t idleTimeoutMs = 0;        // 0 = never sleep
  uint32_t splashWaitMs = 10000;
};

enum class Event : uint8_t {
  None,
  HostLost,      // show "Waiting for MiSTer"
  HostBack,      // a ping after HostLost (the daemon resends the core itself)
  IdleSleep,     // backlight off
  Wake,          // backlight back on
  SplashWaiting, // still on the start screen and nothing received yet
};

class Presence {
 public:
  explicit Presence(const Config& config = Config()) : config_(config) {}

  void setIdleTimeout(uint32_t ms) { config_.idleTimeoutMs = ms; }
  uint32_t idleTimeout() const { return config_.idleTimeoutMs; }

  void start(uint32_t nowMs);
  // Any received byte (also pings and tty2oled startup commands).
  void onTraffic(uint32_t nowMs);
  // Core change, picture, or a command that changes what the screen shows.
  // Returns Wake if it ends an idle sleep.
  Event onActivity(uint32_t nowMs);
  // MDSPING. Returns HostBack if the host had been lost.
  Event onHeartbeat(uint32_t nowMs);
  // Call every loop; returns at most one event per call.
  Event update(uint32_t nowMs);

  bool hostLost() const { return hostLost_; }
  bool idleSleeping() const { return sleeping_; }
  bool heartbeatSeen() const { return heartbeatSeen_; }

 private:
  Config config_;
  uint32_t startMs_ = 0;
  uint32_t lastActivityMs_ = 0;
  uint32_t lastHeartbeatMs_ = 0;
  bool anyTraffic_ = false;
  bool splashHintShown_ = false;
  bool heartbeatSeen_ = false;
  bool hostLost_ = false;
  bool sleeping_ = false;
};

}  // namespace presence
