#pragma once

#include <stddef.h>
#include <stdint.h>

// The start-up picture, stored in the board's flash (LittleFS on the "spiffs" data partition,
// which firmware uploads do not touch). It is shown before the MiSTer sends anything, so it cannot
// be streamed like the core pictures. Kept in PSRAM after loading for redraws.
class StartupLogo {
 public:
  // Largest accepted file. The area is 320x130; even a photo-like PNG of that size fits.
  static constexpr size_t kMaxBytes = 256 * 1024;

  // Mounts the file system (formats it on first use) and loads the stored picture, if any.
  void begin();

  bool present() const { return size_ > 0; }
  const uint8_t* data() const { return data_; }
  size_t size() const { return size_; }
  bool isPng() const { return isPng_; }
  uint32_t crc() const { return crc_; }

  // Replaces the stored picture. Written to a temporary file first and renamed, so a power cut
  // leaves either the old or the new picture. False if storage failed.
  bool store(const uint8_t* data, size_t size, bool isPng);
  bool clear();

 private:
  bool loadFrom(const char* path, bool isPng);

  bool mounted_ = false;
  uint8_t* data_ = nullptr;  // PSRAM, kMaxBytes
  size_t size_ = 0;
  bool isPng_ = true;
  uint32_t crc_ = 0;
};
