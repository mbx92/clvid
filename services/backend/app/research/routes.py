from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.auth import current_user
from app.api.errors import AppError
from app.db import get_db
from app.domain.limits import effective_settings
from app.domain.models import User
from app.media.process import MediaError
from .schemas import SearchInput, SearchResult
from .search import search_videos

router = APIRouter(prefix="/research", tags=["research"])


@router.post("/search", response_model=SearchResult)
def search(body: SearchInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    settings = effective_settings(db, user.id)
    # Do not keep a database read transaction open while waiting on YouTube.
    db.rollback()
    try:
        items = search_videos(body.query, count=body.count, max_seconds=settings.max_video_seconds)
    except MediaError as exc:
        status = {"research_busy": 429, "research_timeout": 504}.get(exc.code, 502)
        raise AppError(status, exc.code.upper(), exc.message) from None
    return {"query": body.query, "items": items,
            "message": None if items else "Tidak ditemukan video publik yang sesuai batas durasi. Coba topik lain atau ubah batas di Pengaturan."}
