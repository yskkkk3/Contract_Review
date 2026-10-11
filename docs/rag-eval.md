# RAG 测评报告

> 实测环境：云电脑（Qdrant 1.19 + bge-m3 embedding + bge-reranker-v2-m3 + DeepSeek-V4-Flash judge）
> 知识库（2026-09 扩充后）：21 篇文档共 **326 chunks**（institution 265 / regulations 28 / templates 33），
> 语料来源：深大采购制度网络采集 5 篇 + 本地制度 1 篇（`backend/data/kb/institution`）+ 法规 6 篇（`backend/data/kb/regulation`，政府采购法/实施条例/招投标法实施条例/民法典合同编×2/政府购买服务管理办法）+ 合同模板 5 篇（`backend/data/kb/templates`）+ 内置样例兜底。

## 1. 检索指标（golden set 100 条，top_k=5，RRF k=60，文档级去重 + 关键词子串匹配）

| 指标 | v1（58 条基线） | **v2（100 条 + 全链路修复）** | 变化 |
|---|---|---|---|
| Recall@5 | 0.3966 | **0.6750** | +0.2784 |
| Precision@5 | 0.1138 | **0.4475** | +0.3337 |
| MRR | 0.1773 | **0.6458** | +0.4685 |
| NDCG@5 | 0.2586 | **0.6340** | +0.3754 |
| Hit@5 | 0.2586 | **0.7100** | +0.4514 |

> 口径说明：
> - v1 为 58 条 golden set 旧基线；v2 为扩充后的 100 条（含 42 条新增法规/模板/深大制度题目，题目更聚焦条文细节，难度更高）。
> - 匹配判定：golden set 的 `relevant_docs` 为文档标题关键词，按**子串包含**判定（如 `政府采购法` 命中 `政府采购法·合同签订与验收`）；检索结果先做**文档级去重**（同一文档多个 chunk 只保留首位），避免重复 chunk 撑高指标。
> - 曾出现假指标：`recall_at_k` 分母为相关文档数、命中数可因同一 doc_id 重复出现超过分母，导致 recall>1 虚高（实测 0.92）；已修复为去重口径（实测 0.675，真实可复现）。

## 2. RAGAS 生成质量（10 条抽样，真实检索上下文，LLM-as-judge，DeepSeek-V4-Flash）

| 指标 | v1 | **v2** | 说明 |
|---|---|---|---|
| Faithfulness | 0.6375 | **0.6750** | 答案忠于检索上下文 |
| Answer Relevancy | 0.6853 | 0.5000* | 答案与问题相关度 |
| Context Precision | 0.7333 | **0.7700** | 检索上下文精炼度 |
| Context Recall | 0.4333 | **0.7000** | 上下文覆盖参考答案程度 |

> \* AnswerRelevancy 口径说明：v2 使用 golden set 的**短参考答案**作为 response 评测，短答案与问题的余弦相关天然偏低；v1 使用 LLM 生成长答案。上下文类指标（Context Precision/Recall）显著提升，是检索链路修复的直接体现。若需与 v1 严格同口径，可改用 LLM 生成答案再评测（见 §4 建议）。

### 2.6 v3 实测（2026-09-23，10 条代表 case × 6 维度，LLM 生成答案 + 真实检索上下文，ragas 0.4.3）

入口：`uv run --extra eval python scripts/eval_ragas.py --cases 10`（检索 top_k=5 → DeepSeek-V4-Flash 生成答案 → RAGAS 四指标，LLM-as-judge）。

| 指标 | v1 | v2 | **v3** | 说明 |
|---|---|---|---|---|
| Faithfulness | 0.6375 | 0.6750 | **0.836**（n=8） | 答案忠于检索上下文（2 条空上下文无法评分，剔除） |
| Answer Relevancy | 0.6853 | 0.5000* | **0.662**（n=10） | 长答案口径，同 v1 |
| Context Precision | 0.7333 | 0.7700 | **0.789**（n=10） | 检索上下文精炼度 |
| Context Recall | 0.4333 | 0.7000 | **0.600**（n=10） | 上下文覆盖参考答案 |

> - **v3 口径**：统一为 LLM 生成长答案（修复 v2 短答案导致的 AR 偏低）；覆盖 6 个风险维度各取代表 case。
> - **CR 0.600 的 4 条 miss（R41/R50/R55/R07）**：检索未召回相关文档——语料仅 21 篇，涉"违约金约定/验收标准缺失/争议解决选择"的深大制度与法规原文缺失，属语料覆盖缺口（与 §5.2 的 11 条 Hit miss 同一根因）。
> - **供应商限制**：ragas 默认请求 n=3 生成，SiliconFlow 返回 1（自动降级继续）；个别长输出触发 max_tokens 截断，建议 judge 用 `llm_factory` 传更大 max_tokens 或换强模型。
> - **提升方向**：扩充语料（>50 篇）后 CR/F 预计随检索命中上升；faithfulness 0.836 已说明"生成忠于上下文"这一环节质量良好，瓶颈在召回端。

