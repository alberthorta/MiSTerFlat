"""Minimal raw serial port for macOS/Linux using only the standard library (no pyserial),
so the same tools run on a Mac and on the MiSTer.

The port is configured like tty2oled does it: `stty 115200 cs8 raw -parenb -cstopb -hupcl -echo`.
The baud rate does not matter for USB CDC but is set anyway.
"""
import os
import select
import termios
import time

# What each board answers to CMDHWINF (<id>;MDS-<version>;), and the PlatformIO environment that
# builds its firmware. A release has one misterlily-<version>-<env>.bin per board.
BOARDS = {
    "HWTDISPS3": "tdisplay_s3",  # LILYGO T-Display-S3
    "HWWSTLCD2": "waveshare_lcd2",  # Waveshare ESP32-S3-Touch-LCD-2
}

# macOS drops output still queued in the USB CDC driver when the port is closed, even after
# tcdrain() (measured: 8 of 10 lines arrived when closing right away, 10 of 10 after 50 ms).
CLOSE_SETTLE_SECONDS = 0.1


class Port:
    def __init__(self, path, baud=115200):
        self.path = path
        self.fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        self._wrote = False
        self._configure(baud)

    def _configure(self, baud):
        attrs = termios.tcgetattr(self.fd)
        iflag, oflag, cflag, lflag, _ispeed, _ospeed, cc = attrs
        # Same effect as cfmakeraw(): no echo, no CR/LF translation, no signals, 8 bits.
        iflag &= ~(termios.IGNBRK | termios.BRKINT | termios.PARMRK | termios.ISTRIP |
                   termios.INLCR | termios.IGNCR | termios.ICRNL | termios.IXON | termios.IXOFF)
        oflag &= ~termios.OPOST
        lflag &= ~(termios.ECHO | termios.ECHONL | termios.ICANON | termios.ISIG | termios.IEXTEN)
        cflag &= ~(termios.CSIZE | termios.PARENB | termios.CSTOPB | termios.HUPCL)
        cflag |= termios.CS8 | termios.CREAD | termios.CLOCAL
        speed = getattr(termios, "B%d" % baud)
        cc[termios.VMIN] = 0
        cc[termios.VTIME] = 0
        termios.tcsetattr(self.fd, termios.TCSANOW, [iflag, oflag, cflag, lflag, speed, speed, cc])

    def close(self):
        if self.fd is not None:
            if self._wrote:
                time.sleep(CLOSE_SETTLE_SECONDS)
            os.close(self.fd)
            self.fd = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def write(self, data):
        if isinstance(data, str):
            data = data.encode()
        view = memoryview(data)
        self._wrote = True
        while view:
            select.select([], [self.fd], [], 1.0)
            try:
                n = os.write(self.fd, view)
            except BlockingIOError:
                continue
            view = view[n:]
        termios.tcdrain(self.fd)

    def read_available(self):
        """Whatever is waiting right now, without waiting. Raises OSError if the device is gone."""
        out = bytearray()
        while True:
            r, _, _ = select.select([self.fd], [], [], 0)
            if not r:
                return bytes(out)
            try:
                chunk = os.read(self.fd, 4096)
            except BlockingIOError:
                return bytes(out)
            if not chunk:
                # Readable but empty: the device went away (macOS returns EOF instead of an error).
                raise OSError("device closed")
            out += chunk

    def read_for(self, seconds):
        """Everything that arrives within `seconds`."""
        out = bytearray()
        end = time.monotonic() + seconds
        while True:
            left = end - time.monotonic()
            if left <= 0:
                return bytes(out)
            r, _, _ = select.select([self.fd], [], [], left)
            if r:
                try:
                    out += os.read(self.fd, 4096)
                except BlockingIOError:
                    pass

    def read_until(self, token, timeout=2.0):
        """Bytes up to and including `token`, or None on timeout."""
        if isinstance(token, str):
            token = token.encode()
        out = bytearray()
        end = time.monotonic() + timeout
        while token not in out:
            left = end - time.monotonic()
            if left <= 0:
                return None
            r, _, _ = select.select([self.fd], [], [], left)
            if r:
                try:
                    out += os.read(self.fd, 4096)
                except BlockingIOError:
                    pass
        return bytes(out)

    def drain(self, quiet=0.15):
        """Discards stale input (old acks) until the line is quiet for `quiet` seconds."""
        total = 0
        while True:
            chunk = self.read_for(quiet)
            if not chunk:
                return total
            total += len(chunk)

    def flush_stale(self):
        """Drops old replies still queued in the device (e.g. ttyacks nobody read).

        The ESP32-S3 USB Serial/JTAG only pushes queued bytes when the firmware writes again,
        so draining alone is not enough: CMDNULL makes it answer, which releases the queue.
        """
        self.drain()
        self.write("CMDNULL\n")
        self.drain()

    def query(self, line, token="\n", timeout=2.0):
        """Sends one command line and returns the reply up to `token` (stale input dropped first)."""
        self.flush_stale()
        self.write(line + "\n")
        return self.read_until(token, timeout)
