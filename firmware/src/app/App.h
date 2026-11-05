#pragma once

#include <stdint.h>

#include <string_view>

#include "Command.h"
#include "Presence.h"
#include "ProtocolParser.h"
#include "WallClock.h"
#include "app/Settings.h"
#include "app/StartupLogo.h"
#include "hal/PowerSwitch.h"
#include "net/Station.h"
#include "transport/SerialTransport.h"
#include "ui/DisplayManager.h"
#include "ui/TouchButtons.h"
#include "ui/WifiScreen.h"

// Glue between the serial protocol and the screens. The parser only produces events; this class
// keeps the state (current core, its picture, display settings) and decides what to draw.
class App : public proto::ParserListener {
 public:
  App(DisplayManager& display, SerialTransport& transport, Settings& settings, StartupLogo& logo,
      PowerSwitch& power);

  void begin();
  void loop();
  void showStartScreen();

  // ParserListener
  void onLine(const char* line, size_t length) override;
  void onImage(const proto::ImageFrame& frame) override;
  void onAsset(const proto::AssetFrame& frame) override;
  void onDiscard(proto::DiscardReason reason, size_t length) override;

  // True while a picture is arriving: the main loop then skips its idle delay.
  bool receiving() const { return parser_.receivingBinary(); }

 private:
  static constexpr size_t kMaxCoreName = 63;

  enum class Screen : uint8_t { Splash, Core, Menu, IdleClock, Waiting, Standby, Other };
  // The MiSTer power relay. Boards without one are always On.
  enum class Power : uint8_t { On, Stopping, Off };

  void handle(const proto::Command& cmd, std::string_view line);
  bool handleTestCommand(std::string_view line);
  static bool changesScreen(proto::CommandId id);
  void noteActivity();
  void pollTouch();
  void handlePresence(presence::Event event);
  void handleConfig(std::string_view args);
  void sendConfig();
  void setCore(std::string_view name);
  // fade: the core changed (dip the backlight if enabled); false for redraws of the same core.
  void showCore(bool fade = false);
  void showMenu(bool dimmed);
  void drawSplash(const char* hint);
  void handleLogo(std::string_view header, const proto::AssetFrame& frame);
  void sendLogoStatus();
  static bool checkCrc(std::string_view hex, const uint8_t* data, size_t length);
  void setTime(std::string_view args);
  void showSplash();
  void setContrast(std::string_view args);
  void setBrightnessLevel(int level);
  static uint8_t contrastForLevel(int level);
  static int levelForContrast(uint8_t contrast);
  void setRotation(std::string_view args);
  void clearWithFill(std::string_view args);
  void sendHardwareInfo();
  void sendInfo();
  void ack();
  void powerOn(bool byHost);
  void requestPowerOff();
  void onHalting();
  void onDown();
  void cutPower();
  void showStandby();
  void pollPower();
  void pollStandbyTouch();
  bool decodeAsset(std::string_view header, const proto::AssetFrame& frame, const char** error);
  void startScreenshot();
  void pumpScreenshot(uint32_t nowMs);

  DisplayManager& display_;
  SerialTransport& transport_;
  Settings& settings_;
  StartupLogo& logo_;
  PowerSwitch& power_;
  proto::ProtocolParser parser_;
  presence::Presence presence_;
  TouchButtons touchButtons_{display_};
  WifiScreen wifi_{display_, transport_};
  Station station_{transport_};
  char shownBoardIp_[16] = {};  // the board's own address as last drawn
  bool wifiDongle_ = false;  // MDSWIFI,dongle,<0|1> from the daemon
  void redrawCurrent();
  Screen screen_ = Screen::Splash;
  wallclock::WallClock clock_;
  int64_t shownMinute_ = -1;  // minute on the clock screen, to redraw when it changes
  char ip_[48] = {};
  // CMDCOR's transition: 0 means "no effect" for that core change.
  bool nextCoreFades_ = true;

  char coreName_[kMaxCoreName + 1] = {};
  size_t coreNameLength_ = 0;
  // The last received picture (CMDCOR/CMDAPD), kept for CMDSPIC.
  uint8_t picture_[proto::kImageBufferBytes] = {};
  proto::ImageFormat pictureFormat_ = proto::ImageFormat::None;
  // MDSIMG pictures live in PSRAM (the parser writes them there). assetValid_ says whether
  // the buffer holds the current core's picture, for CMDSPIC.
  uint8_t* assetBuffer_ = nullptr;
  size_t assetLength_ = 0;
  bool assetValid_ = false;
  bool assetIsPng_ = true;

  // Screenshot being streamed out (MDSSHOT), a little per loop.
  const uint8_t* shotData_ = nullptr;
  size_t shotLeft_ = 0;
  uint32_t shotProgressMs_ = 0;

  // RESET was tapped on the touch buttons. The board stays powered and keeps its clock while the
  // MiSTer reboots, and a rebooted MiSTer starts in the menu. So: dark at once, then after 2 s
  // the menu clock, as if the MiSTer were back already; the daemon sends the same screen when it
  // starts (about 19 s after the reset). "Waiting for MiSTer" is held back for a while meanwhile.
  bool restartDark_ = false;
  bool restartGrace_ = false;
  uint32_t resetTapMs_ = 0;
  void endRestartDark();
  void pollRestart();

  Power powerState_ = Power::On;
  uint32_t cutAtMs_ = 0;      // Stopping: open the relay then
  // Switched on from standby: "Starting MiSTer" until the daemon's first ping, "Waiting for MiSTer"
  // only after kStartGraceMs (the MiSTer boots in about 20 s).
  bool startingUp_ = false;
  uint32_t powerOnMs_ = 0;
  bool standbyDown_ = false;  // a finger is on the standby screen
  uint32_t standbyPollMs_ = 0;

  bool sendTtyAck_ = true;
  bool restartPending_ = false;
  uint32_t restartAtMs_ = 0;

  uint32_t linesReceived_ = 0;
  uint32_t imagesReceived_ = 0;
  uint32_t discards_ = 0;
  proto::ImageResult lastImageResult_ = proto::ImageResult::NoData;
  size_t lastImageBytes_ = 0;
  const char* lastAssetError_ = "none";
};
