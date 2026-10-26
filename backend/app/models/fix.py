from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Fix(Base):
    """One GPS position of a bird in a dataset."""
    __tablename__ = "fixes"
    __table_args__ = (
        UniqueConstraint("dataset_id", "bird_id", "ts", name="uq_fix_dataset_bird_ts"),
        Index("ix_fix_dataset_ts", "dataset_id", "ts"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"))
    bird_id: Mapped[int] = mapped_column(ForeignKey("birds.id", ondelete="CASCADE"))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    event_id: Mapped[str | None] = mapped_column(String(64))

    dataset = relationship("Dataset", back_populates="fixes")
    bird = relationship("Bird", back_populates="fixes")
