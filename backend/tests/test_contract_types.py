"""Contract type seeding, classification and assignment tests."""

import io
from datetime import datetime

import pytest

from app.core.db import SessionLocal
from app.models.contract import ContractFile
from app.services.contract_type_service import classify_contract_type


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("医疗呼吸机设备采购合同.pdf", "货物采购"),
        ("实训楼建设工程监理合同.pdf", "工程建设"),
        ("电子档案与人工智能系统升级合同.pdf", "信息化项目"),
        ("高校消防值守维保合同.pdf", "运维与维保"),
        ("机关餐饮服务合同.pdf", "物业与餐饮"),
        ("校区场地租赁合同.pdf", "租赁服务"),
        ("战略性新兴产业规划课题研究合同.pdf", "咨询与评估"),
        ("食品安全抽样检测服务合同.pdf", "检验与检测"),
        ("高素质农民培训服务合同.pdf", "教育与培训"),
        ("党政机关法律顾问服务合同.pdf", "法律与审计"),
        ("特效影院影片版权租赁合同.pdf", "文化与知识产权"),
        ("纪检监察保密通讯服务合同.pdf", "信息化项目"),
        ("13_公路治超非现场执法系统采购合同.pdf", "信息化项目"),
        ("03_tsinghua_domestic_equipment.docx", "货物采购"),
        ("普通委托服务合同.pdf", "其他服务"),
    ],
)
def test_classify_contract_type(title, expected):
    assert classify_contract_type(title) == expected


def test_default_types_are_seeded(client):
    response = client.get("/api/contract-types")
    assert response.status_code == 200
    names = {item["name"] for item in response.json()["data"]}
    assert {
        "货物采购",
        "工程建设",
        "信息化项目",
        "运维与维保",
        "法律与审计",
        "其他服务",
    }.issubset(names)


def test_raw_upload_assigns_type_and_allows_manual_override(client, auth_headers):
    upload = client.post(
        "/api/contracts/upload_raw",
        files={"file": ("消防维保服务合同.pdf", io.BytesIO(b"%PDF-test"), "application/pdf")},
        headers=auth_headers,
    )
    assert upload.status_code == 200, upload.text
    file_id = upload.json()["data"]["file_id"]
    initial_type_id = upload.json()["data"]["contract_type_id"]
    assert initial_type_id is not None

    types = client.get("/api/contract-types").json()["data"]
    by_name = {item["name"]: item["id"] for item in types}
    assert initial_type_id == by_name["运维与维保"]

    changed = client.post(
        f"/api/contracts/{file_id}/type",
        json={"contract_type_id": by_name["工程建设"], "review_position": 1},
        headers=auth_headers,
    )
    assert changed.status_code == 200, changed.text

    listed = client.get("/api/contracts", headers=auth_headers).json()["data"]
    assert listed[0]["contract_type_id"] == by_name["工程建设"]
    assert listed[0]["review_position"] == 1


def test_manual_type_rejects_unknown_id(client, auth_headers):
    upload = client.post(
        "/api/contracts/upload_raw",
        files={"file": ("合同.pdf", io.BytesIO(b"%PDF-test"), "application/pdf")},
        headers=auth_headers,
    )
    file_id = upload.json()["data"]["file_id"]
    response = client.post(
        f"/api/contracts/{file_id}/type",
        json={"contract_type_id": 999_999, "review_position": 0},
        headers=auth_headers,
    )
    assert response.status_code == 400


def test_contract_search_combines_filters_and_paginates(client, auth_headers):
    titles = [
        "智慧校园系统合同.pdf",
        "医疗设备采购合同.pdf",
        "消防维保服务合同.pdf",
    ]
    file_ids = []
    for title in titles:
        response = client.post(
            "/api/contracts/upload_raw",
            files={"file": (title, io.BytesIO(b"%PDF-test"), "application/pdf")},
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        file_ids.append(response.json()["data"]["file_id"])

    with SessionLocal() as db:
        first = db.get(ContractFile, file_ids[0])
        second = db.get(ContractFile, file_ids[1])
        third = db.get(ContractFile, file_ids[2])
        assert first is not None and second is not None and third is not None
        first.party_a = "河南大学"
        first.party_b = "智慧科技有限公司"
        first.amount = 1_200_000
        first.created_at = datetime(2026, 10, 20, 10, 0, 0)
        second.party_a = "某中心医院"
        second.amount = 500_000
        second.created_at = datetime(2026, 10, 21, 10, 0, 0)
        third.amount = 3_000_000
        third.created_at = datetime(2026, 10, 22, 10, 0, 0)
        db.commit()

    combined = client.get(
        "/api/contracts/search",
        params={
            "title": "智慧校园",
            "party": "河南大学",
            "parse_status": "uploaded",
            "amount_min": 1_000_000,
            "amount_max": 2_000_000,
            "created_from": "2026-10-20",
            "created_to": "2026-10-20",
        },
        headers=auth_headers,
    )
    assert combined.status_code == 200, combined.text
    payload = combined.json()["data"]
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == file_ids[0]

    paged = client.get(
        "/api/contracts/search",
        params={"page": 2, "page_size": 2},
        headers=auth_headers,
    )
    assert paged.status_code == 200, paged.text
    page_data = paged.json()["data"]
    assert page_data["total"] == 3
    assert page_data["page"] == 2
    assert page_data["page_size"] == 2
    assert len(page_data["items"]) == 1


@pytest.mark.parametrize(
    "params",
    [
        {"amount_min": 200, "amount_max": 100},
        {"created_from": "2026-10-22", "created_to": "2026-10-20"},
    ],
)
def test_contract_search_rejects_reversed_ranges(client, auth_headers, params):
    response = client.get("/api/contracts/search", params=params, headers=auth_headers)
    assert response.status_code == 422
