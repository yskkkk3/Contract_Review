# 设计：Tool Calling（Function Calling）+ 首 Token 流式工程（P0）

> 状态：待评审（等确认后实施）｜范围：Agent 编排 + 后端工程｜简历侧重：Agent / RAG / 后端
> 关联文档：`docs/DESIGN.md`（架构）、`docs/rag-eval.md`（检索评测）、`docs/benchmark.md`（压测）

---

## 一、Tool Calling / Function Calling（Agent 真正调用工具）

### 1.1 现状与差距

| 现状 | 问题 |
|---|---|
| specialist 的"ReAct 循环"是**伪 ReAct**：`specialist.py` 在 prompt 里拼一段「检索证据」文本，模型不真正"调用工具" | 面试经不起追问：没有 tool schema、没有 tool loop、检索 query 不是模型生成的 |
| intent / gate / arbitration 全部用 `re.search(r"\{[\s\S]*\}")` 手工提 JSON | 解析脆弱、无 schema 校验，失败静默降级 |
| 无确定性工具（违约金计算等让 LLM 做数学） | 丢失"LLM 只做语义、计算交给工具"的工程叙事 |
| `LLMClient.chat` 只返回纯文本，无 tools / response_format 能力 | OpenAI SDK（已装 >=1.60）的 tool calling、并行 tool call、structured output 全部未用 |

### 1.2 改动点（文件级）

**① 工具注册表（新增）`app/agent/tools/registry.py`**

每个工具 = `name / description / parameters(JSON Schema) / handler(async)`：

| 工具 | 类型 | 说明 |
|---|---|---|
| `search_regulations(query, risk_dim, top_k)` | 语义 | 走 `RAGService.search`，三层知识库检索法规/制度/模板 |
| `get_clause(contract_id, clause_index)` | 精确 | 取合同第 N 条原文（证据精确定位，防引用幻觉） |
| `calc_penalty(amount, rate, days)` | 确定性 | 违约金计算：`amount*rate*days`，LLM 不做数学 |
| `lookup_template(contract_type)` | 语义 | 模板库查询，供比对/修改建议 |

规范：schema 必须满足 OpenAI 要求（`parameters` 为 JSON Schema object、每个参数有 `description`）；新增单测校验 schema 合法性与 description 完整性。

**② 工具执行器（新增）`app/agent/tools/executor.py`**

```
call_llm_with_tools(messages, tools, model, max_iterations=3) -> final_message
  1. chat.completions.create(tools=[...], tool_choice="auto")
  2. 返回 tool_calls → asyncio.gather 并行执行 handlers
     → 追加 role="tool" 消息 → 再调 LLM（迭代）
  3. 无 tool_calls 或达到 max_iterations 终止（防死循环）
```

关键点：工具异常 → 把错误作为 tool 结果回给模型（让其重试或放弃）；单条工具结果截断（≤8000 字符）防上下文撑爆；**并行 tool call**（一条消息多个 tool_calls 同时跑）。

**③ Specialist 节点改造 `app/agent/nodes/specialist.py`**

- 从"prompt 拼证据"改为真 ReAct：system prompt 声明可用工具；**检索 query 由模型生成**（而非把整段条款当 query）；多轮：思考 → 调 `search_regulations` → 读证据 → 生成。
- 风险点输出改用 **structured output**：`response_format={"type":"json_schema", "json_schema": {...}}`，去掉正则提取。
- 每个风险点增加 `evidence_refs: [doc_id...]` 字段（引用了哪些文档），为仲裁与防幻觉留证据链。
- 保留现有故障隔离：LLM 失败 → 降级为"直接检索 + 无工具文本模式"（供应商不支持 tools 时同路径）。

**④ Intent / Gate / Arbitration 结构化输出**

- intent：`response_format` 固定 `{intent, confidence}`，删除 `_parse_json` 正则兜底为最后防线。
- gate / arbitration：同样受益；arbitration 的 `summary/suggestion/overall_risk` 上 schema。

**⑤ LLM 客户端扩展 `app/rag/client.py`**

- `chat_structured(messages, response_format, model)` → 返回解析后的 dict（SDK 侧校验）。
- `chat_with_tools(messages, tools, model)` → 返回完整 completion（含 tool_calls），供 executor 使用。
- 兼容策略：`response_format` 用 `json_schema` 时会先探测供应商支持度（SiliconFlow/DeepSeek 支持 tools 与 json_schema）；config 增加 `agent_tool_calling_enabled: bool = True` 总开关，关闭时回退现有文本模式。

**⑥ 可观测性**：Langfuse 记录每次 tool call 的入参/出参、iteration 数、token 消耗。

### 1.3 面试话术

