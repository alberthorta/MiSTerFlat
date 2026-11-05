#include "app/StartupLogo.h"

#include <LittleFS.h>
#include <esp_heap_caps.h>
#include <string.h>

#include "Crc32.h"
#include "util/Log.h"

namespace {

constexpr const char* kPng = "/logo.png";
constexpr const char* kJpg = "/logo.jpg";
constexpr const char* kTmp = "/logo.tmp";

}  // namespace

void StartupLogo::begin() {
  data_ = static_cast<uint8_t*>(heap_caps_malloc(kMaxBytes, MALLOC_CAP_SPIRAM));
  // formatOnFail: the first boot finds an empty, unformatted partition.
  mounted_ = LittleFS.begin(true);
  LOGF("littlefs %s", mounted_ ? "mounted" : "failed");
  if (!mounted_ || !data_) return;
  if (!loadFrom(kPng, true)) loadFrom(kJpg, false);
}

bool StartupLogo::loadFrom(const char* path, bool isPng) {
  if (!LittleFS.exists(path)) return false;
  File f = LittleFS.open(path, "r");
  if (!f) return false;
  const size_t n = f.size();
  if (n == 0 || n > kMaxBytes || f.read(data_, n) != n) {
    f.close();
    return false;
  }
  f.close();
  size_ = n;
  isPng_ = isPng;
  crc_ = proto::crc32(data_, n);
  LOGF("startup logo %s, %u bytes", path, (unsigned)n);
  return true;
}

bool StartupLogo::store(const uint8_t* data, size_t size, bool isPng) {
  if (!mounted_ || !data_ || size == 0 || size > kMaxBytes) return false;
  File f = LittleFS.open(kTmp, "w");
  if (!f) return false;
  const bool written = f.write(data, size) == size;
  f.close();
  if (!written) {
    LittleFS.remove(kTmp);
    return false;
  }
  LittleFS.remove(kPng);
  LittleFS.remove(kJpg);
  if (!LittleFS.rename(kTmp, isPng ? kPng : kJpg)) return false;
  memcpy(data_, data, size);
  size_ = size;
  isPng_ = isPng;
  crc_ = proto::crc32(data_, size);
  return true;
}

bool StartupLogo::clear() {
  if (!mounted_) return false;
  LittleFS.remove(kPng);
  LittleFS.remove(kJpg);
  size_ = 0;
  crc_ = 0;
  return true;
}