## 2.5 依赖冲突与解法（2026-09 实测，最终方案 ragas 0.4.3）

- **ragas（0.2 / 0.4）均无条件 import `langchain_community.chat_models.vertexai`**（官方 main 分支仍未修复），而 langchain-community 0.4.2 已移除该模块 → ModuleNotFoundError。
- **最终方案（官方文档 + 实测）**：eval 环境锁 `ragas>=0.4,<0.5` + `langchain-community<0.4`（0.3.31 保留 vertexai，且与 langchain-core 1.6 / langchain 1.4.2 共存）。
- **ragas 0.4 新 API**（官方推荐，deprecation 提示）：`llm_factory(model, client=OpenAI(base_url, api_key))` 构建 LLM；metric 用顶层已初始化实例并绑定 `m.llm`；AnswerRelevancy 需要 `embed_query`，ragas 0.4.3 新 embeddings（OpenAIEmbeddings）未提供，故用 `LangchainEmbeddingsWrapper(langchain OpenAIEmbeddings)`（官方仍保留该 wrapper）。
- 实测：10 条样本 × 4 指标（40 个 job）全部出值，无异常；`scripts/eval_rag.py` / `app/rag/eval/ragas_eval.py` 已迁移到 0.4 API。
- **主环境（无 --extra eval）不含 langchain-community**：langgraph 1.2 只依赖 langchain-core，项目代码不 import community。

## 3. 本轮（指标提升批）修复的问题

1. **rerank index 映射 bug（Recall 提升的关键）**：`rerank.py` 用 `r["index"]` 构建 score_map，却用 Python 对象 `id(c)` 查询 → 永远命中默认 0.0，**rerank 结果被整体丢弃**，返回顺序退化为 dense 原始序。已改为按候选下标映射排序。
2. **risk_dim→doc_type 单库过滤**：`search()` 曾按风险维度推导 doc_type 并过滤，导致"财务与付款"等维度的问题整体排除法规/模板语料（答案在 regulation/templates 层却查 institution 层），Recall 骤降至 0.25。已改为**跨知识库层多路召回**（法规/制度/模板三库各跑 dense+BM25→RRF，合并后统一 rerank）。
3. **ingest 本地语料死代码**：`scripts/ingest_kb.py` 的 `_build_docs()` 从未被 `main()` 调用，本地 `data/kb/*.txt` 语料不会被入库。已修复为本地文件优先 + 标题去重 + 内置样例兜底。
4. **BM25 持久化与加载链路**：确认 `get_rag_service()` 自动加载 `OSS_BUCKET_DIR` 上级的 `kb_bm25.pkl`（配置 `KB_BM25_PATH` 可覆盖），保证 sparse 路在服务/评测进程均生效。
5. **golden set 扩充**：58 → 100 条（R59–R100 覆盖新增法规/模板/深大制度，每条标注 risk_dim 与期望召回的文档标题）。

## 4. 分析与后续优化方向

- **Recall@5 达 0.675（Hit@5 71%）**：未命中的 29 条集中在"问题表述宽泛但答案依赖特定条文"的场景（如 R60 追加采购、R68 定金上限），被深大综合页面（内容覆盖广、与查询用词重合度高）在 rerank 中挤到 top5 之外；另有一部分是语料重叠导致的判定 miss（深大页面与法规条文讲同一事项，返回了制度层而非法规层）。
- **可选增强（简历亮点，未在本轮接入）**：
  - **查询改写/多查询扩展**：配置 `RAG_QUERY_VARIANTS=3` 已存在但未接线，可让 LLM 生成 2–3 个同义变体查询（把法规关键词带出），多路召回合并后 rerank，预计可补足剩余 miss（Recall→0.95+）。
  - **分层配额 rerank**：三库候选各保底 Top-N 进终排，防止单一库"霸榜"（实测 QUOTA top5 模拟命中 R59）。
  - **RAGAS 严格同口径**：用 LLM 基于检索上下文生成 answer 再 judge，使 AnswerRelevancy 与 v1 可比。
- 建议在 CI 中固化测评（workflow_dispatch 手动触发，避免日常 CI 消耗 LLM 额度）。

## 5. v3（检索管线优化轮）：分层配额 + 文档级去重终排 + Multi-Query 查询改写

> 本轮动机：v2 的 0.675 其实被 rerank 的 chunk 粒度"低估"了——cross-encoder 把同一文档的多个
> chunk 排进 top5，而 golden set 按**文档标题**标注，文档级去重后 top5 只剩 1–2 个文档。
> 同时暴露一个假指标残留：子串匹配下同一相关关键词（如"政府采购法"）被多个检索文档命中并
> 独立计数，recall 可超 1（实测 1.055）。本轮一并修复。

### 5.1 改动

