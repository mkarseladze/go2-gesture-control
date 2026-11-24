"""Copy the starter into Documents and prepare an isolated Python environment.

Run as the ordinary Ubuntu user (optionally with the vboxsf group).
Does not open a camera, connect to a robot, or install system packages.
"""
from __future__ import annotations

import argparse
import hashlib
from importlib.util import find_spec
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

FILES = ('app.py', 'gestures.py', 'doctor.py', 'test_gate.py', 'test_thumb.py',
         'motion_plan.py', 'test_motion.py',
         'requirements.txt', 'README.txt', 'VALIDATION.txt', 'prepare_ubuntu.py',
         'models/hand_landmarker.task')
MARKER = '.go2-starter-files.json'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def preflight(source):
    if platform.system() != 'Linux':
        raise RuntimeError('Run this preparation script inside Ubuntu.')
    if os.geteuid() == 0:
        raise RuntimeError('Do not run as root. Use the Ubuntu account that owns the project.')
    if sys.version_info < (3, 10):
        raise RuntimeError('Python 3.10 or newer is required for this starter.')
    if find_spec('ensurepip') is None:
        raise RuntimeError('Missing venv support. Run: sudo apt install python3-venv\nThen rerun this script.')
    missing = [name for name in FILES if not (source / name).is_file()]
    if missing:
        raise RuntimeError('Starter files missing: ' + ', '.join(missing))


def copy_project(source, target):
    if source.resolve() == target.resolve():
        return
    marker = target / MARKER
    if target.exists() and not marker.is_file() and any(target.iterdir()):
        raise RuntimeError(f'Target already contains unrelated files: {target}\nUse --destination with a new project folder.')
    previous = json.loads(marker.read_text(encoding='utf-8')) if marker.is_file() else {}
    # Check all conflicts before changing files. Preserve any local edits.
    for name in FILES:
        dest = target / name
        if dest.is_symlink():
            raise RuntimeError(f'Refusing to overwrite a symbolic link: {dest}')
        if dest.exists():
            current = digest(dest.read_bytes())
            incoming = digest((source / name).read_bytes())
            if current != incoming and current != previous.get(name):
                raise RuntimeError(f'Local file has changes; preserved: {dest}')
    target.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name in FILES:
        data = (source / name).read_bytes()
        dest = target / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Do not inherit the read-only permissions of the VirtualBox share.
        if not dest.exists() or digest(dest.read_bytes()) != digest(data):
            dest.write_bytes(data)
        hashes[name] = digest(data)
    marker.write_text(json.dumps(hashes, indent=2) + '\n', encoding='utf-8')


def run(command, target):
    subprocess.run([str(item) for item in command], cwd=target, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path,
                        default=Path.home() / 'Documents' / 'Go2Gesture')
    parser.add_argument('--check-only', action='store_true', help='Preflight only; do not copy or install')
    parser.add_argument('--copy-only', action='store_true', help='Update project files only; keep the existing Python environment')
    args = parser.parse_args()
    source = Path(__file__).resolve().parent
    target = args.destination.expanduser().resolve()
    try:
        preflight(source)
        print(f'Ubuntu preparation | Python {platform.python_version()} | {platform.machine()}', flush=True)
        print(f'Project folder: {target}', flush=True)
        if args.check_only:
            print('PREFLIGHT_OK: no files changed, no packages installed.')
            return 0
        print('[1/5] Copy project into the Ubuntu account...', flush=True)
        copy_project(source, target)
        if args.copy_only:
            print('GO2_UPDATE_OK: project files updated; no packages installed.')
            return 0
        print('[2/5] Create or reuse the isolated Python environment...', flush=True)
        venv = target / '.venv'
        config = venv / 'pyvenv.cfg'
        if venv.exists() and not config.is_file():
            raise RuntimeError(f'Existing .venv is incomplete or unrelated: {venv}\nNo files were removed.')
        if not config.is_file():
            run([sys.executable, '-m', 'venv', venv], target)
        python = venv / 'bin' / 'python'
        print('[3/5] Install project dependencies (internet required)...', flush=True)
        run([python, '-m', 'pip', 'install', '--disable-pip-version-check', '-r', 'requirements.txt'], target)
        print('[4/5] Run command and gesture regression tests...', flush=True)
        run([python, '-m', 'unittest', '-v'], target)
        print('[5/5] Load the hand model and process a blank image...', flush=True)
        run([python, 'app.py', '--self-check'], target)
        run([python, 'doctor.py'], target)
        print('\nGO2_SETUP_OK', flush=True)
        print(f'Project: {target}', flush=True)
        print('No camera opened. No robot connection attempted.', flush=True)
        return 0
    except (RuntimeError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f'\nPREPARATION_STOPPED: {exc}', file=sys.stderr, flush=True)
        print('Send the last part of this output to the chat. Do not reinstall the system.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
