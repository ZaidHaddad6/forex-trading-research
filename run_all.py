"""Launch one bot per instrument in parallel subprocesses."""
import subprocess
import sys
import signal
import os


def already_running() -> bool:
    """Return True if any main.py or run_all.py process is already running."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "main.py"],
            capture_output=True,
        )
        # Exclude our own PID
        pids = [int(p) for p in result.stdout.split() if int(p) != os.getpid()]
        return len(pids) > 0
    except Exception:
        return False

BOTS = [
    {"TRADE_EPIC": "EURUSD",  "TRADE_SIZE": "100", "LOG": "logs/bot_EURUSD.log"},
    {"TRADE_EPIC": "GBPUSD",  "TRADE_SIZE": "100", "LOG": "logs/bot_GBPUSD.log"},
    {"TRADE_EPIC": "USDJPY",  "TRADE_SIZE": "100", "LOG": "logs/bot_USDJPY.log"},
]

processes = []


def launch():
    python = sys.executable
    base_env = os.environ.copy()

    import time
    for i, bot in enumerate(BOTS):
        env = base_env.copy()
        env["TRADE_EPIC"] = bot["TRADE_EPIC"]
        env["TRADE_SIZE"] = bot["TRADE_SIZE"]

        log_path = bot["LOG"]
        log_file = open(log_path, "a")

        proc = subprocess.Popen(
            [python, "main.py"],
            env=env,
            stdout=log_file,
            stderr=log_file,
        )
        processes.append((proc, bot["TRADE_EPIC"], log_file))
        print(f"Started {bot['TRADE_EPIC']} bot — PID {proc.pid} → {log_path}")
        if i < len(BOTS) - 1:
            time.sleep(10)  # stagger logins to avoid rate limiting

    print(f"\n{len(processes)} bots running. Press Ctrl-C to stop all.\n")

    def shutdown(sig, frame):
        print("\nStopping all bots…")
        for proc, epic, log_file in processes:
            proc.terminate()
            log_file.close()
            print(f"  Stopped {epic} (PID {proc.pid})")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Wait for all processes
    for proc, epic, _ in processes:
        proc.wait()


if __name__ == "__main__":
    if already_running():
        print("ERROR: Bot processes are already running. Aborting to prevent duplicates.")
        print("Run: pkill -f main.py  to stop them first.")
        sys.exit(1)
    launch()
