"""Linux parent-death guard, run in a fresh interpreter before exec.

Do not use Popen(preexec_fn=...) in the threaded Celery worker. Setting prctl
inside this tiny child is safe and survives exec of FFmpeg or Whisper's Python.
"""
import ctypes
import os
import signal
import sys


def main():
    expected_parent = int(sys.argv[1])
    command = sys.argv[2:]
    if sys.platform == "linux":
        libc = ctypes.CDLL(None, use_errno=True)
        # PR_SET_PDEATHSIG: the kernel kills this process if its worker dies.
        if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), "Could not install parent-death guard")
        # Close the race where the worker died before prctl was installed.
        if os.getppid() != expected_parent:
            os._exit(1)
    os.execvp(command[0], command)


if __name__ == "__main__":
    main()
