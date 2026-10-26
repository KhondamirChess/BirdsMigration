from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Dataset(Base):
    """One set of GPS tracks: a demo scenario or an imported file (e.g. the China 2022 data)."""
    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)            # display order
    study: Mapped[str] = mapped_column(String(200))
    name_en: Mapped[str] = mapped_column(String(200))
    name_ko: Mapped[str | None] = mapped_column(String(200))
    desc_en: Mapped[str | None] = mapped_column(Text)
    desc_ko: Mapped[str | None] = mapped_column(Text)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    source_file: Mapped[str | None] = mapped_column(String(300))
    import_report: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    fixes = relationship("Fix", back_populates="dataset", cascade="all, delete-orphan", passive_deletes=True)
