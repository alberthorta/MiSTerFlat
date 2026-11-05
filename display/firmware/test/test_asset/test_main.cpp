#include <unity.h>

#include <string.h>

#include <string>
#include <vector>

#include "Crc32.h"
#include "ProtocolParser.h"

using namespace proto;

namespace {

struct Asset {
  std::string command;
  AssetResult result;
  std::vector<uint8_t> data;
  size_t length;
};

struct Recorder : ParserListener {
  std::vector<std::string> lines;
  std::vector<Asset> assets;
  size_t discards = 0;
  void onLine(const char* line, size_t length) override { lines.emplace_back(line, length); }
  void onImage(const ImageFrame&) override {}
  void onAsset(const AssetFrame& f) override {
    assets.push_back({f.commandLine, f.result,
                      f.data ? std::vector<uint8_t>(f.data, f.data + f.length) : std::vector<uint8_t>(), f.length});
  }
  void onDiscard(DiscardReason, size_t) override { ++discards; }
};

Recorder rec;
ProtocolParser* parser;
std::vector<uint8_t> buffer(64 * 1024);
uint32_t now;

void feed(const std::vector<uint8_t>& bytes, size_t chunk) {
  for (size_t i = 0; i < bytes.size(); i += chunk) {
    parser->feed(bytes.data() + i, (bytes.size() - i < chunk) ? bytes.size() - i : chunk, now);
    now += 1;
  }
}

std::vector<uint8_t> payload(size_t n) {
  std::vector<uint8_t> p(n);
  for (size_t i = 0; i < n; ++i) p[i] = static_cast<uint8_t>(i * 31 + 7);  // includes '\n' bytes
  return p;
}

std::vector<uint8_t> frame(const std::vector<uint8_t>& data, const char* rest = ",00000000,png,Test") {
  std::string head = "MDSIMG," + std::to_string(data.size()) + rest + "\n";
  std::vector<uint8_t> out(head.begin(), head.end());
  out.insert(out.end(), data.begin(), data.end());
  return out;
}

}  // namespace

void setUp() {
  rec = Recorder();
  static ProtocolParser p(rec);
  parser = &p;
  parser->reset();
  parser->setAssetBuffer(buffer.data(), buffer.size());
  now = 1000;
}

void tearDown() {}

void test_crc32_matches_zlib() {
  const char* s = "123456789";
  TEST_ASSERT_EQUAL_HEX32(0xCBF43926, crc32(reinterpret_cast<const uint8_t*>(s), 9));
  TEST_ASSERT_EQUAL_HEX32(0x00000000, crc32(nullptr, 0));
}

void test_asset_in_small_chunks_then_command() {
  const std::vector<uint8_t> data = payload(20000);
  std::vector<uint8_t> stream = frame(data);
  const char* next = "CMDDOFF\n";
  stream.insert(stream.end(), next, next + strlen(next));
  feed(stream, 61);
  TEST_ASSERT_EQUAL(1, rec.assets.size());
  TEST_ASSERT_EQUAL(AssetResult::Ok, rec.assets[0].result);
  TEST_ASSERT_EQUAL_STRING("MDSIMG,20000,00000000,png,Test", rec.assets[0].command.c_str());
  TEST_ASSERT_EQUAL(20000, rec.assets[0].length);
  TEST_ASSERT_EQUAL_MEMORY(data.data(), rec.assets[0].data.data(), data.size());
  TEST_ASSERT_EQUAL(1, rec.lines.size());
  TEST_ASSERT_EQUAL_STRING("CMDDOFF", rec.lines[0].c_str());
}

void test_incomplete_asset_times_out_and_parser_recovers() {
  std::vector<uint8_t> stream = frame(payload(5000));
  stream.resize(stream.size() - 100);
  feed(stream, 64);
  TEST_ASSERT_EQUAL(0, rec.assets.size());
  now += kAssetIdleTimeoutMs;
  parser->poll(now);
  TEST_ASSERT_EQUAL(1, rec.assets.size());
  TEST_ASSERT_EQUAL(AssetResult::Incomplete, rec.assets[0].result);
  TEST_ASSERT_EQUAL(4900, rec.assets[0].length);
  const std::vector<uint8_t> line = {'S', 'N', 'E', 'S', '\n'};
  feed(line, 64);
  TEST_ASSERT_EQUAL(1, rec.lines.size());
}

