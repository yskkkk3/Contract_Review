# AGENTS.md — 供 AI Agent（Codex / Claude Code 等）接手的仓库指南

本文件是给**代码修改 Agent** 看的手册：先读这里，再动代码。仓库内其他文档面向人类读者，本文件聚焦"怎么改而不破坏"。

## 1. 项目速览

高校采购合同智能审阅 Agent（简历级工程）：上传合同 → LangGraph 多 Agent 并行审阅 6 个风险维度 → SSE 流式推送风险点与证据 → 合同比对 / 合同问答 / 看板统计。RAG 知识库 = 深大采购制度 + 政府采购法规 + 合同模板（52 篇语料，三层）。

- 后端：FastAPI + SQLAlchemy 2 + Pydantic v2 + JWT + SSE（`backend/`，Python 3.12，uv 管理）
- 前端：Vue3 + TypeScript + Vite + Element Plus（`frontend/`）
- 部署：Docker Compose 六服务（`deploy/`）；CI 五 job（`.github/workflows/ci.yml`）
- 项目定位：面向高校采购场景的独立合同智能审阅系统

## 2. 仓库地图（改代码前先定位）

```
backend/
  app/main.py               FastAPI 入口（路由挂载、中间件、docs）
  app/core/                 config.py（全部配置项）、db.py、redis.py（缓存+分布式锁）、metrics.py（TTFT 滑动窗口）
  app/agent/
    graph.py                LangGraph 状态机：START→intent→(router|arbitration)→specialists→gate→arbitration→END
    state.py                AgentState（含 RISK_DIMS 六个风险维度定义）
    nodes/                  intent.py / router.py / specialist.py / gate.py / arbitration.py（各节点逻辑）
    tools/                  registry.py（4 工具 + 严格 JSON Schema）、executor.py（并行执行+截断+收敛）
    rules/intent_rules.py   意图识别规则降级引擎（纯函数，可单测）
    prompts/                系统提示词模板（*.md，改提示词在这里，不要硬编码进代码）
  app/rag/
    service.py              混合检索服务（dense+sparse→RRF→rerank→分层配额）
    query_expansion.py      Multi-Query 查询改写（TTL 缓存 + 降级）
    client.py               LLMClient（OpenAI SDK；信号量限流 + prompt cache）
    ingest/                 chunker / crawler / loader（知识库构建）
    eval/                   golden_set.py（100 条）、retrieval_metrics.py、ragas_eval.py
  app/api/                  auth / contracts / sessions / reviews / chats / comparisons / admin / dashboard / metrics
  app/services/             review_service.py（审阅 SSE 编排）、chat_service.py（聊天 SSE + TTFT）、document_parse.py（多引擎解析链）
  app/middlewares/          auth.py / logging.py / rate_limit.py
  app/skills/rules.py       6 维度确定性规则引擎（LLM+规则双引擎）
  app/mcp/                  MCP Server（stdio+SSE）/ Client
  scripts/                  ingest_kb.py / eval_rag.py / eval_ragas.py / check_golden.py / gate_metrics.py / bench_locust.py / smoke_agent.py
  tests/                    conftest.py（全局 mock LLM，重要！） + 8 个测试文件
frontend/                   src/（views / api / stores / router）+ vite 配置
deploy/                     docker-compose.yml（mysql/redis/qdrant/langfuse/backend/frontend）
docs/                       DESIGN.md / QUICKSTART.md / benchmark.md / rag-eval.md / resume.md / architecture.svg
Makefile                    命令入口（make help 查看全部）
```

## 3. 环境与命令

