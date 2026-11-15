"""Build a standalone Windows executable (AURA-OS.exe) using PyInstaller."""
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()


def main():
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        "AURA-OS",
        "--add-data",
        "static;static",
        "--hidden-import",
        "uvicorn.logging",
        "--hidden-import",
        "uvicorn.loops.auto",
        "--hidden-import",
        "uvicorn.protocols.http.auto",
        "--hidden-import",
        "pystray._win32",
        "desktop_widget.py",
    ]
    print("Executando:", " ".join(cmd))
    subprocess.check_call(cmd, cwd=str(BASE_DIR))
    print("\nBuild concluido em:", BASE_DIR / "dist" / "AURA-OS")


if __name__ == "__main__":
    main()
