#pragma once

// Byte-stream framing for the tty2oled serial protocol. Pure C++ (no Arduino), so it runs in
// the native unit tests. Time is passed in, never read.
//
// Framing, as implemented by the tty2oled sketch (see docs/protocol.md):
// - Text lines end with '\n'. A trailing '\r' is dropped. Like Serial.readStringUntil() with a
//   500 ms timeout, a partial line is also accepted after 500 ms of silence.
// - A line starting with "CMDCOR" or "CMDAPD" is followed by raw picture bytes with no length
//   header: 2048 bytes (XBM) or 8192 bytes (GSC). The picture ends at 8192 bytes or after
//   500 ms without a new byte.
// - MiSTerLily extension: a line "MDSIMG,<bytes>,..." or "MDSLOGO,<bytes>,..." is followed by
//   exactly <bytes> raw bytes (a PNG or JPEG file). Unlike CMDCOR the length is announced, so
//   nothing is guessed.

#include <stddef.h>
#include <stdint.h>

namespace proto {

constexpr size_t kMaxLineLength = 255;
constexpr size_t kXbmBytes = 2048;  // 256x64, 1 bpp
constexpr size_t kGscBytes = 8192;  // 256x64, 4 bpp
constexpr size_t kImageBufferBytes = kGscBytes;

constexpr uint32_t kLineTimeoutMs = 500;
// The host sleeps 0.2 s between the command line and the data; allow some extra margin.
constexpr uint32_t kImageFirstByteTimeoutMs = 1000;
constexpr uint32_t kImageIdleTimeoutMs = 500;

enum class ImageFormat : uint8_t { None, Xbm, Gsc };

enum class ImageResult : uint8_t {
  Ok,
  NoData,     // the command came, the picture bytes never did
  BadLength,  // bytes stopped at a length that is neither 2048 nor 8192
};

struct ImageFrame {
  const char* commandLine;  // "CMDCOR,<core>[,<t>]" or "CMDAPD,<core>"
  ImageResult result;
  ImageFormat format;
  const uint8_t* data;  // valid only during the callback
  size_t length;
};

// MDSIMG payloads: a whole screen as PNG/JPEG. Photo-like PNGs at 320x170 can exceed 150 KB.
constexpr size_t kMaxAssetBytes = 512 * 1024;
// The sender writes the payload right after the line; a pause this long means it is gone.
constexpr uint32_t kAssetIdleTimeoutMs = 1000;

enum class AssetResult : uint8_t {
  Ok,
  BadHeader,   // no valid <bytes> field; nothing follows we could skip
  TooLarge,    // more than the asset buffer: the bytes are read and dropped
  Incomplete,  // the sender stopped before <bytes> arrived
};

struct AssetFrame {
  const char* commandLine;  // "MDSIMG,<bytes>,<crc32>,<format>,<core>" or "MDSLOGO,<bytes>,<crc32>,<format>"
  AssetResult result;
  const uint8_t* data;  // valid only during the callback
  size_t length;        // bytes received
};

enum class DiscardReason : uint8_t { LineTooLong, NonPrintable };

class ParserListener {
 public:
  virtual ~ParserListener() = default;
  virtual void onLine(const char* line, size_t length) = 0;
  virtual void onImage(const ImageFrame& frame) = 0;
  virtual void onAsset(const AssetFrame& frame) { (void)frame; }
  virtual void onDiscard(DiscardReason reason, size_t length) { (void)reason, (void)length; }
};

class ProtocolParser {
 public:
  explicit ProtocolParser(ParserListener& listener) : listener_(listener) {}

  // Where MDSIMG payloads go (PSRAM on the device). Without a buffer every asset is TooLarge.
  void setAssetBuffer(uint8_t* buffer, size_t capacity) {
    asset_ = buffer;
    assetCapacity_ = capacity;
  }

  void feed(const uint8_t* data, size_t length, uint32_t nowMs);
  // Call often, also when no bytes arrive: timeouts complete lines and pictures.
  void poll(uint32_t nowMs);
  void reset();

  bool receivingImage() const { return state_ == State::Image; }
  bool receivingBinary() const { return state_ == State::Image || state_ == State::Asset; }

 private:
  enum class State : uint8_t { Line, DiscardLine, Image, Asset };

  void acceptLineByte(uint8_t b);
  void completeLine();
  void startImage();
  void finishImage(ImageResult result);
  void startAsset();
  void finishAsset(AssetResult result);

  ParserListener& listener_;
  State state_ = State::Line;
  uint32_t lastByteMs_ = 0;

  char line_[kMaxLineLength + 1] = {};
  size_t lineLength_ = 0;
  size_t discarded_ = 0;

  char imageCommand_[kMaxLineLength + 1] = {};
  uint8_t image_[kImageBufferBytes] = {};
  size_t imageLength_ = 0;
  uint32_t imageStartMs_ = 0;

  uint8_t* asset_ = nullptr;
  size_t assetCapacity_ = 0;
  size_t assetExpected_ = 0;
  size_t assetReceived_ = 0;
};

}  // namespace proto
