#include "CoreNames.h"

namespace coreinfo {

namespace {

struct Entry {
  const char* core;
  const char* name;
};

// Exact, case-sensitive matches. Keep it short; unknown names are shown as received.
constexpr Entry kNames[] = {
    {"MENU", "MiSTer"},
    {"AO486", "PC 486"},
    {"PCXT", "PC XT"},
    {"Minimig", "Amiga"},
    {"Amiga500", "Amiga 500"},
    {"AtariST", "Atari ST"},
    {"ATARI2600", "Atari 2600"},
    {"ATARI5200", "Atari 5200"},
    {"ATARI7800", "Atari 7800"},
    {"ATARI800", "Atari 800"},
    {"AtariLynx", "Atari Lynx"},
    {"Jaguar", "Atari Jaguar"},
    {"C64", "Commodore 64"},
    {"C128", "Commodore 128"},
    {"C16", "Commodore 16"},
    {"VIC20", "VIC-20"},
    {"PET2001", "PET 2001"},
    {"Spectrum", "ZX Spectrum"},
    {"ZX81", "ZX81"},
    {"ZXNext", "ZX Spectrum Next"},
    {"SAMCOUPE", "SAM Coupe"},
    {"Amstrad", "Amstrad CPC"},
    {"BBCMicro", "BBC Micro"},
    {"ARCHIE", "Archimedes"},
    {"MSX", "MSX"},
    {"Apple-II", "Apple II"},
    {"Apple-IIgs", "Apple IIgs"},
    {"MACPLUS", "Macintosh Plus"},
    {"X68000", "Sharp X68000"},
    {"NES", "NES"},
    {"FDS", "Famicom Disk"},
    {"SNES", "Super Nintendo"},
    {"N64", "Nintendo 64"},
    {"GAMEBOY", "Game Boy"},
    {"GAMEBOY2P", "Game Boy 2P"},
    {"GBC", "Game Boy Color"},
    {"SGB", "Super Game Boy"},
    {"GBA", "Game Boy Advance"},
    {"GBA2P", "Game Boy Adv. 2P"},
    {"VirtualBoy", "Virtual Boy"},
    {"PokemonMini", "Pokemon Mini"},
    {"SG1000", "SG-1000"},
    {"SMS", "Master System"},
    {"Genesis", "Mega Drive"},
    {"MegaDrive", "Mega Drive"},
    {"MegaCD", "Mega-CD"},
    {"S32X", "32X"},
    {"Saturn", "Saturn"},
    {"PSX", "PlayStation"},
    {"TGFX16", "PC Engine"},
    {"NEOGEO", "Neo Geo"},
    {"WONDERSWAN", "WonderSwan"},
    {"Coleco", "ColecoVision"},
    {"Intellivision", "Intellivision"},
    {"VECTREX", "Vectrex"},
    {"ODYSSEY2", "Odyssey 2"},
    {"ChannelF", "Channel F"},
    {"Astrocade", "Astrocade"},
    {"CD-i", "CD-i"},
    {"3DO", "3DO"},
};

}  // namespace

std::string_view displayName(std::string_view coreName) {
  for (const auto& e : kNames) {
    if (coreName == e.core) return e.name;
  }
  return coreName;
}

}  // namespace coreinfo
