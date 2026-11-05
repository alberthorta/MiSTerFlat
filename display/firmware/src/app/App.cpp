#include "app/App.h"

#include <Arduino.h>
#include <esp_heap_caps.h>
#include <stdio.h>
#include <string.h>

#include "Crc32.h"
#include "config.h"
#include "ui/CoreScreen.h"
#include "ui/LegacyCanvas.h"
#include "ui/MenuScreen.h"
#include "ui/SplashScreen.h"
#include "ui/Logos.h"
#include "ui/StandbyScreen.h"
#include "ui/Theme.h"
#include "util/Log.h"

namespace {

constexpr size_t kReadChunkBytes = 512;
// Upper bound per loop() call, so a host that never stops sending cannot starve the timers.
constexpr int kMaxReadsPerLoop = 32;
// A screenshot the host stops reading is abandoned after this long without progress.
constexpr uint32_t kShotStallMs = 1000;
// Lets the "ttyack;" of CMDRESET leave before the chip restarts.
constexpr uint32_t kRestartDelayMs = 100;
constexpr uint32_t kMsPerMinute = 60000;
constexpr const char* kWaitingText = "Waiting for MiSTer";
// After a RESET tap: dark this long, then the menu clock.
constexpr uint32_t kRestartDarkMs = 2000;
// The daemon is back about 19 s after the reset; "Waiting for MiSTer" only after this long.
constexpr uint32_t kRestartGraceMs = 60000;
// Power off: the daemon answers MDSBTN,poweroff with MDSPOWER,halting after its sync, then runs
// poweroff. It sends MDSPOWER,down when init stops it at the end of the shutdown, after the stop
// scripts and umount; the relay opens kDownMs after that. kHaltMs after "halting" is only the
// safety limit if "down" never comes. Without any answer the relay opens kHaltReplyMs after the
// request (an old daemon, a hung MiSTer), and without a daemon at all at once.
constexpr uint32_t kHaltMs = 30000;
constexpr uint32_t kDownMs = 1500;
constexpr uint32_t kHaltReplyMs = 8000;
constexpr uint32_t kNoHostCutMs = 1000;
constexpr uint32_t kStartGraceMs = 60000;
constexpr uint32_t kStandbyPollMs = 20;
// After a tap on the standby screen, the power prompt waits this long for the second tap.
constexpr uint32_t kPromptMs = 5000;
constexpr const char* kStartingText = "Starting MiSTer";
constexpr const char* kStoppingText = "Shutting down";

}  // namespace

App::App(DisplayManager& display, SerialTransport& transport, Settings& settings, StartupLogo& logo,
         PowerSwitch& power)
    : display_(display), transport_(transport), settings_(settings), logo_(logo), power_(power), parser_(*this) {}

void App::showStartScreen() {
  if (PowerSwitch::available() && !power_.on()) {
    showStandby();
  } else {
    showSplash();
  }
}

void App::begin() {
  assetBuffer_ = static_cast<uint8_t*>(heap_caps_malloc(proto::kMaxAssetBytes, MALLOC_CAP_SPIRAM));
  parser_.setAssetBuffer(assetBuffer_, assetBuffer_ ? proto::kMaxAssetBytes : 0);
  LOGF("asset buffer %s", assetBuffer_ ? "ok" : "missing");
  presence_.setIdleTimeout(settings_.idleMinutes() * kMsPerMinute);
  presence_.start(millis());
  touchButtons_.setBrightness(levelForContrast(settings_.contrast()));
  touchButtons_.setPowerOff(PowerSwitch::available());
  station_.begin();
  if (PowerSwitch::available() && !power_.on()) {
    powerState_ = Power::Off;
    display_.setBrightness(Settings::backlightFor(0));
  }

  // The sketch prints "ttyrdy;" here, but no tty2oled script reads it. Over USB it stays
  // queued until the next reply and then corrupts that reply (installer.sh reads one line for
  // CMDHWINF), so we do not send it.
}

void App::loop() {
  uint8_t buffer[kReadChunkBytes];
  // Read until the FIFO is empty: while it is full the host is held off (NAK).
  for (int i = 0; i < kMaxReadsPerLoop; ++i) {
    const size_t n = transport_.read(buffer, sizeof(buffer));
    if (n == 0) break;
    // Data with the relay open: the MiSTer has power some other way (no relay fitted).
    if (powerState_ == Power::Off) powerOn(true);
    presence_.onTraffic(millis());
    parser_.feed(buffer, n, millis());
  }
  parser_.poll(millis());
  handlePresence(presence_.update(millis()));
  display_.tick(millis());
  if ((screen_ == Screen::Menu || screen_ == Screen::IdleClock) && clock_.valid() &&
      clock_.minuteStamp(millis()) != shownMinute_) {
    showMenu(screen_ == Screen::IdleClock);
  }
  pumpScreenshot(millis());
  station_.poll(millis());
  if (strcmp(shownBoardIp_, station_.ip()) != 0) {
    // The board got or lost its address: the screens that show it draw again.
    strncpy(shownBoardIp_, station_.ip(), sizeof(shownBoardIp_) - 1);
    if (screen_ == Screen::Menu || screen_ == Screen::IdleClock) showMenu(screen_ == Screen::IdleClock);
    if (screen_ == Screen::Standby) showStandby();
  }
  pollPower();
  if (MDS_HAS_TOUCH) {
    pollTouch();
    pollRestart();
  }
  transport_.poll(millis());

  if (restartPending_ && static_cast<int32_t>(millis() - restartAtMs_) >= 0) {
    LOGF("restart");
    ESP.restart();
  }
}

