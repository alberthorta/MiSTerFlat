#pragma once

#include <stddef.h>
#include <stdint.h>

#include <string_view>

#include "ProtocolParser.h"
#include "ui/DisplayManager.h"

namespace CoreScreen {

// Text-only core screen: the system name, large and centered. When the friendly name differs
// from the MiSTer core name (PSX -> PlayStation), the core name is shown small underneath.
void drawNameOnly(DisplayManager& display, std::string_view coreName);

// tty2oled artwork scaled to the full width (320x80), centered, no text: the logos carry the
// name. Falls back to drawNameOnly() if the picture is not valid.
void drawWithArtwork(DisplayManager& display, std::string_view coreName, proto::ImageFormat format,
                     const uint8_t* data, size_t length);

enum class AssetFormat : uint8_t { Png, Jpeg };

// A native colour picture (PNG or JPEG), normally 320x170, centered on black. Smaller pictures
// are centered, larger ones cropped. Returns false (nothing presented) if decoding fails.
bool drawAsset(DisplayManager& display, AssetFormat format, const uint8_t* data, size_t length);

}  // namespace CoreScreen
