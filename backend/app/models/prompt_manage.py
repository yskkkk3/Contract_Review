from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.user import utcnow


class Prompt(Base):
    """三级 Prompt：system（系统）→ org（机构）→ override（个性化）"""

    __tablename__ = "prompts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    level: Mapped[str] = mapped_column(String(16), index=True)  # system | org | override
    contract_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("contract_types.id"), nullable=True, index=True
    )
    base_prompt_id: Mapped[int | None] = mapped_column(
        ForeignKey("prompts.id"), nullable=True
    )  # org 指向 system；override 指向 org
    organization_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_name: Mapped[str] = mapped_column(String(128))
    prompt_content: Mapped[str] = mapped_column(Text)
    is_active: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