bool App::handleTestCommand(std::string_view line) {
#if MDS_TEST_COMMANDS
  // Before parsing: the parser takes words it does not know for core names, which would count as
  // a screen change.
  // MDSBUTTONS,<held button 0-3 or -1>,<reset armed 0|1>: the touch buttons in a given state.
  if (line.substr(0, 10) == "MDSBUTTONS") {
    int held = -1, armed = 0;
    sscanf(std::string(line).c_str(), "MDSBUTTONS,%d,%d", &held, &armed);
    touchButtons_.preview(held, armed != 0, millis());
    return true;
  }
  // MDSTAP,<x>,<y>: a 100 ms touch at that point, as if a finger tapped the screen.
  if (line.substr(0, 7) == "MDSTAP,") {
    int x = 0, y = 0;
    sscanf(std::string(line).c_str(), "MDSTAP,%d,%d", &x, &y);
    display_.injectTouch(x, y, 100);
    return true;
  }
#endif
  (void)line;
  return false;
}

void App::onLine(const char* line, size_t length) {
  ++linesReceived_;
  const std::string_view text(line, length);
  if (handleTestCommand(text)) {
    ack();
    return;
  }
  const proto::Command cmd = proto::parseCommand(text);
  LOGF("line '%s' -> %d", line, (int)cmd.id);
  if (changesScreen(cmd.id)) noteActivity();
  handle(cmd, text);
  ack();
}

void App::onImage(const proto::ImageFrame& frame) {
  ++imagesReceived_;
  lastImageResult_ = frame.result;
  lastImageBytes_ = frame.length;
  LOGF("image '%s' result %d format %d bytes %u", frame.commandLine, (int)frame.result, (int)frame.format,
       (unsigned)frame.length);

  noteActivity();
  const std::string_view command(frame.commandLine);
  const proto::CoreCommand cc = proto::parseCoreCommand(command);
  setCore(cc.core);
  nextCoreFades_ = cc.transition != 0;
  assetValid_ = false;
  if (frame.result == proto::ImageResult::Ok) {
    memcpy(picture_, frame.data, frame.length);
    pictureFormat_ = frame.format;
  } else {
    // A missing or cut picture: show the name rather than an error or stale artwork.
    pictureFormat_ = proto::ImageFormat::None;
  }
  // CMDAPD only loads the picture; CMDSPIC shows it later.
  if (command.substr(0, 6) == "CMDCOR") showCore(true);
  ack();
}

void App::onAsset(const proto::AssetFrame& frame) {
  const std::string_view header(frame.commandLine);
  if (header.substr(0, 8) == "MDSLOGO,") {
    handleLogo(header, frame);
    ack();
    return;
  }
  if (header.substr(0, 10) == "MDSSYSIMG,") {
    // MDSSYSIMG,<bytes>,<crc32 hex>,<png|jpg>,<index>. The frame came into the picture buffer.
    assetValid_ = false;
    std::string_view f[4];
    int32_t index = -1;
    if (frame.result == proto::AssetResult::Ok && proto::splitFields(header.substr(10), f, 4) == 4 &&
        proto::parseInt(f[3], index) && checkCrc(f[1], frame.data, frame.length)) {
      uint32_t crc = 0;
      for (char c : f[1]) crc = crc << 4 | static_cast<uint32_t>(c <= '9' ? c - '0' : (c | 0x20) - 'a' + 10);
      systems_.onCover(index, crc, f[2] == "png", frame.data, frame.length);
    }
    ack();
    return;
  }
  ++imagesReceived_;
  noteActivity();
  const char* error = nullptr;
  // The parser already wrote over the buffer, so the previous asset is gone either way.
  assetValid_ = false;
  pictureFormat_ = proto::ImageFormat::None;
  // The core name is the last field; take it first so a failed picture still shows the name.
  std::string_view f[4];
  if (header.size() > 7 && proto::splitFields(header.substr(7), f, 4) == 4) setCore(f[3]);
  if (frame.result == proto::AssetResult::Ok && decodeAsset(header, frame, &error)) {
    lastAssetError_ = "none";
    transport_.write("MDSIMG;ok\n");
  } else {
    if (frame.result == proto::AssetResult::BadHeader) error = "header";
    if (frame.result == proto::AssetResult::TooLarge) error = "size";
    if (frame.result == proto::AssetResult::Incomplete) error = "incomplete";
    lastAssetError_ = error ? error : "unknown";
    char reply[40];
    snprintf(reply, sizeof(reply), "MDSIMG;err=%s\n", lastAssetError_);
    transport_.write(reply);
    // Still a core change: show the name rather than the previous core's picture.
    showCore(true);
  }
  LOGF("asset '%s' result %d error %s", frame.commandLine, (int)frame.result, lastAssetError_);
  ack();
}

