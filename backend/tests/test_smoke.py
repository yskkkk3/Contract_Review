"""API smoke tests: auth -> session -> file -> admin -> dashboard."""


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_register_login_me(client):
    r = client.post("/api/users", json={"username": "alice", "password": "secret123"})
    assert r.status_code == 200
    assert r.json()["data"]["username"] == "alice"

    r = client.post("/api/auth/login", json={"identifier": "alice", "password": "secret123"})
    assert r.status_code == 200
    token = r.json()["data"]["access_token"]
    assert token

    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["data"]["username"] == "alice"


def test_bad_login(client):
    r = client.post("/api/auth/login", json={"identifier": "nobody", "password": "wrong"})
    assert r.status_code == 401


def test_unauthorized_access(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_session_crud(client, auth_headers):
    r = client.post(
        "/api/sessions",
        json={"title": "test review", "session_type": "review"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    session_id = r.json()["data"]["session_id"]

    r = client.get("/api/sessions?session_type=review&page=1&page_size=20", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["data"]["total"] == 1

    r = client.put(
        f"/api/sessions/{session_id}/title",
        json={"session_id": session_id, "new_title": "renamed"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["data"]["title"] == "renamed"

    r = client.delete(f"/api/sessions/{session_id}", headers=auth_headers)
    assert r.status_code == 200


def test_contract_type_crud(client):
    r = client.post("/api/contract-types", json={"name": "服务类", "description": "服务合同"})
    assert r.status_code == 200
    type_id = r.json()["data"]["id"]

    r = client.get("/api/contract-types")
    assert r.status_code == 200
    assert any(t["name"] == "服务类" for t in r.json()["data"])

    r = client.post(f"/api/contract-types/{type_id}/activate?is_active=0")
    assert r.status_code == 200
    assert r.json()["data"]["is_active"] == 0


def test_model_config_crud(client):
    r = client.post(
        "/api/model-configs",
        json={
            "model_name": "DeepSeek-V3.2",
            "model_type": "review",
            "provider": "siliconflow",
            "api_endpoint": "https://api.siliconflow.cn/v1",
            "temperature": 0.7,
            "top_p": 0.95,
            "max_tokens": 4096,
        },
    )
    assert r.status_code == 200
    mid = r.json()["data"]["id"]
    r = client.get("/api/model-configs?model_type=review")
    assert r.status_code == 200
    assert len(r.json()["data"]) == 1
    r = client.delete(f"/api/model-configs/{mid}")
    assert r.status_code == 200


def test_dashboard(client):
    r = client.get("/api/dashboard/overview")
    assert r.status_code == 200
    assert "reviewed_contracts" in r.json()["data"]

    r = client.get("/api/dashboard/trends?period=month")
    assert r.status_code == 200
