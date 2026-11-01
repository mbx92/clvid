from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine = create_engine(settings.database_url, pool_pre_ping=True,
                       connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {})
if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def sqlite_foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope():
    with SessionLocal() as session:
        try:
            yield session
            session.commit()
        except BaseException:
            session.rollback()
            raise


def get_db():
    with SessionLocal() as session:
        yield session
