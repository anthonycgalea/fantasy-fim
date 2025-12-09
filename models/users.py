from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Player(Base):
    __tablename__ = "players"
    user_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    is_admin: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
