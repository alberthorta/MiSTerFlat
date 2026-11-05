#pragma once

// Human-readable system names for MiSTer core names (the text in /tmp/CORENAME).
// Core names were taken from the file names in venice1200/MiSTer_tty2oled_pictures (e20f6bb),
// which are keyed by CORENAME. Arcade cores use their MAME set name and are not listed.

#include <string_view>

namespace coreinfo {

// The display name for `coreName`, or `coreName` itself if it is not in the table.
std::string_view displayName(std::string_view coreName);

}  // namespace coreinfo
