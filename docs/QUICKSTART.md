# 快速启动与测试指南

本文档说明如何启动项目（Docker 一键 / 本地开发）并执行全部测试与验证。

## 1. 环境要求

| 组件 | 版本 | 用途 |
|---|---|---|
| Docker + Docker Compose | v2+ | 一键部署（推荐） |
| Python | 3.12 | 后端（经 `uv` 管理） |
| uv | >=0.5 | Python 依赖与虚拟环境 |
| Node.js | 22 | 前端构建 |

## 2. 快速启动（Docker 一键）

```bash
# 1) 克隆并配置密钥（SiliconFlow API key 必填）
git clone git@github.com:yskkkk3/Contract_Review.git
cd contract-review
cp backend/.env.example .env
vim .env                      # 填入 SILICONFLOW_API_KEY=sk-xxx

# 2) 构建并启动六服务（mysql/redis/qdrant/langfuse/backend/frontend）
#    .env 必须位于项目根目录（compose 通过 env_file: ../.env 注入 backend 容器）
docker compose -f deploy/docker-compose.yml up -d --build

# 3) 等待健康检查通过后，构建知识库（深大制度 + 法规 + 模板）
docker compose -f deploy/docker-compose.yml exec backend python scripts/ingest_kb.py

# 4) 打开前端
open http://localhost            # 注册账号 → 上传合同 → 发起审阅
```

> 服务端口：前端 `http://localhost`，后端 API `http://localhost:8080/api`，Langfuse `http://localhost:3000`，Qdrant `http://localhost:6333`。

> **`.env` 位置约定**：统一放**项目根目录**（`cp backend/.env.example .env`）。
> - Docker：`deploy/docker-compose.yml` 通过 `env_file: ../.env` 注入 backend 容器；
> - 本地开发：`backend/app/core/config.py` 会回退读取上级目录 `../.env`，无需重复配置。

## 3. 本地开发模式（前后端分离）

```bash
# ---- 后端（backend/）----
cd backend
uv sync                          # 安装依赖（含 dev）
uv run uvicorn app.main:app --reload --port 8080

# ---- 前端（frontend/）----
cd frontend
npm install
npm run dev                      # http://localhost:5173，/api 代理到 8080
```

本地后端默认使用 SQLite（无 MySQL/Redis 也可跑单测），需要向量检索时需另起 Qdrant：

```bash
docker run -d -p 6333:6333 -v qdrant_storage:/qdrant/storage qdrant/qdrant
uv run python scripts/ingest_kb.py     # 构建知识库到 Qdrant + BM25
```

## 4. 测试与验证

```bash
cd backend

# 4.1 单元测试 + 集成测试（33 项，无需外部服务）
uv run pytest tests/ -q

# 4.2 代码规范检查
uv run ruff check app/ tests/ scripts/

# 4.3 端到端冒烟（真实 LLM + 本地 Qdrant，验证 Agent+RAG 全链路）
uv run python scripts/smoke_agent.py
# 预期输出：6 个维度专家并行审阅 → N 个风险点 + 整体风险等级 + 总耗时

# 4.4 RAG 检索质量测评（需 Qdrant + 已构建知识库）
uv run --extra eval python scripts/eval_rag.py
# 产出：Recall@K / Precision@K / MRR / NDCG@K / Hit@K（golden set 58 条）

# 4.5 RAGAS 生成质量测评（LLM-as-judge，需 SILICONFLOW_API_KEY）
#     eval 环境：ragas 0.4.3 + langchain-community<0.4（ragas 依赖 vertexai 模块，community 0.4 已移除）
uv run --extra eval python - << 'EOF'
import asyncio
from app.rag.eval.golden_set import GOLDEN_SET
from app.rag.eval.ragas_eval import build_ragas_dataset, run_ragas_eval
cases = [{"question": c.question, "answer": c.expected_answer,
          "contexts": [c.expected_answer], "ground_truth": c.expected_answer} for c in GOLDEN_SET[:10]]
asyncio.run(run_ragas_eval(build_ragas_dataset(cases)))
EOF

# 4.6 前端类型检查 + 构建
cd ../frontend && npm run build
```

## 5. 性能压测（Locust）

```bash
cd backend

# 先准备压测账号与数据：注册 bench/bench123，上传已解析合同，创建审阅会话，
# 并把 id 填入 scripts/bench_locust.py 顶部 CONTRACT_IDS / SESSION_IDS

# 有头模式（浏览器操作 http://localhost:8089）
locust -f scripts/bench_locust.py --host http://localhost:8080

# 无头模式（CI/脚本用）
locust -f scripts/bench_locust.py --host http://localhost:8080 \
  --headless -u 20 -r 5 --run-time 5m --html report.html
```

关键指标（回填至 `docs/benchmark.md`）：登录/列表延迟 P50/P95、审阅 SSE **TTFT** 与完整时长、聊天 SSE 首 token 延迟、成功率与吞吐。

## 5.5 文档解析与 MCP

- **多引擎解析**：默认回退链 `pdfplumber→pymupdf→pypdf→docx→libreoffice→ocr`；本地 OCR 需要 poppler 与 tesseract。可选 `cloud_ocr` 使用百炼 `qwen3.5-ocr`，默认复用 Embedding Key；启用后扫描页会发送到百炼。复杂版面可选 `uv sync --extra heavy-doc`（docling/mineru）。
- **MCP Server**：`uv run python -m app.mcp.server`（stdio，供 Claude/Cursor 等客户端）；或 `.env` 设 `MCP_ENABLED=true` 后经 `/api/mcp`（streamable-http）接入；工具：search_knowledge_base / ask_contract_assistant / health_check。
- **规则引擎 Skills**：`app/skills/rules.py` 提供 6 维度 8 条确定性规则（预付款>30%、违约金基数、验收标准等），输出与 LLM 专家同构，可并入审阅。

## 6. 常见问题

| 问题 | 处理 |
|---|---|
| `Illegal header value b'Bearer '` | 未配置 `SILICONFLOW_API_KEY`：检查 `backend/.env` 或 shell 环境变量 |
| `Qdrant connection refused` | 未启动 Qdrant：`docker run -d -p 6333:6333 qdrant/qdrant` 或走 docker compose |
| 审阅接口报 `file not parsed` | 上传后等待解析完成（`parse_status=parsed`）再发起审阅 |
| 前端 SSE 无响应 | 确认反向代理关闭了缓冲（Nginx `proxy_buffering off`；Vite 代理天然支持） |
| 数据库表未创建 | 后端启动时自动 `create_all`；如需 MySQL，先建库 `CREATE DATABASE contract_review CHARACTER SET utf8mb4` |

## 7. CI（GitHub Actions）

推送 `main` 自动触发 5 个 Job：

```
lint (ruff) → test (pytest) → frontend-build (vue-tsc + vite) → docker-build → deploy (占位)
```

本地等价复现：

```bash
cd backend && uv sync --frozen && uv run pytest tests/ -q && uv run ruff check app/ tests/ scripts/
cd frontend && npm ci && npm run build
```
