from __future__ import annotations

import argparse
import os
from pathlib import Path


def _tokenize_cmdline(cmdline: str) -> list[str]:
    if not cmdline:
        return []
    if "\x00" in cmdline:
        return [part for part in cmdline.split("\x00") if part]
    return cmdline.split()


def _option_value(tokens: list[str], option: str) -> str | None:
    for index, token in enumerate(tokens[:-1]):
        if token == option:
            return tokens[index + 1]
    return None


def is_repo_owned_backend_cmdline(cmdline: str, repo_dir: str, port: int = 8080) -> bool:
    tokens = _tokenize_cmdline(cmdline)
    if not tokens:
        return False

    try:
        uvicorn_index = tokens.index("-m")
    except ValueError:
        return False

    if uvicorn_index + 1 >= len(tokens) or tokens[uvicorn_index + 1] != "uvicorn":
        return False
    if "main:app" not in tokens:
        return False
    if _option_value(tokens, "--host") != "0.0.0.0":
        return False
    if _option_value(tokens, "--port") != str(port):
        return False

    env_file = _option_value(tokens, "--env-file")
    if not env_file:
        return False

    expected_env = os.path.realpath(os.path.join(repo_dir, ".env"))
    return os.path.realpath(env_file) == expected_env


def _listener_inodes(port: int) -> set[str]:
    inodes: set[str] = set()
    target_port = f"{port:04X}"
    for proc_file in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            lines = Path(proc_file).read_text().splitlines()
        except OSError:
            continue
        for line in lines[1:]:
            columns = line.split()
            if len(columns) < 10:
                continue
            state = columns[3]
            if state != "0A":
                continue
            local_address = columns[1]
            _, port_hex = local_address.rsplit(":", 1)
            if port_hex.upper() == target_port:
                inodes.add(columns[9])
    return inodes


def find_listener_pids(port: int) -> list[int]:
    inodes = _listener_inodes(port)
    if not inodes:
        return []

    pids: set[int] = set()
    for entry in os.scandir("/proc"):
        if not entry.name.isdigit():
            continue
        fd_dir = os.path.join(entry.path, "fd")
        try:
            for fd_entry in os.scandir(fd_dir):
                try:
                    target = os.readlink(fd_entry.path)
                except OSError:
                    continue
                if not target.startswith("socket:["):
                    continue
                inode = target[8:-1]
                if inode in inodes:
                    pids.add(int(entry.name))
                    break
        except OSError:
            continue
    return sorted(pids)


def read_cmdline(pid: int) -> str:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return ""
    return raw.decode(errors="ignore")


def classify_port_owner(port: int, repo_dir: str) -> tuple[str, list[int]]:
    pids = find_listener_pids(port)
    if not pids:
        return "none", []

    if all(is_repo_owned_backend_cmdline(read_cmdline(pid), repo_dir=repo_dir, port=port) for pid in pids):
        return "repo-owned", pids

    return "other", pids


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    classify_parser = subparsers.add_parser("classify-port")
    classify_parser.add_argument("--port", type=int, required=True)
    classify_parser.add_argument("--repo-dir", required=True)

    args = parser.parse_args()

    if args.command == "classify-port":
        kind, pids = classify_port_owner(port=args.port, repo_dir=args.repo_dir)
        if pids:
            print(kind, *pids)
        else:
            print(kind)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
