
from pydantic import BaseModel


class OverviewResponse(BaseModel):
    reviewed_contracts: int = 0
    service_departments: int = 0
    users_count: int = 0
    served_faculty_students: int = 0
    total_reviewed_amount: float = 0.0


class RevisionsResponse(BaseModel):
    risk_points_revised: int = 0
    error_points_revised: int = 0


class ContractTypesStatsResponse(BaseModel):
    reviewed_contracts: int = 0
    using_units: list[str] = []
    users_count: int = 0
    service_contracts: int = 0
    goods_contracts: int = 0
    infrastructure_contracts: int = 0


class TrendItem(BaseModel):
    date: str
    total: int = 0
    service: int = 0
    goods: int = 0
    infrastructure: int = 0


class DepartmentUsageItem(BaseModel):
    department_name: str
    contract_review: int = 0
    contract_verification: int = 0
    contract_comparison: int = 0
    total: int = 0
