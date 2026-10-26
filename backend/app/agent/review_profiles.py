"""Immutable review checklists. Keywords route checks; they never establish risks."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from types import MappingProxyType

from app.agent.state import RISK_DIMS

PROFILE_VERSION = "1"


@dataclass(frozen=True)
class ReviewCheck:
    id: str
    title: str
    risk_dim: str
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class ReviewProfile:
    key: str
    name: str
    family: str
    checks: tuple[ReviewCheck, ...]
    version: str = PROFILE_VERSION


def _profile(key, name, family, rows):
    return ReviewProfile(key, name, family, tuple(
        ReviewCheck(f"{key}.{code}", title, RISK_DIMS[dim], tuple(words.split("|")))
        for code, dim, title, words in rows
    ))


COMMON = _profile("common", "通用合同", "common", (
    ("identity", 0, "主体身份、授权与规则适用", "主体|授权|资质|签约|审批"),
    ("payment", 1, "价款、付款与结算", "价款|付款|发票|结算|费用"),
    ("rights", 2, "知识产权、数据与保密", "知识产权|数据|保密|成果|许可"),
    ("liability", 3, "违约责任、变更与退出", "违约|解除|终止|责任|赔偿"),
    ("delivery", 4, "交付、验收与持续保障", "交付|验收|质保|保修|标准"),
    ("disputes", 5, "争议解决、管辖与送达", "争议|仲裁|管辖|法院|送达"),
))

_PROFILES = (
    _profile("goods", "货物采购", "goods", (
        ("specification", 4, "货物规格、数量及替代", "型号|规格|数量|替代|品牌"),
        ("handover", 4, "运输、交付与风险转移", "运输|包装|交货|交付|风险转移"),
        ("price", 1, "货款、税费与付款节点", "货款|价款|税费|付款|发票"),
        ("warranty", 4, "质量保障与维修退换", "质保|保修|售后|退换|维修"),
    )),
    _profile("construction", "工程建设", "construction", (
        ("scope", 4, "工程范围、图纸与工程量", "图纸|工程量|施工范围|工程范围"),
        ("schedule", 3, "工期、停工与顺延", "工期|停工|顺延|进度|开工"),
        ("changes", 1, "变更、签证与工程结算", "变更|签证|结算|审价|造价"),
        ("quality", 4, "工程验收、缺陷与保修", "竣工|隐蔽工程|验收|缺陷|保修"),
    )),
    _profile("technology", "信息化项目", "technology", (
        ("deliverables", 4, "源代码、部署材料与交付", "源代码|部署|接口|技术文档|测试"),
        ("rights", 2, "软件成果、许可与第三方组件", "定制|软件许可|开源|第三方组件|知识产权"),
        ("data", 2, "数据处理、访问与安全", "数据|备份|个人信息|访问权限|安全事件"),
        ("exit", 3, "系统退出、迁移与接管", "退出|迁移|停服|接管|终止"),
    )),
    _profile("maintenance", "运维与维保", "ongoing_service", (
        ("sla", 4, "响应、修复与服务可用性", "响应|修复|恢复|可用率|sla|工单"),
        ("scope", 4, "巡检、备件与服务边界", "备件|耗材|巡检|维保范围|维护范围"),
        ("fees", 1, "维保费用与服务考核", "服务费|额外收费|考核|扣费|结算"),
        ("continuity", 3, "服务中断、交接与过渡", "中断|移交|交接|过渡|终止"),
    )),
    _profile("facilities", "物业与餐饮", "ongoing_service", (
        ("scope", 4, "服务区域、频次与质量", "保洁|安保|食堂|物业|消杀|巡查"),
        ("safety", 0, "安全、卫生与事件处置", "食品|卫生|安全事故|健康|应急"),
        ("staff", 0, "服务人员、管理与责任边界", "人员|派驻|劳动关系|外包|管理责任"),
        ("assessment", 1, "服务考核与费用结算", "考核|餐费|结算|扣费|服务费"),
    )),
    _profile("lease", "租赁服务", "lease", (
        ("object", 4, "租赁物、用途与交接", "租赁物|用途|交接|现状|附属设施"),
        ("costs", 1, "租金、押金与费用承担", "租金|押金|递增|物业费|水电"),
        ("maintenance", 3, "维修、损毁与保险责任", "维修|修缮|损毁|保险|损坏"),
        ("exit", 3, "转租、续租与退租返还", "退租|返还|恢复原状|转租|续租"),
    )),
    _profile("consulting", "咨询与评估", "professional_service", (
        ("deliverables", 4, "咨询范围与成果要求", "研究报告|成果|咨询范围|研究方法|评估报告"),
        ("acceptance", 4, "成果验收与修改安排", "验收|评价|修改|标准|轮次"),
        ("independence", 0, "独立性、资格与利益冲突", "利益冲突|独立|回避|资格|关联关系"),
        ("rights", 2, "成果使用、资料与保密", "成果使用|保密|底稿|归属|资料"),
    )),
    _profile("inspection", "检验与检测", "professional_service", (
        ("scope", 4, "检测项目、标准与方法", "检测项目|指标|标准|方法|检测范围"),
        ("samples", 4, "抽样、封样与样品流转", "抽样|封样|样品|留样|流转"),
        ("reports", 3, "报告用途、异议与复检", "报告|结论|复检|异议|责任"),
        ("data", 2, "检测资料、报告披露与保密", "检测数据|披露|保密|报告使用|记录"),
    )),
    _profile("training", "教育与培训", "professional_service", (
        ("plan", 4, "课程、师资与培训计划", "课程|课时|师资|教材|教学"),
        ("acceptance", 4, "出勤、考核与培训成果", "出勤|考核|培训效果|结业|学员"),
        ("changes", 1, "改期、取消与退费结算", "退费|取消|改期|人数|费用"),
        ("materials", 2, "教材、录制与学员信息", "肖像|录制|教材|个人信息|课程版权"),
    )),
    _profile("legal_audit", "法律与审计", "professional_service", (
        ("scope", 4, "委托事项、权限与成果", "委托事项|代理权限|审计范围|成果|底稿"),
        ("independence", 0, "执业资格、独立性与冲突", "独立|利益冲突|回避|资质|专业人员"),
        ("fees", 1, "专业服务费与额外支出", "收费|差旅|第三方费用|追加收费|结算"),
        ("materials", 2, "委托资料、底稿与保密", "保密|委托资料|底稿|留存|返还"),
    )),
    _profile("culture_ip", "文化与知识产权", "intellectual_property", (
        ("rights", 2, "权利来源与授权链", "许可|授权|作品|权利来源|转授权|第三方"),
        ("license", 2, "许可范围、期限与使用方式", "地域|期限|媒介|次数|独占|使用方式"),
        ("delivery", 4, "素材、活动与成果交付", "素材|节目|活动|验收|审核|档期"),
        ("claims", 3, "第三方主张、退出与责任", "侵权|索赔|下架|退款|责任"),
    )),
    _profile("other_services", "其他服务", "generic_service", (
        ("scope", 4, "服务范围、成果与边界", "服务范围|成果|边界|服务内容"),
        ("fees", 1, "计费依据、费用与结算", "计费|费用|付款|结算"),
        ("acceptance", 4, "服务标准、验收与考核", "服务标准|验收|考核|合格"),
        ("exit", 3, "终止、交接与资料返还", "终止|交接|资料返还|解除"),
    )),
)
PROFILES = MappingProxyType({profile.name: profile for profile in _PROFILES})
_ALIASES = {"服务": "其他服务", "服务采购": "其他服务", "货物": "货物采购", "工程": "工程建设"}
_active: ContextVar[ReviewProfile | None] = ContextVar("review_profile", default=None)

_MATERIAL_HINTS = (
    ("竞争性磋商文件", ("竞争性磋商文件", "磋商文件")),
    ("采购文件或招标文件", ("采购文件", "招标文件")),
    ("供应商响应文件", ("响应文件",)),
    ("投标文件", ("投标文件",)),
    ("成交通知书或中标通知书", ("成交通知书", "中标通知书")),
    ("技术需求书或技术规格书", ("技术需求书", "技术规格书", "技术要求")),
    ("报价、服务或交付清单", ("报价清单", "服务清单", "交付清单")),
    ("授权委托书", ("授权委托书", "授权文件")),
    ("数据处理或保密协议", ("数据处理协议", "保密协议")),
)


def get_profile(contract_type: str | None = None) -> ReviewProfile:
    name = (contract_type or "").strip()
    return PROFILES.get(_ALIASES.get(name, name), COMMON)


def active_profile() -> ReviewProfile | None:
    return _active.get()


@contextmanager
def profile_scope(contract_type: str | None):
    token = _active.set(get_profile(contract_type))
    try:
        yield _active.get()
    finally:
        _active.reset(token)


def profiled(state_arg=0):
    """Keep node-local context even when a node is invoked without the graph."""
    def decorate(fn):
        @wraps(fn)
        async def run(*args, **kwargs):
            state = kwargs.get("state") if "state" in kwargs else args[state_arg]
            with profile_scope(state.get("contract_type")):
                return await fn(*args, **kwargs)
        return run
    return decorate


def matching_checks(contract_type: str, text: str, risk_dim: str | None = None) -> tuple[ReviewCheck, ...]:
    profile = get_profile(contract_type)
    if profile is COMMON:
        return ()
    normalized = text.casefold()
    return tuple(check for check in profile.checks if (
        (risk_dim is None or check.risk_dim == risk_dim)
        and any(word.casefold() in normalized for word in check.keywords)
    ))


def contextual_query(query: str, risk_dim: str | None = None) -> str:
    profile = active_profile()
    if profile is None or profile is COMMON:
        return query
    matched = matching_checks(profile.name, query, risk_dim)
    return " ".join([query, profile.name, *(check.title for check in matched[:2])])


def review_scope(contract_type: str | None = None) -> dict:
    profile = get_profile(contract_type)
    checks = COMMON.checks + (profile.checks if profile is not COMMON else ())
    return {
        "profile_id": profile.key, "profile_name": profile.name, "version": profile.version,
        "contract_type": contract_type or "", "fallback": profile is COMMON,
        "checklist_status": "configured", "base_dimensions": list(RISK_DIMS),
        "checks": [{"id": check.id, "title": check.title, "risk_dim": check.risk_dim} for check in checks],
    }


def assessed_scope(contract_type, outputs, supplement_files=None):
    scope = review_scope(contract_type)
    scope["supplement_files"] = list(supplement_files or [])
    scope["missing_materials"] = []
    profile = get_profile(contract_type)
    if profile is COMMON:
        return scope
    records = [item for output in outputs for item in output.get("check_results", []) if isinstance(item, dict)]
    assessments = []
    for check in profile.checks:
        matched = [item for item in records if item.get("check_id") == check.id]
        if len(matched) == 1 and isinstance(matched[0].get("status"), str) and matched[0].get("status") in {
            "reviewed", "not_applicable", "needs_material", "unverified",
        } and matched[0].get("reason"):
            item = dict(matched[0])
        else:
            item = {"check_id": check.id, "status": "unverified", "reason": "未收到该项唯一有效的核对记录", "clause_indices": []}
        assessments.append({**item, "title": check.title, "risk_dim": check.risk_dim})
    scope["check_results"] = assessments
    scope["checklist_status"] = "incomplete" if any(
        item["status"] in {"unverified", "needs_material"} for item in assessments
    ) else "reviewed"
    missing_materials = []
    for item in assessments:
        if item["status"] != "needs_material":
            continue
        suggested = [
            label for label, aliases in _MATERIAL_HINTS
            if any(alias in item["reason"] for alias in aliases)
        ]
        missing_materials.append({
            "id": item["check_id"],
            "title": item["title"],
            "risk_dim": item["risk_dim"],
            "reason": item["reason"],
            "suggested_files": suggested or [f"与“{item['title']}”相关的附件或证明材料"],
            "clause_indices": item.get("clause_indices", []),
        })
    scope["missing_materials"] = missing_materials
    return scope
