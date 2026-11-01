#pragma once

#include <stdint.h>

#include <string_view>

#include "transport/SerialTransport.h"
#include "ui/DisplayManager.h"

// Wi-Fi set-up on the touch screen, opened from the touch buttons in the MiSTer menu when the
// daemon reports a Wi-Fi dongle. It asks the host to scan (MDSWIFI,scan), lists the networks
// (drag to scroll), takes the password on an on-screen keyboard and asks the host to join
// (MDSWIFI,join,<ssid hex>,<password hex>). The daemon does the work: mister/wifi.py.
class WifiScreen {
 public:
  WifiScreen(DisplayManager& display, SerialTransport& transport) : display_(display), transport_(transport) {}

  bool active() const { return state_ != State::Closed; }
  void open(uint32_t nowMs);
  void close() { state_ = State::Closed; }
  // MDSWIFI lines from the host (the text after "MDSWIFI,"), except "dongle,...".
  void onHost(std::string_view args, uint32_t nowMs);

  struct Result {
    bool activity = false;  // any touch
    bool closed = false;    // the user closed it: the caller redraws its own screen
  };
  Result poll(uint32_t nowMs);

 private:
  enum class State : uint8_t { Closed, Scanning, List, Keyboard, Connecting, Done };
  enum Layer : uint8_t { kLower, kUpper, kDigits, kSymbols };
  static constexpr int kMaxNets = 20;
  static constexpr size_t kMaxPassword = 63;  // WPA passphrase: 8..63 characters

  struct Net {
    uint8_t ssid[32];
    uint8_t length;
    int8_t signal;  // dBm
    bool secure;
    bool linked;    // wlan0 is on it now
  };

  void scan(uint32_t nowMs);
  void join(uint32_t nowMs);
  void tap(int x, int y, uint32_t nowMs);
  void tapList(int x, int y, uint32_t nowMs);
  void tapKeyboard(int x, int y, uint32_t nowMs);
  void tapDone(int x, int y, uint32_t nowMs);
  int keyAt(int x, int y, char* out) const;  // key code at a point, see the .cpp

  void draw();
  void drawHeader(const char* title, bool back, bool rescan);
  void drawList();
  void drawKeyboard();
  void drawMessage(const char* line1, const char* line2, const char* line3);
  void drawDone();
  int maxScroll() const;

  DisplayManager& display_;
  SerialTransport& transport_;
  State state_ = State::Closed;
  uint32_t stateMs_ = 0;  // when the current state began (timeouts, dots)
  uint32_t lastPollMs_ = 0;
  uint32_t lastDotsMs_ = 0;

  Net nets_[kMaxNets];
  int netCount_ = 0;
  int scroll_ = 0;     // pixels the list is moved up
  int selected_ = -1;  // net being joined

  char password_[kMaxPassword + 1] = {};
  size_t passwordLength_ = 0;
  Layer layer_ = kLower;
  int heldKey_ = -1;  // key under the finger, drawn lit

  bool joinOk_ = false;
  char result_[96] = {};  // the address, or the reason it failed

  // Touch: a drag scrolls the list, a touch that does not move is a tap.
  bool down_ = false;
  bool moved_ = false;
  int downX_ = 0;
  int downY_ = 0;
  int lastX_ = 0;
  int lastY_ = 0;
  int downScroll_ = 0;
};