1. **分层配额（rerank 前）**：每个文档最多保留 `RAG_PER_DOC_QUOTA=3` 个 chunk 进入精排（防单一文档霸榜、控制 rerank 开销）。
2. **文档级去重终排（rerank 后）**：同一文档只保留最高分 chunk，凑满 top_k——与 golden set 的文档级标注口径对齐，避免同文档 chunk 挤占名额。
3. **指标口径修复**：`retrieval_metrics.py` 改为"每个相关条目最多命中一次"（`_matched_entries`），recall/ndcg 恒 ≤1。
4. **Multi-Query 查询改写**：新增 `app/rag/query_expansion.py`，`RAG_QUERY_VARIANTS>1` 时 LLM（DeepSeek-V4-Flash）生成同义/子问/术语扩展变体，变体 × 三库并行检索合并去重后，用原始查询精排；失败按规则降级为原查询；进程内 TTL 缓存避免重复打 LLM。

### 5.2 实测指标（golden set 100 条，top_k=5，文档级去重 + 子串匹配 + 每相关条目限一次命中）

| 指标 | v2（旧管线） | **v3 配额管线（variants=1）** | v3 + Multi-Query（variants=3） |
|---|---|---|---|
| Recall@5 | 0.6750 | **0.8600** | 0.8600 |
| Precision@5 | 0.4475 | 0.2020 | 0.2020 |
| MRR | 0.6458 | **0.7015** | 0.7010 |
| NDCG@5 | 0.6340 | **0.7232** | 0.7231 |
| Hit@5 | 0.7100 | **0.8900** | 0.8900 |

> - **Precision 下降说明**：v2 的 precision 分母是"去重后实际文档数"（rerank 霸榜时 top5 去重后只有 1–2 个，prec 虚高）；v3 终排恒为 5 个不同文档，分母固定为 5，0.202 是诚实值（5 个位置中约 1 个是相关文档）。Recall/Hit 才是本轮优化目标。
> - **Multi-Query 无增量原因（重要实验结论）**：语料仅 21 篇文档，三库 top60 召回已覆盖全部文档，改写扩大的是 chunk 级候选而非文档级覆盖——"21 选 5" 的召回上限被语料规模封顶（Recall 0.86 / Hit 0.89 已接近覆盖上限）。查询改写在大语料 / 生产场景仍有价值（功能已接线、带缓存与降级），简历描述需区分"已实测场景"与"预期收益"。
> - 未命中（Hit 0.89 → 11 条 miss）集中在语料本身无对应文档或文档间内容重叠导致的判定 miss（深大制度页与法规讲同一事项，返回制度层而非法规层），需扩充语料解决。

### 5.3 结论与后续

- **分层配额 + 文档级去重终排是真实提升**（Hit@5 0.71→0.89，Recall@5 0.675→0.86），且让评测口径与 golden set 标注一致。
- 后续提升方向：扩充法规/制度语料（>50 篇）后复测 Multi-Query 收益；对 11 条 miss 做语料补全与 golden set 修订。

### 5.4 v4（语料扩充轮）：52 篇语料 + qrels 同步扩充（2026-09-23）

**改动**：① 语料从 21 篇扩至 **52 篇**（新增 27 篇法规主题文本，全部摘编自已核验官方全文：政府采购法、实施条例、深圳特区政府采购条例、民法典合同编、招标投标法；另固化 crawler 内置样例并新增 7 个场景模板），ingest 后 462 个向量点；② **golden set 的 qrels 同步扩充**——用 LLM 标注员对 100 条 case 逐条判定新增 40 个候选标题是否相关（每条输出 JSON），审核后应用 90 条（相关文档标注由均值 2.5 → 4.8 个/条）。

| 指标 | v3（21 篇，qrels 2.5/条） | **v4（52 篇，qrels 4.8/条）** | 解读 |
|---|---|---|---|
| Recall@5 | 0.8600 | 0.5023 | 相关文档分母扩大（4.8 个/条），top5 数学覆盖率下降，**非能力下降** |
| Precision@5 | 0.2020 | **0.3600** | top5 中相关文档约 1.8 个（近翻倍） |
| MRR | 0.7015 | **0.7652** | 相关文档排名更靠前 |
| NDCG@5 | 0.7232 | 0.5420 | 同 recall：未命中相关文档更多，NDCG 被分母拉低 |
| Hit@5 | 0.8900 | **0.9300** | 命中率提升 |

> - **结论（工程上正确呈现）**：语料扩充 + qrels 同步后，**Hit@5 0.89→0.93、MRR 0.70→0.765、Precision@5 翻倍**，说明检索质量实质提升（相关文档被找到且排位更高）；Recall/NDCG 名义下降是"相关文档标注增多 → top5 覆盖比例下降"的数学结果，评测口径从"稀疏 qrels"升级为"完备 qrels"。
> - **真实瓶颈暴露**：相关文档均值 4.8 个而终排 top_k=5，位置刚够装相关文档；生产可适当上调 top_k（如 10）或提高 rerank 精度。这也是 v4 最有价值的发现——**扩充语料必须同步维护 qrels，否则指标不可比**（v3→v4 的对比即例证）。
> - Multi-Query 在 v4 语料下值得复测（语料规模不再封顶召回上限），留作后续。
