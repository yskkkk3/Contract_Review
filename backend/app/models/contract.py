from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.user import utcnow


class ContractType(Base):
    """合同类型（服务/货物/基建/科研仪器/租赁…）"""

    __tablename__ = "contract_types"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    description: Mapped[str] = mapped_column(String(255), default="")
    is_active: Mapped[int] = mapped_column(Integer, default=1)  # 1 激活 / 0 停用
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ContractFile(Base):
    __tablename__ = "contract_files"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(16))  # pdf | docx | doc
    file_path: Mapped[str] = mapped_column(String(512))  # 原始文件
    content_path: Mapped[str] = mapped_column(String(512), default="")  # 解析文本
    parse_status: Mapped[str] = mapped_column(String(16), default="parsed")  # parsed | uploaded
    party_a: Mapped[str] = mapped_column(String(255), default="")
    party_b: Mapped[str] = mapped_column(String(255), default="")
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    contract_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("contract_types.id"), nullable=True
    )
    review_position: Mapped[int] = mapped_column(Integer, default=0)  # 0 甲方 / 1 乙方
    is_accepted: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    contract_type: Mapped[ContractType | None] = relationship()
