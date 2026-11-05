#include <unity.h>

#include <string.h>

#include <string>
#include <vector>

#include "../fixtures.h"
#include "ProtocolParser.h"

using namespace proto;

namespace {

struct Image {
  std::string command;
  ImageResult result;
  ImageFormat format;
  std::vector<uint8_t> data;
};

struct Recorder : ParserListener {
  std::vector<std::string> lines;
  std::vector<Image> images;
  size_t discards = 0;

  void onLine(const char* line, size_t length) override { lines.emplace_back(line, length); }
  void onImage(const ImageFrame& f) override {
    images.push_back({f.commandLine, f.result, f.format, std::vector<uint8_t>(f.data, f.data + f.length)});
  }
  void onDiscard(DiscardReason, size_t) override { ++discards; }
};

Recorder rec;
ProtocolParser* parser;
uint32_t now;

void feedText(const char* s) { parser->feed(reinterpret_cast<const uint8_t*>(s), strlen(s), now); }

// Feeds data in chunks of `chunk` bytes, advancing time by `stepMs` per chunk (USB packets).
void feedChunks(const uint8_t* data, size_t length, size_t chunk, uint32_t stepMs) {
  for (size_t i = 0; i < length; i += chunk) {
    const size_t n = (length - i < chunk) ? length - i : chunk;
    parser->feed(data + i, n, now);
    now += stepMs;
  }
}

void wait(uint32_t ms) {
  now += ms;
  parser->poll(now);
}

const char* kCorLine = "CMDCOR,MDSTEST,-1\n";
const size_t kCorLineLength = 18;

}  // namespace

void setUp() {
  rec = Recorder();
  static ProtocolParser p(rec);
  parser = &p;
  parser->reset();
  now = 1000;
}

void tearDown() {}

void test_one_complete_command() {
  feedText("CMDCON,100\n");
  TEST_ASSERT_EQUAL(1, rec.lines.size());
  TEST_ASSERT_EQUAL_STRING("CMDCON,100", rec.lines[0].c_str());
}

void test_command_split_into_single_bytes() {
  const char* s = "CMDROT,1\n";
  feedChunks(reinterpret_cast<const uint8_t*>(s), strlen(s), 1, 1);
  TEST_ASSERT_EQUAL(1, rec.lines.size());
  TEST_ASSERT_EQUAL_STRING("CMDROT,1", rec.lines[0].c_str());
}

void test_startup_sequence_in_one_chunk() {
  parser->feed(kCapture_startup, sizeof(kCapture_startup), now);
  TEST_ASSERT_EQUAL(4, rec.lines.size());
  TEST_ASSERT_EQUAL_STRING("QWERTZ", rec.lines[0].c_str());
  TEST_ASSERT_EQUAL_STRING("CMDCON,100", rec.lines[1].c_str());
  TEST_ASSERT_EQUAL_STRING("CMDSETTIME,1759939200", rec.lines[2].c_str());
  TEST_ASSERT_EQUAL_STRING("CMDSAVER,0,0,0", rec.lines[3].c_str());
}

void test_crlf_and_empty_lines() {
  feedText("SNES\r\n\n\r\nCMDCLS\r\n");
  TEST_ASSERT_EQUAL(2, rec.lines.size());
  TEST_ASSERT_EQUAL_STRING("SNES", rec.lines[0].c_str());
  TEST_ASSERT_EQUAL_STRING("CMDCLS", rec.lines[1].c_str());
}

void test_bare_core_name_capture() {
  parser->feed(kCapture_name, sizeof(kCapture_name), now);
  TEST_ASSERT_EQUAL(1, rec.lines.size());
  TEST_ASSERT_EQUAL_STRING("Atari5200", rec.lines[0].c_str());
}

void test_partial_line_completes_after_timeout() {
  feedText("PSX");
  wait(kLineTimeoutMs - 1);
  TEST_ASSERT_EQUAL(0, rec.lines.size());
  wait(1);
  TEST_ASSERT_EQUAL(1, rec.lines.size());
  TEST_ASSERT_EQUAL_STRING("PSX", rec.lines[0].c_str());
}