bool App::decodeAsset(std::string_view header, const proto::AssetFrame& frame, const char** error) {
  // MDSIMG,<bytes>,<crc32 hex>,<png|jpg>,<core>
  std::string_view f[4];
  if (proto::splitFields(header.substr(7), f, 4) != 4 || f[1].size() != 8) {
    *error = "header";
    return false;
  }
  if (!checkCrc(f[1], frame.data, frame.length)) {
    *error = "crc";
    return false;
  }
  const bool png = f[2] == "png";
  if (!png && f[2] != "jpg") {
    *error = "format";
    return false;
  }
  if (settings_.fade()) display_.armFade(millis());
  const bool ok = CoreScreen::drawAsset(display_, png ? CoreScreen::AssetFormat::Png : CoreScreen::AssetFormat::Jpeg,
                                        frame.data, frame.length);
  display_.disarmFade();
  if (!ok) {
    *error = "decode";
    return false;
  }
  screen_ = Screen::Core;
  assetValid_ = true;
  assetIsPng_ = png;
  assetLength_ = frame.length;
  return true;
}

bool App::checkCrc(std::string_view hex, const uint8_t* data, size_t length) {
  if (hex.size() != 8) return false;
  uint32_t crc = 0;
  for (char c : hex) {
    const int v = (c >= '0' && c <= '9')   ? c - '0'
                  : (c >= 'a' && c <= 'f') ? c - 'a' + 10
                  : (c >= 'A' && c <= 'F') ? c - 'A' + 10
                                           : -1;
    if (v < 0) return false;
    crc = (crc << 4) | static_cast<uint32_t>(v);
  }
  return proto::crc32(data, length) == crc;
}

void App::handleLogo(std::string_view header, const proto::AssetFrame& frame) {
  // MDSLOGO,<bytes>,<crc32 hex>,<png|jpg>
  std::string_view f[3];
  const char* error = nullptr;
  bool png = true;
  if (frame.result == proto::AssetResult::TooLarge || frame.length > StartupLogo::kMaxBytes) {
    error = "size";
  } else if (frame.result != proto::AssetResult::Ok) {
    error = frame.result == proto::AssetResult::Incomplete ? "incomplete" : "header";
  } else if (proto::splitFields(header.substr(8), f, 3) != 3 || (f[2] != "png" && f[2] != "jpg")) {
    error = "header";
  } else if (!checkCrc(f[1], frame.data, frame.length)) {
    error = "crc";
  } else {
    png = f[2] == "png";
    // Cheap sanity check of the file signature; a picture that still fails to decode at boot
    // falls back to the text start screen.
    static const uint8_t kPngSig[4] = {0x89, 'P', 'N', 'G'};
    const bool sigOk = png ? (frame.length > 8 && memcmp(frame.data, kPngSig, 4) == 0)
                           : (frame.length > 2 && frame.data[0] == 0xFF && frame.data[1] == 0xD8);
    if (!sigOk) {
      error = "format";
    } else if (!logo_.store(frame.data, frame.length, png)) {
      error = "storage";
    }
  }
  char reply[48];
  snprintf(reply, sizeof(reply), "MDSLOGO;%s%s\n", error ? "err=" : "ok", error ? error : "");
  transport_.write(reply);
  if (!error && (screen_ == Screen::Splash || screen_ == Screen::Waiting)) {
    drawSplash(screen_ == Screen::Waiting ? kWaitingText : nullptr);
  }
}

void App::sendLogoStatus() {
  char reply[80];
  if (logo_.present()) {
    snprintf(reply, sizeof(reply), "MDSLOGO;crc=%08lx;bytes=%u;format=%s\n", (unsigned long)logo_.crc(),
             (unsigned)logo_.size(), logo_.isPng() ? "png" : "jpg");
  } else {
    snprintf(reply, sizeof(reply), "MDSLOGO;none\n");
  }
  transport_.write(reply);
}

void App::drawSplash(const char* hint) {
  SplashScreen::Logo logo;
  // Switching the MiSTer on or off shows the MiSTer logo, as the standby screen does; the board's
  // own start screen keeps the start-up picture.
  if (hint == kStartingText || hint == kStoppingText) {
    logo.data = kLogoPng;
    logo.size = sizeof(kLogoPng);
    logo.png = true;
    SplashScreen::draw(display_, "v" MDS_FW_VERSION, hint, &logo);
    return;
  }
  logo.data = logo_.data();
  logo.size = logo_.size();
  logo.png = logo_.isPng();
  SplashScreen::draw(display_, "v" MDS_FW_VERSION, hint, logo_.present() ? &logo : nullptr);
}

void App::onDiscard(proto::DiscardReason reason, size_t length) {
  ++discards_;
  LOGF("discard reason %d, %u bytes", (int)reason, (unsigned)length);
}

