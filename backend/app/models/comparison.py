from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.user import utcnow


class ComparisonTask(Base):
    __tablename__ = "comparison_tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    standard_file_id: Mapped[int] = mapped_column(ForeignKey("contract_files.id"))
    comparison_file_id: Mapped[int] = mapped_column(ForeignKey("contract_files.id"))
    diff_summary: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    diff_result: Mapped[str] = mapped_column(Text, default="[]")  # JSON
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
