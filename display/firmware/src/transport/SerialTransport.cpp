#include "transport/SerialTransport.h"

#include <hal/usb_serial_jtag_ll.h>
#include <string.h>

// Why polling instead of a driver (all three were tried on the board, see docs/research.md §6):
// - Arduino HWCDC (`Serial`, core 2.0.17): 4 of 5 replies never reached the host although
//   write() reported success; its "connected" state machine stranded them.
// - ESP-IDF v4.4.7 usb_serial_jtag driver: when its TX interrupt runs with an empty queue it
//   clears IN_EMPTY and disables itself; later writes then hang until something else flushes
//   the FIFO. Reproducible ~10 s after boot. Its RX interrupt also drops packets when the ring
//   buffer is full.
// - Polling the FIFO registers has neither problem and gives real USB flow control on RX.
// `Serial` (HWCDC) must never be started in this firmware.

namespace {

constexpr size_t kFifoBytes = 64;
// If the host stops reading (port closed), queued replies are stale by the time it reads
// again; drop them so the next reader does not get a pile of old "ttyack;". The 64 bytes
// already in the hardware FIFO cannot be taken back.
constexpr uint32_t kStaleTxMs = 300;

}  // namespace

void SerialTransport::begin() {}

void SerialTransport::poll(uint32_t nowMs) {
  if (txUsed() == 0) {
    lastTxProgressMs_ = nowMs;
    return;
  }
  bool wrote = false;
  while (txUsed() > 0 && usb_serial_jtag_ll_txfifo_writable()) {
    const uint8_t b = tx_[txTail_ % kTxQueueBytes];
    if (usb_serial_jtag_ll_write_txfifo(&b, 1) != 1) break;
    ++txTail_;
    wrote = true;
  }
  if (wrote) {
    usb_serial_jtag_ll_txfifo_flush();
    lastTxProgressMs_ = nowMs;
  } else if (nowMs - lastTxProgressMs_ >= kStaleTxMs) {
    txTail_ = txHead_;
    ++staleFlushes_;
  }
}

size_t SerialTransport::read(uint8_t* buffer, size_t capacity) {
  return usb_serial_jtag_ll_read_rxfifo(buffer, capacity < kFifoBytes ? capacity : kFifoBytes);
}

bool SerialTransport::write(const char* text, size_t length) {
  if (length == 0) return true;
  if (length > kTxQueueBytes - txUsed()) {
    ++droppedWrites_;
    return false;
  }
  for (size_t i = 0; i < length; ++i) tx_[(txHead_ + i) % kTxQueueBytes] = static_cast<uint8_t>(text[i]);
  txHead_ += length;
  return true;
}

bool SerialTransport::write(const char* text) { return write(text, strlen(text)); }
