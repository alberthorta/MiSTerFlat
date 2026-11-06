#pragma once

#include <stdint.h>

#include <string_view>

#include "transport/SerialTransport.h"

// This board's own Wi-Fi (not the MiSTer's: that is the Wi-Fi screen and the daemon's wifi.py).
// The network is set from MiSTerManager through the daemon (MDSSTA, docs/protocol.md) and kept
// in NVS. Once the board has an address it serves the virtual display (RemoteView), also while
// the MiSTer is switched off.
//
// A new network is stored only after the board got an address on it: a wrong password goes back
// to the network that worked before.
class Station {
 public:
  explicit Station(SerialTransport& transport) : transport_(transport) {}

  void begin();
  // MDSSTA arguments: "" (status), "scan", "join,<ssid hex>,<password hex>", "forget".
  void onHost(std::string_view args);
  void poll(uint32_t nowMs);

  // For MDSINFO.
  const char* stateName() const;
  const char* ip() const { return ip_; }

 private:
  enum class State : uint8_t { Off, Connecting, Ok, Fail };

  void connect(const char* ssid, const char* password, uint32_t nowMs);
  void setState(State s);
  void sendStatus();
  void pumpScan();

  SerialTransport& transport_;
  State state_ = State::Off;
  char ssid_[33] = {};      // the network in use or being tried
  char password_[65] = {};
  char savedSsid_[33] = {};  // the one in NVS
  char savedPassword_[65] = {};
  bool trying_ = false;      // ssid_ is a new network, not saved yet
  uint32_t connectStartMs_ = 0;
  char ip_[16] = {};
  int rssi_ = 0;
  int failReason_ = 0;
  int sentReason_ = 0;  // sent with fail: see the status line in docs/protocol.md
  uint32_t lastCheckMs_ = 0;
  bool statusDirty_ = false;
  bool serverStarted_ = false;

  // Scan results go out a few lines per loop: the TX queue holds 1 KB.
  bool scanning_ = false;
  int scanRetries_ = 0;
  uint32_t scanRetryAtMs_ = 0;  // a failed scan starts again then (0 = no retry waiting)
  int scanResult_ = 0;
  int scanCount_ = -1;  // results waiting to be sent, -1 = none
  int scanSent_ = 0;
};
