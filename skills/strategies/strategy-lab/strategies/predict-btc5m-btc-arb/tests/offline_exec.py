"""Run the replay CLI with no socket available (SPEC-07-001 M2 §15.2).

This is a test launcher, not part of the research path. It installs a seccomp
filter on the child process that refuses the socket calls, checks that the
filter works by running a control process that tries to create a socket, and
then runs the real CLI with a cleared environment, an empty working directory
and closed file descriptors.

The filter is installed with ``prctl(PR_SET_NO_NEW_PRIVS)`` and
``PR_SET_SECCOMP`` with a BPF program, through the existing libc. Nothing is
installed and the host's network configuration is not touched: only the child
process is restricted.
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import errno
import json
import os
import platform
import resource
import socket
import stat
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

# The Linux x86-64 syscall numbers the filter refuses.
SYS_SOCKET = 41
SYS_SOCKETPAIR = 53
SYS_CONNECT = 42
SYS_SENDTO = 44
SYS_SENDMSG = 46
SYS_SENDMMSG = 307

PR_SET_NO_NEW_PRIVS = 38
PR_SET_SECCOMP = 22
SECCOMP_MODE_FILTER = 2

BPF_LD = 0x00
BPF_W = 0x00
BPF_ABS = 0x20
BPF_JMP = 0x05
BPF_JEQ = 0x10
BPF_JGE = 0x30
BPF_K = 0x00
BPF_RET = 0x06
BPF_ALU = 0x04
BPF_AND = 0x50

AUDIT_ARCH_X86_64 = 0xC000003E
SECCOMP_RET_ALLOW = 0x7FFF0000
SECCOMP_RET_ERRNO = 0x00050000
SECCOMP_RET_KILL_PROCESS = 0x80000000


class FilterError(RuntimeError):
    """The filter could not be installed, so the check cannot be trusted."""


def _libc():
    path = ctypes.util.find_library("c")
    if not path:
        raise FilterError("libc was not found")
    library = ctypes.CDLL(path, use_errno=True)
    return library


def _sock_filter() -> bytes:
    """The BPF program: refuse the socket calls, allow everything else.

    Each statement is ``(code, jt, jf, k)``, the layout the kernel reads.
    """
    statements: list[tuple[int, int, int, int]] = [
        # Load the architecture; refuse anything but x86-64.
        (BPF_LD | BPF_W | BPF_ABS, 0, 0, 4),
        (BPF_JMP | BPF_JEQ | BPF_K, 1, 0, AUDIT_ARCH_X86_64),
        (BPF_RET | BPF_K, 0, 0, SECCOMP_RET_KILL_PROCESS),
        # Load the syscall number.
        (BPF_LD | BPF_W | BPF_ABS, 0, 0, 0),
    ]
    # Refuse each socket-related syscall with EPERM: if the number matches,
    # return EPERM; otherwise skip over the return and test the next one.
    for number in (SYS_SOCKET, SYS_SOCKETPAIR, SYS_CONNECT,
                   SYS_SENDTO, SYS_SENDMSG, SYS_SENDMMSG):
        statements.append((BPF_JMP | BPF_JEQ | BPF_K, 0, 1, number))
        statements.append((BPF_RET | BPF_K, 0, 0, SECCOMP_RET_ERRNO | errno.EPERM))
    # Allow everything else.
    statements.append((BPF_RET | BPF_K, 0, 0, SECCOMP_RET_ALLOW))
    packed = b"".join(struct.pack("HBBI", *statement) for statement in statements)
    return packed


def install_filter() -> None:
    """Install the filter on this process."""
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise FilterError("the filter is only supported on Linux x86-64")
    libc = _libc()
    libc.prctl.restype = ctypes.c_int
    libc.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
                           ctypes.c_ulong, ctypes.c_ulong]
    if libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        code = ctypes.get_errno()
        raise FilterError(f"PR_SET_NO_NEW_PRIVS failed: {os.strerror(code)}")
    program = _sock_filter()
    buffer = ctypes.create_string_buffer(program, len(program))
    # The sock_fprog structure carries the instruction count and the pointer
    # to the instructions.
    class SockFprog(ctypes.Structure):
        _fields_ = [("len", ctypes.c_ushort),
                    ("filter", ctypes.POINTER(ctypes.c_ubyte))]

    instructions = (ctypes.c_ubyte * len(program)).from_buffer_copy(program)
    fprog = SockFprog(len(program) // 8, instructions)
    address = ctypes.addressof(fprog)
    if libc.prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, address, 0, 0) != 0:
        code = ctypes.get_errno()
        raise FilterError(f"PR_SET_SECCOMP failed: {os.strerror(code)}")


def clean_descriptors(preserve: tuple[int, ...] = ()) -> list[int]:
    """Close every inherited non-standard descriptor and reject socket stdio."""
    for descriptor in range(3):
        try:
            if stat.S_ISSOCK(os.fstat(descriptor).st_mode):
                raise FilterError("socket standard descriptor")
        except OSError:
            pass
    maximum = resource.getrlimit(resource.RLIMIT_NOFILE)[1]
    if maximum == resource.RLIM_INFINITY:
        maximum = os.sysconf("SC_OPEN_MAX")
    lower = 3
    for descriptor in sorted(preserve) + [maximum]:
        os.closerange(lower, descriptor)
        lower = descriptor + 1
    remaining = []
    for entry in Path("/proc/self/fd").iterdir():
        descriptor = int(entry.name)
        if descriptor >= 3 and descriptor not in preserve:
            try:
                os.fstat(descriptor)
            except OSError:
                continue
            remaining.append(descriptor)
    if remaining:
        raise FilterError(f"inherited descriptors remain: {remaining}")
    return remaining


class FilteredRunner:
    """Runs a child with the filter installed, using fork and exec."""

    @staticmethod
    def run(command: list[str], cwd: str, environment: dict) -> subprocess.CompletedProcess:
        read_fd, write_fd = os.pipe()
        pid = os.fork()
        if pid == 0:  # the child
            os.close(read_fd)
            try:
                install_filter()
            except FilterError as exc:
                os.write(write_fd, f"filter.failed: {exc}\n".encode())
                os._exit(70)
            os.close(write_fd)
            try:
                clean_descriptors()
                os.chdir(cwd)
                os.environ.clear()
                os.environ.update(environment)
                print(json.dumps({"inherited_fds": [], "environment": dict(os.environ),
                                  "cwd_empty": not any(Path.cwd().iterdir())}), flush=True)
                os.execve(command[0], command, environment)
            except (OSError, FilterError) as exc:
                print(f"exec.failed: {exc}", file=sys.stderr, flush=True)
                os._exit(70)
        os.close(write_fd)
        message = os.read(read_fd, 4096).decode(errors="replace")
        os.close(read_fd)
        _, status = os.waitpid(pid, 0)
        completed = subprocess.CompletedProcess(
            command, os.waitstatus_to_exitcode(status), stdout="", stderr=message)
        return completed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="offline_exec.py",
        description="Run the replay CLI with no socket available.")
    parser.add_argument("--rust-bin", required=True)
    parser.add_argument("--mode", required=True, choices=("replay", "proxy"))
    parser.add_argument("--config", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--from-ms", required=True, type=int)
    parser.add_argument("--to-ms", required=True, type=int)
    parser.add_argument("--extra", action="append", default=[],
                        help="An extra option to pass to the CLI, for a negative check.")
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[6]
    relative = "skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/tests/offline_exec.py"
    if (root != Path("/home/pascal/workspace/yquant-investment")
            or not (root / "AGENTS.md").is_file()
            or (root / relative).resolve() != Path(__file__).resolve()):
        print("workspace.invalid", file=sys.stderr)
        return 64
    binary = (root / args.rust_bin).resolve() if not Path(args.rust_bin).is_absolute() \
        else Path(args.rust_bin)
    config = (root / args.config).resolve() if not Path(args.config).is_absolute() \
        else Path(args.config)
    input_path = (root / args.input).resolve() if not Path(args.input).is_absolute() \
        else Path(args.input)
    output = (root / args.output).resolve() if not Path(args.output).is_absolute() \
        else Path(args.output)
    summary = (root / args.summary).resolve() if not Path(args.summary).is_absolute() \
        else Path(args.summary)

    if not binary.is_file():
        print(f"rustBin.missing: {binary}", file=sys.stderr)
        return 64

    # The control: the filter must refuse a socket in a child process.
    if not control_in_child_fails():
        print("filter.controlFailed", file=sys.stderr)
        return 70
    print(json.dumps({"socket_control_errno": errno.EPERM}), flush=True)

    environment = {
        "LANG": "C.UTF-8",
        "TZ": "UTC",
    }
    with tempfile.TemporaryDirectory(prefix="btc-arb-offline-") as workdir:
        command = [
            str(binary),
            "--mode", args.mode,
            "--config", str(config),
            "--input", str(input_path),
            "--output", str(output),
            "--summary", str(summary),
            "--from-ms", str(args.from_ms),
            "--to-ms", str(args.to_ms),
        ]
        command.extend(args.extra)
        completed = FilteredRunner.run(command, workdir, environment)

    if completed.stderr:
        print(completed.stderr.strip(), file=sys.stderr)
    print(json.dumps({"exit_code": completed.returncode}, ensure_ascii=False))
    return completed.returncode


def control_in_child_fails() -> bool:
    """Whether the filter stops a socket in a child process."""
    read_fd, write_fd = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(read_fd)
        try:
            install_filter()
        except FilterError:
            os.write(write_fd, b"filter.failed\n")
            os._exit(70)
        try:
            clean_descriptors((write_fd,))
            os.environ.clear()
            os.environ.update({"LANG": "C.UTF-8", "TZ": "UTC"})
            socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        except OSError as exc:
            os.write(write_fd, f"errno:{exc.errno}\n".encode())
            os._exit(0)
        os.write(write_fd, b"created\n")
        os._exit(1)
    os.close(write_fd)
    message = os.read(read_fd, 4096).decode(errors="replace")
    os.close(read_fd)
    _, status = os.waitpid(pid, 0)
    code = os.waitstatus_to_exitcode(status)
    if code != 0:
        print(message.strip(), file=sys.stderr)
        return False
    return message.strip() == f"errno:{errno.EPERM}"


if __name__ == "__main__":
    sys.exit(main())
