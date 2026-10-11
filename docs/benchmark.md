# 性能压测报告（Locust）

> 实测环境：云电脑（无 Docker，本地 SQLite + fakeredis + Qdrant 1.19 + SiliconFlow 真实 LLM）
> 后端端口 8090；数据：6 账号 × 独立合同/会话；压测时间 2026-09-23

## 1. 场景与配置

| 项 | 值 |
|---|---|
| 工具 | Locust 2.46.6（headless） |
| 常规场景 | 6 并发用户 × 6 分钟（登录/列表/聊天 SSE 混合，权重 2:2:1） |
| 审阅专项 | 2 并发用户 × 8 分钟（仅审阅 SSE） |
| LLM 链路 | 真实 SiliconFlow（DeepSeek-V3.2 审阅 / V4-Flash 聊天） |

## 2. 常规场景指标（6 用户 / 6 分钟）

| 接口 | 请求数 | 成功率 | Avg | P50 | P95 | P99 | Max |
|---|---|---|---|---|---|---|---|
| POST /api/auth/login | 6 | 100% | 305ms | 330ms | 420ms | 420ms | 420ms |
| GET /api/contracts（列表） | 123 | 100% | 41ms | 33ms | 57ms | 230ms | 300ms |
| POST /api/chats（SSE） | 118 | 100% | 120ms | 120ms | 140ms | 220ms | 230ms |

## 3. 审阅 SSE 专项（2 用户 / 8 分钟）

| 指标 | 值 |
|---|---|
| 完成审阅次数 | 4（0 失败） |
| 完整审阅时长 | Avg 205s · Min 158s · Max 251s · Med 250s |
| SSE 首包（TTFT） | **37.1s**（流式改造后；改造前 172.9s） |

## 4. 压测暴露并已修复的问题

1. **SSE 非真流式**：原实现 graph 跑完才一次性输出（TTFT≈173s）。已改造为 LangGraph custom stream 模式：每个专家任务完成即推送 SSE，TTFT 降至 **37.1s**（后续可进一步细粒度化到条款级）。
2. **多账号并发 401**：login 将 access_token 单值写入 Redis，多用户共用账号导致 token 互踢。压测脚本改为每用户独立账号。
3. **Locust SSE API 兼容**：`client.stream()` 在 locust 2.46 已移除，改为 `client.request(..., stream=True)`；`iter_lines()` 返回 bytes 需解码。
4. **审阅并发安全**：`start_review` 会清理同 session 旧任务，压测按用户隔离 session，避免互删。

## 4.5 首 Token 流式工程实测（Phase B，2026-09-23）

> 新增 `/api/metrics` 滑动窗口（200）聚合：TTFT / 总延迟 P50/P95/P99 / TPOT；聊天 done 事件与审阅 end 事件均携带 metrics。

| 链路 | 指标 | 实测（n=6 并发，独立会话） | 目标 | 备注 |
|---|---|---|---|---|
| 聊天 SSE | TTFT | min 980ms · p50 3793ms · p95 8414ms · max 124763ms | P50<300ms | 并发 6 路同时打 SiliconFlow，供应商排队显著（124s 长尾为单个异常样本） |
| 聊天 SSE | total | min 4.8s · p50 9.3s · max 202.7s | — | 同上排队影响 |
| 聊天 SSE | 单路 TTFT | 734.9ms（Phase B 冒烟单样本，无并发） | — | 无并发时接近目标 |
| 审阅 SSE | meta 首字节 | <100ms（graph 前发出） | <100ms | 与 LLM 无关，必达 |
| 审阅 SSE | 完整时长 | 131.7s（3 chunks） | 首风险点 <3s | 专家并行 ReAct + 工具循环（真实 LLM） |

**结论与优化方向（面试可展开）**：单路 TTFT ~735ms 已接近目标；并发后 P50 恶化到 3.8s，主因是**供应商推理队列**而非服务端——已设计但未接线的对策：① `RAG_`/聊天侧应用层并发限流（信号量，防止突发全量打给供应商）；② prompt cache（`llm_prompt_cache` 配置已加，减少 prefill）；③ 输入裁剪（合同原文 8000 字截断，已实现）。真实压测口径应区分"服务端延迟"与"供应商端到端延迟"。

## 5. 说明与局限

- 本环境用 SQLite+fakeredis 替代 MySQL/Redis，读写并发低于生产 Docker（mysql/redis）配置，P99 尾部延迟会略低于真实部署。
- 审阅耗时由 LLM 推理主导（6 专家并行 ReAct），与并发无关；真实部署建议接入缓存与模型蒸馏。
