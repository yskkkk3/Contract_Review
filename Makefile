# ============================================================
# Contract Review Agent — 项目命令入口
# 用法：make help          查看全部可用命令
# 依赖：make / docker compose / uv / node
# ============================================================

# ---------- 变量 ----------
COMPOSE  := docker compose -f deploy/docker-compose.yml

# ---------- 通用 ----------
.PHONY: help
help: ## 显示全部可用命令
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ---------- 环境安装 ----------
.PHONY: setup
setup: ## 安装后端(uv sync)与前端(npm install)全部依赖
	cd backend && uv sync
	cd frontend && npm install

# ---------- Docker 启动 ----------
.PHONY: up
up: ## Docker 一键构建并启动全部服务（需根目录 .env 已配置）
	$(COMPOSE) up -d --build

.PHONY: down
down: ## 停止并移除容器
	$(COMPOSE) down

.PHONY: restart
restart: ## 重启全部服务
	$(COMPOSE) restart

.PHONY: ps
ps: ## 查看容器状态
	$(COMPOSE) ps

.PHONY: logs
logs: ## 跟踪查看容器日志
	$(COMPOSE) logs -f

.PHONY: backend-logs
backend-logs: ## 仅跟踪 backend 容器日志
	$(COMPOSE) logs -f backend

.PHONY: ingest
ingest: ## 在 backend 容器内构建知识库（深大制度+法规+模板 → Qdrant/BM25）
	$(COMPOSE) exec backend python scripts/ingest_kb.py

# ---------- 本地开发（前后端分离） ----------
.PHONY: dev-backend
dev-backend: ## 本地启动后端 API（http://localhost:8080/docs，自动重载）
	cd backend && uv run uvicorn app.main:app --reload --port 8080

.PHONY: dev-frontend
dev-frontend: ## 本地启动前端（http://localhost:5173，/api 代理到 8080）
	cd frontend && npm run dev

.PHONY: qdrant
qdrant: ## 本地启动 Qdrant 容器（:6333，向量检索用）
	docker run -d --name cr-qdrant -p 6333:6333 -v qdrant_storage:/qdrant/storage qdrant/qdrant

# ---------- 测试与质量 ----------
.PHONY: test
test: ## 后端单元 + 集成测试（无需外部服务）
	cd backend && uv run pytest tests/ -q

.PHONY: lint
lint: ## 后端代码规范检查（ruff）
	cd backend && uv run ruff check app/ tests/ scripts/

.PHONY: frontend-build
frontend-build: ## 前端类型检查 + 生产构建
	cd frontend && npm run build

.PHONY: smoke
smoke: ## 端到端冒烟：真实 LLM + Qdrant 验证 Agent+RAG 全链路
	cd backend && uv run python scripts/smoke_agent.py

# ---------- RAG 测评 ----------
.PHONY: eval-rag
eval-rag: ## RAG 检索质量测评（Recall@K/MRR/NDCG，需 Qdrant + 已 ingest）
	cd backend && uv run --extra eval python scripts/eval_rag.py

# ---------- 性能压测 ----------
.PHONY: bench
bench: ## Locust 压测：20 并发 5 分钟（需先配置 scripts/bench_locust.py 账号与 id）
	cd backend && locust -f scripts/bench_locust.py --host http://localhost:8080 \
		--headless -u 20 -r 5 --run-time 5m --html report.html

# ---------- CI 本地复现 ----------
.PHONY: ci
ci: ## 本地复现 GitHub Actions 全部 Job（lint → test → frontend-build）
	make lint
	make test
	make frontend-build
