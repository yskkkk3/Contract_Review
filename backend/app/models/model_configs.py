from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.user import utcnow


class ModelConfig(Base):
    __tablename__ = "model_configs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    model_name: Mapped[str] = mapped_column(String(128))
    model_type: Mapped[str] = mapped_column(String(32), index=True)  # review | chat | intent | embedding | rerank
    provider: Mapped[str] = mapped_column(String(64), default="siliconflow")
    api_endpoint: Mapped[str] = mapped_column(String(255), default="https://api.siliconflow.cn/v1")
    api_key: Mapped[str] = mapped_column(String(255), default="")  # 引用环境变量，不落明文
    temperature: Mapped[float] = mapped_column(Float, default=0.7)
    top_p: Mapped[float] = mapped_column(Float, default=0.95)
    max_tokens: Mapped[int] = mapped_column(Integer, default=4096)
    is_default: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
