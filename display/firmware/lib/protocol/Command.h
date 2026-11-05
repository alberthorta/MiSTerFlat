#pragma once

// Turns one received text line into a command id plus its parameter text.
// Matching order and exact-vs-prefix rules follow the tty2oled sketch (MiSTer_SSD1322_USB.ino,
// BuildVersion 230702). Our own commands use the "MDS" prefix, which no tty2oled command uses.

#include <stddef.h>
#include <stdint.h>

#include <string_view>

namespace proto {

enum class CommandId : uint8_t {
  CoreName,        // any line that is not a command: tty2oled sends a bare core name when it has no picture
  UnknownCommand,  // starts with "CMD" but we do not know it: ignored, never shown as a core name
  Qwertz,          // first transmission after the host opens the port
  // tty2oled commands
  Null,
  ClearScreen,          // CMDCLS, "cls"
  ClearBuffer,          // CMDCLSWU
  ClearWithTransition,  // CMDCLST,t,c
  StartScreen,          // CMDSORG, "sorg"
  Bye,                  // CMDBYE, "bye"
  SetCommandDelay,      // CMDSECD,ms
  ShowCommandDelay,     // CMDSHCD
  ShowSystemHardware,   // CMDSHSYSHW
  HardwareInfo,         // CMDHWINF
  TestPicture,          // CMDTEST
  ShowCoreName,         // CMDSNAM
  ShowPicture,          // CMDSPIC[,t]
  ShowSmallPicture,     // CMDSSCP
  DisplayOff,           // CMDDOFF
  DisplayOn,            // CMDDON
  DisplayUpdate,        // CMDDUPD
  Text,                 // CMDTXT,f,c,b,x,y,text
  Geometry,             // CMDGEO,g,c,x,y,i,j,k,l
  SetTime,              // CMDSETTIME,epoch
  Contrast,             // CMDCON,0..255
  Rotate,               // CMDROT,0|1
  SwitchScreensaver,    // CMDSWSAVER,0|1
  Screensaver,          // CMDSAVER,mode,interval,start
  SetTtyAck,            // CMDSTTYACK,0|1
  Reset,                // CMDRESET
  ShowTime,             // CMDSHTIME
  // MiSTerLily commands
  MdsPing,  // MDSPING -> "MDSPONG"
  MdsInfo,  // MDSINFO -> one info line
  MdsCore,  // MDSCORE,<core name> -> show the core name (no picture transfer)
  MdsLogo,  // MDSLOGO -> stored start-up logo: "MDSLOGO;crc=<hex>;bytes=<n>;format=<png|jpg>" or "MDSLOGO;none"
  MdsNet,   // MDSNET,<ip> -> the MiSTer's address, shown on the menu screen ("" = none)
  MdsWifi,  // MDSWIFI,dongle|scanning|net|end|status,... -> the Wi-Fi screen (touch boards)
  MdsCfg,   // MDSCFG -> settings; MDSCFG,idle,<minutes>; MDSCFG,reset
  MdsVol,   // MDSVOL,<level 0-7>,<muted 0|1> -> the MiSTer's global volume (touch volume row)
  MdsPower, // MDSPOWER,halting|down -> the MiSTer is shutting down / is down (power relay)
  MdsHang,  // MDSHANG (test builds only): stop feeding the watchdog
  MdsSta,   // MDSSTA[,scan|join,<ssid hex>,<password hex>|forget] -> this board's own Wi-Fi
  MdsSys,   // MDSSYS,clear|item,<i>,<crc32>,<name> -> the systems of the system picker (touch boards)
  MdsShot,  // MDSSHOT -> "MDSSHOT,<w>,<h>,<bytes>\n" + "ttyack;" + framebuffer (RGB565 big-endian)
};

struct Command {
  CommandId id = CommandId::CoreName;
  std::string_view name;  // the matched keyword ("CMDCON"), empty for CoreName
  std::string_view args;  // text after the keyword and its ',' ("100"), or the whole line for CoreName
};

Command parseCommand(std::string_view line);

// Splits "a,b,c" into at most maxFields views. The last field keeps any further commas, so
// CMDTXT text can contain ','. Returns the number of fields.
size_t splitFields(std::string_view args, std::string_view* fields, size_t maxFields);

// "CMDCOR,<core>[,<t>]" / "CMDAPD,<core>": like the sketch, the name ends at the first ',' after
// the keyword; t is the transition (-1 = random, 0 = none), clamped to -1..kMaxTransition.
struct CoreCommand {
  std::string_view core;
  int32_t transition = -1;
};
constexpr int32_t kMaxTransition = 23;
CoreCommand parseCoreCommand(std::string_view line);

// Strict decimal integer (optional leading '-'), no spaces. False on empty or junk.
bool parseInt(std::string_view text, int32_t& out);

}  // namespace proto