void App::handle(const proto::Command& cmd, std::string_view line) {
  using proto::CommandId;
  bool present = true;
  switch (cmd.id) {
    case CommandId::CoreName:  // tty2oled sends the bare name when it has no picture
    case CommandId::MdsCore:
      setCore(cmd.args);
      pictureFormat_ = proto::ImageFormat::None;
      assetValid_ = false;
      showCore(true);
      break;
    case CommandId::ShowCoreName:
      screen_ = Screen::Core;
      CoreScreen::drawNameOnly(display_, std::string_view(coreName_, coreNameLength_));
      break;
    case CommandId::ShowPicture:
      showCore();
      break;

    case CommandId::ClearScreen:
      display_.canvas().fillScreen(theme::kBackground);
      display_.present();
      break;
    case CommandId::ClearBuffer:
      display_.canvas().fillScreen(theme::kBackground);
      break;
    case CommandId::ClearWithTransition:
      clearWithFill(cmd.args);
      break;
    case CommandId::DisplayUpdate:
      display_.present();
      break;
    case CommandId::StartScreen:
      showSplash();
      break;
    case CommandId::TestPicture:
      LegacyCanvas::testPattern(display_);
      break;
    case CommandId::Text:
      if (LegacyCanvas::text(display_, cmd.args, &present)) {
        if (present) display_.present();
      } else {
        LegacyCanvas::parameterError(display_, line);
      }
      break;
    case CommandId::Geometry:
      if (LegacyCanvas::geometry(display_, cmd.args, &present)) {
        if (present) display_.present();
      } else {
        LegacyCanvas::parameterError(display_, line);
      }
      break;

    case CommandId::DisplayOff:
      display_.sleep();
      break;
    case CommandId::DisplayOn:
      display_.wake();
      break;
    case CommandId::Contrast:
      setContrast(cmd.args);
      break;
    case CommandId::Rotate:
      setRotation(cmd.args);
      break;

    case CommandId::HardwareInfo:
      sendHardwareInfo();
      break;
    case CommandId::MdsPing: {
      // The uptime lets the daemon notice that the board restarted and resend the core.
      char reply[40];
      const int n = snprintf(reply, sizeof(reply), "MDSPONG;up=%lu\n", (unsigned long)millis());
      if (n > 0) transport_.write(reply, n);
      handlePresence(presence_.onHeartbeat(millis()));
      startingUp_ = false;
      break;
    }
    case CommandId::MdsPower:
      if (cmd.args == "halting") onHalting();
      if (cmd.args == "down") onDown();
      break;
    case CommandId::MdsCfg:
      handleConfig(cmd.args);
      break;
    case CommandId::MdsLogo:
      sendLogoStatus();
      break;
    case CommandId::MdsSta:
      station_.onHost(cmd.args);
      break;
    case CommandId::MdsSys: {
      const bool had = systems_.available();
      systems_.onHost(cmd.args);
      if (had != systems_.available() && screen_ == Screen::Menu) showMenu(false);
      break;
    }
    case CommandId::MdsWifi:
      if (cmd.args.substr(0, 7) == "dongle,") {
        wifiDongle_ = cmd.args.substr(7) == "1";
      } else {
        wifi_.onHost(cmd.args, millis());
      }
      break;
    case CommandId::MdsVol: {
      std::string_view f[2];
      int32_t level = 0, muted = 0;
      if (proto::splitFields(cmd.args, f, 2) == 2 && proto::parseInt(f[0], level) && proto::parseInt(f[1], muted)) {
        touchButtons_.setVolume(level, muted != 0);
      }
      break;
    }
    case CommandId::MdsNet: {
      const size_t n = cmd.args.size() < sizeof(ip_) - 1 ? cmd.args.size() : sizeof(ip_) - 1;
      memcpy(ip_, cmd.args.data(), n);
      ip_[n] = '\0';
      if (screen_ == Screen::Menu) showMenu(false);
      break;
    }
    case CommandId::SetTime:
      setTime(cmd.args);
      break;
    case CommandId::MdsHang:
#if MDS_TEST_COMMANDS
      LOGF("MDSHANG: spinning until the watchdog fires");
      for (;;) {
      }
#endif
      break;
    case CommandId::MdsInfo:
      sendInfo();
      break;
    case CommandId::MdsShot:
      startScreenshot();
      break;
    case CommandId::SetTtyAck: {
      int32_t v = 1;
      if (proto::parseInt(cmd.args, v)) sendTtyAck_ = v != 0;
      break;
    }
    case CommandId::Reset:
      restartPending_ = true;
      restartAtMs_ = millis() + kRestartDelayMs;
      break;

    default:
      // Accepted and ignored: QWERTZ, CMDNULL, CMDSAVER, CMDSWSAVER, CMDSECD, unknown CMD*.
      break;
  }
}

void App::setCore(std::string_view name) {
  coreNameLength_ = name.size() < kMaxCoreName ? name.size() : kMaxCoreName;
  memcpy(coreName_, name.data(), coreNameLength_);
  coreName_[coreNameLength_] = '\0';
}

void App::showCore(bool fade) {
  if (fade && nextCoreFades_ && settings_.fade()) display_.armFade(millis());
  nextCoreFades_ = true;
  screen_ = Screen::Core;
  const std::string_view name(coreName_, coreNameLength_);
  // The menu gets the clock screen unless a picture for it arrived (art/MENU.png, MENU.gsc).
  if (!assetValid_ && pictureFormat_ == proto::ImageFormat::None && name == "MENU" && clock_.valid()) {
    showMenu(false);
    display_.disarmFade();
    return;
  }
  struct Disarm {
    DisplayManager& d;
    ~Disarm() { d.disarmFade(); }
  } disarm{display_};
  if (assetValid_ && CoreScreen::drawAsset(display_, assetIsPng_ ? CoreScreen::AssetFormat::Png : CoreScreen::AssetFormat::Jpeg,
                                           assetBuffer_, assetLength_)) {
    return;
  }
  if (pictureFormat_ == proto::ImageFormat::None) {
    CoreScreen::drawNameOnly(display_, name);
    return;
  }
  const size_t length = pictureFormat_ == proto::ImageFormat::Xbm ? proto::kXbmBytes : proto::kGscBytes;
  CoreScreen::drawWithArtwork(display_, name, pictureFormat_, picture_, length);
}

void App::showSplash() {
  screen_ = Screen::Splash;
  drawSplash(nullptr);
}