依赖：Python 3.12 + [uv](https://docs.astral.sh/uv/) + Node 22 + Docker（可选）。后端 `.env` 放**项目根目录**（`backend/.env.example` 是模板），config.py 会回退读取。

```bash
make setup            # 后端 uv sync + 前端 npm install
make test             # pytest（无需外部服务、无需 key，conftest 已 mock LLM）
make lint             # ruff check app/ tests/ scripts/
make frontend-build   # 前端类型检查 + 构建
make ci               # 本地复现 CI：lint → test → frontend-build
make dev-backend      # 本地后端 :8080（http://localhost:8080/docs）
make dev-frontend     # 本地前端 :5173（/api 代理 8080）
make up / down        # Docker 全套起停
make ingest           # 重建知识库（Qdrant + BM25，需已 ingest 环境）
make eval-rag         # RAG 检索评测（uv run --extra eval）
make smoke            # 端到端冒烟（真实 LLM + Qdrant）
```

本地无 Docker 时的替代（云电脑实践过的组合）：

```bash
# Qdrant 二进制 + redislite（嵌入式 Redis，必须保持进程存活）
cd /home/user/qdrant-bin && ./qdrant --config-path /home/user/qdrant-config.yaml &
python -c "import redislite,time; r=redislite.Redis('/tmp/cr-redis.db',serverconfig={'port':'6379','bind':'127.0.0.1','save':''}); [time.sleep(3600) for _ in range(3600)]" &
# 后端（SQLite 替代 MySQL）
cd backend && DATABASE_URL=sqlite:////path/dev.db QDRANT_HOST=localhost uv run uvicorn app.main:app --port 8082 &
# 前端
cd frontend && VITE_API_BASE=http://localhost:8082/api npm run dev
```

## 4. 架构速览（改代码前必须理解）

**Agent 编排（LangGraph）**：`intent`（LLM 结构化意图识别，失败走 `rules/intent_rules.py` 规则引擎降级）→ 意图 `chat` 直接短路到 arbitration；意图 `review` 走 `router`（按风险维度分发条款）→ `specialists`（6 个专家节点**并行** ReAct 循环，可调用工具）→ `gate`（质检：风险点去重、必填字段校验、证据引用核对）→ `arbitration`（合并汇总 + 分类排序）。

**工具调用（Function Calling）**：`tools/registry.py` 注册 4 个工具（违约金试算 / 法规查证 / 条款抽取 / 模板匹配），全部严格 JSON Schema；`tools/executor.py` 并行执行、结果截断（8000 字符）、异常回喂给模型、迭代上限（3 轮）防死循环、耗尽后追加"禁止再调工具"收敛消息。**新增工具 = registry 注册 + executor 无需改动 + 测试用例**。

**RAG 链路**：问题 →（可选）Multi-Query 改写 → 三库（制度/法规/模板）并行混合检索（bge-m3 dense + BM25 sparse）→ RRF 融合 → 分层配额（每文档 ≤3 chunk 进 rerank）→ bge-reranker-v2-m3 精排 → 文档级去重终排 top5 → 证据拼装上下文。BM25 索引是 `data/kb_bm25.pkl`（ingest 生成）。

**SSE 协议（前端依赖，改事件名必须同步前端）**：
- 聊天：`start` → `delta`（文本增量）→ `usage` → `done`（含 `metrics.ttft_ms / total_ms / tpots`）
- 审阅：`meta`（task_id/session_id/chunk_count，**graph 执行前发出**）→ `risk_point`（每个风险点一条）→ `end`（summary + metrics）
- `/api/metrics`：TTFT/总延迟滑动窗口 P50/P95/P99/TPOT 聚合

## 5. 硬性约束（违反 = 返工）

1. **API key 只存在于本地 `.env`**：任何文件不得出现真实 key；`git push` 前 `git diff` 检查；`.env` 已被 gitignore，不要 `git add -f`。
2. **LLM 接入只走 OpenAI SDK**（`app/rag/client.py`）：供应商通过 `.env` 的 `LLM_BASE_URL` / `LLM_API_KEY` 切换（默认 SiliconFlow），不新增厂商 SDK；**主环境不 import `langchain-community`**（仅 eval extra 内为 RAGAS 兼容锁 `langchain-community<0.4` 与 `langchain-openai`）。
3. **提交规范**：英文 Conventional Commits（`feat/fix/docs/refactor/perf/test/chore`），如 `feat(agent): add evidence-verification tool`；一个 commit 一件事。
4. **CI 必须全绿**才能算完成：lint（ruff）→ test（pytest 无 key 环境）→ frontend-build → docker-build → rag-eval（golden 静态门禁必跑；配置了 `SILICONFLOW_API_KEY` secret 后自动升级为指标门禁 Recall@5≥0.6 / MRR≥0.4 / NDCG≥0.5，低于阈值会红）。
5. **测试不得依赖真实 LLM / 网络 / key**：`tests/conftest.py` 已全局 mock `get_sf_client`（FakeLLMClient）；新测试遵循同一模式；新实例化 `LLMClient()` 的测试必须 mock `AsyncOpenAI` 构造（见 `tests/test_llm_client.py` 的 `fake_openai` fixture），否则 CI 无 key 会抛 `Missing credentials`。
6. **依赖用 uv 管理**：新增依赖用 `uv add`；改 `pyproject.toml` 后必须 `uv lock` 并提交 `uv.lock`；⚠️ `uv sync` 会卸载未在依赖中声明的包（`redislite` 已在 dev 组声明，别再踩坑）；CI 用 `uv sync --frozen`（`uv.lock` 必须与 pyproject 一致）。
7. **提示词进 `app/agent/prompts/*.md`**，不硬编码在节点代码里；新增提示词文件需在 `prompts.py` 注册加载。
8. **ruff 规范**：line-length 100；忽略 `E501/B008`；新代码必须过 `ruff check app/ tests/ scripts/`。
9. **不改用户数据 / 不删他人文件**：只动与任务相关的文件；`.env`、`data/`、`docs/` 中的既有报告是用户资产。

## 6. 修改各模块的注意点

### Agent 编排
- 节点状态字段在 `state.py` 定义（`RiskPoint` 等 schema），新增字段要同步 review_service / 前端类型。
- 专家节点输出**多供应商字段漂移归一化**：`chat_structured` 的 JSON 可能返回 `high/low` 或 `高/中/低`、`risk_type` 或 `risk_dim`、`suggested_revision` 或 `suggested_content`——统一走 `_parse_risk_points` 归一化，条款原文缺失用 chunk 兜底。**新增供应商 / 模型时先验证字段**。
- 意图降级：`nodes/intent.py` 先 LLM（`chat_structured` + `response_format=json_schema`），解析失败或类型非法 → `rules/intent_rules.py` 规则引擎（强关键词 → 组合规则 → 否定词清零 → 同分仲裁）。改意图分类必须同步 `test_intent_rules.py` 的混淆样本。

### RAG
- 评测口径：`eval_rag.py` 用 golden set 100 条（`app/rag/eval/golden_set.py`），文档级去重 + 关键词子串匹配 + 每相关条目限一次命中（防 recall>1 假指标）。
- **golden qrels 必须与语料同步**：新增语料文档后，相关文档标注（relevant_docs）要同步扩充，否则指标不可比（历史教训：21→52 篇时 Recall 0.86→0.50 是 qrels 变密的数学结果，不是能力下降——报告时讲清口径）。
- 语料文件：`backend/data/kb/{institution,regulation,templates}/*.txt`；新增语料要重新 `ingest_kb.py` 并复测。
- RAGAS 评测：`uv sync --extra eval` 后 `uv run --extra eval python scripts/eval_ragas.py --cases 10`（LLM-as-judge，消耗真实 token，不要在 CI 默认跑）。

### 后端 / API
- 统一响应结构：成功 `{code:0, data:...}`，错误走统一异常处理（`app/utils/` 或 main.py 注册），新路由必须遵循。
- 鉴权中间件默认开启（`AUTH_MIDDLEWARE_ENABLED`），白名单路径在中间件内维护；新公开接口要加白名单。
- Redis：缓存与分布式锁在 `app/core/redis.py`；限流开关 `RATE_LIMIT_ENABLED`（默认关）。
- 文档解析链：`services/document_parse.py` 按配置有序回退（pdfplumber→PyMuPDF→pypdf→docx→LibreOffice→OCR→DeepSeek OCR→Docling/MinerU）；新增引擎在该文件注册。

### 前端
- Vue3 `<script setup>` + TS；API 封装在 `src/api/`；SSE 消费在 chats/reviews 视图（事件名与后端 §4 协议一致）。
- 组件库 Element Plus；图表 ECharts；状态 Pinia。
- `npm run build` 必须过（vue-tsc 类型检查）。

## 7. 已知陷阱（先看，省时间）

| 陷阱 | 说明 |
|---|---|
| `uv sync` 清依赖 | 任何手动 pip 装的包会被移除；全部依赖必须进 pyproject/uv.lock |
| 测试无 key 崩溃 | `LLMClient()` / `AsyncOpenAI()` 在无 key 环境抛 Missing credentials；测试必须走 conftest mock 或 fake_openai fixture |
| 工具循环返回 tool 消息 | 迭代耗尽后模型可能把 tool 消息当答案；executor 已追加收敛消息，改动 executor 别删 |
| usage 与 content 同 chunk | SSE 解析用独立 `if` 而非 `elif`（部分供应商同 chunk 带 usage 和 delta） |
| rerank index 错位 | rerank 结果按候选下标映射排序，不要用对象 id 查询 |
| redislite 存活 | 嵌入式 Redis 是前台进程，后台跑要 keep-alive；挂了后端限流/缓存静默失效 |
| qdrant 端口 | 本地 Qdrant 挂了检索返回空；改动 RAG 前先 `curl localhost:6333/collections` |

## 8. 提交前检查清单

- [ ] `git diff` 无真实 key / 密钥
- [ ] `make lint && make test` 全过（无 key 环境验证过）
- [ ] 涉及前端：`make frontend-build`
- [ ] 涉及语料/评测口径：`check_golden.py` 过；指标变化已记录 docs/rag-eval.md
- [ ] 涉及依赖：`uv.lock` 已更新并提交
- [ ] commit 消息：英文 Conventional Commits
- [ ] 推送后 CI 全绿（lint/test/frontend-build/docker-build/rag-eval）

## 9. 文档导航

| 文档 | 内容 |
|---|---|
| `README.md` | 项目介绍、架构图、快速开始、技术栈、目录结构 |
| `docs/DESIGN.md` | 详细设计：架构、Agent 状态机、RAG 链路、数据库 E-R、Docker、CI |
| `docs/QUICKSTART.md` | 启动 / 测试 / 压测 / 故障排查 |
| `docs/benchmark.md` | 压测报告（TTFT / 完整时长 / TPOT，真实 LLM 实测） |
| `docs/rag-eval.md` | RAG 检索指标（Recall/MRR/NDCG/Hit）+ RAGAS 生成质量 + 评测方法论 |
| `docs/resume.md` | 简历项目文案与面试话术（改代码不必动） |
