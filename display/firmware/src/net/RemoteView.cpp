#include "net/RemoteView.h"

#include "config.h"

#if MDS_HAS_STATION

#include <Arduino.h>
#include <esp_heap_caps.h>
#include <esp_http_server.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <freertos/task.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

#include <atomic>

#include "net/RemotePage.h"
#include "util/Log.h"

namespace remote {

namespace {

constexpr int kMaxClients = 3;
constexpr uint32_t kMinFrameGapMs = 66;  // at most 15 frames per second to the page
// A finger from a page that went quiet (phone locked, network gone) is lifted after this.
// The page repeats a held touch every second, so a 2 s hold to power off still works.
constexpr uint32_t kTouchStaleMs = 2500;
constexpr size_t kHeaderBytes = 6;

httpd_handle_t server = nullptr;
TaskHandle_t sender = nullptr;
SemaphoreHandle_t frameLock = nullptr;  // guards pub*
SemaphoreHandle_t sent = nullptr;       // the HTTP task finished one send round

uint8_t* pub = nullptr;  // the last published frame
size_t pubBytes = 0;
int pubWidth = 0, pubHeight = 0;
bool pubLight = true;
uint32_t pubSeq = 0;
uint8_t* out = nullptr;  // the encoded frame being sent
size_t outBytes = 0;
size_t outCapacity = 0;

portMUX_TYPE clientsMux = portMUX_INITIALIZER_UNLOCKED;
int clients[kMaxClients] = {-1, -1, -1};
std::atomic<int> clientCount{0};
std::atomic<bool> needFrame{false};
std::atomic<bool> needSend{false};  // a new client: send even if the frame did not change

std::atomic<uint32_t> touchState{0};  // bit 31 down, bits 16-27 x, bits 0-11 y
std::atomic<uint32_t> touchMs{0};

void addClient(int fd) {
  portENTER_CRITICAL(&clientsMux);
  int n = 0;
  bool added = false;
  for (int& c : clients) {
    if (c == fd) added = true;
  }
  for (int& c : clients) {
    if (!added && c < 0) {
      c = fd;
      added = true;
    }
    if (c >= 0) ++n;
  }
  clientCount = n;
  portEXIT_CRITICAL(&clientsMux);
}

void removeClient(int fd) {
  portENTER_CRITICAL(&clientsMux);
  int n = 0;
  for (int& c : clients) {
    if (c == fd) c = -1;
    if (c >= 0) ++n;
  }
  clientCount = n;
  portEXIT_CRITICAL(&clientsMux);
  if (n == 0) touchState = 0;  // nobody left to lift the finger
}

// Run-length code over 16-bit pixels: a byte t, then
//   t & 0x80: one pixel repeated (t & 0x7f) + 1 times;
//   else:     (t + 1) pixels as they are.
// The screens are mostly flat colour; a full core picture still shrinks a little.
size_t encode(const uint8_t* src, size_t pixels, uint8_t* dst) {
  const uint16_t* p = reinterpret_cast<const uint16_t*>(src);
  size_t o = 0, i = 0;
  while (i < pixels) {
    size_t run = 1;
    while (i + run < pixels && run < 128 && p[i + run] == p[i]) ++run;
    if (run >= 3) {
      dst[o++] = static_cast<uint8_t>(0x80 | (run - 1));
      memcpy(dst + o, p + i, 2);
      o += 2;
      i += run;
      continue;
    }
    // Literal: until the next run of 3 or 128 pixels.
    size_t lit = 0;
    while (i + lit < pixels && lit < 128) {
      if (i + lit + 2 < pixels && p[i + lit] == p[i + lit + 1] && p[i + lit] == p[i + lit + 2]) break;
      ++lit;
    }
    dst[o++] = static_cast<uint8_t>(lit - 1);
    memcpy(dst + o, p + i, lit * 2);
    o += lit * 2;
    i += lit;
  }
  return o;
}

void sendRound(void*) {
  httpd_ws_frame_t frame = {};
  frame.type = HTTPD_WS_TYPE_BINARY;
  frame.final = true;
  frame.payload = out;
  frame.len = outBytes;
  int fds[kMaxClients];
  portENTER_CRITICAL(&clientsMux);
  memcpy(fds, clients, sizeof(fds));
  portEXIT_CRITICAL(&clientsMux);
  for (int fd : fds) {
    if (fd < 0) continue;
    if (httpd_ws_get_fd_info(server, fd) != HTTPD_WS_CLIENT_WEBSOCKET ||
        httpd_ws_send_frame_async(server, fd, &frame) != ESP_OK) {
      removeClient(fd);
      httpd_sess_trigger_close(server, fd);
    }
  }
  xSemaphoreGive(sent);
}

void senderTask(void*) {
  uint32_t sentSeq = 0;
  uint32_t lastMs = 0;
  for (;;) {
    ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(1000));
    if (clientCount == 0) continue;
    const uint32_t gap = millis() - lastMs;
    if (gap < kMinFrameGapMs) vTaskDelay(pdMS_TO_TICKS(kMinFrameGapMs - gap));
    xSemaphoreTake(frameLock, portMAX_DELAY);
    const bool fresh = pubSeq != sentSeq;
    if (pub && (fresh || needSend)) {
      needSend = false;
      sentSeq = pubSeq;
      out[0] = 'F';
      out[1] = pubLight ? 1 : 0;
      out[2] = pubWidth & 0xFF;
      out[3] = pubWidth >> 8;
      out[4] = pubHeight & 0xFF;
      out[5] = pubHeight >> 8;
      outBytes = kHeaderBytes + encode(pub, pubBytes / 2, out + kHeaderBytes);
      xSemaphoreGive(frameLock);
      lastMs = millis();
      // Wait for the round: the next encode would overwrite `out` while it is still going out.
      if (httpd_queue_work(server, sendRound, nullptr) == ESP_OK) xSemaphoreTake(sent, portMAX_DELAY);
    } else {
      xSemaphoreGive(frameLock);
    }
  }
}

esp_err_t pageHandler(httpd_req_t* req) {
  httpd_resp_set_type(req, "text/html; charset=utf-8");
  httpd_resp_set_hdr(req, "Cache-Control", "no-store");
  return httpd_resp_send(req, kRemotePage, HTTPD_RESP_USE_STRLEN);
}

esp_err_t wsHandler(httpd_req_t* req) {
  if (req->method == HTTP_GET) {
    // The handshake: from now on this socket gets the frames.
    addClient(httpd_req_to_sockfd(req));
    needSend = true;
    needFrame = true;
    return ESP_OK;
  }
  httpd_ws_frame_t frame = {};
  esp_err_t err = httpd_ws_recv_frame(req, &frame, 0);
  if (err != ESP_OK) return err;
  char text[33];
  if (frame.len >= sizeof(text)) return ESP_FAIL;  // not one of ours: close the socket
  frame.payload = reinterpret_cast<uint8_t*>(text);
  err = httpd_ws_recv_frame(req, &frame, frame.len);
  if (err != ESP_OK || frame.type != HTTPD_WS_TYPE_TEXT) return err;
  text[frame.len] = '\0';
  // "d x y" finger down, "m x y" it moved, "u" lifted.
  int x = 0, y = 0;
  if ((text[0] == 'd' || text[0] == 'm') && sscanf(text + 1, "%d %d", &x, &y) == 2) {
    x = constrain(x, 0, cfg::kScreenWidth - 1);
    y = constrain(y, 0, cfg::kScreenHeight - 1);
    touchState = 0x80000000u | static_cast<uint32_t>(x) << 16 | static_cast<uint32_t>(y);
    touchMs = millis();
  } else if (text[0] == 'u') {
    touchState = 0;
  }
  return ESP_OK;
}

// With close_fn set, closing the socket is up to us.
void onClose(httpd_handle_t, int fd) {
  removeClient(fd);
  close(fd);
}

}  // namespace

