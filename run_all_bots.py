import signal
import subprocess
import sys
import time
from pathlib import Path

import database


BOT_FILES = [
    "bot.py",
    "bot_admin.py",
    "bot_dip.py",
    "bot_inv.py",
    "bot_spy.py",
    "bot_war.py",
]


def get_python_executable(root: Path) -> str:
    venv_python = root / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def start_bot(root, python_exe, bot_file):
    bot_path = root / bot_file
    if not bot_path.exists():
        print(f"[SKIP] {bot_file} not found.")
        return None

    print(f"[START] {bot_file}", flush=True)
    return subprocess.Popen(
        [python_exe, str(bot_path)],
        cwd=str(root),
        stdin=subprocess.DEVNULL,
    )


def launch_bots():
    root = Path(__file__).resolve().parent
    python_exe = get_python_executable(root)
    database.init_db()
    processes = {}

    print("Launching all Telegram bots...", flush=True)

    for bot_file in BOT_FILES:
        process = start_bot(root, python_exe, bot_file)
        if process is not None:
            processes[bot_file] = process

    print(f"\nAll bots started. Total running: {len(processes)}", flush=True)
    print("Press Ctrl+C to stop them all.\n", flush=True)

    try:
        while processes:
            for bot_file, process in list(processes.items()):
                exit_code = process.poll()
                if exit_code is None:
                    continue
                print(f"[EXIT] {bot_file} exited with code {exit_code}; restarting.", flush=True)
                processes[bot_file] = start_bot(root, python_exe, bot_file)
            time.sleep(5)
    except KeyboardInterrupt:
        print("\nStopping all bot processes...", flush=True)
        for proc in processes.values():
            if proc.poll() is None:
                proc.terminate()
        for proc in processes.values():
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        print("All bots stopped.", flush=True)


if __name__ == "__main__":
    launch_bots()
