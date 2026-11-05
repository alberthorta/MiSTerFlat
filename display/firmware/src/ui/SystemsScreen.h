#pragma once

#include <stdint.h>

#include <string_view>

#include "hal/Lgfx.h"
#include "transport/SerialTransport.h"
#include "ui/DisplayManager.h"

// The quick launch on touch boards, opened from the Systems button of the menu clock. Two cover
// flows: the systems, then the games of the one tapped. Drag to move; a tap on a side cover brings
// it to the middle; a tap on the middle system opens its games, on the middle game starts it
// (MDSSYS,play,<i>,<j>). The back button (top left) goes from the games to the systems and from the
// systems to the clock; 10 s without a touch goes back to the clock.
//
// The host owns the lists (see docs/protocol.md, MDSSYS): systems after it sees the board, games
// when a system is opened. Covers are asked for when needed and kept in PSRAM, smaller, until the
// host sends a different crc. Game covers are kept for one system at a time.
class SystemsScreen {
 public:
  SystemsScreen(DisplayManager& display, SerialTransport& transport) : display_(display), transport_(transport) {}

  // At least one system: the menu clock shows the Systems button.
  bool available() const { return systemCount_ > 0; }
  bool active() const { return active_; }
  void open(uint32_t nowMs);
  void close() { active_ = false; }
  // MDSSYS lines from the host (the text after "MDSSYS,").
  void onHost(std::string_view args);
  // A cover (MDSSYSIMG,<bytes>,<crc32>,<png|jpg>,<i>[,<j>]), crc already checked. game -1: the
  // cover of system `system`.
  void onCover(int system, int game, uint32_t crc, bool png, const uint8_t* data, size_t length);

  struct Result {
    bool activity = false;  // any touch
    bool closed = false;    // closed by the user or by the timeout: the caller redraws its screen
    bool loading = false;   // a game was started: the host sends its picture next
  };
  Result poll(uint32_t nowMs);

  static constexpr int kMaxSystems = 12;
  static constexpr int kMaxGames = 20;

 private:
  struct Item {
    char name[41];
    uint32_t crc;      // of the host's picture (0 = none)
    uint32_t haveCrc;  // of the cover we hold (0 = none)
    bool requested;
    LGFX_Sprite* cover;  // full brightness
    LGFX_Sprite* dim;    // darker copy for the side positions
  };
  // Size and spacing of one cover flow.
  struct Geometry {
    int w, h;       // cover size, drawn 1:1 in the middle
    int centreY;
    float nearX;    // the first neighbour is this far from the middle
    float farX;     // and each one after it this much more
    float scale;    // host picture -> cover
  };
  enum class Level : uint8_t { Systems, Games };

  Item* items() { return level_ == Level::Systems ? systems_ : games_; }
  int count() const { return level_ == Level::Systems ? systemCount_ : gameCount_; }
  const Geometry& geometry() const;
  float maxPos() const { return count() > 0 ? count() - 1 : 0; }

  void openGames(int system);
  void backToSystems();
  void requestCovers();
  void tap(int x, int y);
  void draw();
  void drawCover(const Item& item, float d);
  bool makeSprites(Item& item, const Geometry& g);
  void setCover(Item& item, const Geometry& g, uint32_t crc, bool png, const uint8_t* data, size_t length);
  static bool parseItem(std::string_view crcHex, std::string_view name, Item& item);

  DisplayManager& display_;
  SerialTransport& transport_;
  Item systems_[kMaxSystems] = {};
  Item games_[kMaxGames] = {};
  int systemCount_ = 0;
  int gameCount_ = 0;
  int gamesOf_ = -1;        // the system whose games are in games_
  // Waiting for the game list: -2 until its first line, then the number announced; -1 = not waiting.
  int gamesExpected_ = -1;
  bool active_ = false;
  bool closedByHost_ = false;  // the host sent a new list while open: back to the clock
  bool dirty_ = false;
  Level level_ = Level::Systems;

  float pos_ = 0;     // the item in the middle; fractions while moving
  float target_ = 0;  // where pos_ goes after a drag or a tap
  float systemPos_ = 0;  // pos_ of the systems while the games show
  bool down_ = false;
  bool moved_ = false;
  int downX_ = 0;
  int downY_ = 0;
  int lastX_ = 0;
  float downPos_ = 0;
  float velocity_ = 0;  // pixels per ms, smoothed, while dragging
  uint32_t lastMoveMs_ = 0;
  uint32_t lastTouchMs_ = 0;
  uint32_t lastPollMs_ = 0;
  uint32_t lastFrameMs_ = 0;
  int playing_ = -1;  // the game just started
};