void test_xbm_capture_ends_on_idle_timeout() {
  parser->feed(kCapture_xbm, sizeof(kCapture_xbm), now);
  TEST_ASSERT_TRUE(parser->receivingImage());
  TEST_ASSERT_EQUAL(0, rec.images.size());
  wait(kImageIdleTimeoutMs);
  TEST_ASSERT_EQUAL(1, rec.images.size());
  const Image& img = rec.images[0];
  TEST_ASSERT_EQUAL_STRING("CMDCOR,MDSTEST,-1", img.command.c_str());
  TEST_ASSERT_EQUAL(ImageResult::Ok, img.result);
  TEST_ASSERT_EQUAL(ImageFormat::Xbm, img.format);
  TEST_ASSERT_EQUAL(kXbmBytes, img.data.size());
  TEST_ASSERT_EQUAL_MEMORY(kCapture_xbm + kCorLineLength, img.data.data(), kXbmBytes);
  TEST_ASSERT_EQUAL(0, rec.lines.size());
}

void test_gsc_capture_fragmented_completes_without_timeout() {
  feedChunks(kCapture_gsc, sizeof(kCapture_gsc), 7, 0);
  TEST_ASSERT_EQUAL(1, rec.images.size());
  TEST_ASSERT_EQUAL(ImageFormat::Gsc, rec.images[0].format);
  TEST_ASSERT_EQUAL_MEMORY(kCapture_gsc + kCorLineLength, rec.images[0].data.data(), kGscBytes);
  TEST_ASSERT_FALSE(parser->receivingImage());
}

void test_host_sleep_between_command_and_data() {
  feedText(kCorLine);
  wait(200);  // tty2oled.sh: sleep ${WAITSECS}
  feedChunks(kCapture_gsc + kCorLineLength, kGscBytes, 64, 1);
  TEST_ASSERT_EQUAL(1, rec.images.size());
  TEST_ASSERT_EQUAL(ImageResult::Ok, rec.images[0].result);
}

void test_usb_packet_size_chunks() {
  feedChunks(kCapture_xbm, sizeof(kCapture_xbm), 64, 1);
  wait(kImageIdleTimeoutMs);
  TEST_ASSERT_EQUAL(1, rec.images.size());
  TEST_ASSERT_EQUAL(ImageFormat::Xbm, rec.images[0].format);
}

void test_command_right_after_gsc_in_same_chunk() {
  std::vector<uint8_t> stream(kCapture_gsc, kCapture_gsc + sizeof(kCapture_gsc));
  const char* next = "CMDDOFF\n";
  stream.insert(stream.end(), next, next + strlen(next));
  parser->feed(stream.data(), stream.size(), now);
  TEST_ASSERT_EQUAL(1, rec.images.size());
  TEST_ASSERT_EQUAL(1, rec.lines.size());
  TEST_ASSERT_EQUAL_STRING("CMDDOFF", rec.lines[0].c_str());
}

void test_command_after_xbm_and_gap() {
  parser->feed(kCapture_xbm, sizeof(kCapture_xbm), now);
  now += kImageIdleTimeoutMs + 100;
  feedText("CMDDON\n");
  TEST_ASSERT_EQUAL(1, rec.images.size());
  TEST_ASSERT_EQUAL(ImageResult::Ok, rec.images[0].result);
  TEST_ASSERT_EQUAL(1, rec.lines.size());
  TEST_ASSERT_EQUAL_STRING("CMDDON", rec.lines[0].c_str());
}

void test_malformed_payload_length() {
  feedText(kCorLine);
  feedChunks(kCapture_gsc + kCorLineLength, 3000, 64, 1);
  wait(kImageIdleTimeoutMs);
  TEST_ASSERT_EQUAL(1, rec.images.size());
  TEST_ASSERT_EQUAL(ImageResult::BadLength, rec.images[0].result);
  TEST_ASSERT_EQUAL(ImageFormat::None, rec.images[0].format);
  TEST_ASSERT_EQUAL(3000, rec.images[0].data.size());
  feedText("SNES\n");
  TEST_ASSERT_EQUAL(1, rec.lines.size());
  TEST_ASSERT_EQUAL_STRING("SNES", rec.lines[0].c_str());
}

