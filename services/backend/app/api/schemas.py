from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator
from app.domain.limits import MAX_CLIP_MS, MAX_SOURCE_SECONDS, MAX_SOURCE_BYTES


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LoginInput(StrictModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class ProjectInput(StrictModel):
    name: str = Field(min_length=1, max_length=200)


class ProcessingSettingsInput(StrictModel):
    max_video_seconds: int = Field(ge=60, le=MAX_SOURCE_SECONDS, strict=True)
    max_upload_bytes: int = Field(ge=1024**2, le=MAX_SOURCE_BYTES, strict=True)
    max_clip_ms: int = Field(ge=5000, le=MAX_CLIP_MS, strict=True)

    @model_validator(mode="after")
    def clip_within_source(self):
        if self.max_clip_ms > self.max_video_seconds * 1000:
            raise ValueError("Batas klip tidak boleh lebih panjang dari batas video sumber.")
        return self


class SourceUrlInput(StrictModel):
    url: str = Field(min_length=8, max_length=4096)


class ProcessInput(StrictModel):
    language: Literal["auto", "id", "en"] = "auto"
    content_profile: Literal["general", "gaming"] = "general"
    visual_analysis: bool = False
    count: int = Field(default=5, ge=1, le=20)
    min_duration_ms: int = Field(default=30000, ge=5000, le=MAX_CLIP_MS)
    max_duration_ms: int = Field(default=60000, ge=5000, le=MAX_CLIP_MS)
    analyze: bool = True
    transcribe_again: bool = False

    @model_validator(mode="after")
    def duration_order(self):
        if self.visual_analysis and (self.content_profile != "gaming" or not self.analyze):
            raise ValueError("Analisis frame hanya tersedia saat mencari kandidat Game / gameplay.")
        if self.min_duration_ms > self.max_duration_ms:
            raise ValueError("Durasi minimum harus lebih kecil dari maksimum.")
        return self


class SourceRegion(StrictModel):
    x: float = Field(ge=0, le=1, allow_inf_nan=False)
    y: float = Field(ge=0, le=1, allow_inf_nan=False)
    width: float = Field(ge=0.02, le=1, allow_inf_nan=False)
    height: float = Field(ge=0.02, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def inside_source(self):
        # Account for floating-point addition at the normalized right/bottom
        # edge. Pixel rounding is shared by the browser and media renderer.
        if self.x + self.width > 1 + 1e-9 or self.y + self.height > 1 + 1e-9:
            raise ValueError("Area harus berada di dalam frame sumber.")
        return self


class GamingLayout(StrictModel):
    facecam: SourceRegion
    gameplay: SourceRegion
    facecam_height: float = Field(default=0.28, ge=0.15, le=0.45, allow_inf_nan=False)
    facecam_fit: Literal["fill", "fit"] = "fill"
    gameplay_fit: Literal["fill", "fit"] = "fit"


class Crop(StrictModel):
    mode: Literal["fill", "fit", "gaming"] = "fill"
    tracking: Literal["static", "face", "speaker"] = "static"
    x: float = Field(default=0.5, ge=0, le=1)
    y: float = Field(default=0.5, ge=0, le=1)
    gaming: GamingLayout | None = None

    @model_validator(mode="after")
    def layout_matches_mode(self):
        if self.mode == "gaming":
            if self.gaming is None:
                raise ValueError("Mode gaming memerlukan area facecam dan gameplay.")
            if self.tracking != "static":
                raise ValueError("Mode gaming memakai dua area tetap; pelacakan wajah atau pembicara tidak tersedia.")
        elif self.gaming is not None:
            raise ValueError("Pengaturan gaming hanya berlaku pada mode gaming.")
        return self

    @model_serializer(mode="wrap")
    def serialize_crop(self, handler):
        result = handler(self)
        if self.gaming is None:
            result.pop("gaming", None)
        return result


class RemotionTitle(StrictModel):
    enabled: bool = False
    text: str = Field(default="", max_length=80)
    duration_ms: int = Field(default=1200, ge=300, le=5000)

    @model_validator(mode="after")
    def require_enabled_text(self):
        if self.enabled and not self.text.strip():
            raise ValueError("Isi teks intro atau outro yang diaktifkan.")
        if any(ord(character) < 32 and character not in "\t\n\r" for character in self.text):
            raise ValueError("Teks intro atau outro mengandung karakter yang tidak didukung.")
        return self


class RemotionZoom(StrictModel):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    scale: float = Field(default=1.2, ge=1, le=2, allow_inf_nan=False)
    x: float = Field(default=.5, ge=0, le=1, allow_inf_nan=False)
    y: float = Field(default=.5, ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def time_order(self):
        if self.end_ms <= self.start_ms:
            raise ValueError("Waktu akhir zoom harus setelah awal.")
        return self


class RemotionEffects(StrictModel):
    transition_in: Literal["none", "fade", "slide"] = "none"
    transition_out: Literal["none", "fade", "slide"] = "none"
    transition_ms: int = Field(default=300, ge=100, le=1000)
    intro: RemotionTitle = Field(default_factory=RemotionTitle)
    outro: RemotionTitle = Field(default_factory=RemotionTitle)
    zooms: list[RemotionZoom] = Field(default_factory=list, max_length=20)


class SubtitleStyle(StrictModel):
    enabled: bool = True
    renderer: Literal["ffmpeg", "remotion"] = "ffmpeg"
    remotion_template: Literal["minimal", "gaming", "cinematic"] = "gaming"
    remotion_effects: RemotionEffects = Field(default_factory=RemotionEffects)
    display_mode: Literal["sentence", "words"] = "sentence"
    animation: Literal["none", "fade", "pop", "rise"] = "none"
    animation_ms: int = Field(default=180, ge=100, le=500)
    font_size: int = Field(default=52, ge=24, le=100)
    position: Literal["top", "bottom"] = "bottom"
    background: bool = True
    safe_margin: float = Field(default=0.15, ge=0.05, le=0.35)
    auto_fit: bool = True
    bold: bool = False
    italic: bool = False
    uppercase: bool = False
    text_color: str = Field(default="#FFFFFF", pattern=r"^#[0-9a-fA-F]{6}$")
    outline_color: str = Field(default="#111111", pattern=r"^#[0-9a-fA-F]{6}$")
    outline_width: float = Field(default=2.5, ge=0, le=8)
    shadow: float = Field(default=0, ge=0, le=8)
    background_color: str = Field(default="#000000", pattern=r"^#[0-9a-fA-F]{6}$")


class TrackingCrop(Crop):
    mode: Literal["fill"] = "fill"
    tracking: Literal["face", "speaker"]


class TrackingPreviewInput(StrictModel):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    crop_json: TrackingCrop


class Cue(StrictModel):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    text: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def time_order(self):
        if self.end_ms <= self.start_ms:
            raise ValueError("Waktu akhir subtitle harus setelah awal.")
        return self


class ClipInput(StrictModel):
    title: str = Field(default="Klip manual", min_length=1, max_length=200)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    transcript_id: str | None = None
    crop_json: Crop = Field(default_factory=Crop)
    subtitle_style_json: SubtitleStyle = Field(default_factory=SubtitleStyle)
    cues: list[Cue] | None = Field(default=None, max_length=2000)


class ClipPatch(StrictModel):
    expected_revision: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, gt=0)
    crop_json: Crop | None = None
    subtitle_style_json: SubtitleStyle | None = None
    cues: list[Cue] | None = Field(default=None, max_length=2000)


class SubtitleGenerateInput(StrictModel):
    expected_revision: int = Field(ge=1)
    language: Literal["auto", "id", "en"] = "auto"
    replace_existing: bool = False


class ExportInput(StrictModel):
    revision: int = Field(ge=1)
    resolution: Literal[720, 1080] = 1080
