"""View the RealSense color feed from the Jetson alongside gesture control."""
import argparse
import socket
import struct
import sys

import cv2
import numpy as np

HEADER = struct.Struct("!dfHHII")
MAX_PAYLOAD = 8 * 1024 * 1024
WINDOW = "Go2 RealSense - Jetson"


def receive(stream, size):
    data = stream.read(size)
    if len(data) != size:
        raise ConnectionError("Jetson camera stream closed")
    return data


def camera_frames(host, port):
    """Yield decoded color frames without opening a GUI window."""
    with socket.create_connection((host, port), timeout=3) as connection:
        with connection.makefile("rb") as stream:
            while True:
                _, _, _, _, jpeg_size, depth_size = HEADER.unpack(receive(stream, HEADER.size))
                if not 0 < jpeg_size <= jpeg_size + depth_size <= MAX_PAYLOAD:
                    raise ValueError("Invalid Jetson camera frame size")
                jpeg = receive(stream, jpeg_size)
                receive(stream, depth_size)
                frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
                if frame is None:
                    raise ValueError("Invalid Jetson camera image")
                yield frame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", nargs="?", default="192.168.123.18")
    parser.add_argument("--port", type=int, default=5600)
    args = parser.parse_args()
    try:
        for frame in camera_frames(args.host, args.port):
            cv2.imshow(WINDOW, frame)
            if cv2.waitKey(1) & 0xFF in (27, ord("q"), ord("Q")):
                break
            try:
                visible = cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE)
            except cv2.error as exc:
                if exc.code != -27:  # HighGUI window was already destroyed.
                    raise
                break
            if visible < 1:
                break
    except (OSError, ValueError, cv2.error) as exc:
        print(f"Camera error: {exc}", file=sys.stderr)
        return 1
    finally:
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
