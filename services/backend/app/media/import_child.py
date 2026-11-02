"""Download with Python networking guards; external tools may only read local files."""
import json
from pathlib import Path
import shutil
import sys

from .process import MediaError
from .remote_guard import install_network_guard, validate_url
from .import_formats import shortlist_formats
from .import_errors import import_error, public_import_error


def enforce_import_limits(info, config):
    if info.get("_type") in ("playlist", "multi_video") or info.get("is_live"):
        raise MediaError("invalid_source_type", "Gunakan satu video yang sudah selesai, bukan playlist atau siaran langsung.")
    duration = info.get("duration")
    if isinstance(duration, (int, float)) and duration > config["max_seconds"]:
        raise MediaError("duration_limit", f"Durasi video {duration/60:.1f} menit melebihi batas {config['max_seconds']/60:g} menit. Naikkan batas durasi di Pengaturan lalu coba lagi.")
    sizes = [stream.get("filesize") for stream in info.get("requested_formats", [])] or [info.get("filesize")]
    if all(type(size) in (int, float) and size > 0 for size in sizes) and sum(sizes) > config["max_bytes"]:
        raise MediaError("file_too_large", f"Ukuran video melebihi batas {config['max_bytes']/1024**3:g} GiB. Naikkan batas ukuran di Pengaturan lalu coba lagi.")


def local_postprocessor_args():
    # yt-dlp scopes input options by postprocessor AND executable. A bare
    # 'ffmpeg_i' key is ignored by Merger/Fixup and loses the local-only guard.
    from yt_dlp.postprocessor import ffmpeg as postprocessors
    base = postprocessors.FFmpegPostProcessor
    return {f"{cls.pp_key().lower()}+ffmpeg_i": ["-protocol_whitelist", "file,pipe"]
            for cls in vars(postprocessors).values()
            if isinstance(cls, type) and issubclass(cls, base)}


def install_process_guard(directory):
    directory = Path(directory).resolve()
    def audit(event, args):
        if event in ("os.system", "os.posix_spawn", "os.posix_spawnp"):
            raise PermissionError("External command blocked")
        if event != "subprocess.Popen":
            return
        executable, argv = args[:2]
        if Path(executable).name not in ("ffmpeg", "ffprobe", "ffmpeg.exe", "ffprobe.exe") or isinstance(argv, str):
            raise PermissionError("External downloader blocked")
        if any("://" in str(value) or str(value).startswith(("concat:", "subfile:", "crypto:", "data:", "pipe:", "tcp:", "udp:")) for value in argv):
            raise PermissionError("External networking blocked")
        for index, value in enumerate(argv):
            if value == "-i":
                path = Path(argv[index+1].removeprefix("file:")).resolve()
                if not path.is_relative_to(directory) or not path.is_file():
                    raise PermissionError("Input outside download directory")
                # A protocol whitelist prevents downloaded playlists from
                # making FFmpeg perform a second unguarded network request.
                if "-protocol_whitelist" not in argv or argv[argv.index("-protocol_whitelist")+1] != "file,pipe":
                    raise PermissionError("Local protocol whitelist required")
    sys.addaudithook(audit)


def main(request):
    from yt_dlp import YoutubeDL
    from .render import check_disk
    config = json.loads(Path(request).read_text(encoding="utf-8"))
    directory = Path(config["directory"])
    output = Path(config["output"])
    install_network_guard()
    install_process_guard(directory)
    limit_failure = None
    phase = "download"
    class Quiet:
        def debug(self, message):
            nonlocal limit_failure
            # yt-dlp may skip an oversized file without raising an exception.
            # Retain a fixed safe error, never the provider's raw diagnostics.
            if "larger than max-filesize" in message:
                limit_failure = MediaError("file_too_large", "Ukuran unduhan melebihi batas. Naikkan batas ukuran di Pengaturan lalu coba lagi.")
        def info(self, *_): pass
        def warning(self, *_): pass
        def error(self, *_): pass
    def hook(info):
        nonlocal limit_failure
        downloaded = info.get("downloaded_bytes", 0)
        if max(downloaded, info.get("total_bytes") or 0) > config["max_bytes"]:
            limit_failure = MediaError("file_too_large", "Ukuran unduhan melebihi batas. Naikkan batas ukuran di Pengaturan lalu coba lagi.")
            raise limit_failure
        check_disk(directory, 0, config["min_free"])
        total = info.get("total_bytes") or info.get("total_bytes_estimate")
        if total:
            print(f"segment_end_ms={min(990, int(downloaded/total*1000))}", flush=True)
    def selector(ctx):
        formats = shortlist_formats(ctx["formats"], max_width=config["max_width"], max_height=config["max_height"], target_height=config["target_height"])
        yield from downloader.build_format_selector("bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b")({**ctx, "formats": formats})
    def postprocess(info):
        nonlocal phase
        if info.get("status") == "started":
            phase = "merge" if info.get("postprocessor", "").lower() == "merger" else "convert"
        elif info.get("status") == "finished":
            phase = "download"
    try:
        check_disk(directory, 0, config["min_free"])
        ffmpeg_path = shutil.which(config["ffmpeg"])
        if not ffmpeg_path:
            raise import_error("import_tool_missing")
        with YoutubeDL(dict(quiet=True, no_warnings=True, logger=Quiet(), noplaylist=True,
                            proxy="", enable_file_urls=False, cachedir=False, js_runtimes={},
                            outtmpl=str(directory/"source.%(ext)s"), format=selector, merge_output_format="mp4",
                            ffmpeg_location=ffmpeg_path,
                            max_filesize=config["max_bytes"], socket_timeout=30,
                            retries=2, fragment_retries=2, progress_hooks=[hook], postprocessor_hooks=[postprocess],
                            postprocessor_args=local_postprocessor_args())) as downloader:
            info = downloader.extract_info(validate_url(config["url"]), download=False)
            enforce_import_limits(info, config)
            downloader.process_info(info)
            if limit_failure:
                raise limit_failure
            candidates = [p for p in directory.glob("source.*") if p.suffix in (".mp4", ".mkv", ".webm")]
            if len(candidates) != 1:
                raise import_error("import_incomplete")
            path = candidates[0]
            enforce_import_limits({"filesize": path.stat().st_size}, config)
            if path.suffix != ".mp4":
                phase = "convert"
                from .process import ffmpeg
                converted = directory/"import.mp4"
                ffmpeg(["-protocol_whitelist", "file,pipe", "-i", str(path), "-c", "copy", str(converted)], binary=config["ffmpeg"])
                path = converted
            output.write_text(json.dumps(dict(path=str(path), title=(info.get("title") or "Video URL")[:200])), encoding="utf-8")
    except Exception as exc:
        # Signed URLs, cookies and provider diagnostics must not reach job logs.
        failure = public_import_error(limit_failure or exc, phase=phase)
        error = {"code": failure.code, "message": failure.message}
        output.write_text(json.dumps({"error": error}), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1])