bool start() {
  if (server) return true;
  const size_t frameBytes = static_cast<size_t>(cfg::kScreenWidth) * cfg::kScreenHeight * 2;
  outCapacity = kHeaderBytes + frameBytes + frameBytes / 128 + 16;
  pub = static_cast<uint8_t*>(heap_caps_malloc(frameBytes, MALLOC_CAP_SPIRAM));
  out = static_cast<uint8_t*>(heap_caps_malloc(outCapacity, MALLOC_CAP_SPIRAM));
  frameLock = xSemaphoreCreateMutex();
  sent = xSemaphoreCreateBinary();
  if (!pub || !out || !frameLock || !sent) {
    LOGF("remote: no memory");
    return false;
  }
  httpd_config_t config = HTTPD_DEFAULT_CONFIG();
  config.max_open_sockets = kMaxClients + 2;
  config.lru_purge_enable = true;
  config.stack_size = 6144;
  config.close_fn = onClose;
  if (httpd_start(&server, &config) != ESP_OK) {
    LOGF("remote: server did not start");
    server = nullptr;
    return false;
  }
  static const httpd_uri_t page = {"/", HTTP_GET, pageHandler, nullptr, false, false, nullptr};
  static const httpd_uri_t ws = {"/ws", HTTP_GET, wsHandler, nullptr, true, false, nullptr};
  httpd_register_uri_handler(server, &page);
  httpd_register_uri_handler(server, &ws);
  xTaskCreatePinnedToCore(senderTask, "remote", 4096, nullptr, 2, &sender, 0);
  LOGF("remote: serving on port 80");
  return true;
}

bool watching() { return clientCount > 0; }

bool wantsFrame() { return needFrame; }

void publish(const uint8_t* frame, size_t bytes, int width, int height, bool lightOn) {
  if (clientCount == 0 || !pub || !frame) return;
  needFrame = false;
  if (xSemaphoreTake(frameLock, pdMS_TO_TICKS(50)) != pdTRUE) return;
  memcpy(pub, frame, bytes);
  pubBytes = bytes;
  pubWidth = width;
  pubHeight = height;
  pubLight = lightOn;
  ++pubSeq;
  xSemaphoreGive(frameLock);
  xTaskNotifyGive(sender);
}

bool touch(int* x, int* y) {
  const uint32_t s = touchState;
  if (!(s & 0x80000000u)) return false;
  if (millis() - touchMs > kTouchStaleMs) {
    touchState = 0;
    return false;
  }
  *x = (s >> 16) & 0xFFF;
  *y = s & 0xFFF;
  return true;
}

}  // namespace remote

#else  // boards without the station

namespace remote {
bool start() { return false; }
bool watching() { return false; }
bool wantsFrame() { return false; }
void publish(const uint8_t*, size_t, int, int, bool) {}
bool touch(int*, int*) { return false; }
}  // namespace remote

#endif
