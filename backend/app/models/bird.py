from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Bird(Base):
    """A tagged individual. Tags are unique only inside a study, so a bird is (study, tag);
    the 20 demo mallards are shared by all three demo scenarios."""
    __tablename__ = "birds"
    __table_args__ = (UniqueConstraint("study", "tag", name="uq_bird_study_tag"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    study: Mapped[str] = mapped_column(String(200))
    tag: Mapped[str] = mapped_column(String(100))          # individual-local-identifier, e.g. MAL-01
    species: Mapped[str | None] = mapped_column(String(200))

    fixes = relationship("Fix", back_populates="bird", passive_deletes=True)