void App::showMenu(bool dimmed) {
  screen_ = dimmed ? Screen::IdleClock : Screen::Menu;
  shownMinute_ = clock_.minuteStamp(millis());
  // The Wi-Fi screen or the system picker is on top; redrawCurrent() brings the clock back.
  if (wifi_.active() || systems_.active()) return;
  MenuScreen::draw(display_, clock_.local(millis()), ip_, dimmed, settings_.clockFont(), station_.ip(),
                   !dimmed && systems_.available());
}

void App::setTime(std::string_view args) {
  // Epoch seconds (10 digits today): too long for parseInt.
  int64_t v = 0;
  if (args.empty() || args.size() > 12) return;
  for (char c : args) {
    if (c < '0' || c > '9') return;
    v = v * 10 + (c - '0');
  }
  clock_.set(v, millis());
  if (screen_ == Screen::Menu || screen_ == Screen::IdleClock) showMenu(screen_ == Screen::IdleClock);
}

bool App::changesScreen(proto::CommandId id) {
  using proto::CommandId;
  switch (id) {
    case CommandId::CoreName:
    case CommandId::MdsCore:
    case CommandId::ShowCoreName:
    case CommandId::ShowPicture:
    case CommandId::ClearScreen:
    case CommandId::ClearWithTransition:
    case CommandId::DisplayUpdate:
    case CommandId::StartScreen:
    case CommandId::TestPicture:
    case CommandId::Text:
    case CommandId::Geometry:
    case CommandId::DisplayOn:
      return true;
    default:
      return false;  // pings, settings, queries and tty2oled startup noise do not wake the screen
  }
}

void App::endRestartDark() {
  if (!restartDark_) return;
  restartDark_ = false;
  display_.setBacklightOn(true);
}

void App::pollRestart() {
  if (restartDark_ && millis() - resetTapMs_ >= kRestartDarkMs) {
    setCore("MENU");
    pictureFormat_ = proto::ImageFormat::None;
    assetValid_ = false;
    showCore();
    endRestartDark();
  }
  if (restartGrace_ && millis() - resetTapMs_ >= kRestartGraceMs) {
    restartGrace_ = false;
    if (presence_.hostLost()) {
      screen_ = Screen::Waiting;
      drawSplash(kWaitingText);
    }
  }
}

void App::noteActivity() {
  endRestartDark();
  restartGrace_ = false;
  // A new screen from the host (a game was loaded) wins over the Wi-Fi screen and the picker.
  wifi_.close();
  systems_.close();
  systems_.close();
  if (presence_.onActivity(millis()) == presence::Event::Wake) {
    LOGF("idle sleep: wake");
    display_.setBacklightOn(true);
    // The idle clock replaced the core screen; whatever comes next draws over it anyway.
    if (screen_ == Screen::IdleClock) screen_ = Screen::Other;
  }
  if (screen_ == Screen::Waiting || screen_ == Screen::Splash) screen_ = Screen::Other;
}

void App::redrawCurrent() {
  if (screen_ == Screen::Menu || screen_ == Screen::IdleClock) {
    showMenu(screen_ == Screen::IdleClock);
  } else if (coreNameLength_ > 0) {
    showCore();
  } else {
    drawSplash(screen_ == Screen::Waiting ? kWaitingText : nullptr);
  }
}

void App::pollTouch() {
  if (powerState_ == Power::Off) {
    pollStandbyTouch();
    return;
  }
  if (powerState_ == Power::Stopping) return;
  if (wifi_.active()) {
    const WifiScreen::Result w = wifi_.poll(millis());
    if (w.activity) presence_.onActivity(millis());
    if (w.closed) redrawCurrent();
    return;
  }
  if (systems_.active()) {
    const SystemsScreen::Result s = systems_.poll(millis());
    if (s.activity) presence_.onActivity(millis());
    if (s.closed) redrawCurrent();
    return;
  }
  const std::string_view core(coreName_, coreNameLength_);
  touchButtons_.setWifiSlot(wifiDongle_ && core == "MENU");
  if (screen_ == Screen::Menu && systems_.available()) {
    const MenuScreen::Rect b = MenuScreen::systemsButton(display_);
    touchButtons_.setShortcut(b.x - 8, b.y - 8, b.w + 16, b.h + 14);
  } else {
    touchButtons_.setShortcut(0, 0, 0, 0);
  }
  const TouchButtons::Result t = touchButtons_.poll(millis());
  // A tap counts as activity for idle sleep, but unlike a host command it leaves the start and
  // "Waiting for MiSTer" screens as they are.
  if (t.activity) endRestartDark();
  if (t.activity && presence_.onActivity(millis()) == presence::Event::Wake) {
    LOGF("idle sleep: wake (touch)");
    display_.setBacklightOn(true);
    if (screen_ == Screen::IdleClock && coreNameLength_ > 0) showCore();
  }
  if (t.pressed && strcmp(t.pressed, "wifi") == 0) {
    // Handled here, not by the host: the Wi-Fi screen asks the daemon for what it needs.
    wifi_.open(millis());
    return;
  }
  if (t.pressed && strcmp(t.pressed, "systems") == 0) {
    systems_.open(millis());
    return;
  }
  if (t.pressed && strcmp(t.pressed, "poweroff") == 0) {
    requestPowerOff();
    return;
  }
  if (t.pressed && strcmp(t.pressed, "bright") == 0) {
    // This display's own setting: kept here, the host is not told.
    setBrightnessLevel(t.level);
    return;
  }
  if (t.pressed) {
    char line[24];
    if (strcmp(t.pressed, "vol") == 0) {
      snprintf(line, sizeof(line), "MDSBTN,vol,%d\n", t.level);
    } else {
      snprintf(line, sizeof(line), "MDSBTN,%s\n", t.pressed);
    }
    transport_.write(line);
    LOGF("button %s", t.pressed);
    if (strcmp(t.pressed, "reset") == 0) {
      restartDark_ = restartGrace_ = true;
      resetTapMs_ = millis();
      ip_[0] = '\0';  // the daemon sends the addresses again when it starts
      display_.setBacklightOn(false);
    }
  }
}

