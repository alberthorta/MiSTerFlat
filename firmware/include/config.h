#pragma once

#include <stdint.h>

#define MDS_FW_VERSION "0.4.1"

// One firmware, several boards: platformio.ini sets MDS_BOARD_* per environment. Each board file
// gives its pins, panel, screen size and the id it answers to CMDHWINF.
#if defined(MDS_BOARD_WAVESHARE_LCD2)
#include "boards/waveshare_lcd2.h"
#else
#include "boards/tdisplay_s3.h"
#endif
