"""
Build script for Telegram AI Summary Bot — Setup Wizard.

Creates a single-file executable using PyInstaller.

Usage:
    python build.py
    uv run python build.py
"""

import subprocess
import sys
import shutil
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
DIST_DIR = ROOT_DIR / "dist"
BUILD_DIR = ROOT_DIR / "build"


def clean() -> None:
    for d in (DIST_DIR, BUILD_DIR):
        if d.exists():
            shutil.rmtree(d)
    for spec in ROOT_DIR.glob("*.spec"):
        spec.unlink(missing_ok=True)


def build() -> None:
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", "Telegram-AI-Summary-Setup",
        "--clean",
        "--noconfirm",
        "--add-data", f"{ROOT_DIR / '.env.example'};.",
        "--add-data", f"{ROOT_DIR / 'bot.py'};.",
        "--hidden-import", "telethon",
        "--hidden-import", "google.genai",
        "--hidden-import", "numpy",
        "--hidden-import", "questionary",
        "--hidden-import", "rich",
        "--hidden-import", "dotenv",
        str(ROOT_DIR / "setup_wizard.py"),
    ]

    print("[*] Building...")
    result = subprocess.run(cmd, cwd=str(ROOT_DIR))
    if result.returncode != 0:
        print("[!] Build failed.")
        sys.exit(1)

    exe_name = "Telegram-AI-Summary-Setup.exe" if sys.platform == "win32" else "Telegram-AI-Summary-Setup"
    exe_path = DIST_DIR / exe_name
    if exe_path.exists():
        print(f"[+] Built: {exe_path}")
    else:
        print(f"[!] Expected output not found: {exe_path}")


def main() -> None:
    clean()
    build()


if __name__ == "__main__":
    main()
