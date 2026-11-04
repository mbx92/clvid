from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

class Theme(Strict):
    background: str = Field(default="#132923", pattern=r"^#[0-9a-fA-F]{6}$")
    foreground: str = Field(default="#FFFFFF", pattern=r"^#[0-9a-fA-F]{6}$")
    accent: str = Field(default="#D9F279", pattern=r"^#[0-9a-fA-F]{6}$")
    font: Literal["sans", "serif", "mono"] = "sans"
    motion: Literal["fade", "rise", "zoom", "none"] = "rise"
    align: Literal["left", "center"] = "left"
    font_size: int = Field(default=72, ge=40, le=100)
    uppercase: bool = False

class VisualItem(Strict):
    icon: Literal['bean', 'cup', 'leaf', 'water', 'sun', 'person', 'box', 'check', 'question'] = 'box'
    label: str = Field(default='', max_length=32)

class Visual(Strict):
    kind: Literal['none', 'coffee_compare', 'coffee_flat', 'coffee_pair', 'coffee_separate', 'coffee_peaberry', 'coffee_reveal', 'diagram', 'comparison', 'steps'] = 'none'
    items: list[VisualItem] = Field(default_factory=list, max_length=4)
    motion: Literal['gentle', 'still'] = 'gentle'
    reveal_ms: int = Field(default=2000, ge=0, le=10000)

class VisualPlanItem(Strict):
    scene_id: str = Field(min_length=1, max_length=64)
    visual: Visual

class VisualPlan(Strict):
    scenes: list[VisualPlanItem] = Field(min_length=1, max_length=20)

class Caption(Strict):
    start_ms: int = Field(ge=0, le=30000, strict=True)
    end_ms: int = Field(gt=0, le=30000, strict=True)
    text: str = Field(min_length=1, max_length=200)

class Scene(Strict):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    layout: Literal["title", "split", "quote", "stat"] = "title"
    title: str = Field(default="", max_length=120)
    text: str = Field(default="", max_length=360)
    narration: str = Field(default="", max_length=600)
    visual_note: str = Field(default="", max_length=500)
    visual: Visual = Field(default_factory=Visual)
    duration_ms: int = Field(default=5000, ge=1000, le=30000, multiple_of=100)
    asset_id: str | None = Field(default=None, max_length=36)
    audio_id: str | None = Field(default=None, max_length=36)
    media_start_ms: int = Field(default=0, ge=0, le=180000)
    show_caption: bool = True
    captions: list[Caption] = Field(default_factory=list, max_length=200)
    caption_audio_id: str | None = Field(default=None, max_length=36)
    caption_narration: str = Field(default="", max_length=600)

    @model_validator(mode="after")
    def caption_bounds(self):
        previous_end = 0
        for cue in self.captions:
            if not previous_end <= cue.start_ms < cue.end_ms <= self.duration_ms:
                raise ValueError("Waktu subtitle harus berurutan, tidak bertumpuk, dan berada di dalam durasi adegan. Sesuaikan subtitle sebelum memperpendek adegan.")
            previous_end = cue.end_ms
        return self

class Document(Strict):
    title: str = Field(default="Video baru", min_length=1, max_length=200)
    script: str = Field(default="", max_length=12000)
    style_prompt: str = Field(default="", max_length=2000)
    preserve_script: bool = True
    aspect: Literal["portrait", "landscape", "square"] = "portrait"
    theme: Theme = Field(default_factory=Theme)
    scenes: list[Scene] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def duration_and_ids(self):
        if sum(s.duration_ms for s in self.scenes) > 180000:
            raise ValueError("Durasi maksimum 3 menit.")
        if len({s.id for s in self.scenes}) != len(self.scenes):
            raise ValueError("ID adegan harus unik.")
        return self

class SaveInput(Strict):
    expected_version: int = Field(ge=1)
    document: Document

class ActionInput(Strict):
    expected_version: int = Field(ge=1)
    mode: Literal["storyboard", "style", "visuals"] = "storyboard"
    scene_id: str | None = Field(default=None, min_length=1, max_length=64)

class TemplateInput(Strict):
    name: str = Field(min_length=1, max_length=80)
    theme: Theme

PRESETS = [
    {"id": "editorial", "name": "Editorial", "theme": Theme().model_dump()},
    {"id": "paper", "name": "Paper", "theme": Theme(background="#F5F0E6", foreground="#292522", accent="#B7462F", font="serif", motion="fade").model_dump()},
    {"id": "electric", "name": "Electric", "theme": Theme(background="#16152D", foreground="#FFFFFF", accent="#C7ACFF", font="sans", motion="zoom", align="center", uppercase=True).model_dump()},
]
