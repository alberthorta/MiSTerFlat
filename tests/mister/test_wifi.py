#!/usr/bin/env python3
"""Checks wifi.py without a dongle: PSK, parsing `iw scan`, and adding a network to the config.

    python3 tests/mister/test_wifi.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "mister"))
import wifi  # noqa: E402

failures = 0


def check(name, ok, detail=""):
    global failures
    print("{} {}{}".format("PASS" if ok else "FAIL", name, "" if ok else "  " + detail))
    failures += not ok


# IEEE 802.11i-2004 annex H.4 test vector (also what wpa_passphrase prints).
check("PSK test vector", wifi.psk(b"IEEE", "password") ==
      "f42c6fc52df0ebef9ebb4b90b38a5f902e83fe1b135a70e23aed762e9710a12e")

SCAN = """BSS 8e:78:48:f8:a6:82(on wlan0) -- associated
\tcapability: ESS Privacy SpectrumMgmt (0x1111)
\tsignal: -55.00 dBm
\tSSID: Home
\tRSN:\t * Version: 1
BSS 4a:ba:4e:65:b7:ce(on wlan0)
\tcapability: ESS Privacy (0x0111)
\tsignal: -45.00 dBm
\tSSID: Printer
\tRSN:\t * Version: 1
BSS de:08:da:bc:11:ef(on wlan0)
\tcapability: ESS (0x0401)
\tsignal: -62.00 dBm
\tSSID: \\x00\\x00
BSS 84:78:48:f8:a6:83(on wlan0)
\tcapability: ESS (0x0401)
\tsignal: -70.00 dBm
\tSSID: Caf\\xc3\\xa9 open
BSS 84:78:48:f8:a6:84(on wlan0)
\tcapability: ESS Privacy (0x0411)
\tsignal: -40.00 dBm
\tSSID: Home
\tRSN:\t * Version: 1
BSS 84:78:48:f8:a6:85(on wlan0)
\tcapability: ESS Privacy (0x0411)
\tsignal: -50.00 dBm
\tSSID:
\tRSN:\t * Version: 1
"""
nets = wifi.parse_scan(SCAN)
names = [n[0] for n in nets]
check("connected network first", names[0] == b"Home" and nets[0][3], repr(nets))
check("one entry per name, hidden ones out", names == [b"Home", b"Printer", "Café open".encode()], repr(names))
check("open network seen as open", nets[2][2] is False and nets[1][2] is True, repr(nets))
check("\\xNN bytes decoded", "Café open".encode() in names)

OLD = 'ctrl_interface=DIR=/var/run/wpa_supplicant\n\nnetwork={\n\tssid="Home"\n\tpsk="secret"\n}\n'
new = wifi.add_network(OLD, b"Cafe", "pass word,1")
head, blocks = wifi.split_conf(new)
check("old network kept", len(blocks) == 2 and wifi.block_ssid(blocks[0]) == b"Home", new)
check("header kept", head == ["ctrl_interface=DIR=/var/run/wpa_supplicant"], repr(head))
check("new network in hex, hashed key, highest priority",
      "ssid=43616665" in blocks[1] and "psk=" + wifi.psk(b"Cafe", "pass word,1") in blocks[1]
      and wifi.block_priority(blocks[1]) == 1 and "pass word" not in new, new)
again = wifi.add_network(new, b"Home", "")
_, blocks = wifi.split_conf(again)
check("re-adding a saved network replaces it", [wifi.block_ssid(b) for b in blocks] == [b"Cafe", b"Home"], again)
check("open network: key_mgmt=NONE, priority above the others",
      "key_mgmt=NONE" in blocks[1] and wifi.block_priority(blocks[1]) == 2, again)
sys.exit(1 if failures else 0)