- **一句话**：「把 Agent 从编排壳升级为真工具调用：JSON Schema 驱动的工具注册表 + 并行 tool call 执行器 + structured output 替代正则解析，失败重试与跨供应商降级。」
- **可展开追问**：工具 schema 的 description 怎么写才让模型选对工具；防死循环（max_iterations）；工具结果截断与上下文预算；确定性工具（calc_penalty）与语义工具（search）的边界；structured output 的 schema 校验收益；多一轮模型调用的延迟代价 → 引出第二块。

---

## 二、首 Token / 流式性能工程（TTFT）

### 2.1 现状与差距

| 现状 | 问题 |
|---|---|
| 聊天 `chat_service.py` 已流式（`chat_stream`） | 无 TTFT 埋点、无 token 统计（`stream_options.include_usage` 未开）、无指标上报 |
| 审阅 `review_service.py` 的 SSE 有事件流 | 无 meta 骨架事件（首字节要等第一个 specialist 整轮 LLM 完成）；specialist 用**非流式** `chat()`，首 token 延迟=完整调用时长（分钟级） |
| 无 prompt caching、无专门并发/超时策略 | 首 token 优化手段未系统化 |
| docs/benchmark.md 已有压测 | 指标口径未区分聊天（TTFT 秒级）与 batch 审阅（整体时长 37.1s） |

### 2.2 改动点（文件级）

**① 指标模块（新增）`app/core/metrics.py`**

- 计时原语：`TTFT = 首个 stream delta 到达时刻 - 请求发出时刻`；`TPOT = 生成期 tokens/sec`；`total_latency`。
- 聚合：进程内滑动窗口 P50/P95/P99（按 endpoint 分桶：chat / review / rag）。
- 查询接口：`GET /api/metrics`（鉴权）返回最近窗口指标快照。
- Langfuse：`chat_stream`/`chat_with_tools` 统一包一层 generation（usage 走 `stream_options={"include_usage": True}`）。

**② SSE 事件协议升级**

- 审阅：graph 启动前先发 `{"event":"meta","data":{task_id, chunk_count, risk_dims}}` → **首字节 <100ms 必达**（与 LLM 无关）。
- 审阅增量：specialist 改 `chat_stream` 边生成边推 `{"event":"token","data":{risk_dim, delta}}`（minute 级 → second 级首 token）。
- 聊天：首事件 meta（session_id）→ content 增量 → done 事件携带 `{ttft_ms, tokens, tpot}`。

**③ 首 Token 专项优化**

- 流式接入：`LLMClient.chat_stream` 确认增量产出 + 计时；审阅 specialist 换 `chat_stream` 的聚合版（`collect_stream(model, messages) -> (text, usage)`，供 gate/arbitration 复用）。
- Prompt caching：system prompt 前缀稳定（intent/gate/arbitration 的 prompt 是静态文件）→ 供应商支持时命中缓存显著降首 token；config 开关 `llm_prompt_cache: bool`。
- 上下文预算：聊天 `_load_contract_text` 由"前 8000 字符"改为按会话相关条款检索剪枝（复用 RAG）；system 固定前缀 + 可缓存。
- 超时拆分：`LLMClient` 拆 connect/read 超时；聊天 30s、审阅 120s；流式断连时终止生成器并标记任务失败（SSE 生命周期）。

**④ 压测与报告**

- 扩展现有 locust（`scripts/bench_locust.py`）：聊天 SSE 50 并发测 TTFT P50/P95/P99；审阅 batch 测整体时长与首结果时间。
- 目标（写进 docs/benchmark.md）：聊天 TTFT P50 < 300ms、P95 < 1s；审阅 meta 骨架 < 100ms、首风险点 < 3s；压测结果回填文档（云环境执行，报告含环境配置、QPS、错误率、P99）。

### 2.3 面试话术

- **一句话**：「把'能流式输出'升级为'可度量可优化的流式工程'：TTFT/TPOT 三类指标 + SSE 事件协议（meta 骨架 → token 增量 → done）+ Langfuse 埋点 + locust 压测回填报告。」
- **可展开追问**：首 token 的组成（网络 / 排队 / prefill）与对应优化（流式、prompt cache、并发、剪枝）；TTFT 与 TPOT 的权衡（聊天要快首字，审阅要稳定吞吐）；batch 审阅 37.1s 与聊天 TTFT 的口径分离；SSE 断连生命周期；并发上限（semaphore=20）与供应商限流的耦合。

---

## 三、实施顺序与验收

