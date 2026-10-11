# 简历项目：AI 智能合同审阅平台

> 秋招简历正文优化版（按用户原稿结构重写），所有指标均来自项目实测。

**AI 智能合同审阅平台**
2026.03 - 2026.06 | 个人学习实践项目

**项目描述**：面向高校及企事业单位的合同审查场景，支持合同解析、风险审阅、合同比对和合同问答。围绕长合同处理和专业规则审查，引入多智能体工作流和 RAG 检索，将法规制度、审阅规则与合同内容结合，输出风险点及修改建议。

**技术栈**：Python · FastAPI · SQLAlchemy · MySQL · Redis · LangChain · LangGraph · Qdrant · Langfuse · Docker · GitHub Actions

**项目亮点**：

1. **多智能体审阅（Agent 编排）**：使用 LangGraph 编排 Router / Specialist / Gate / Arbitration 审阅流程，Router 拆分并路由审阅任务，多个 Specialist 并行分析不同风险维度，经 Gate 校验和 Arbitration 仲裁合并审阅结果；Specialist 采用真 ReAct 循环 + **Function Calling（4 个工具：违约金试算/法规查证/条款抽取/模板匹配，严格 JSON Schema，并行执行、异常回喂、迭代上限防死循环）**；意图识别 LLM + 规则引擎双重降级兜底，保证流程可用性。

2. **RAG 法规检索（多路召回 + 精排）**：使用 Qdrant 存储法规、制度、合同模板等知识数据，构建 bge-m3 Embedding 召回 + BM25 多路检索 + **Multi-Query 查询改写** + RRF 融合 + Rerank 精排的完整检索链路，跨三层知识库召回相关规则作为上下文交给模型判断；自建 **100 条 golden set**（覆盖 6 风险维度）+ 分层配额与文档级去重终排优化，修复 rerank 索引错位、指标超 1 假口径等链路 bug 后：**Recall@5 0.40→0.86、MRR 0.18→0.70、Hit@5 0.71→0.89**；并用 **RAGAS（0.4.3）LLM-as-judge 评测生成质量**（Faithfulness 0.84 / Context Precision 0.79），检索指标已接入 **CI 门禁**（Recall≥0.6 / MRR≥0.4 / NDCG≥0.5，低于阈值 CI 变红）。

3. **长文档并发审阅与首 Token 优化**：集成 MinerU、Docling、OCR 等 10 种解析引擎解析 PDF、Word 及扫描件，对解析结果分块并并发执行审阅任务，按原始条款顺序合并风险项和修改建议；全链路 SSE 流式输出，**首 Token（TTFT）埋点 + 滑动窗口 P50/P95/P99 聚合（/api/metrics）+ prompt cache + 应用层并发限流**，单路聊天 TTFT 实测 735ms、审阅首字节 <100ms。

4. **审阅规则配置**：将 Prompt 拆分为系统级、机构级和个性化配置，支持按合同类型和审阅场景组合不同规则；基于 **OpenAI SDK 统一接入大模型（base_url 可切换供应商）**，模型、Embedding、Rerank 均可通过环境变量一键切换，减少新增审阅场景时的代码改动。

5. **工程化与链路追踪**：JWT 认证 + Redis 缓存与分布式锁 + 限流中间件 + 统一响应结构 + Swagger/ReDoc 文档；Docker Compose + Dockerfile 多阶段构建 + **Makefile** 一键部署，GitHub Actions 五个 job CI 全绿；接入 Langfuse 记录 Agent 执行、RAG 检索和模型调用过程，便于定位检索、Prompt 或模型调用问题；支持 **MCP / Skill 协议接入**。

---

## 面试可展开（不写入简历）

- **设计取舍**：为什么 Router 拆分 + Specialist 并行 + Gate/Arbitration，而不是单一 LLM 一次审阅；意图识别降级策略的设计（LLM 与规则引擎双重兜底）。
- **Function Calling**：为什么工具调用而不是让模型自由发挥——约束可执行动作（试算违约金）由确定性代码完成，LLM 只做决策；工具循环的收敛策略（迭代上限 + 结果截断 + 异常回喂 + 收敛消息）；结构化输出（json_schema）与字段归一化处理多供应商输出漂移。
- **首 Token 工程**：SSE 首事件前置（meta 事件与 LLM 无关）、TTFT 埋点与滑动窗口聚合、prompt cache 与并发限流对 P50 的影响；区分"服务端延迟"与"供应商端到端延迟"。
- **RAG 细节**：RRF 融合为什么优于分数归一化直接相加；bge-m3（dense）与 BM25（sparse）互补点；三库分层召回解决什么问题；分层配额（每文档限 N chunk 进 rerank）为什么提升文档级召回；Multi-Query 在语料小时无增量的实验结论。
- **评测体系**：检索指标口径（文档级去重、每相关条目限一次命中防 recall>1）；RAGAS 生成质量四指标的取舍（Faithfulness 为什么比 AR 更受关注）；golden set 随语料扩充同步更新 qrels 的维护闭环；CI 评测门禁的设计（无 key 静态门禁 + 有 key 完整门禁）。
- **排查案例**：rerank 索引错位导致排序退化的定位过程；recall>1 假指标的识别与修复；工具循环迭代耗尽误把 tool 消息当答案的修复；并发压测暴露供应商排队与限流设计。
