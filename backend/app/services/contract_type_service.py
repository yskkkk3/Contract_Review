"""Default contract types and deterministic upload classification."""

from dataclasses import dataclass

from sqlalchemy.orm import Session as DBSession

from app.models.contract import ContractType


@dataclass(frozen=True)
class ContractTypeDefinition:
    name: str
    description: str
    keywords: tuple[str, ...]


DEFAULT_CONTRACT_TYPES: tuple[ContractTypeDefinition, ...] = (
    ContractTypeDefinition(
        "货物采购",
        "设备、仪器、材料、办公用品及其他实物采购合同",
        (
            "设备采购",
            "器材采购",
            "货物采购",
            "服装器材",
            "印刷品",
            "印刷",
            "采购合同",
            "equipment",
            "goods",
            "procurement",
        ),
    ),
    ContractTypeDefinition(
        "工程建设",
        "建设、改造、施工及工程监理合同",
        ("建设工程", "工程施工", "工程监理", "项目监理", "装修改造", "大中修"),
    ),
    ContractTypeDefinition(
        "信息化项目",
        "软件开发、系统集成、数字化平台及信息化建设合同",
        (
            "信息化",
            "系统集成",
            "软件开发",
            "平台建设",
            "人工智能",
            "智慧",
            "系统采购",
            "执法系统",
            "通讯服务",
            "电信服务",
        ),
    ),
    ContractTypeDefinition(
        "运维与维保",
        "网络、系统、设施设备、消防及车辆运行维护合同",
        ("运维", "运行维护", "维修保养", "维护保养", "消防值守", "消防维保", "维保"),
    ),
    ContractTypeDefinition(
        "物业与餐饮",
        "物业管理、保洁、安保及餐饮保障服务合同",
        ("物业", "保洁", "餐饮", "食堂", "安保服务", "后勤服务"),
    ),
    ContractTypeDefinition(
        "租赁服务",
        "场地、房屋、设备及其他资产租赁合同",
        ("租赁", "出租", "承租", "场地租用", "房屋租用"),
    ),
    ContractTypeDefinition(
        "咨询与评估",
        "咨询、规划、评估、课题研究及造价服务合同",
        ("咨询", "评估", "评价", "规划", "课题研究", "结算评审", "造价"),
    ),
    ContractTypeDefinition(
        "检验与检测",
        "检验检测、监测、鉴定及抽样服务合同",
        ("检验", "检测", "监测", "鉴定", "抽样", "食品抽检"),
    ),
    ContractTypeDefinition(
        "教育与培训",
        "教师培训、职业培训及人才培养服务合同",
        ("培训", "培育", "人才培养", "课程服务", "教学服务"),
    ),
    ContractTypeDefinition(
        "法律与审计",
        "法律顾问、诉讼代理、财务审计及专项审计合同",
        ("法律顾问", "法律服务", "律师", "审计", "会计师事务所"),
    ),
    ContractTypeDefinition(
        "文化与知识产权",
        "文化活动、影视版权、体育及知识产权许可合同",
        ("版权", "播放权", "知识产权", "文化活动", "影片", "体育赛事"),
    ),
    ContractTypeDefinition(
        "其他服务",
        "无法归入其他默认类别的综合服务合同",
        ("服务采购", "服务合同", "委托服务"),
    ),
)

_TYPE_PRIORITY = {definition.name: index for index, definition in enumerate(DEFAULT_CONTRACT_TYPES)}


def ensure_default_contract_types(db: DBSession) -> dict[str, ContractType]:
    """Create missing built-in types and return all built-ins keyed by name.

    The caller owns the transaction. Existing names, descriptions and activation states are preserved.
    """
    names = [definition.name for definition in DEFAULT_CONTRACT_TYPES]
    existing = db.query(ContractType).filter(ContractType.name.in_(names)).all()
    by_name = {item.name: item for item in existing}
    for definition in DEFAULT_CONTRACT_TYPES:
        if definition.name not in by_name:
            item = ContractType(name=definition.name, description=definition.description)
            db.add(item)
            by_name[definition.name] = item
    db.flush()
    return by_name


def classify_contract_type(title: str, content: str = "") -> str:
    """Classify a contract using weighted title and content keyword matches."""
    title_text = _normalize(title)
    content_text = _normalize(content[:20_000])
    scores: dict[str, int] = {}
    for definition in DEFAULT_CONTRACT_TYPES:
        score = 0
        for keyword in definition.keywords:
            normalized_keyword = _normalize(keyword)
            score += title_text.count(normalized_keyword) * 8
            score += min(content_text.count(normalized_keyword), 3)
        scores[definition.name] = score

    best_name, best_score = min(
        scores.items(),
        key=lambda item: (-item[1], _TYPE_PRIORITY[item[0]]),
    )
    return best_name if best_score > 0 else "其他服务"


def resolve_contract_type(
    db: DBSession, title: str, content: str = ""
) -> ContractType | None:
    """Resolve an active built-in type, falling back to ``其他服务``."""
    by_name = ensure_default_contract_types(db)
    selected = by_name[classify_contract_type(title, content)]
    if selected.is_active:
        return selected
    fallback = by_name["其他服务"]
    return fallback if fallback.is_active else None


def _normalize(value: str) -> str:
    return "".join((value or "").lower().split())