void App::handlePresence(presence::Event event) {
  // Shutting down or off: no MiSTer is expected, the screen stays as it is.
  if (powerState_ != Power::On) return;
  switch (event) {
    case presence::Event::HostLost:
      LOGF("host lost");
      if (restartGrace_ || startingUp_) break;  // expected while the MiSTer reboots; pollRestart() handles it
      wifi_.close();
      systems_.close();
      screen_ = Screen::Waiting;
      drawSplash(kWaitingText);
      break;
    case presence::Event::SplashWaiting:
      if (screen_ == Screen::Splash) drawSplash(kWaitingText);
      break;
    case presence::Event::IdleSleep:
      LOGF("idle sleep");
      if (settings_.idleClock() && clock_.valid()) {
        showMenu(true);  // a dim clock instead of a dark screen
      } else {
        display_.setBacklightOn(false);
      }
      break;
    case presence::Event::Wake:
      display_.setBacklightOn(true);
      break;
    case presence::Event::HostBack:  // the daemon resends the core when it reconnects
    case presence::Event::None:
      break;
  }
}

void App::handleConfig(std::string_view args) {
  // MDSCFG                -> list
  // MDSCFG,idle,<minutes> -> idle sleep after <minutes> without a core change (0 = never)
  // MDSCFG,fade,<0|1>     -> backlight dip on core changes
  // MDSCFG,idleclock,<0|1> -> when idle, a dim clock instead of backlight off
  // MDSCFG,clockfont,<n>  -> font of the time on the clock screen (MenuScreen::kClockFonts)
  // MDSCFG,brightness,<0-7> -> backlight in the steps of the touch row; CMDCON is ignored after it
  // MDSCFG,autoon,<0|1>  -> power relay: switch the MiSTer on when the box gets power
  // MDSCFG,logo,0         -> delete the stored start-up picture
  // MDSCFG,reset          -> defaults
  std::string_view f[2];
  const size_t n = args.empty() ? 0 : proto::splitFields(args, f, 2);
  int32_t v = 0;
  if (n == 2 && f[0] == "idle" && proto::parseInt(f[1], v) && v >= 0 && v <= Settings::kMaxIdleMinutes) {
    settings_.setIdleMinutes(static_cast<uint16_t>(v));
    presence_.setIdleTimeout(settings_.idleMinutes() * kMsPerMinute);
  } else if (n == 2 && f[0] == "fade" && proto::parseInt(f[1], v) && (v == 0 || v == 1)) {
    settings_.setFade(v == 1);
  } else if (n == 2 && f[0] == "idleclock" && proto::parseInt(f[1], v) && (v == 0 || v == 1)) {
    settings_.setIdleClock(v == 1);
  } else if (n == 2 && f[0] == "brightness" && proto::parseInt(f[1], v) && v >= 0 && v <= TouchButtons::kLevelMax) {
    setBrightnessLevel(v);
  } else if (n == 2 && f[0] == "clockfont" && proto::parseInt(f[1], v) && v >= 0 &&
             v < MenuScreen::kClockFontCount) {
    settings_.setClockFont(static_cast<uint8_t>(v));
    if (screen_ == Screen::Menu || screen_ == Screen::IdleClock) showMenu(screen_ == Screen::IdleClock);
  } else if (n == 2 && f[0] == "autoon" && proto::parseInt(f[1], v) && (v == 0 || v == 1)) {
    settings_.setAutoOn(v == 1);
  } else if (n == 2 && f[0] == "logo" && f[1] == "0") {
    logo_.clear();
    if (screen_ == Screen::Splash || screen_ == Screen::Waiting) {
      drawSplash(screen_ == Screen::Waiting ? kWaitingText : nullptr);
    }
  } else if (n == 1 && f[0] == "reset") {
    settings_.resetToDefaults();
    presence_.setIdleTimeout(0);
    display_.setBrightness(Settings::backlightFor(settings_.contrast()));
    touchButtons_.setBrightness(levelForContrast(settings_.contrast()));
    display_.setRotation(cfg::kRotationNormal);
  } else if (n != 0) {
    transport_.write("MDSCFG;err=args\n");
    return;
  }
  sendConfig();
}

void App::sendConfig() {
  char line[160];
  const int n = snprintf(line, sizeof(line),
                         "MDSCFG;contrast=%u;rotate=%d;idle=%u;fade=%d;idleclock=%d;screenbrightness=%d;clockfont=%u;"
                         "brightness=%d;autoon=%d\n",
                         settings_.contrast(), settings_.rotated() ? 1 : 0, settings_.idleMinutes(),
                         settings_.fade() ? 1 : 0, settings_.idleClock() ? 1 : 0, settings_.screenBrightness() ? 1 : 0,
                         settings_.clockFont(), levelForContrast(settings_.contrast()), settings_.autoOn() ? 1 : 0);
  if (n > 0) transport_.write(line, n);
}

