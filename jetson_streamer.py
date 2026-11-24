"""Run this ON THE GO2's JETSON when the RealSense is plugged into the Jetson.

It sends colour (JPEG) + aligned depth (half size, zlib) to the laptop over
the robot's Ethernet network. The laptop connects to it:
    python3 go2_gesture_control.py --source jetson --jetson-ip 192.168.123.18

Run:  python3 jetson_streamer.py            (Ctrl+C to stop)
Needs only: pyrealsense2, opencv-python (or JetPack's cv2), numpy.
"""
import argparse
import socket
import struct
import time
import zlib

import cv2
import numpy as np

HEADER = struct.Struct("!dfHHII")   # must match camera_sources.py


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5600)
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--jpeg-quality", type=int, default=80)
    ap.add_argument("--no-depth", action="store_true", help="send colour only")
    ap.add_argument("--video-device", help="V4L2 color device, for example /dev/video2")
    args = ap.parse_args()

    capture = None
    pipeline = None
    scale = 0.0
    if args.video_device:
        capture = cv2.VideoCapture(args.video_device, cv2.CAP_V4L2)
        if not capture.isOpened():
            raise SystemExit(f"Cannot open color device {args.video_device}")
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
        capture.set(cv2.CAP_PROP_FPS, args.fps)
        ok, first_frame = capture.read()
        if not ok or first_frame is None:
            capture.release()
            raise SystemExit(f"No color frames from {args.video_device}; check the V4L2 device.")
        print(f"Color camera started: {args.video_device}")
    else:
        try:
            import pyrealsense2 as rs
        except ImportError:
            raise SystemExit("pyrealsense2 is missing. For color, use --video-device /dev/videoN.")
        pipeline = rs.pipeline()
        cfg = rs.config()
        cfg.enable_stream(rs.stream.color, args.width, args.height, rs.format.bgr8, args.fps)
        if not args.no_depth:
            cfg.enable_stream(rs.stream.depth, args.width, args.height, rs.format.z16, args.fps)
        profile = pipeline.start(cfg)
        if not args.no_depth:
            scale = profile.get_device().first_depth_sensor().get_depth_scale()
            align = rs.align(rs.stream.color)
        print(f"RealSense started, depth scale {scale}")

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", args.port))
    server.listen(1)

    try:
        while True:
            print(f"Waiting for laptop on port {args.port}...")
            conn, addr = server.accept()
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            conn.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 256 * 1024)
            print(f"Laptop connected: {addr[0]}")
            sent, t0 = 0, time.time()
            try:
                while True:
                    if capture is not None:
                        ok, color = capture.read()
                        if not ok or color is None:
                            raise SystemExit(f"Color frames stopped on {args.video_device}")
                    else:
                        ok, frames = pipeline.try_wait_for_frames(1000)
                        if not ok:
                            continue
                        if not args.no_depth:
                            frames = align.process(frames)
                            d = frames.get_depth_frame()
                            if not d:
                                continue
                        c = frames.get_color_frame()
                        if not c:
                            continue
                        color = np.asanyarray(c.get_data())
                    ok, jpg = cv2.imencode(".jpg", color,
                                           [cv2.IMWRITE_JPEG_QUALITY, args.jpeg_quality])
                    if not ok:
                        continue
                    jpg = jpg.tobytes()
                    if args.no_depth or capture is not None:
                        dbytes, dw, dh = b"", 0, 0
                    else:
                        depth = np.asanyarray(d.get_data())
                        small = cv2.resize(depth, (depth.shape[1] // 2, depth.shape[0] // 2),
                                           interpolation=cv2.INTER_NEAREST)
                        dh, dw = small.shape
                        dbytes = zlib.compress(small.tobytes(), 1)
                    conn.sendall(HEADER.pack(time.time(), scale, dw, dh, len(jpg), len(dbytes))
                                 + jpg + dbytes)
                    sent += 1
                    if time.time() - t0 >= 5:
                        print(f"  streaming {sent / (time.time() - t0):.1f} fps")
                        sent, t0 = 0, time.time()
            except (BrokenPipeError, ConnectionResetError, OSError) as e:
                print(f"Laptop disconnected ({e})")
            finally:
                conn.close()
    except KeyboardInterrupt:
        pass
    finally:
        if pipeline is not None:
            pipeline.stop()
        if capture is not None:
            capture.release()
        server.close()


if __name__ == "__main__":
    main()
