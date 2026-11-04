#include <unity.h>

#include <string>

#include "Command.h"

using namespace proto;

void setUp() {}
void tearDown() {}

namespace {
std::string str(std::string_view v) { return std::string(v); }
}  // namespace

void test_core_name() {
  Command c = parseCommand("PlayStation");
  TEST_ASSERT_EQUAL(CommandId::CoreName, c.id);
  TEST_ASSERT_EQUAL_STRING("PlayStation", str(c.args).c_str());
}

void test_unknown_cmd_is_not_a_core_name() {
  TEST_ASSERT_EQUAL(CommandId::UnknownCommand, parseCommand("CMDFOO,1").id);
  TEST_ASSERT_EQUAL(CommandId::UnknownCommand, parseCommand("CMDENOTA").id);
}

void test_qwertz_with_leading_noise() {
  TEST_ASSERT_EQUAL(CommandId::Qwertz, parseCommand("QWERTZ").id);
  TEST_ASSERT_EQUAL(CommandId::Qwertz, parseCommand("xx~QWERTZ").id);
}

void test_exact_commands() {
  TEST_ASSERT_EQUAL(CommandId::ClearScreen, parseCommand("CMDCLS").id);
  TEST_ASSERT_EQUAL(CommandId::ClearScreen, parseCommand("cls").id);
  TEST_ASSERT_EQUAL(CommandId::ClearBuffer, parseCommand("CMDCLSWU").id);
  TEST_ASSERT_EQUAL(CommandId::HardwareInfo, parseCommand("CMDHWINF").id);
  TEST_ASSERT_EQUAL(CommandId::DisplayOn, parseCommand("CMDDON").id);
  TEST_ASSERT_EQUAL(CommandId::DisplayOff, parseCommand("CMDDOFF").id);
  TEST_ASSERT_EQUAL(CommandId::Reset, parseCommand("CMDRESET").id);
  TEST_ASSERT_EQUAL(CommandId::MdsPing, parseCommand("MDSPING").id);
  TEST_ASSERT_EQUAL(CommandId::MdsInfo, parseCommand("MDSINFO").id);
  // Exact means exact: trailing text makes it something else.
  TEST_ASSERT_EQUAL(CommandId::UnknownCommand, parseCommand("CMDHWINF2").id);
}

void test_prefix_commands_and_args() {
  Command c = parseCommand("CMDCON,100");
  TEST_ASSERT_EQUAL(CommandId::Contrast, c.id);
  TEST_ASSERT_EQUAL_STRING("CMDCON", str(c.name).c_str());
  TEST_ASSERT_EQUAL_STRING("100", str(c.args).c_str());

  c = parseCommand("CMDCLST,19,13");
  TEST_ASSERT_EQUAL(CommandId::ClearWithTransition, c.id);
  TEST_ASSERT_EQUAL_STRING("19,13", str(c.args).c_str());

  c = parseCommand("CMDSPIC");
  TEST_ASSERT_EQUAL(CommandId::ShowPicture, c.id);
  TEST_ASSERT_EQUAL(0, c.args.size());

  TEST_ASSERT_EQUAL(CommandId::SetTime, parseCommand("CMDSETTIME,1759939200").id);
  TEST_ASSERT_EQUAL(CommandId::Screensaver, parseCommand("CMDSAVER,0,0,0").id);
  TEST_ASSERT_EQUAL(CommandId::SwitchScreensaver, parseCommand("CMDSWSAVER,1").id);
  TEST_ASSERT_EQUAL(CommandId::Rotate, parseCommand("CMDROT,1").id);
  TEST_ASSERT_EQUAL(CommandId::Text, parseCommand("CMDTXT,1,15,0,10,20,Hello").id);

  c = parseCommand("MDSCORE,Atari 5200");
  TEST_ASSERT_EQUAL(CommandId::MdsCore, c.id);
  TEST_ASSERT_EQUAL_STRING("Atari 5200", str(c.args).c_str());

  c = parseCommand("MDSWIFI,net,-59,1,1,547578");
  TEST_ASSERT_EQUAL(CommandId::MdsWifi, c.id);
  TEST_ASSERT_EQUAL_STRING("net,-59,1,1,547578", str(c.args).c_str());

  c = parseCommand("MDSVOL,4,0");
  TEST_ASSERT_EQUAL(CommandId::MdsVol, c.id);
  TEST_ASSERT_EQUAL_STRING("4,0", str(c.args).c_str());

  c = parseCommand("MDSPOWER,halting");
  TEST_ASSERT_EQUAL(CommandId::MdsPower, c.id);
  TEST_ASSERT_EQUAL_STRING("halting", str(c.args).c_str());
}

