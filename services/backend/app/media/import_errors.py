"""Turn private downloader diagnostics into stable, actionable public errors."""
import errno
import re

from .process import MediaError


MESSAGES = {
    "import_tool_missing": "Komponen pengolah video di server belum tersedia. Hubungi pengelola aplikasi untuk memperbaiki instalasi, lalu pilih Coba lagi.",
    "import_merge_failed": "Video dan audio gagal digabungkan. Coba lagi; jika tetap gagal, hubungi pengelola aplikasi untuk memeriksa pengolah video di server.",
    "import_conversion_failed": "Video yang diunduh gagal disiapkan menjadi MP4. Coba URL lain atau unggah file MP4.",
    "source_login_required": "Sumber meminta login atau membatasi video untuk akun tertentu. Impor dengan login belum didukung. Gunakan video publik atau unggah file MP4 yang Anda miliki.",
    "source_verification_required": "Situs sumber meminta verifikasi tambahan sebelum video dapat diunduh. Coba lagi nanti atau unggah file MP4 yang Anda miliki.",
    "source_access_denied": "Situs sumber menolak akses unduhan. Pastikan video dapat diakses publik; jika tetap gagal, gunakan URL lain atau unggah file MP4.",
    "source_unavailable": "Video tidak ditemukan atau sudah tidak tersedia di situs sumber. Periksa URL atau gunakan video lain.",
    "source_rate_limited": "Situs sumber membatasi permintaan sementara. Tunggu beberapa menit, lalu pilih Coba lagi.",
    "source_network_error": "Koneksi ke situs sumber terputus atau kehabisan waktu. Periksa koneksi internet server, lalu pilih Coba lagi.",
    "source_address_blocked": "URL atau pengalihannya menuju alamat jaringan yang tidak diizinkan. Gunakan URL video publik.",
    "source_format_unavailable": "Sumber tidak menyediakan format video yang dapat diimpor. Coba URL lain atau unggah file MP4.",
    "source_url_unsupported": "Situs atau jenis URL ini belum didukung untuk impor. Gunakan URL video dari situs lain atau unggah file MP4.",
    "import_incomplete": "Unduhan belum menghasilkan file video yang lengkap. Pilih Coba lagi; jika berulang, gunakan URL lain atau unggah file MP4.",
    "import_worker_failed": "Proses impor di server berhenti sebelum selesai. Pilih Coba lagi; jika berulang, hubungi pengelola aplikasi untuk memeriksa layanan pemrosesan.",
    "import_timeout": "Impor melewati batas waktu pemrosesan. Periksa koneksi internet server, lalu coba lagi atau unggah file MP4.",
    "insufficient_disk": "Ruang penyimpanan server tidak cukup. Kosongkan ruang penyimpanan, lalu pilih Coba lagi.",
    "url_download_failed": "Impor video belum berhasil. Pilih Coba lagi; jika tetap gagal, gunakan URL lain atau unggah file MP4.",
}


def import_error(code):
    return MediaError(code, MESSAGES[code])


def public_import_error(exc, *, phase="download"):
    # Only application-owned messages may cross the child process boundary.
    if isinstance(exc, MediaError):
        if exc.code in ("duration_limit", "file_too_large", "invalid_source_type", "invalid_url"):
            return exc
        if exc.code in MESSAGES:
            return import_error(exc.code)
        if exc.code == "process_timeout":
            return import_error("import_timeout")
    if isinstance(exc, OSError) and exc.errno == errno.ENOSPC:
        return import_error("insufficient_disk")
    # Inspect provider text for known causes, but never return it. Strip URLs
    # first so query tokens cannot accidentally determine the error category.
    text = re.sub(r"https?://\S+", "", str(exc)).lower().replace("’", "'")
    if "ffmpeg" in text and any(s in text for s in ("not installed", "not found", "does not exist")):
        return import_error("import_tool_missing")
    if "no space left on device" in text:
        return import_error("insufficient_disk")
    if phase == "merge":
        return import_error("import_merge_failed")
    if phase == "convert":
        return import_error("import_conversion_failed")
    if any(s in text for s in ("confirm you're not a bot", "captcha", "javascript challenge", "challenge solving failed")):
        return import_error("source_verification_required")
    if any(s in text for s in ("private video", "login required", "sign in", "members-only", "age-restricted")):
        return import_error("source_login_required")
    if re.search(r"http (?:error )?429\b", text) or "too many requests" in text:
        return import_error("source_rate_limited")
    if any(s in text for s in ("requested format is not available", "no video formats", "only images are available")):
        return import_error("source_format_unavailable")
    if "unsupported url" in text or "no suitable extractor" in text:
        return import_error("source_url_unsupported")
    if re.search(r"http (?:error )?(?:404|410)\b", text) or any(s in text for s in ("video unavailable", "video has been removed", "video is unavailable")):
        return import_error("source_unavailable")
    if re.search(r"http (?:error )?(?:401|403)\b", text) or "not available in your country" in text:
        return import_error("source_access_denied")
    if isinstance(exc, PermissionError):
        return import_error("source_address_blocked")
    if isinstance(exc, (TimeoutError, ConnectionError)) or any(s in text for s in (
            "timed out", "connection reset", "connection refused", "temporary failure in name resolution",
            "name or service not known", "network is unreachable", "remote end closed connection")):
        return import_error("source_network_error")
    return import_error("url_download_failed")
