from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.user import utcnow


class ReviewTask(Base):
    __tablename__ = "review_tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"), index=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("contract_files.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    stance: Mapped[str] = mapped_column(String(16), default="甲方")  # 甲方 | 乙方
    intensity: Mapped[str] = mapped_column(String(16), default="标准")  # 严格 | 标准 | 宽松
    description: Mapped[str] = mapped_column(Text, default="")
    contract_type: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|processing|completed|failed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ReviewResult(Base):
    """单条风险点"""

    __tablename__ = "review_results"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("review_tasks.id"), index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"), index=True)
    index: Mapped[int] = mapped_column(Integer)  # 原条款顺序
    original_content: Mapped[str] = mapped_column(Text)
    risk_analysis: Mapped[str] = mapped_column(Text, default="")
    risk_level: Mapped[str] = mapped_column(String(8), default="低")  # 高 | 中 | 低
    suggested_content: Mapped[str] = mapped_column(Text, default="")
    risk_dim: Mapped[str] = mapped_column(String(32), default="")  # 风险维度
    is_accepted: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