void App::setContrast(std::string_view args) {
  int32_t contrast = 0;
  if (!proto::parseInt(args, contrast)) return;
  if (settings_.screenBrightness()) return;
  contrast = contrast < 0 ? 0 : (contrast > 255 ? 255 : contrast);
  settings_.setContrast(static_cast<uint8_t>(contrast));
  display_.setBrightness(Settings::backlightFor(settings_.contrast()));
  touchButtons_.setBrightness(levelForContrast(settings_.contrast()));
}

// From the touch row or MDSCFG,brightness: stored, and from then on CMDCON is ignored.
void App::setBrightnessLevel(int level) {
  settings_.setContrast(contrastForLevel(level));
  settings_.setScreenBrightness(true);
  display_.setBrightness(Settings::backlightFor(settings_.contrast()));
  touchButtons_.setBrightness(level);
  LOGF("brightness %d (contrast %u)", level, settings_.contrast());
}

// The brightness row has kLevelMax + 1 steps over the whole CMDCON range.
uint8_t App::contrastForLevel(int level) {
  return static_cast<uint8_t>(level * 255 / TouchButtons::kLevelMax);
}

int App::levelForContrast(uint8_t contrast) {
  return (contrast * TouchButtons::kLevelMax + 127) / 255;
}

void App::setRotation(std::string_view args) {
  int32_t r = 0;
  proto::parseInt(args, r);  // like toInt(): junk means 0
  settings_.setRotated(r == 1);
  display_.setRotation(r == 1 ? cfg::kRotationFlipped : cfg::kRotationNormal);
}

void App::clearWithFill(std::string_view args) {
  // CMDCLST,t,c: fill with grey level c. The transition t is ignored for now.
  std::string_view f[2];
  int32_t level = 0;
  if (proto::splitFields(args, f, 2) == 2) proto::parseInt(f[1], level);
  pictureFormat_ = proto::ImageFormat::None;  // the sketch clears its picture buffer too
  display_.canvas().fillScreen(LegacyCanvas::grey(level));
  display_.present();
}

void App::sendHardwareInfo() {
  // installer.sh reads this with `read`, takes ${BLA:0:9} as the board id and ${SWver:10} as
  // the version. The id is exactly 9 characters and unknown to the tty2oled flasher; the version
  // starts with a letter, so it compares newer than any tty2oled build date and no update is offered.
  transport_.write(MDS_BOARD_ID ";MDS-" MDS_FW_VERSION ";\n");
}

void App::sendInfo() {
  char line[320];
  const int n = snprintf(line, sizeof(line),
                         "MDSINFO;fw=%s;board=" MDS_BOARD_NAME ";psram=%u;fb=%s;uptime_ms=%lu;reset=%d;"
                         "lines=%lu;images=%lu;discards=%lu;txdrop=%lu;txstale=%lu;lastimg=%d:%u;asseterr=%s;"
                         "host=%s;idle=%s;power=%s;sta=%s;heap=%u;core=%s\n",
                         MDS_FW_VERSION, (unsigned)ESP.getPsramSize(), display_.hasFramebuffer() ? "psram" : "direct",
                         (unsigned long)millis(), (int)esp_reset_reason(), (unsigned long)linesReceived_,
                         (unsigned long)imagesReceived_, (unsigned long)discards_,
                         (unsigned long)transport_.droppedWrites(), (unsigned long)transport_.staleFlushes(),
                         (int)lastImageResult_, (unsigned)lastImageBytes_, lastAssetError_,
                         presence_.heartbeatSeen() ? (presence_.hostLost() ? "lost" : "ok") : "none",
                         presence_.idleSleeping() ? "sleep" : "awake",
                         !PowerSwitch::available()           ? "none"
                         : powerState_ == Power::On          ? "on"
                         : powerState_ == Power::Stopping    ? "stopping"
                                                             : "off",
                         station_.stateName(), (unsigned)ESP.getFreeHeap(), coreName_);
  if (n > 0) transport_.write(line, static_cast<size_t>(n) < sizeof(line) ? n : sizeof(line) - 1);
}

void App::startScreenshot() {
  if (shotLeft_ > 0 || !display_.hasFramebuffer()) {
    transport_.write("MDSSHOT,0,0,0\n");
    return;
  }
  char header[48];
  const int n = snprintf(header, sizeof(header), "MDSSHOT,%d,%d,%u\n", display_.width(), display_.height(),
                         (unsigned)display_.framebufferSize());
  if (n <= 0 || !transport_.write(header, n)) return;
  shotData_ = display_.framebufferBytes();
  shotLeft_ = display_.framebufferSize();
  shotProgressMs_ = millis();
}

void App::pumpScreenshot(uint32_t nowMs) {
  if (shotLeft_ == 0) return;
  // Leave room so acks and replies are never refused while a screenshot is going out.
  constexpr size_t kReserve = 128;
  const size_t room = transport_.writeRoom();
  if (room > kReserve) {
    size_t n = room - kReserve;
    if (n > shotLeft_) n = shotLeft_;
    transport_.write(reinterpret_cast<const char*>(shotData_), n);
    shotData_ += n;
    shotLeft_ -= n;
    shotProgressMs_ = nowMs;
  } else if (nowMs - shotProgressMs_ >= kShotStallMs) {
    shotLeft_ = 0;
  }
}