void test_too_large_is_skipped_in_sync() {
  std::vector<uint8_t> stream = frame(payload(buffer.size() + 10));
  const char* next = "PSX\n";
  stream.insert(stream.end(), next, next + strlen(next));
  feed(stream, 512);
  TEST_ASSERT_EQUAL(1, rec.assets.size());
  TEST_ASSERT_EQUAL(AssetResult::TooLarge, rec.assets[0].result);
  TEST_ASSERT_EQUAL(1, rec.lines.size());
  TEST_ASSERT_EQUAL_STRING("PSX", rec.lines[0].c_str());
}

void test_bad_headers() {
  const char* bad[] = {"MDSIMG,abc,0,png,X\n", "MDSIMG,0,0,png,X\n", "MDSIMG,-5,0,png,X\n", "MDSIMG,99999999,0,png,X\n",
                       "MDSIMG,100\n"};
  for (const char* h : bad) {
    const std::vector<uint8_t> v(h, h + strlen(h));
    feed(v, 64);
  }
  TEST_ASSERT_EQUAL(5, rec.assets.size());
  for (const auto& a : rec.assets) TEST_ASSERT_EQUAL(AssetResult::BadHeader, a.result);
  TEST_ASSERT_FALSE(parser->receivingBinary());
}

void test_no_buffer_means_too_large() {
  parser->setAssetBuffer(nullptr, 0);
  feed(frame(payload(100)), 64);
  TEST_ASSERT_EQUAL(1, rec.assets.size());
  TEST_ASSERT_EQUAL(AssetResult::TooLarge, rec.assets[0].result);
}

void test_tty2oled_still_works_after_asset() {
  feed(frame(payload(300)), 64);
  const char* cor = "CMDCOR,X,-1\n";
  std::vector<uint8_t> v(cor, cor + strlen(cor));
  std::vector<uint8_t> gsc(kGscBytes, 0x11);
  v.insert(v.end(), gsc.begin(), gsc.end());
  feed(v, 64);
  TEST_ASSERT_EQUAL(1, rec.assets.size());
  TEST_ASSERT_FALSE(parser->receivingBinary());
}

void test_logo_frame_uses_the_same_framing() {
  const std::vector<uint8_t> data = payload(3000);
  std::string head = "MDSLOGO," + std::to_string(data.size()) + ",00000000,png\n";
  std::vector<uint8_t> stream(head.begin(), head.end());
  stream.insert(stream.end(), data.begin(), data.end());
  const char* next = "MDSLOGO\n";  // the status query is a normal line
  stream.insert(stream.end(), next, next + strlen(next));
  feed(stream, 64);
  TEST_ASSERT_EQUAL(1, rec.assets.size());
  TEST_ASSERT_EQUAL(AssetResult::Ok, rec.assets[0].result);
  TEST_ASSERT_EQUAL_STRING("MDSLOGO,3000,00000000,png", rec.assets[0].command.c_str());
  TEST_ASSERT_EQUAL_MEMORY(data.data(), rec.assets[0].data.data(), data.size());
  TEST_ASSERT_EQUAL(1, rec.lines.size());
  TEST_ASSERT_EQUAL_STRING("MDSLOGO", rec.lines[0].c_str());
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_crc32_matches_zlib);
  RUN_TEST(test_asset_in_small_chunks_then_command);
  RUN_TEST(test_incomplete_asset_times_out_and_parser_recovers);
  RUN_TEST(test_too_large_is_skipped_in_sync);
  RUN_TEST(test_bad_headers);
  RUN_TEST(test_no_buffer_means_too_large);
  RUN_TEST(test_tty2oled_still_works_after_asset);
  RUN_TEST(test_logo_frame_uses_the_same_framing);
  return UNITY_END();
}