void test_command_without_picture_data() {
  feedText("CMDCOR,Genesis,-1\n");
  wait(kImageFirstByteTimeoutMs - 1);
  TEST_ASSERT_EQUAL(0, rec.images.size());
  wait(1);
  TEST_ASSERT_EQUAL(1, rec.images.size());
  TEST_ASSERT_EQUAL(ImageResult::NoData, rec.images[0].result);
  TEST_ASSERT_EQUAL_STRING("CMDCOR,Genesis,-1", rec.images[0].command.c_str());
}

void test_apd_also_receives_picture() {
  feedText("CMDAPD,MDSTEST\n");
  feedChunks(kCapture_gsc + kCorLineLength, kGscBytes, 512, 1);
  TEST_ASSERT_EQUAL(1, rec.images.size());
  TEST_ASSERT_EQUAL_STRING("CMDAPD,MDSTEST", rec.images[0].command.c_str());
}

void test_overlong_line_is_dropped_and_parser_recovers() {
  std::string longLine(kMaxLineLength + 50, 'A');
  longLine += "\nSNES\n";
  feedText(longLine.c_str());
  TEST_ASSERT_EQUAL(1, rec.discards);
  TEST_ASSERT_EQUAL(1, rec.lines.size());
  TEST_ASSERT_EQUAL_STRING("SNES", rec.lines[0].c_str());
}

void test_max_length_line_is_accepted() {
  std::string line(kMaxLineLength, 'B');
  feedText((line + "\n").c_str());
  TEST_ASSERT_EQUAL(1, rec.lines.size());
  TEST_ASSERT_EQUAL(kMaxLineLength, rec.lines[0].size());
}

void test_binary_garbage_is_not_a_core_name() {
  const uint8_t junk[] = {0x01, 0xff, 0x00, 'A', 0x7f, '\n', 'N', 'E', 'S', '\n'};
  parser->feed(junk, sizeof(junk), now);
  TEST_ASSERT_EQUAL(1, rec.discards);
  TEST_ASSERT_EQUAL(1, rec.lines.size());
  TEST_ASSERT_EQUAL_STRING("NES", rec.lines[0].c_str());
}

void test_timer_wraparound() {
  now = 0xFFFFFF00u;
  feedText("CMDCOR,X,-1\n");
  wait(kImageFirstByteTimeoutMs);
  TEST_ASSERT_EQUAL(1, rec.images.size());
  TEST_ASSERT_EQUAL(ImageResult::NoData, rec.images[0].result);
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_one_complete_command);
  RUN_TEST(test_command_split_into_single_bytes);
  RUN_TEST(test_startup_sequence_in_one_chunk);
  RUN_TEST(test_crlf_and_empty_lines);
  RUN_TEST(test_bare_core_name_capture);
  RUN_TEST(test_partial_line_completes_after_timeout);
  RUN_TEST(test_xbm_capture_ends_on_idle_timeout);
  RUN_TEST(test_gsc_capture_fragmented_completes_without_timeout);
  RUN_TEST(test_host_sleep_between_command_and_data);
  RUN_TEST(test_usb_packet_size_chunks);
  RUN_TEST(test_command_right_after_gsc_in_same_chunk);
  RUN_TEST(test_command_after_xbm_and_gap);
  RUN_TEST(test_malformed_payload_length);
  RUN_TEST(test_command_without_picture_data);
  RUN_TEST(test_apd_also_receives_picture);
  RUN_TEST(test_overlong_line_is_dropped_and_parser_recovers);
  RUN_TEST(test_max_length_line_is_accepted);
  RUN_TEST(test_binary_garbage_is_not_a_core_name);
  RUN_TEST(test_timer_wraparound);
  return UNITY_END();
}
