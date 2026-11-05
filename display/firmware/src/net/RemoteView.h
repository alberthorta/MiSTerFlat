#pragma once

#include <stddef.h>
#include <stdint.h>

// The virtual display: a web page on this board (port 80) that shows the screen and takes
// touches, so a phone can be the display. The screen goes out as the framebuffer itself, so the
// page is the same as the panel pixel for pixel; touches come back as a finger on the panel.
//
// Threads: publish() runs in the main loop (from DisplayManager::present()); the encoder and
// sender run in their own task and in the HTTP server task. The frame is copied under a mutex
// only while someone watches, so with no page open this costs nothing.
namespace remote {

bool start();
bool watching();
// A finished frame (RGB565 big-endian, row-major) and whether the backlight is on.
void publish(const uint8_t* frame, size_t bytes, int width, int height, bool lightOn);
// A page just connected and has no frame yet: DisplayManager::tick() publishes the current one.
// From the main loop, between two drawings, so the page never gets a half-drawn frame.
bool wantsFrame();
// The page's finger, for DisplayManager::touched(): true while it is down.
bool touch(int* x, int* y);

}  // namespace remote
