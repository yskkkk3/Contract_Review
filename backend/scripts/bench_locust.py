"""Locust 压测脚本：登录 → 列表 → 审阅 SSE → 聊天 SSE 全链路。

用法:
  locust -f scripts/bench_locust.py --host http://localhost:8080
  # 或无头模式
  locust -f scripts/bench_locust.py --host http://localhost:8080 \
    --headless -u 20 -r 5 --run-time 5m --html report.html

指标关注（docs/benchmark.md）:
  - /api/auth/login: P50/P95 延迟
  - /api/reviews/start: SSE 首包时间（TTFT）、完整审阅时长、成功率
  - /api/chats: SSE 流式首 token 延迟、完整回复时长
"""
import json

from locust import HttpUser, between, task

USERNAME = "bench"
PASSWORD = "bench123"

# 压测需预先准备：每个账号独立合同+会话（scripts 提供 bench_prepare 一键准备）
# SESSION_IDS 按用户索引对应：bench->2, bench_1->3, ...（本机压测环境实测值）
CONTRACT_IDS = []
SESSION_IDS = [2, 3, 4, 5, 6, 7]


class ContractReviewUser(HttpUser):
    wait_time = between(1, 3)
    _user_index = 0  # 每个用户独立账号，避免登录互踢（access_token 单值覆盖）

    def on_start(self):
        cls = self.__class__
        idx = cls._user_index
        cls._user_index += 1
        username = f"{USERNAME}_{idx}" if idx > 0 else USERNAME
        self.session_id = SESSION_IDS[idx % len(SESSION_IDS)]
        resp = self.client.post(
            "/api/auth/login",
            json={"identifier": username, "password": PASSWORD},
        )
        if resp.status_code == 200:
            self.token = resp.json()["data"]["access_token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            self.token = None

    @task(2)
    def list_contracts(self):
        if self.token:
            self.client.get("/api/contracts?page=1&page_size=10", headers=self.headers)

    @task(1)
    def review_sse(self):
        """审阅 SSE 全链路：测 TTFT 与完整时长。"""
        if not self.token or not CONTRACT_IDS:
            return
        with self.client.request(
            "POST",
            "/api/reviews/start",
            json={
                "session_id": self.session_id,
                "contract_type": "服务",
                "stance": "甲方",
                "intensity": "标准",
                "max_concurrent": 10,
            },
            headers=self.headers,
            stream=True,
            catch_response=True,
            name="/api/reviews/start (SSE)",
        ) as resp:
            first = True
            done = False
            for line in resp.iter_lines():
                if not line or not line.startswith(b"data:"):
                    continue
                payload = json.loads(line[5:].decode("utf-8"))
                if first:
                    # 首包时间 = TTFT，由 Locust 自动计时（stream 计时从请求发出到首个响应）
                    first = False
                if payload.get("event") == "end":
                    done = True
                if payload.get("event") == "error":
                    resp.failure(payload.get("data", {}).get("message", "review error"))
            if not done:
                resp.failure("SSE stream ended without 'end' event")

    @task(2)
    def chat_sse(self):
        """聊天 SSE：流式首 token 与完整回复。"""
        if not self.token:
            return
        with self.client.request(
            "POST",
            "/api/chats",
            json={"session_id": self.session_id, "content": "付款条款一般包含哪些要素？"},
            headers=self.headers,
            stream=True,
            catch_response=True,
            name="/api/chats (SSE)",
        ) as resp:
            got_content = False
            done = False
            for line in resp.iter_lines():
                if not line or not line.startswith(b"data:"):
                    continue
                payload = json.loads(line[5:].decode("utf-8"))
                if payload.get("type") == "content":
                    got_content = True
                if payload.get("type") == "done":
                    done = True
                if payload.get("type") == "error":
                    resp.failure(payload.get("message", "chat error"))
            if not got_content or not done:
                resp.failure("chat SSE incomplete")
