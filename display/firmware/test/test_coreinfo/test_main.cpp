#include <unity.h>

#include <string>

#include "CoreNames.h"

void setUp() {}
void tearDown() {}

namespace {
std::string name(const char* core) { return std::string(coreinfo::displayName(core)); }
}  // namespace

void test_known_cores() {
  TEST_ASSERT_EQUAL_STRING("PlayStation", name("PSX").c_str());
  TEST_ASSERT_EQUAL_STRING("Atari 5200", name("ATARI5200").c_str());
  TEST_ASSERT_EQUAL_STRING("Super Nintendo", name("SNES").c_str());
  TEST_ASSERT_EQUAL_STRING("Amiga", name("Minimig").c_str());
}

void test_unknown_core_is_returned_as_is() {
  TEST_ASSERT_EQUAL_STRING("llander", name("llander").c_str());
  TEST_ASSERT_EQUAL_STRING("psx", name("psx").c_str());  // exact, case-sensitive
  TEST_ASSERT_EQUAL_STRING("", name("").c_str());
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_known_cores);
  RUN_TEST(test_unknown_core_is_returned_as_is);
  return UNITY_END();
}
