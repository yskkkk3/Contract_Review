"""LangGraph review agent state definition."""
from typing import TypedDict

# 6 个风险维度专家
RISK_DIMS = [
    "主体资格与合规",
    "财务与付款",
    "知识产权与保密",
    "违约责任与解除",
    "验收交付与质保",
    "争议解决与管辖",
]

RISK_DIM_KEYWORDS: dict[str, list[str]] = {
    "主体资格与合规": ["资质", "主体", "营业执照", "授权", "备案", "审批", "合法", "中标", "信用代码", "签约资格", "代理"],
    "财务与付款": ["付款", "价款", "金额", "发票", "预付款", "质保金", "结算", "账户", "汇率", "定金", "报酬", "支付"],
    "知识产权与保密": ["知识产权", "保密", "著作权", "专利", "商标", "数据", "专有技术", "披露", "开源"],
    "违约责任与解除": ["违约", "解除", "终止", "赔偿", "责任", "不可抗力", "损失", "免责", "索赔"],
    "验收交付与质保": ["验收", "交付", "质保", "保修", "标准", "检验", "安装", "调试", "售后", "培训", "合格"],
    "争议解决与管辖": ["争议", "仲裁", "诉讼", "管辖", "法院", "适用法律", "调解", "送达"],
}


class ReviewState(TypedDict):
    # 任务参数
    session_id: int
    file_id: int
    user_id: int
    contract_type: str
    stance: str
    intensity: str
    description: str
    max_concurrent: int
    content_path: str  # 合同解析文本路径（工具 get_clause 使用）

    # 流程数据
    chunks: list[str]                     # 合同分块（按条款）
    intent: str                           # review / compare / chat / admin
    intent_confidence: float
    routed: list[dict]                    # [{chunk_index, risk_dims}]
    specialist_outputs: list[dict]  # [{chunk_index, risk_dim, result}]
    gated: list[dict]                     # 质检通过的结果
    final_risk_points: list[dict]         # 仲裁后按 index 排序
    summary: dict                         # {summary, suggestion, overall_risk}
    errors: list[str]