void test_split_fields_keeps_commas_in_last_field() {
  std::string_view f[6];
  size_t n = splitFields("1,15,0,10,20,Hello, world", f, 6);
  TEST_ASSERT_EQUAL(6, n);
  TEST_ASSERT_EQUAL_STRING("1", str(f[0]).c_str());
  TEST_ASSERT_EQUAL_STRING("Hello, world", str(f[5]).c_str());

  n = splitFields("SNES,-1", f, 6);
  TEST_ASSERT_EQUAL(2, n);
  TEST_ASSERT_EQUAL_STRING("-1", str(f[1]).c_str());

  n = splitFields("", f, 6);
  TEST_ASSERT_EQUAL(1, n);
  TEST_ASSERT_EQUAL(0, f[0].size());
}

void test_parse_int() {
  int32_t v = 0;
  TEST_ASSERT_TRUE(parseInt("255", v));
  TEST_ASSERT_EQUAL(255, v);
  TEST_ASSERT_TRUE(parseInt("-1", v));
  TEST_ASSERT_EQUAL(-1, v);
  TEST_ASSERT_FALSE(parseInt("", v));
  TEST_ASSERT_FALSE(parseInt("-", v));
  TEST_ASSERT_FALSE(parseInt("12a", v));
  TEST_ASSERT_FALSE(parseInt(" 1", v));
  TEST_ASSERT_FALSE(parseInt("9999999999", v));
}

void test_core_command() {
  CoreCommand c = parseCoreCommand("CMDCOR,SNES,-1");
  TEST_ASSERT_EQUAL_STRING("SNES", str(c.core).c_str());
  TEST_ASSERT_EQUAL(-1, c.transition);

  c = parseCoreCommand("CMDCOR,llander,19");
  TEST_ASSERT_EQUAL_STRING("llander", str(c.core).c_str());
  TEST_ASSERT_EQUAL(19, c.transition);

  c = parseCoreCommand("CMDCOR,Amstrad PCW");
  TEST_ASSERT_EQUAL_STRING("Amstrad PCW", str(c.core).c_str());
  TEST_ASSERT_EQUAL(-1, c.transition);

  TEST_ASSERT_EQUAL(kMaxTransition, parseCoreCommand("CMDCOR,X,99").transition);
  TEST_ASSERT_EQUAL(-1, parseCoreCommand("CMDCOR,X,-7").transition);
  TEST_ASSERT_EQUAL(0, parseCoreCommand("CMDCOR,X,abc").transition);  // toInt() semantics
  TEST_ASSERT_EQUAL_STRING("MDSTEST", str(parseCoreCommand("CMDAPD,MDSTEST").core).c_str());
  TEST_ASSERT_EQUAL(0, parseCoreCommand("CMDCOR").core.size());
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_core_name);
  RUN_TEST(test_unknown_cmd_is_not_a_core_name);
  RUN_TEST(test_qwertz_with_leading_noise);
  RUN_TEST(test_exact_commands);
  RUN_TEST(test_prefix_commands_and_args);
  RUN_TEST(test_split_fields_keeps_commas_in_last_field);
  RUN_TEST(test_parse_int);
  RUN_TEST(test_core_command);
  return UNITY_END();
}