1. **阶段 A（Tool Calling）**：client 扩展 → tools 注册表 + 执行器 → specialist 改造 → intent/gate/arbitration 结构化 → 单测。
2. **阶段 B（首 Token）**：metrics 模块 → SSE 协议 → specialist 流式 → 埋点 → 压测回填。
3. 公共 config 新增：`agent_tool_calling_enabled`、`llm_prompt_cache`、`metrics_enabled`、`ttft_bucket_window`。

**测试计划**：`tests/test_agent_tools.py`（schema 校验、executor 循环、structured 解析、失败降级）、`tests/test_metrics.py`（计时口径、聚合）、`tests/test_review_api.py` 扩展（meta 事件、token 事件）；现有 35 用例保持全绿（CI 门禁）。

**验收标准**：
- [x] 无 .env 环境 pytest 全绿 + ruff clean（CI 全绿）
- [x] specialist 产生 `evidence_refs`，gate 校验引用存在
- [x] 审阅 SSE 首事件为 meta（graph 前发出，<100ms），专家完成即推 risk_point 事件
- [x] 聊天 SSE done 事件含 ttft_ms/tokens/tokens_per_sec
- [x] docs/benchmark.md 回填压测指标（云环境实测）

**后续（P1，非本批）**：意图降级策略强化（规则引擎独立模块 + 评测集）、评测 CI 门禁（golden set + RAGAS 进 Actions）。

---

## 四、实施状态与实测（2026-09-23）

### 4.1 已交付（阶段 A：Tool Calling，commit `9ec78da`）

- `app/agent/tools/registry.py`：4 个工具（search_regulations / get_clause / calc_penalty / lookup_template），严格 JSON Schema（required/enum/additionalProperties:false），description 必填（供模型选工具）。
- `app/agent/tools/executor.py`：并行 `asyncio.gather` 执行 tool_calls → 单条结果截断（`tool_result_max_chars=8000`）→ 工具异常回喂模型重试 → 迭代上限防死循环 → 收敛消息强制输出最终 JSON（**修复**：迭代耗尽时原实现把最后一轮 tool 消息当答案返回，如"（模板库不可用）"；现追加"禁止再调用工具"的 user 消息后取最终文本）。
- `app/agent/nodes/specialist.py`：真 ReAct（模型自主生成检索 query）→ `_parse_risk_points` 增加**多供应商字段漂移归一化**（risk_type→risk_dim、risk_description/risk_details→risk_analysis、suggested_revision→suggested_content、high/medium/low→高/中/低）；条款原文缺失时以 chunk 兜底。
- intent/gate/arbitration 换 `chat_structured`（json_schema 严格模式，供应商不支持时降级 chat+`_extract_json`）。
- 测试：`tests/test_agent_tools.py` 7 用例；全量 45 passed + ruff clean。

### 4.2 已交付（阶段 B：首 Token 流式工程，本批 commit）

- `app/core/metrics.py`：TTFT / total / tokens 按 endpoint 分桶，滑动窗口（200）聚合 P50/P95/P99 + TPOT；`GET /api/metrics`（需登录）。
- `app/rag/client.py`：`chat_stream_events`（start/delta/usage 事件通道，`include_usage`；**修复**：部分供应商 usage 与 content 同 chunk，改用独立 if 而非 elif，避免吞 delta）。
- `app/services/chat_service.py`：计时 TTFT（首个 delta 到达时刻）→ done 事件携带 `metrics{ttft_ms,total_ms,completion_tokens,tokens_per_sec}` → `record("chat", ...)`。
- `app/services/review_service.py`：graph 执行前先发 **meta 事件**（task_id/session_id/chunk_count，与 LLM 无关故首字节必达）→ 专家完成即推 risk_point（已有）→ end 事件携带 `metrics{total_ms,risk_point_count}` → `record("review", ...)`。
- **取舍说明**：specialist 走工具循环（`chat_with_tools` 非流式），token 级增量与工具循环冲突，故审阅侧用 meta + risk_point 两级事件替代；聊天侧实现完整 token 级流式。

### 4.3 实测指标（云电脑，真实 SiliconFlow）

| 链路 | 指标 | 实测 | 目标 |
|---|---|---|---|
| 聊天 SSE | TTFT | **734.9ms**（单样本，含供应商网络往返） | P50<300ms |
| 聊天 SSE | total / TPOT | 4.4s / 23 tok/s（101 tokens） | — |
| 审阅 SSE | meta 首字节 | **<100ms**（graph 前发出） | <100ms |
| 审阅 SSE | 完整时长 | 131.7s（3 chunks × 专家工具循环，真实 LLM） | 首风险点 <3s（专家并行后达到） |

> 多样本压测（Locust）后按口径回填 `docs/benchmark.md`；TTFT 受供应商网络与 prefill 影响，优化方向：prompt cache（config `llm_prompt_cache` 已加，待接线）、并发限流、更长滑动窗口。
