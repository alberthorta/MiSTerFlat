#!/usr/bin/env python3
"""Checks display_wifi.py: MDSSTA lines into the state file, and the command file.

    python3 tests/mister/test_display_wifi.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "mister"))
import display_wifi as dw  # noqa: E402

failures = 0


def check(name, ok, detail=""):
    global failures
    print("{} {}{}".format("PASS" if ok else "FAIL", name, "" if ok else "  " + detail))
    failures += not ok


home = "Casa 5G".encode().hex()
state = dw.new_state()

check("other lines are not ours", not dw.handle_line(b"MDSPONG;up=5", state))
check("status", dw.handle_line(b"MDSSTA,status,ok,192.168.53.70,-58," + home.encode() + b"\n", state)
      and state["state"] == "ok" and state["ip"] == "192.168.53.70" and state["rssi"] == -58
      and state["ssid"] == "Casa 5G", str(state))

dw.handle_line("MDSSTA,scanning", state)
check("scanning clears the list", state["scanning"] and state["networks"] == [])
dw.handle_line("MDSSTA,net,-40,1," + home, state)
dw.handle_line("MDSSTA,net,-71,0," + "Cafe".encode().hex(), state)
dw.handle_line("MDSSTA,net,-80,1,zz", state)  # bad hex: no name, dropped
dw.handle_line("MDSSTA,end", state)
check("networks", not state["scanning"] and state["networks"] == [
    {"ssid": "Casa 5G", "rssi": -40, "secure": True}, {"ssid": "Cafe", "rssi": -71, "secure": False}],
    str(state["networks"]))

with tempfile.TemporaryDirectory() as tmp:
    cmd = os.path.join(tmp, "cmd")
    with open(cmd, "w") as f:
        f.write("scan\njoin {} {}\nstatus\njoin nothex 00\nforget\nrm -rf /\n".format(home, "secret12".encode().hex()))
    lines = dw.take_commands(state, cmd)
    check("commands", lines == ["MDSSTA,scan\n", "MDSSTA,join,{},{}\n".format(home, "secret12".encode().hex()),
                                "MDSSTA\n", "MDSSTA,forget\n"], str(lines))
    check("command file removed", not os.path.exists(cmd))
    check("open network join", dw.take_commands(state, cmd) == [])
    with open(cmd, "w") as f:
        f.write("join {}\n".format(home))
    check("join without password", dw.take_commands(state, cmd) == ["MDSSTA,join,{},\n".format(home)])

    dw.handle_line("MDSSTA,status,fail,,0," + home, state)
    check("failed join keeps a message", state["error"] == "Could not join Casa 5G. Check the password.", state["error"])
    dw.handle_line("MDSSTA,status,connecting,,0," + "Old".encode().hex(), state)
    check("message stays while it goes back to the old network", state["error"] != "")
    dw.handle_line("MDSSTA,status,ok,10.0.0.2,-50," + "Old".encode().hex(), state)
    check("message cleared once connected", state["error"] == "")

    out = os.path.join(tmp, "state")
    dw.write_state(state, out)
    with open(out) as f:
        saved = json.load(f)
    check("state file", saved["ip"] == "10.0.0.2" and "joining" not in saved, str(saved))
    dw.write_state(None, out)
    check("state file removed", not os.path.exists(out))

print("{} failure(s)".format(failures))
sys.exit(1 if failures else 0)
