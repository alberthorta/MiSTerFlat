#include "ProtocolParser.h"

#include <string.h>

#include "Command.h"

namespace proto {

namespace {

bool startsWith(const char* s, size_t length, const char* prefix) {
  const size_t n = strlen(prefix);
  return length >= n && memcmp(s, prefix, n) == 0;
}

// Core names and commands are plain text. A line with control bytes is almost always the tail
// of a picture that was cut by a timeout, and must not be shown as a core name.
bool isPrintable(const char* s, size_t length) {
  for (size_t i = 0; i < length; ++i) {
    const uint8_t c = static_cast<uint8_t>(s[i]);
    if (c < 0x20 || c == 0x7F) return false;
  }
  return true;
}

}  // namespace

void ProtocolParser::feed(const uint8_t* data, size_t length, uint32_t nowMs) {
  // Timeouts that expired before this chunk arrived must close the previous frame first.
  poll(nowMs);
  if (length > 0) lastByteMs_ = nowMs;

  size_t i = 0;
  while (i < length) {
    if (state_ == State::Asset) {
      size_t take = assetExpected_ - assetReceived_;
      if (take > length - i) take = length - i;
      // Too large: keep counting so the stream stays in sync, but store nothing.
      if (assetExpected_ <= assetCapacity_) memcpy(asset_ + assetReceived_, data + i, take);
      assetReceived_ += take;
      i += take;
      if (assetReceived_ == assetExpected_) {
        finishAsset(assetExpected_ <= assetCapacity_ ? AssetResult::Ok : AssetResult::TooLarge);
      }
      continue;
    }
    if (state_ == State::Image) {
      size_t take = kImageBufferBytes - imageLength_;
      if (take > length - i) take = length - i;
      memcpy(image_ + imageLength_, data + i, take);
      imageLength_ += take;
      i += take;
      if (imageLength_ == kImageBufferBytes) finishImage(ImageResult::Ok);
      continue;
    }
    acceptLineByte(data[i++]);
  }
}

void ProtocolParser::poll(uint32_t nowMs) {
  const uint32_t idle = nowMs - lastByteMs_;
  switch (state_) {
    case State::Line:
      if (lineLength_ > 0 && idle >= kLineTimeoutMs) completeLine();
      break;
    case State::DiscardLine:
      if (idle >= kLineTimeoutMs) {
        listener_.onDiscard(DiscardReason::LineTooLong, discarded_);
        state_ = State::Line;
      }
      break;
    case State::Image:
      if (imageLength_ == 0) {
        if (nowMs - imageStartMs_ >= kImageFirstByteTimeoutMs) finishImage(ImageResult::NoData);
      } else if (idle >= kImageIdleTimeoutMs) {
        finishImage(imageLength_ == kXbmBytes ? ImageResult::Ok : ImageResult::BadLength);
      }
      break;
    case State::Asset:
      if (idle >= kAssetIdleTimeoutMs) finishAsset(AssetResult::Incomplete);
      break;
  }
}

void ProtocolParser::reset() {
  state_ = State::Line;
  lineLength_ = 0;
  discarded_ = 0;
  imageLength_ = 0;
  assetReceived_ = 0;
}

void ProtocolParser::acceptLineByte(uint8_t b) {
  if (state_ == State::DiscardLine) {
    ++discarded_;
    if (b == '\n') {
      listener_.onDiscard(DiscardReason::LineTooLong, discarded_);
      state_ = State::Line;
    }
    return;
  }

  if (b == '\n') {
    completeLine();
    return;
  }
  if (lineLength_ == kMaxLineLength) {
    discarded_ = lineLength_ + 1;
    lineLength_ = 0;
    state_ = State::DiscardLine;
    return;
  }
  line_[lineLength_++] = static_cast<char>(b);
}

void ProtocolParser::completeLine() {
  size_t n = lineLength_;
  lineLength_ = 0;
  if (n > 0 && line_[n - 1] == '\r') --n;
  line_[n] = '\0';
  if (n == 0) return;

  if (!isPrintable(line_, n)) {
    listener_.onDiscard(DiscardReason::NonPrintable, n);
    return;
  }
  if (startsWith(line_, n, "CMDCOR") || startsWith(line_, n, "CMDAPD")) {
    memcpy(imageCommand_, line_, n + 1);
    startImage();
    return;
  }
  if (startsWith(line_, n, "MDSIMG,") || startsWith(line_, n, "MDSLOGO,")) {
    memcpy(imageCommand_, line_, n + 1);
    startAsset();
    return;
  }
  listener_.onLine(line_, n);
}

void ProtocolParser::startImage() {
  state_ = State::Image;
  imageLength_ = 0;
  imageStartMs_ = lastByteMs_;
}

void ProtocolParser::finishImage(ImageResult result) {
  ImageFrame frame;
  frame.commandLine = imageCommand_;
  frame.result = result;
  frame.data = image_;
  frame.length = imageLength_;
  frame.format = ImageFormat::None;
  if (result == ImageResult::Ok) frame.format = imageLength_ == kXbmBytes ? ImageFormat::Xbm : ImageFormat::Gsc;

  state_ = State::Line;
  imageLength_ = 0;
  listener_.onImage(frame);
}

void ProtocolParser::startAsset() {
  // "<keyword>,<bytes>,...": only the length matters here; the rest is for the listener.
  std::string_view fields[3];
  const std::string_view line(imageCommand_);
  const std::string_view args = line.substr(line.find(',') + 1);
  int32_t bytes = 0;
  // A length beyond the protocol limit is treated as a broken header rather than skipped: the
  // parser would otherwise swallow everything that follows.
  if (splitFields(args, fields, 3) < 2 || !parseInt(fields[0], bytes) || bytes <= 0 ||
      static_cast<size_t>(bytes) > kMaxAssetBytes) {
    assetReceived_ = 0;
    finishAsset(AssetResult::BadHeader);
    return;
  }
  state_ = State::Asset;
  assetExpected_ = static_cast<size_t>(bytes);
  assetReceived_ = 0;
}

void ProtocolParser::finishAsset(AssetResult result) {
  AssetFrame frame;
  frame.commandLine = imageCommand_;
  frame.result = result;
  frame.data = (result == AssetResult::Ok) ? asset_ : nullptr;
  frame.length = assetReceived_;

  state_ = State::Line;
  assetReceived_ = 0;
  listener_.onAsset(frame);
}

}  // namespace proto
