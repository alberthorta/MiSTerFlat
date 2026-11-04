#include "Command.h"

namespace proto {

namespace {

struct Keyword {
  const char* text;
  CommandId id;
};

// Whole-line matches (newCommand == "...").
constexpr Keyword kExact[] = {
    {"CMDNULL", CommandId::Null},
    {"cls", CommandId::ClearScreen},
    {"sorg", CommandId::StartScreen},
    {"bye", CommandId::Bye},
    {"CMDCLS", CommandId::ClearScreen},
    {"CMDCLSWU", CommandId::ClearBuffer},
    {"CMDSORG", CommandId::StartScreen},
    {"CMDBYE", CommandId::Bye},
    {"CMDSHCD", CommandId::ShowCommandDelay},
    {"CMDSHSYSHW", CommandId::ShowSystemHardware},
    {"CMDHWINF", CommandId::HardwareInfo},
    {"CMDTEST", CommandId::TestPicture},
    {"CMDSNAM", CommandId::ShowCoreName},
    {"CMDSSCP", CommandId::ShowSmallPicture},
    {"CMDDOFF", CommandId::DisplayOff},
    {"CMDDON", CommandId::DisplayOn},
    {"CMDDUPD", CommandId::DisplayUpdate},
    {"CMDRESET", CommandId::Reset},
    {"CMDSHTIME", CommandId::ShowTime},
    {"MDSPING", CommandId::MdsPing},
    {"MDSINFO", CommandId::MdsInfo},
    {"MDSSHOT", CommandId::MdsShot},
    {"MDSLOGO", CommandId::MdsLogo},
    {"MDSCFG", CommandId::MdsCfg},
    {"MDSHANG", CommandId::MdsHang},
};

// Prefix matches (newCommand.startsWith("...")), checked in the sketch's order.
// CMDCOR/CMDAPD are handled by ProtocolParser because they switch to binary mode.
constexpr Keyword kPrefix[] = {
    {"CMDCLST", CommandId::ClearWithTransition},
    {"CMDSECD", CommandId::SetCommandDelay},
    {"CMDSPIC", CommandId::ShowPicture},
    {"CMDTXT", CommandId::Text},
    {"CMDGEO", CommandId::Geometry},
    {"CMDSETTIME,", CommandId::SetTime},
    {"CMDCON", CommandId::Contrast},
    {"CMDROT", CommandId::Rotate},
    {"CMDSWSAVER", CommandId::SwitchScreensaver},
    {"CMDSAVER", CommandId::Screensaver},
    {"CMDSTTYACK", CommandId::SetTtyAck},
    {"MDSCORE,", CommandId::MdsCore},
    {"MDSCFG,", CommandId::MdsCfg},
    {"MDSNET,", CommandId::MdsNet},
    {"MDSWIFI,", CommandId::MdsWifi},
    {"MDSVOL,", CommandId::MdsVol},
    {"MDSPOWER,", CommandId::MdsPower},
};

std::string_view afterKeyword(std::string_view line, size_t keywordLength) {
  std::string_view rest = line.substr(keywordLength);
  if (!rest.empty() && rest.front() == ',') rest.remove_prefix(1);
  return rest;
}

}  // namespace

Command parseCommand(std::string_view line) {
  Command cmd;

  // The sketch uses endsWith: noise received before the host configured the port may precede it.
  const std::string_view kQwertz = "QWERTZ";
  if (line.size() >= kQwertz.size() && line.substr(line.size() - kQwertz.size()) == kQwertz) {
    cmd.id = CommandId::Qwertz;
    return cmd;
  }

  for (const auto& k : kExact) {
    if (line == k.text) {
      cmd.id = k.id;
      cmd.name = line;
      return cmd;
    }
  }
  for (const auto& k : kPrefix) {
    const std::string_view keyword(k.text);
    if (line.substr(0, keyword.size()) == keyword) {
      cmd.id = k.id;
      cmd.name = line.substr(0, keyword.back() == ',' ? keyword.size() - 1 : keyword.size());
      cmd.args = afterKeyword(line, cmd.name.size());
      return cmd;
    }
  }
  if (line.substr(0, 3) == "CMD") {
    cmd.id = CommandId::UnknownCommand;
    cmd.name = line;
    return cmd;
  }

  cmd.id = CommandId::CoreName;
  cmd.args = line;
  return cmd;
}

CoreCommand parseCoreCommand(std::string_view line) {
  CoreCommand out;
  constexpr size_t kKeywordLength = 6;  // "CMDCOR" / "CMDAPD"
  if (line.size() <= kKeywordLength) return out;
  std::string_view rest = line.substr(kKeywordLength);
  if (rest.front() == ',') rest.remove_prefix(1);
  const size_t comma = rest.find(',');
  out.core = rest.substr(0, comma);
  if (comma != std::string_view::npos) {
    int32_t t = -1;
    // The sketch uses toInt(), which turns junk into 0 (no transition).
    if (!parseInt(rest.substr(comma + 1), t)) t = 0;
    out.transition = t < -1 ? -1 : (t > kMaxTransition ? kMaxTransition : t);
  }
  return out;
}

size_t splitFields(std::string_view args, std::string_view* fields, size_t maxFields) {
  if (maxFields == 0) return 0;
  size_t count = 0;
  while (count + 1 < maxFields) {
    const size_t comma = args.find(',');
    if (comma == std::string_view::npos) break;
    fields[count++] = args.substr(0, comma);
    args.remove_prefix(comma + 1);
  }
  fields[count++] = args;
  return count;
}

bool parseInt(std::string_view text, int32_t& out) {
  bool negative = false;
  if (!text.empty() && text.front() == '-') {
    negative = true;
    text.remove_prefix(1);
  }
  if (text.empty() || text.size() > 9) return false;
  int32_t value = 0;
  for (char c : text) {
    if (c < '0' || c > '9') return false;
    value = value * 10 + (c - '0');
  }
  out = negative ? -value : value;
  return true;
}

}  // namespace proto
