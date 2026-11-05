#pragma once

#include <stddef.h>
#include <stdint.h>

namespace proto {

// CRC-32 as zlib/PNG/Python's zlib.crc32 compute it (reflected, polynomial 0xEDB88320).
uint32_t crc32(const uint8_t* data, size_t length);

}  // namespace proto
