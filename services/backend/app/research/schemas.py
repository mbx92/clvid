from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    query: str = Field(min_length=2, max_length=200)
    count: int = Field(default=6, ge=1, le=10, strict=True)

    @field_validator("query")
    @classmethod
    def printable_query(cls, value):
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("Topik tidak boleh mengandung karakter kontrol.")
        return value


class VideoResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{11}$")
    url: str
    thumbnail_url: str
    title: str = Field(min_length=1, max_length=200)
    channel: str = Field(max_length=120)
    description: str = Field(max_length=600)
    duration_ms: int | None = Field(default=None, ge=1, le=86_400_000)
    view_count: int | None = Field(default=None, ge=0, le=10**15)

    @model_validator(mode="after")
    def canonical_links(self):
        if self.url != f"https://www.youtube.com/watch?v={self.id}" or self.thumbnail_url != f"https://i.ytimg.com/vi/{self.id}/hqdefault.jpg":
            raise ValueError("Unexpected search result URL")
        return self


class SearchResult(BaseModel):
    query: str
    items: list[VideoResult] = Field(max_length=10)
    message: str | None = None
