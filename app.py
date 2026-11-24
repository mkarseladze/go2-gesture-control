"""Camera gesture preview with an optional Go2 controller."""
from __future__ import annotations

import argparse
import math
from collections import deque
from dataclasses import replace
from pathlib import Path
import sys
from threading import Event, Thread
import time

from dance_music import DEFAULT_DURATION, DanceMusic, RobotDanceMusic
from gestures import ACTIONS, DANCE1, CommandGate, HEART, HELLO, SIT, STAND_UP, STOP, UNKNOWN
from wrist_gestures import classify_control, classify_two_hands, thumb_ratio
from motion_plan import MAX_FRAME_AGE, plan_for
from wave_gesture import WaveDetector

MODEL = Path(__file__).resolve().parent / "models" / "hand_landmarker.task"
WINDOW = "Go2 Gesture Control"
CONNECTIONS = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7),
               (7, 8), (5, 9), (9, 10), (10, 11), (11, 12), (9, 13),
               (13, 14), (14, 15), (15, 16), (13, 17), (0, 17),
               (17, 18), (18, 19), (19, 20)]


def read_robot_camera(host, latest, waves, tracking, shutdown, options):
    import cv2
    import mediapipe as mp

    from view_jetson_camera import camera_frames

    wave = WaveDetector()
    last_detection = -1
    try:
        with mp.tasks.vision.HandLandmarker.create_from_options(options) as detector:
            for frame in camera_frames(host, 5600):
                if shutdown.is_set():
                    return
                now = time.monotonic()
                latest.append((now, frame))
                timestamp = int(now * 1000)
                if timestamp - last_detection < 65:
                    continue
                last_detection = timestamp
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = detector.detect_for_video(
                    mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), timestamp)
                height, width = frame.shape[:2]
                hands = [[(p.x * width, p.y * height) for p in hand]
                         for hand in result.hand_landmarks]
                started = wave.update(hands, now)
                if started is not None:
                    waves.append((started, now))
                    status = "Wave detected"
                elif not hands:
                    status = "No hand detected"
                elif len(hands) > 1:
                    status = "Show only one hand"
                elif wave.last_seen is None:
                    status = "Hand seen | Open your palm"
                else:
                    status = f"Open hand | Wave {wave.sweeps}/4"
                tracking.append((now, status, hands))
    except Exception as exc:
        latest.append((0.0, None))
        if not shutdown.is_set():
            print(f"Go2 camera error: {exc}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera", type=int, default=0, help="Camera index (default 0)")
    parser.add_argument("--realsense", action="store_true", help="Use the RealSense color stream")
    parser.add_argument("--self-check", action="store_true", help="Load model, test blank frame; no camera")
    parser.add_argument("--go2", "--go2-forward", dest="go2_forward", metavar="INTERFACE",
                        help="Enable supervised Go2 control")
    parser.add_argument("--jetson-camera", metavar="HOST", help="Show the Go2 RGB view beside gestures")
    parser.add_argument("--dance-music", action="store_true",
                        help="Play the Dance1 soundtrack on the laptop after SDK acknowledgment")
    parser.add_argument("--dance-duration", type=float, default=DEFAULT_DURATION,
                        help="Soundtrack length in seconds (default %(default)s)")
    parser.add_argument("--go2-dance-file", metavar="FILE", nargs="?",
                        const=str(MODEL.parent.parent / "dance-balanda.m4a"),
                        help="Play a local audio file on the Go2 speaker from 0:22")
    parser.add_argument("--go2-audio-ip", default="192.168.123.161",
                        help="Go2 WebRTC address (default %(default)s)")
    args = parser.parse_args()
    if args.go2_dance_file and (not args.go2_forward or args.dance_music):
        parser.error("--go2-dance-file requires --go2 and uses the Go2 speaker")
    if args.dance_music and not args.go2_forward:
        parser.error("--dance-music requires --go2")
    if not math.isfinite(args.dance_duration) or args.dance_duration <= 0:
        parser.error("--dance-duration must be a positive number")
    mode = "LIVE GO2" if args.go2_forward else "CAMERA ONLY"
    source = "RealSense RGB" if args.realsense else f"Camera {args.camera}"
    try:
        import cv2
        import mediapipe as mp
        import numpy as np
    except (ImportError, OSError) as exc:
        print(f"Dependency error: {exc}\nSee README.txt, installation section.", file=sys.stderr)
        return 1
    if not MODEL.is_file():
        print("Missing model: models/hand_landmarker.task. Extract the entire ZIP.", file=sys.stderr)
        return 1
    options = mp.tasks.vision.HandLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(MODEL)),
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        num_hands=2,
        min_hand_detection_confidence=0.6,
        min_hand_presence_confidence=0.6,
        min_tracking_confidence=0.5,
    )
    gate = CommandGate()
    capture = None
    realsense = None
    controller = None
    music = None
    music_deadline = None
    exit_code = 0
    camera_shutdown = Event()
    wave_events = deque(maxlen=1)
    robot_tracking = deque([(0.0, "", [])], maxlen=1)
    robot_frames = deque([(0.0, None)], maxlen=1)
    try:
        with mp.tasks.vision.HandLandmarker.create_from_options(options) as detector:
            if args.self_check:
                image = mp.Image(image_format=mp.ImageFormat.SRGB,
                                 data=np.zeros((480, 640, 3), dtype=np.uint8))
                result = detector.detect_for_video(image, 0)
                if result.hand_landmarks:
                    raise RuntimeError("Unexpected hand on a blank test frame")
                print("PASS: dependencies, model loading and inference. Camera was not opened.")
                return 0
            if args.realsense:
                import pyrealsense2 as rs

                context = rs.context()
                if not context.query_devices():
                    raise RuntimeError("No RealSense camera accessible. Check USB and device permissions.")
                pipeline = rs.pipeline(context)
                config = rs.config()
                config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
                pipeline.start(config)
                realsense = pipeline
            else:
                capture = cv2.VideoCapture(args.camera)
                if not capture.isOpened():
                    raise RuntimeError("Camera unavailable. Close other camera apps, or try --camera 1.")
                capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if args.go2_forward:
                from go2_controller import Go2Controller

                if args.go2_dance_file:
                    music = RobotDanceMusic(args.go2_dance_file, args.go2_audio_ip)
                elif args.dance_music:
                    music = DanceMusic(args.dance_duration)
                controller = Go2Controller(args.go2_forward, report_dance=music is not None)
            if args.jetson_camera:
                robot_options = replace(options, min_hand_detection_confidence=0.45,
                                        min_hand_presence_confidence=0.45)
                Thread(target=read_robot_camera,
                       args=(args.jetson_camera, robot_frames, wave_events, robot_tracking,
                             camera_shutdown, robot_options),
                       daemon=True).start()
            print(f"{mode}: A = enable/disable commands; SPACE = disable; ESC/Q = quit.")
            print("Show one hand, upright, palm toward camera.")
            last_timestamp = -1
            previous = None
            last_action = None
            stopped_since = None
            while True:
                if realsense is None:
                    ok, frame = capture.read()
                else:
                    color = realsense.wait_for_frames(timeout_ms=1000).get_color_frame()
                    ok = bool(color)
                    frame = np.asanyarray(color.get_data()) if ok else None
                captured_at = time.monotonic()
                if not ok or frame is None:
                    raise RuntimeError("Camera frame unavailable; preview stopped.")
                if not args.realsense:
                    frame = cv2.flip(frame, 1)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                timestamp = max(last_timestamp + 1, int(captured_at * 1000))
                last_timestamp = timestamp
                result = detector.detect_for_video(
                    mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), timestamp)
                height, width = frame.shape[:2]
                hands = [[(point.x * width, point.y * height) for point in hand]
                         for hand in result.hand_landmarks]
                if len(hands) == 1:
                    raw, fingers = classify_control(hands[0])
                    if raw == HEART:
                        hint = "Hold the finger heart steady"
                    elif raw == DANCE1:
                        hint = "Hold thumb and pinky out"
                    elif raw == SIT:
                        hint = "Hold the index finger pointed down"
                    else:
                        raised = "".join("1" if finger else "0" for finger in fingers)
                        hint = f"Movement: fingers up | {raised} | Thumb: {thumb_ratio(hands[0]):.2f}"
                elif len(hands) == 2:
                    raw = classify_two_hands(hands)
                    hint = ("Hold both index fingers up" if raw == STAND_UP
                            else "Stand up: index fingers up on both hands")
                else:
                    raw, hint = UNKNOWN, "No hand visible"
                # Slow inference must not promote a stale image to a movement candidate.
                if time.monotonic() - captured_at > MAX_FRAME_AGE:
                    raw, hint = UNKNOWN, "Processing too slow; command stopped"
                output = gate.update(raw, captured_at)
                now = time.monotonic()
                frame_age = now - captured_at
                if music is not None:
                    while controller.dance_events:
                        event, event_at = controller.dance_events.popleft()
                        if args.go2_dance_file:
                            if event == "started" and time.monotonic() - event_at < 1:
                                music.start()
                            elif event == "ended":
                                music.end_playback()
                        elif event == "accepted" and time.monotonic() - event_at < 1:
                            music.start()
                            music_deadline = event_at + args.dance_duration
                    if music_deadline is not None and now >= music_deadline:
                        music.stop()
                        music_deadline = None
                if gate.armed and output == STOP and gate.candidate == STOP:
                    if stopped_since is None:
                        stopped_since = now
                else:
                    stopped_since = None
                if wave_events:
                    started, finished = wave_events.pop()
                    if (stopped_since is not None and started >= stopped_since + 0.5
                            and robot_frames[-1][1] is not None
                            and 0 <= time.monotonic() - finished <= MAX_FRAME_AGE):
                        output = HELLO
                if output in ACTIONS and frame_age <= MAX_FRAME_AGE:
                    if controller is not None:
                        controller.update(output)
                    gate.disarm()
                    last_action = output
                else:
                    output = plan_for(output, enabled=gate.armed, frame_age=frame_age).command
                    if controller is not None and last_action is None:
                        controller.update(output)
                if last_action is not None:
                    output = last_action
                    hint = "Action requested once | A: re-enable" if controller else "Action confirmed | A: re-enable"
                for landmarks in result.hand_landmarks:
                    points = [(int(p.x * width), int(p.y * height)) for p in landmarks]
                    for a, b in CONNECTIONS:
                        cv2.line(frame, points[a], points[b], (0, 220, 100), 2)
                    for point in points:
                        cv2.circle(frame, point, 4, (40, 180, 255), -1)
                panel = np.full((224, width, 3), (30, 26, 23), dtype=np.uint8)
                neutral = (225, 225, 225)
                accent = (105, 235, 125) if gate.armed else (100, 175, 255)
                command_color = (100, 215, 255) if output == STOP else (105, 235, 125)
                status = "ENABLED (A: disable)" if gate.armed else "DISABLED (A: enable)"
                detected = f"Detected gesture: {raw}"
                if gate.candidate != STOP and output == STOP:
                    elapsed = captured_at - gate.since
                    progress = min(elapsed / gate.hold_seconds, gate.count / gate.min_frames, 1)
                    detected += f" | Confirming {progress:.0%}"
                rows = (
                    (f"{mode}   |   {status}", 32, 0.68, accent, 2),
                    (f"LAST ACTION: {last_action}" if last_action is not None else f"COMMAND: {output}",
                     82, 1.25, command_color, 2),
                    (detected, 121, 0.62, neutral, 1),
                    (f"{source}  |  {hint}", 152, 0.53, neutral, 1),
                    ("SPACE: disable   |   Q / ESC: exit", 198, 0.58, neutral, 1),
                )
                for label, y, scale, color, weight in rows:
                    cv2.putText(panel, label, (14, y), cv2.FONT_HERSHEY_SIMPLEX,
                                scale, color, weight, cv2.LINE_AA)
                if args.jetson_camera:
                    received_at, robot_frame = robot_frames[-1]
                    if robot_frame is None or time.monotonic() - received_at > 1:
                        robot_frame = np.full_like(frame, (30, 26, 23))
                        cv2.putText(robot_frame, "Waiting for Go2 camera", (14, 40),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, neutral, 1, cv2.LINE_AA)
                    else:
                        original_height, original_width = robot_frame.shape[:2]
                        robot_frame = cv2.resize(robot_frame, (width, height))
                        seen_at, wave_status, tracked_hands = robot_tracking[-1]
                        if time.monotonic() - seen_at < 0.35:
                            cv2.rectangle(robot_frame, (0, 0), (width, 50), (30, 26, 23), -1)
                            cv2.putText(robot_frame, wave_status, (14, 33),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.66, neutral, 2, cv2.LINE_AA)
                            for hand in tracked_hands:
                                points = [(int(x * width / original_width),
                                           int(y * height / original_height)) for x, y in hand]
                                for a, b in CONNECTIONS:
                                    cv2.line(robot_frame, points[a], points[b], (0, 220, 100), 2)
                                for point in points:
                                    cv2.circle(robot_frame, point, 3, (40, 180, 255), -1)
                    cv2.putText(robot_frame, "Go2 RealSense | Wave to say hello", (14, height - 18),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.65, neutral, 2, cv2.LINE_AA)
                    cv2.putText(frame, "Gesture camera", (14, height - 18),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.65, neutral, 2, cv2.LINE_AA)
                    frame = np.hstack([frame, robot_frame])
                    panel = cv2.copyMakeBorder(panel, 0, 0, 0, width, cv2.BORDER_REPLICATE)
                cv2.imshow(WINDOW, np.vstack([panel, frame]))
                if output != previous:
                    print(f"{time.strftime('%H:%M:%S')} {mode}: {output}", flush=True)
                    previous = output
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord('q'), ord('Q')):
                    break
                if key in (ord('a'), ord('A')):
                    gate.toggle()
                    stopped_since = None
                    last_action = None
                    if controller is not None and not gate.armed:
                        controller.update(STOP)
                elif key == 32:
                    gate.disarm()
                    stopped_since = None
                    last_action = None
                    if controller is not None:
                        controller.update(STOP)
                try:
                    visible = cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE)
                except cv2.error as exc:
                    if exc.code != -27:  # HighGUI window was already destroyed.
                        raise
                    break
                if visible < 1:
                    break
    except KeyboardInterrupt:
        print("Interrupted.")
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        exit_code = 1
    finally:
        camera_shutdown.set()
        gate.disarm()
        if controller is not None:
            try:
                controller.close()
            except RuntimeError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                exit_code = 1
        if music is not None:
            music.stop()
        if capture is not None:
            capture.release()
        if realsense is not None:
            realsense.stop()
        cv2.destroyAllWindows()
        print(f"{mode}: session ended.")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
