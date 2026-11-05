#pragma once

#include <stddef.h>
#include <stdint.h>

// The ESP32-S3 USB Serial/JTAG CDC port, driven by polling its 64-byte hardware FIFOs from the
// main loop (no interrupt, no driver). See docs/research.md section 6 for why.
//
// RX: bytes stay in the hardware FIFO until read(). While it is full the controller NAKs the
// host, so the host waits instead of losing data, however long the loop is busy drawing.
// TX: messages go to a small RAM queue; poll() moves them into the FIFO as the host reads.
class SerialTransport {
 public:
  void begin();

  // Moves queued TX bytes to the hardware. Call every loop iteration.
  void poll(uint32_t nowMs);

  // Copies up to `capacity` received bytes into `buffer`. Never waits.
  size_t read(uint8_t* buffer, size_t capacity);

  // All or nothing, never waits. Returns false and drops the message if the queue is full.
  bool write(const char* text, size_t length);
  bool write(const char* text);

  size_t writeRoom() const { return kTxQueueBytes - txUsed(); }

  uint32_t droppedWrites() const { return droppedWrites_; }
  uint32_t staleFlushes() const { return staleFlushes_; }

 private:
  static constexpr size_t kTxQueueBytes = 1024;

  size_t txUsed() const { return txHead_ - txTail_; }

  uint8_t tx_[kTxQueueBytes] = {};
  size_t txHead_ = 0;  // free-running; index with % kTxQueueBytes
  size_t txTail_ = 0;
  uint32_t lastTxProgressMs_ = 0;
  uint32_t droppedWrites_ = 0;
  uint32_t staleFlushes_ = 0;
};
