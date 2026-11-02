from __future__ import annotations

from dataclasses import dataclass
import os
import signal
import subprocess
import threading
import time


class MediaError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


class Cancelled(MediaError):
    def __init__(self):
        super().__init__("cancelled", "Pekerjaan dibatalkan.")


@dataclass
class ProcessResult:
    stdout: str
    stderr: str
    returncode: int


class ProgressParser:
    def __init__(self, duration_ms):
        self.duration = duration_ms
        self.buffer = ""
        self.value = None

    def feed(self, text, final=False):
        self.buffer += text
        lines = self.buffer.split("\n")
        self.buffer = "" if final else lines.pop()
        for line in lines:
            key, _, value = line.strip().partition("=")
            if key == "progress_reset":
                self.value = 0.0 if self.duration else None
            if not self.duration:
                continue
            try:
                if key == "segment_end_ms":
                    amount = float(value) / self.duration
                elif key in ("out_time_ms", "out_time_us"):
                    amount = float(value) / 1000 / self.duration
                else:
                    continue
                self.value = max(self.value or 0, min(.99, amount))
            except ValueError:
                pass
        return self.value


def run_process(args, *, timeout=14400, cancelled=None, progress=None, duration_ms=None, env=None, cwd=None):
    if cancelled and cancelled():
        raise Cancelled()
    parser = ProgressParser(duration_ms)
    buffers = {"stdout": "", "stderr": ""}
    lock = threading.Lock()
    def reader(pipe, name):
        try:
            while data := os.read(pipe.fileno(), 8192):
                text = data.decode("utf-8", errors="replace")
                with lock:
                    buffers[name] = (buffers[name] + text)[-2_000_000:]
                    if name == "stdout":
                        parser.feed(text)
        finally:
            pipe.close()
    proc = subprocess.Popen([str(a) for a in args], stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, cwd=cwd,
                            start_new_session=os.name != "nt")
    threads = [threading.Thread(target=reader, args=(getattr(proc, n), n), daemon=True) for n in buffers]
    for thread in threads:
        thread.start()
    started, previous = time.monotonic(), object()
    try:
        while True:
            if cancelled and cancelled():
                raise Cancelled()
            if time.monotonic() - started > timeout:
                raise MediaError("process_timeout", "Pemrosesan media melewati batas waktu.")
            with lock:
                current = parser.value
            if progress and current != previous:
                progress(current)
                previous = current
            if proc.poll() is not None and not any(thread.is_alive() for thread in threads):
                break
            time.sleep(.05)
        for thread in threads:
            thread.join()
        final = parser.feed("", final=True)
        if progress and final != previous:
            progress(final)
        return ProcessResult(buffers["stdout"], buffers["stderr"], proc.returncode)
    finally:
        if proc.poll() is None or any(thread.is_alive() for thread in threads):
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
            else:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            proc.wait()
        for thread in threads:
            thread.join(timeout=2)


def ffmpeg(args, *, binary="ffmpeg", **kwargs):
    result = run_process([binary, "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
                          "-progress", "pipe:1", *args], **kwargs)
    if result.returncode:
        raise MediaError("media_decode_failed", "FFmpeg gagal memproses video. " + result.stderr[-1600:])
    return result