void App::ack() {
  if (sendTtyAck_) transport_.write("ttyack;");
}

void App::powerOn(bool byHost) {
  power_.set(true);
  settings_.setPowerOn(true);
  powerState_ = Power::On;
  standbyDown_ = standbyPrompt_ = false;
  display_.setBrightness(Settings::backlightFor(settings_.contrast()));
  if (byHost) {
    LOGF("power: data from the MiSTer while off, relay on");
    showSplash();  // whatever the host sends next draws over it
    return;
  }
  LOGF("power: on (touch)");
  startingUp_ = true;
  powerOnMs_ = millis();
  screen_ = Screen::Splash;
  drawSplash(kStartingText);
}

void App::requestPowerOff() {
  wifi_.close();
  systems_.close();
  endRestartDark();
  restartGrace_ = startingUp_ = false;
  powerState_ = Power::Stopping;
  display_.setBacklightOn(true);
  screen_ = Screen::Other;
  drawSplash(kStoppingText);
  if (presence_.heartbeatSeen() && !presence_.hostLost()) {
    transport_.write("MDSBTN,poweroff\n");
    cutAtMs_ = millis() + kHaltReplyMs;
    LOGF("power: off requested, waiting for the MiSTer");
  } else {
    cutAtMs_ = millis() + kNoHostCutMs;
    LOGF("power: off requested, no MiSTer daemon: cutting");
  }
}

// MDSPOWER,halting: after our request, or the MiSTer shutting down by itself (the daemon sends it
// for any poweroff it starts).
void App::onHalting() {
  if (!PowerSwitch::available() || powerState_ == Power::Off) return;
  if (powerState_ == Power::On) {
    wifi_.close();
    systems_.close();
    endRestartDark();
    restartGrace_ = startingUp_ = false;
    powerState_ = Power::Stopping;
    display_.setBacklightOn(true);
    screen_ = Screen::Other;
    drawSplash(kStoppingText);
  }
  cutAtMs_ = millis() + kHaltMs;
  LOGF("power: MiSTer halting, cut in %lu ms", (unsigned long)kHaltMs);
}

// MDSPOWER,down: the MiSTer is past umount; init still syncs and kills the rest for about a second.
void App::onDown() {
  if (!PowerSwitch::available() || powerState_ == Power::Off) return;
  if (powerState_ == Power::On) onHalting();
  cutAtMs_ = millis() + kDownMs;
  LOGF("power: MiSTer down, cut in %lu ms", (unsigned long)kDownMs);
}

void App::cutPower() {
  standbyPrompt_ = false;
  power_.set(false);
  settings_.setPowerOn(false);
  powerState_ = Power::Off;
  startingUp_ = restartGrace_ = restartDark_ = false;
  ip_[0] = '\0';
  setCore("");
  pictureFormat_ = proto::ImageFormat::None;
  assetValid_ = false;
  display_.setBacklightOn(true);
  display_.setBrightness(Settings::backlightFor(0));
  showStandby();
}

void App::showStandby() {
  screen_ = Screen::Standby;
  if (standbyPrompt_) {
    StandbyScreen::drawPrompt(display_, station_.ip());
  } else if (clock_.valid()) {
    shownMinute_ = clock_.minuteStamp(millis());
    const wallclock::DateTime now = clock_.local(millis());
    StandbyScreen::drawIdle(display_, &now, station_.ip());
  } else {
    shownMinute_ = -1;
    StandbyScreen::drawIdle(display_, nullptr, station_.ip());
  }
}

void App::setStandbyPrompt(bool on) {
  standbyPrompt_ = on;
  promptUntilMs_ = millis() + kPromptMs;
  display_.setBrightness(Settings::backlightFor(on ? settings_.contrast() : 0));
  showStandby();
}

void App::pollPower() {
  if (!PowerSwitch::available()) return;
  const uint32_t now = millis();
  if (powerState_ == Power::Stopping && static_cast<int32_t>(now - cutAtMs_) >= 0) cutPower();
  if (powerState_ == Power::Off && screen_ == Screen::Standby) {
    if (standbyPrompt_ && !standbyDown_ && static_cast<int32_t>(now - promptUntilMs_) >= 0) {
      setStandbyPrompt(false);
    } else if (!standbyPrompt_ && clock_.valid() && clock_.minuteStamp(now) != shownMinute_) {
      showStandby();
    }
  }
  if (startingUp_ && now - powerOnMs_ >= kStartGraceMs) {
    startingUp_ = false;
    if (screen_ == Screen::Splash) {
      screen_ = Screen::Waiting;
      drawSplash(kWaitingText);
    }
  }
}

void App::pollStandbyTouch() {
  const uint32_t now = millis();
  if (now - standbyPollMs_ < kStandbyPollMs) return;
  standbyPollMs_ = now;
  int x, y;
  if (display_.touched(&x, &y)) {
    standbyDown_ = true;
    return;
  }
  // The finger left the glass: that is the tap. The first one shows the prompt, the second one
  // (while it shows) switches the MiSTer on.
  if (!standbyDown_) return;
  standbyDown_ = false;
  if (standbyPrompt_) {
    standbyPrompt_ = false;
    powerOn(false);
  } else {
    setStandbyPrompt(true);
  }
}
