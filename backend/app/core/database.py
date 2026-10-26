"""SQLAlchemy engine, session factory and the declarative base."""
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

# timestamps are stored and returned in UTC whatever the server's own time zone is
_url = get_settings().database_url
engine = create_engine(_url, pool_pre_ping=True,
                       connect_args={"options": "-c timezone=UTC"} if _url.startswith("postgresql") else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request, committed by the services."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def create_tables() -> None:
    """Create all database tables that do not exist yet."""
    import app.models  # noqa: F401  registers the tables on Base.metadata
    Base.metadata.create_all(engine)
