"""Play a bounded soundtrack through the laptop's selected audio output."""
import os
import shutil
import subprocess
import sys
import sysconfig

VIDEO = "https://www.youtube.com/watch?v=V8D_GL_WWFY"
START_SECONDS = 22
DEFAULT_DURATION = 45


class DanceMusic:
    def __init__(self, duration):
        self.player = shutil.which("vlc")
        if self.player is None:
            raise RuntimeError("VLC is required for --dance-music")
        self.duration = duration
        self.process = None

    def start(self):
        self.stop()
        try:
            self.process = subprocess.Popen([
                self.player, "--intf=dummy", "--no-one-instance", "--no-video",
                "--play-and-exit", f"--start-time={START_SECONDS}",
                f"--stop-time={START_SECONDS + self.duration}", VIDEO,
            ])
        except OSError as exc:
            print(f"Dance music could not start: {exc}", file=sys.stderr)

    def stop(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()


class RobotDanceMusic:
    def __init__(self, source, ip):
        from importlib.util import find_spec
        from pathlib import Path
        from threading import Event, Thread

        source = Path(source).expanduser().resolve()
        if not source.is_file():
            raise RuntimeError(f"Dance audio file not found: {source}")
        worker = Path(__file__).with_name("go2_dance_audio.py")
        deps = worker.with_name(".go2-audio-deps")
        bundled = (deps / "unitree_webrtc_connect").is_dir() and (deps / "imageio_ffmpeg").is_dir()
        if not bundled and (find_spec("unitree_webrtc_connect") is None or
                            not (shutil.which("ffmpeg") or find_spec("imageio_ffmpeg"))):
            raise RuntimeError("Go2 speaker requires unitree-webrtc-connect and ffmpeg.")
        env = os.environ.copy()
        if bundled:
            existing = env.get("PYTHONPATH")
            env["PYTHONPATH"] = os.pathsep.join([str(deps), existing]) if existing else str(deps)
            multiarch = sysconfig.get_config_var("MULTIARCH")
            if multiarch:
                portaudio = deps / "portaudio" / "usr" / "lib" / multiarch
                if portaudio.is_dir():
                    existing_libraries = env.get("LD_LIBRARY_PATH")
                    env["LD_LIBRARY_PATH"] = (
                        os.pathsep.join([str(portaudio), existing_libraries])
                        if existing_libraries else str(portaudio)
                    )
        self.ready = Event()
        self.process = subprocess.Popen(
            [sys.executable, str(worker), ip, str(source)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, env=env,
        )
        Thread(target=self._read_status, daemon=True).start()

    def _read_status(self):
        with self.process.stdout as stream:
            for line in stream:
                print(line, end="", flush=True)
                if line.strip() == "Go2 speaker ready for Dance1":
                    self.ready.set()

    def start(self):
        if not self.ready.is_set():
            print("Go2 speaker is still connecting. No audio was queued.", file=sys.stderr)
            return
        self._send("play")

    def end_playback(self):
        self._send("stop")

    def _send(self, command):
        if self.process.poll() is not None:
            print("Go2 speaker is unavailable. Check the WebRTC error above.", file=sys.stderr)
            return
        try:
            self.process.stdin.write(command + "\n")
            self.process.stdin.flush()
        except BrokenPipeError:
            print("Go2 speaker connection closed.", file=sys.stderr)

    def stop(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=2)
