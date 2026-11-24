"""Read-only environment report. Does not open camera or connect to a robot."""
from pathlib import Path
import platform
import sys
import socket
from importlib.util import find_spec
from importlib import metadata

print("Go2 camera demo: environment report")
print("OS:", platform.platform())
release = Path('/etc/os-release')
if release.is_file():
    for line in release.read_text().splitlines():
        if line.startswith('PRETTY_NAME='):
            print("Distribution:", line.split('=', 1)[1].strip('"'))
print("Architecture:", platform.machine())
print("Python:", sys.version.split()[0])
print("Python executable:", sys.executable)
print("Virtual environment:", sys.prefix != sys.base_prefix)
if sys.platform.startswith('linux'):
    print("glibc:", ' '.join(platform.libc_ver()))
    print("Camera devices:", ', '.join(str(p) for p in sorted(Path('/dev').glob('video*'))) or "none found")
for package in ('mediapipe', 'opencv-contrib-python', 'numpy'):
    try:
        print(package + ':', metadata.version(package))
    except metadata.PackageNotFoundError:
        print(package + ': not installed in this Python environment')
for label, module in [('Unitree SDK2 Python', 'unitree_sdk2py'),
                       ('RealSense Python', 'pyrealsense2')]:
    try:
        available = find_spec(module) is not None
    except (ImportError, ValueError):
        available = False
    print(label + ':', 'module found (connection not tested)' if available else 'not found in this Python environment')
try:
    print('Network interfaces:', ', '.join(name for _, name in socket.if_nameindex()))
except OSError:
    print('Network interfaces: unavailable')
print("Model:", "present" if (Path(__file__).resolve().parent / 'models/hand_landmarker.task').is_file() else "missing")
print("No camera was opened. No robot connection was attempted.")
