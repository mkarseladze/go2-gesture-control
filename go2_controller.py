"""Explicit, Go2 SDK2 adapter for the camera application."""
import os
from pathlib import Path
import socket
import subprocess
import struct
import time
from collections import deque
from threading import Thread


COMMAND_CODES = {"FORWARD": 1, "BACKWARD": 2, "LEFT": 3, "RIGHT": 4, "HEART": 5, "SIT": 6, "STAND_UP": 7, "HELLO": 8, "DANCE1": 9}


class Go2Controller:
    def __init__(self, interface, *, report_dance=False):
        socket.if_nametoindex(interface)
        carrier = Path("/sys/class/net") / interface / "carrier"
        if carrier.read_text().strip() != "1":
            raise RuntimeError(f"No Ethernet link on {interface}")
        directory = Path(__file__).resolve().parent
        executable = directory / "go2_forward"
        if not executable.is_file():
            raise RuntimeError("Build go2_forward first (see README.txt).")
        subprocess.run([directory / "read_go2_state", interface], check=True, timeout=8)
        self.dance_events = deque()
        self.process = subprocess.Popen(
            [executable, interface], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE if report_dance else None,
        )
        if report_dance:
            Thread(target=self._read_status, daemon=True).start()
        os.set_blocking(self.process.stdin.fileno(), False)

    def _read_status(self):
        with self.process.stdout as stream:
            for raw_line in stream:
                line = raw_line.decode(errors="replace").strip()
                print(line, flush=True)
                events = {
                    "Go2 accepted Dance1()": "accepted",
                    "Go2 Dance1 started": "started",
                    "Go2 Dance1 ended": "ended",
                }
                if line in events:
                    self.dance_events.append((events[line], time.monotonic()))

    def update(self, command):
        if self.process.poll() is not None:
            raise RuntimeError("Go2 controller exited. Check the SDK error in the terminal.")
        # Low four bits encode the command. Zero is an immediate stop.
        code = COMMAND_CODES.get(command, 0)
        request = (time.monotonic_ns() << 4) | code if code else 0
        os.write(self.process.stdin.fileno(), struct.pack("=Q", request))

    def close(self):
        self.process.stdin.close()
        try:
            status = self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
            raise RuntimeError("Go2 controller timed out during shutdown") from None
        if status:
            raise RuntimeError(f"Go2 controller exited with status {status}")
