#pragma once

// Debug log on UART0 (Serial0, GPIO43/44). Never on the USB CDC port: that port carries
// the tty2oled protocol and the MiSTer scripts read replies from it.

#ifndef MDS_DEBUG_LOG
#define MDS_DEBUG_LOG 0
#endif

#if MDS_DEBUG_LOG
#include <Arduino.h>
#define LOG_BEGIN() Serial0.begin(115200)
#define LOGF(fmt, ...) Serial0.printf("[%7lu] " fmt "\n", (unsigned long)millis(), ##__VA_ARGS__)
#else
#define LOG_BEGIN() \
  do {              \
  } while (0)
#define LOGF(...) \
  do {            \
  } while (0)
#endif
