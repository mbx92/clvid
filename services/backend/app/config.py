from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    app_origin: str = "http://localhost:8080"
    database_url: str = "postgresql+psycopg://clipper:CHANGE_ME@postgres:5432/clipper"
    redis_url: str = "redis://redis:6379/0"
    media_root: Path = Path("/data/media")
    max_upload_bytes: int = 2_147_483_648
    max_video_seconds: int = 3600
    max_video_width: int = 3840
    max_video_height: int = 2160
    min_free_disk_bytes: int = 1_073_741_824
    max_active_jobs_per_user: int = 6
    session_hours: int = 168
    cookie_secure: bool = False
    login_max_attempts: int = 8
    login_window_seconds: int = 900
    whisper_model: str = "small"
    whisper_device: str = "auto"
    whisper_compute_type: str = "auto"
    whisper_cpu_threads: int = Field(default=4, ge=1, le=64)
    whisper_batch_size: int = Field(default=8, ge=1, le=32)
    whisper_beam_size: int = Field(default=5, ge=1, le=10)
    whisper_download_root: str = "/data/whisper"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"
    deepseek_timeout_seconds: int = 90
    deepseek_max_retries: int = 2
    deepseek_chunk_tokens: int = 6000
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    subtitle_font_path: str = "/app/fonts/NotoSans-Regular.ttf"
    import_max_height: int = Field(default=1080, ge=240, le=2160)
    preview_max_width: int = Field(default=1280, ge=320, le=3840)
    preview_threads: int = Field(default=4, ge=1, le=64)
    tracking_model_path: str = "/app/models/face_detection_yunet_2023mar.onnx"
    speaker_model_path: str = "/app/models/light_asd_talkset.onnx"
    job_timeout_seconds: int = 14400
    media_timeout_seconds: int = 14400
    job_lease_seconds: int = 90
    heartbeat_seconds: int = 15
    job_max_attempts: int = 3
    dispatch_interval_seconds: int = 2
    reconcile_interval_seconds: int = 15
    partial_upload_ttl_seconds: int = 86400
    scratch_ttl_seconds: int = 86400
    pipeline_version: str = "1"
    default_language: str = "auto"
    social_encryption_key: str = ""
    social_public_base_url: str = ""
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    meta_client_id: str = ""
    meta_client_secret: str = ""
    meta_graph_version: str = ""
    tiktok_client_key: str = ""
    tiktok_client_secret: str = ""
    tiktok_direct_post_enabled: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
