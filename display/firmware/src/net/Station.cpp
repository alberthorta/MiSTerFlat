#include "net/Station.h"

#include "config.h"

#if MDS_HAS_STATION

#include <ESPmDNS.h>
#include <Preferences.h>
#include <WiFi.h>
#include <stdio.h>
#include <string.h>

#include <algorithm>

#include "Command.h"
#include "net/RemoteView.h"
#include "util/Log.h"

namespace {

constexpr const char* kHostname = "misterlily";
constexpr uint32_t kCheckMs = 500;
// A new network that gives no address in this time counts as failed (wrong password, too far).
constexpr uint32_t kJoinTimeoutMs = 20000;
// The stored network is tried again this often while there is no address. The driver's own
// reconnect gives up for good after some errors (an auth failure at start-up, seen in Nov 2026),
// and the board then stayed "connecting" until it was restarted.
constexpr uint32_t kRetryMs = 30000;
constexpr int kMaxNetworks = 20;
constexpr int kScanRetries = 3;
constexpr uint32_t kScanRetryGapMs = 700;
// Lower than the 20 dBm default: the Waveshare board's 3.3 V regulator dips on transmit peaks,
// and the box sits next to the router anyway.
constexpr wifi_power_t kTxPower = WIFI_POWER_13dBm;

struct Network {
  char ssid[33];
  int rssi;
  bool secure;
};
Network networks[kMaxNetworks];

// Why the last try failed, for the status line: the driver's disconnect reason, or kNoAddress when
// the board joined the network but got no address. Written from the Wi-Fi event task.
constexpr int kNoAddress = 1000;
volatile int lastReason = 0;
volatile bool associated = false;


void toHex(const char* text, char* out, size_t outSize) {
  static const char kDigits[] = "0123456789abcdef";
  size_t o = 0;
  for (const unsigned char* p = reinterpret_cast<const unsigned char*>(text); *p && o + 2 < outSize; ++p) {
    out[o++] = kDigits[*p >> 4];
    out[o++] = kDigits[*p & 15];
  }
  out[o] = '\0';
}

int hexDigit(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

// False on odd length, a bad digit, a NUL byte or a result longer than maxLength.
bool fromHex(std::string_view hex, char* out, size_t maxLength) {
  if (hex.size() % 2 || hex.size() / 2 > maxLength) return false;
  for (size_t i = 0; i < hex.size(); i += 2) {
    const int hi = hexDigit(hex[i]), lo = hexDigit(hex[i + 1]);
    if (hi < 0 || lo < 0 || (hi == 0 && lo == 0)) return false;
    out[i / 2] = static_cast<char>(hi << 4 | lo);
  }
  out[hex.size() / 2] = '\0';
  return true;
}

void copy(char* dst, const char* src, size_t size) {
  strncpy(dst, src, size - 1);
  dst[size - 1] = '\0';
}

}  // namespace

void Station::begin() {
  Preferences prefs;
  if (prefs.begin("sta", true)) {
    prefs.getString("ssid", savedSsid_, sizeof(savedSsid_));
    prefs.getString("pass", savedPassword_, sizeof(savedPassword_));
    prefs.end();
  }
  // Our own NVS keys hold the network; the Wi-Fi driver must not keep a second copy.
  WiFi.persistent(false);
  WiFi.onEvent([](arduino_event_id_t event, arduino_event_info_t info) {
    if (event == ARDUINO_EVENT_WIFI_STA_CONNECTED) {
      associated = true;
    } else if (event == ARDUINO_EVENT_WIFI_STA_DISCONNECTED) {
      associated = false;
      lastReason = info.wifi_sta_disconnected.reason;
    } else if (event == ARDUINO_EVENT_WIFI_STA_GOT_IP) {
      lastReason = 0;
    }
  });
  if (savedSsid_[0]) connect(savedSsid_, savedPassword_, millis());
}

void Station::connect(const char* ssid, const char* password, uint32_t nowMs) {
  copy(ssid_, ssid, sizeof(ssid_));
  copy(password_, password, sizeof(password_));
  WiFi.setHostname(kHostname);
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.disconnect();
  WiFi.begin(ssid_, password_[0] ? password_ : nullptr);
  WiFi.setTxPower(kTxPower);
  connectStartMs_ = nowMs;
  ip_[0] = '\0';
  lastReason = 0;
  associated = false;
  LOGF("sta: joining %s", ssid_);
  setState(State::Connecting);
}

void Station::setState(State s) {
  if (s != state_) statusDirty_ = true;
  state_ = s;
}

const char* Station::stateName() const {
  switch (state_) {
    case State::Connecting: return "connecting";
    case State::Ok: return "ok";
    case State::Fail: return "fail";
    default: return "off";
  }
}

void Station::sendStatus() {
  char ssidHex[sizeof(ssid_) * 2 + 1];
  toHex(ssid_, ssidHex, sizeof(ssidHex));
  char line[170];
  const int n = snprintf(line, sizeof(line), "MDSSTA,status,%s,%s,%d,%s,%d\n", stateName(), ip_,
                         state_ == State::Ok ? rssi_ : 0, ssidHex,
                         state_ == State::Fail ? failReason_ : state_ == State::Connecting ? lastReason : 0);
  if (n > 0 && transport_.write(line, n)) statusDirty_ = false;
}

void Station::onHost(std::string_view args) {
  if (args.empty()) {
    if (state_ == State::Ok) rssi_ = WiFi.RSSI();
    statusDirty_ = true;
    return;
  }
  if (args == "scan") {
    if (scanning_ || scanCount_ >= 0) return;
    if (WiFi.getMode() == WIFI_OFF) {
      WiFi.setHostname(kHostname);
      WiFi.mode(WIFI_STA);
    }
    if (WiFi.scanNetworks(true) == WIFI_SCAN_FAILED) {
      transport_.write("MDSSTA,end,-2\n");
      return;
    }
    scanning_ = true;
    scanRetries_ = 0;
    scanRetryAtMs_ = 0;
    transport_.write("MDSSTA,scanning\n");
    return;
  }
  if (args.substr(0, 5) == "join,") {
    std::string_view f[2];
    char ssid[33], password[65];
    if (proto::splitFields(args.substr(5), f, 2) != 2 || f[0].empty() || !fromHex(f[0], ssid, 32) ||
        !fromHex(f[1], password, 64) || (password[0] && strlen(password) < 8)) {
      transport_.write("MDSSTA,status,fail,,0,\n");
      return;
    }
    trying_ = strcmp(ssid, savedSsid_) != 0 || strcmp(password, savedPassword_) != 0;
    connect(ssid, password, millis());
    return;
  }
  if (args == "forget") {
    Preferences prefs;
    if (prefs.begin("sta", false)) {
      prefs.clear();
      prefs.end();
    }
    savedSsid_[0] = savedPassword_[0] = ssid_[0] = password_[0] = ip_[0] = '\0';
    trying_ = false;
    WiFi.disconnect(true);
    WiFi.mode(WIFI_OFF);
    LOGF("sta: forgotten");
    setState(State::Off);
  }
}

void Station::pumpScan() {
  if (scanning_) {
    if (scanRetryAtMs_) {
      if (static_cast<int32_t>(millis() - scanRetryAtMs_) < 0) return;
      scanRetryAtMs_ = 0;
      if (WiFi.scanNetworks(true) != WIFI_SCAN_FAILED) return;
    }
    const int n = WiFi.scanComplete();
    if (n == WIFI_SCAN_RUNNING) return;
    if (n <= 0 && scanRetries_ < kScanRetries) {
      // The driver fails a scan now and then (status 1, no networks), more often while the daemon
      // talks to the board; MiSTerManager scans with the MiSTer's own dongle when it can. Try again.
      ++scanRetries_;
      WiFi.scanDelete();
      scanRetryAtMs_ = millis() + kScanRetryGapMs;
      if (!scanRetryAtMs_) scanRetryAtMs_ = 1;
      return;
    }
    scanning_ = false;
    scanResult_ = n;
    // One line per name, strongest first: several access points often share one.
    int count = 0;
    for (int i = 0; i < n; ++i) {
      const String name = WiFi.SSID(i);
      if (name.isEmpty() || name.length() > 32) continue;
      const int rssi = WiFi.RSSI(i);
      int found = -1;
      for (int j = 0; j < count; ++j) {
        if (name == networks[j].ssid) found = j;
      }
      if (found >= 0) {
        networks[found].rssi = std::max(networks[found].rssi, rssi);
        continue;
      }
      if (count == kMaxNetworks) continue;
      copy(networks[count].ssid, name.c_str(), sizeof(networks[count].ssid));
      networks[count].rssi = rssi;
      networks[count].secure = WiFi.encryptionType(i) != WIFI_AUTH_OPEN;
      ++count;
    }
    WiFi.scanDelete();
    std::sort(networks, networks + count, [](const Network& a, const Network& b) { return a.rssi > b.rssi; });
    scanCount_ = count;
    scanSent_ = 0;
  }
  while (scanCount_ >= 0) {
    if (transport_.writeRoom() < 120) return;
    if (scanSent_ == scanCount_) {
      // The raw scan result: the number of access points, or -2 if the scan failed.
      char end[24];
      const int len = snprintf(end, sizeof(end), "MDSSTA,end,%d\n", scanResult_);
      transport_.write(end, len);
      scanCount_ = -1;
      return;
    }
    const Network& net = networks[scanSent_++];
    char ssidHex[sizeof(net.ssid) * 2 + 1];
    toHex(net.ssid, ssidHex, sizeof(ssidHex));
    char line[110];
    const int len = snprintf(line, sizeof(line), "MDSSTA,net,%d,%d,%s\n", net.rssi, net.secure ? 1 : 0, ssidHex);
    if (len > 0) transport_.write(line, len);
  }
}

void Station::poll(uint32_t nowMs) {
  pumpScan();
  if (statusDirty_) sendStatus();
  if (nowMs - lastCheckMs_ < kCheckMs) return;
  lastCheckMs_ = nowMs;
  if (state_ == State::Off || state_ == State::Fail) return;

  // Modem sleep saves power between beacons, but delays every packet by up to ~300 ms.
  WiFi.setSleep(!remote::watching());

  if (WiFi.status() == WL_CONNECTED) {
    if (state_ != State::Ok) {
      copy(ip_, WiFi.localIP().toString().c_str(), sizeof(ip_));
      rssi_ = WiFi.RSSI();
      LOGF("sta: %s on %s", ip_, ssid_);
      if (trying_) {
        Preferences prefs;
        if (prefs.begin("sta", false)) {
          prefs.putString("ssid", ssid_);
          prefs.putString("pass", password_);
          prefs.end();
        }
        copy(savedSsid_, ssid_, sizeof(savedSsid_));
        copy(savedPassword_, password_, sizeof(savedPassword_));
        trying_ = false;
      }
      if (!serverStarted_) {
        serverStarted_ = remote::start();
        if (MDNS.begin(kHostname)) MDNS.addService("http", "tcp", 80);
      }
      setState(State::Ok);
    }
    return;
  }
  if (state_ == State::Ok) {
    // Lost the network: the driver reconnects by itself.
    ip_[0] = '\0';
    connectStartMs_ = nowMs;
    setState(State::Connecting);
    return;
  }
  if (lastReason != sentReason_) {
    sentReason_ = lastReason;
    statusDirty_ = true;
  }
  if (!trying_ && nowMs - connectStartMs_ > kRetryMs) {
    LOGF("sta: no address on %s (%d), trying again", ssid_, lastReason);
    const int reason = lastReason;
    connect(ssid_, password_, nowMs);
    lastReason = reason;  // keep showing why until the next try says otherwise
    return;
  }
  if (trying_ && nowMs - connectStartMs_ > kJoinTimeoutMs) {
    failReason_ = associated ? kNoAddress : lastReason;
    LOGF("sta: could not join %s (%d)", ssid_, failReason_);
    setState(State::Fail);
    sendStatus();
    trying_ = false;
    if (savedSsid_[0]) {
      connect(savedSsid_, savedPassword_, nowMs);
    } else {
      WiFi.disconnect(true);
      WiFi.mode(WIFI_OFF);
    }
  }
}

#else  // boards without the station

void Station::begin() {}
void Station::onHost(std::string_view) {}
void Station::poll(uint32_t) {}
const char* Station::stateName() const { return "none"; }

#endif
