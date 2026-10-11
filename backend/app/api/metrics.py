"""Performance metrics route: expose sliding-window TTFT / latency snapshot."""
from fastapi import APIRouter, Depends

from app.core.metrics import snapshot
from app.core.security import get_current_user
from app.models.user import User

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
async def get_metrics(current_user: User = Depends(get_current_user)):
    """流式性能指标快照：chat / review 各 endpoint 的 TTFT / 总延迟 P50/P95/P99。"""
    return snapshot()
