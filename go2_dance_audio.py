"""Play a local soundtrack on the Go2 speaker through its WebRTC audio channel."""
import asyncio
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory


async def serve(ip, source):
    from aiortc.contrib.media import MediaPlayer
    from unitree_webrtc_connect import UnitreeWebRTCConnection, WebRTCConnectionMethod

    with TemporaryDirectory() as directory:
        clip = Path(directory) / "dance.wav"
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            from imageio_ffmpeg import get_ffmpeg_exe

            ffmpeg = get_ffmpeg_exe()
        subprocess.run([
            ffmpeg, "-nostdin", "-loglevel", "error", "-ss", "22", "-i", source,
            "-vn", "-ac", "1", "-ar", "48000", str(clip),
        ], check=True)
        key = os.environ.get("GO2_AUDIO_AES_KEY")
        if key and not re.fullmatch(r"[0-9a-fA-F]{32}", key):
            raise ValueError("GO2_AUDIO_AES_KEY must contain 32 hexadecimal characters")
        connection = UnitreeWebRTCConnection(
            WebRTCConnectionMethod.LocalSTA, ip=ip, aes_128_key=key
        )
        try:
            await asyncio.wait_for(connection.connect(), timeout=20)
            print("Go2 speaker ready for Dance1", flush=True)
            player = None
            sender = None
            try:
                while command := await asyncio.to_thread(sys.stdin.buffer.readline):
                    if player is not None:
                        sender.replaceTrack(None)
                        player.audio.stop()
                        player = None
                    if command.strip() == b"play":
                        player = MediaPlayer(str(clip))
                        if sender is None:
                            sender = connection.pc.addTrack(player.audio)
                        else:
                            sender.replaceTrack(player.audio)
            finally:
                if player is not None:
                    player.audio.stop()
        finally:
            await connection.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(serve(sys.argv[1], sys.argv[2]))
    except Exception as error:
        print(f"Go2 speaker error: {error}", file=sys.stderr)
        raise SystemExit(1)
