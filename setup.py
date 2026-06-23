#!/usr/bin/env python3
"""local-caption — cross-platform setup (Windows / macOS / Linux).

    python setup.py        (or: python3 setup.py)

Creates ./.venv-whisperx and installs every dependency into it (single venv).
Run all the caption scripts with that venv's python afterwards.
"""
import os
import sys
import shutil
import subprocess
import venv

HERE = os.path.dirname(os.path.abspath(__file__))
VENV = os.path.join(HERE, ".venv-whisperx")


def venv_python():
    if os.name == "nt":
        return os.path.join(VENV, "Scripts", "python.exe")
    return os.path.join(VENV, "bin", "python")


def main():
    print("== local-caption setup ==")

    v = sys.version_info
    print(f"python {v.major}.{v.minor}.{v.micro}  ({sys.platform})")
    if v < (3, 9):
        sys.exit("!! Python 3.9+ required.")
    if v >= (3, 14):
        print("note: very new Python. torch ships wheels for it; if whisperx (or another dep) has")
        print("      no wheel yet, fall back to Python 3.11-3.12 and re-run.")

    if shutil.which("ffmpeg") is None:
        print("!!  ffmpeg not found. Install it, then re-run:")
        print("    macOS: brew install ffmpeg | Ubuntu: sudo apt install ffmpeg | Windows: winget install ffmpeg")
    else:
        print("ok: ffmpeg present")

    py = venv_python()
    if not os.path.exists(py):
        print("-- creating ./.venv-whisperx --")
        venv.EnvBuilder(with_pip=True).create(VENV)
    else:
        print("ok: ./.venv-whisperx already exists")

    subprocess.run([py, "-m", "pip", "install", "--upgrade", "pip"], check=False)
    print("-- installing requirements (heavy: torch + whisperx, a few minutes) --")
    r = subprocess.run([py, "-m", "pip", "install", "-r", os.path.join(HERE, "requirements.txt")])
    if r.returncode != 0:
        print("\n!! dependency install failed.")
        print("   Most often this is torch for your platform. Install the right build from")
        print("   https://pytorch.org/get-started/locally/ into ./.venv-whisperx, then re-run setup.")
        sys.exit(r.returncode)

    # Pre-fetch the Whisper 'small' model so the first caption is instant (clone -> setup -> ready).
    print("-- downloading the Whisper 'small' model (~460 MB, one-time) --")
    if subprocess.run([py, "-c", "import whisper; whisper.load_model('small')"]).returncode == 0:
        print("ok: Whisper model ready")
    else:
        print("   (couldn't pre-fetch the model; it will auto-download on your first caption instead)")

    rel = r".venv-whisperx\Scripts\python" if os.name == "nt" else "./.venv-whisperx/bin/python"
    print("\n== done ==  engine + model + fonts ready.\n")
    print("Caption a video — one command:")
    print(f"  {rel} caption.py your_video.mp4")
    print(f"  {rel} caption.py your_video.mp4 --style hormozi       # pick a famous look")
    print("Styles: clean bold hormozi green beast impact bebas tiktok pill boxed yellow neon gradient minimal subtitle")


if __name__ == "__main__":
    main()
