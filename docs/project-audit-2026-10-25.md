# 项目排查报告（2026-10-25）

本次检查覆盖后端 API、鉴权、数据归属、审阅编排、聊天上下文、RAG、管理配置、前端事件流、Docker 和 CI。没有修改业务代码、现有报告、`.env` 或用户数据；保留了检查开始前已有的 `backend/run_dev.py` 修改。

结论：现有检查全部通过，但存在可复现的匿名改密、匿名管理操作、合同泄露、跨用户访问、文件删除与数据库状态不一致、比对漏检，以及审阅被意图识别短路的问题。当前不宜直接作为多用户生产系统对外开放。

优先级：P0 = 立即修复的账户安全问题；P1 = 上线前修复的数据安全/核心结果错误；P2 = 功能完整性、稳定性或部署质量问题。标记“复现”的项目使用本机隔离数据验证；标记“静态确认”的项目有明确代码路径，但没有对真实线上服务执行操作。

## 验证范围与结果

| 检查 | 结果 |
| --- | --- |
| 后端 ruff：`ruff check app/ tests/ scripts/` | 通过 |
| 后端 pytest：内存 SQLite，清空推理 API key 环境变量 | 241 passed，26.29 秒；104 条依赖/配置警告 |
| 前端类型检查与生产构建：`npm run build` | 通过；存在大 JS chunk 警告 |
| 前端测试：`npm test` | 31 passed |
| 前端 lint：`npm run lint` | 通过 |
| 知识库静态门禁：`scripts/check_golden.py` | 通过：120 条 golden，35 条关键用例 |
| 隔离漏洞复现 | 内存数据库 + 临时 DOCX/文本 + TestClient；结果见下文 |
| Docker 构建、Compose 启动、真实 LLM / RAG 指标评测 | 未运行；当前环境没有发现 Docker 命令，未消耗真实模型 token |

沙箱内 Windows asyncio 初始化卡在 `socket._fallback_socketpair → accept`；允许本机通信后测试正常通过。这是本次执行环境限制，没有将它列为项目缺陷。初次挂起的检查进程已停止。

本地生效设置仅提取开关和凭据是否配置，没有输出密钥：鉴权开关开；限流关；MCP 关；工具调用开；专家证据审计开；RAG 证据精排开；Multi-Query 为 3；存储为 OSS；云 OCR 已列入解析引擎；独立 embedding/rerank 配置存在；BM25 文件存在；JWT 未使用默认值；Langfuse 凭据未配置。文件存在和开关开启不等于外部服务已连通。

## 需要优先修复的问题

### A01 · P0 · 匿名用户可修改任意账户密码和禁用账户【复现】

位置：`backend/app/api/users.py:40`、`:56`；`backend/app/middlewares/auth.py:13`。

`PUT /api/users/{user_id}`、禁用接口和用户列表没有 `get_current_user`，中间件又将整个 `/api/users` 前缀放入白名单。复现：不带 Authorization 修改另一账户密码，返回 200。攻击者能接管已知 ID 的账户；用户列表还提供可枚举的 ID。

建议：仅注册接口允许匿名；查询、改密、禁用分别实施本人或管理员校验；敏感账户操作撤销已有会话。前端管理员路由守卫不能代替后端权限。

### A02 · P1 · 管理接口可被匿名读写【复现】

位置：`backend/app/api/admin.py:81`、`:124`；`backend/app/middlewares/auth.py:32`。

合同类型、提示词、模型配置的管理路由均没有后端身份和角色依赖。中间件遇到没有 Bearer 的请求直接放行。复现：匿名 `POST /api/prompts` 返回 200。即使前端隐藏管理菜单，直接 HTTP 请求仍可操作。

建议：为管理写操作统一增加管理员依赖；按业务需要单独保留合同类型公开读取。中间件白名单按路径和方法精确匹配，并核查所有未声明鉴权依赖的路由。

### A03 · P1 · 合同下载完全缺少身份和归属校验【复现】

位置：`backend/app/api/contracts.py:119`。

下载接口仅按连续递增的 `file_id` 查记录，不验证当前用户。复现：匿名下载另一账户合同返回 200。使用 OSS 时也会为同样的匿名请求签发下载跳转 URL。

建议：校验登录及文件所有者/授权关系后再返回文件或签名链接；同步将前端下载改为携带身份的请求。

### A04 · P1 · 多个接口缺少对象归属校验，可串读和改写他人合同【复现/静态确认】

位置：`backend/app/api/sessions.py:24`、`backend/app/api/comparisons.py:96`、`backend/app/api/reviews.py:29`、`:51`。

创建会话只检查合同存在；合同比对只检查两份文件存在及格式；合同/风险点采纳只检查目标记录存在，没有验证记录属于当前用户。复现：用户 B 关联用户 A 的合同、比对 A 的文件、采纳 A 的合同，均返回 200。

这还构成间接读取链：B 建立自己的会话并关联 A 的文件后，聊天和审阅服务只校验会话属于 B，随后读取 A 的文本。风险点采纳的跨用户写入路径由代码静态确认。

建议：统一封装按所有者查询资源；入口及服务层均检查合同归属；确认 session_type 与具体操作一致；增加两个不同用户之间的负向用例。

### A05 · P1 · 删除被引用的合同会先丢文件，再因外键约束失败【复现】

位置：`backend/app/api/contracts.py:140`；`backend/app/api/sessions.py:84`；`backend/app/models/session_message.py`、`models/review.py`、`models/comparison.py`。

合同删除先删除原始文件/解析文本，再删除数据库记录。数据库外键没有级联策略；合同被会话/任务引用时，MySQL 会拒绝数据库删除。使用隔离 SQLite 开启 `PRAGMA foreign_keys=ON` 后复现：抛 `IntegrityError`，原始文件已经不存在。

会话删除也未处理 messages/review/comparison 子记录，在启用外键的数据库上存在同类约束失败。默认测试 SQLite 未启用外键，因此遗漏了这类部署差异。

建议：先确定引用对象的业务删除策略，完成数据库事务后再可靠清理文件，或使用软删除和可重试清理队列；增加启用外键的测试。不要简单对现有用户数据执行批量级联删除。

### A06 · P1 · 审阅并发锁获取过晚，失败请求仍会删除已有结果【复现】

位置：`backend/app/services/review_service.py:70`、`:116`。

清理旧任务、删除结果、创建新任务均发生在获取锁之前；锁只在 SSE 生成器内获取。复现：仅调用响应准备函数、不消费任何 SSE，即已将旧结果从 1 条变为 0 条。第二请求即使最终抢锁失败，也可能先删除第一请求的任务/结果，并留下新的 processing 任务。

建议：在任何持久化变更之前获取锁；用独立审阅版本保存新结果，成功后切换当前版本；失败或取消时保留上次有效结果；长任务需要锁续租或明确的总时限。

### A07 · P1 · 审阅备注可使整个审阅流程跳过，却返回“完成、低风险”【复现】

位置：`backend/app/agent/nodes/intent.py`、`backend/app/agent/graph.py`、`backend/app/agent/nodes/arbitration.py`。

专用审阅入口仍根据用户的说明重新识别意图。非 review 会直接跳过 router/specialists/gate；仲裁看到空风险、空 errors 就会给出 completed 和低风险。

使用假模型令结构化识别失败，再输入说明“重点关注付款期限”，规则分类返回 `chat`，仲裁返回 `review_status=completed`、`overall_risk=低`。本次复现没有调用真实 LLM。

建议：专用审阅接口强制保持 review，备注仅用于审阅重点；真正不能执行审阅时明确返回 incomplete/错误，不能将“没执行”计为“未发现风险”。

### A08 · P1 · 审阅超时配置未使用，断流后任务状态可能永久 processing【静态确认】

位置：`backend/app/core/config.py:153`、`backend/app/services/review_service.py:132`、`:211`。

`review_stream_timeout` 只在配置中声明，未被执行链读取；审阅 SSE 没有聊天流已有的心跳和超时机制。图执行可多次等待模型/检索，首个 meta 后的长空窗可能超过 Nginx 300 秒读超时。取消异常不由 `except Exception` 处理，任务状态没有专门取消收尾，启动后读取文件失败也发生在生成器异常处理之前。

建议：明确审阅总时限、节点时限、心跳和取消语义；取消/失败统一写入终态；异常时 rollback 后再记录状态；为超时和断开连接添加回归覆盖。

### A09 · P1 · DOCX 比对忽略表格，采购清单和价款变更会漏检【复现】

位置：`backend/app/api/comparisons.py` 的 `_docx_paragraphs`。

比对只遍历 `doc.paragraphs`，没有读取表格。两份仅有一张表格且单元格内容不同的 DOCX，结果为 `standard_paragraphs=0`、`comparison_paragraphs=0`、`difference_count=0`。

建议：按文档顺序同时抽取段落和表格单元格，保留位置；增加单元格修改、行增删、表格前后段落的用例。该问题比纯 UI 显示缺陷更严重，因为会形成无差异的误判。

## 已实现但未接入、未生效或只接入一部分

### A10 · P2 · 管理后台保存的模型与提示词没有参与实际推理【静态确认】

位置：`backend/app/api/admin.py`、`backend/app/agent/prompts.py`、`backend/app/rag/client.py`。

全仓库搜索 `Prompt`/`ModelConfig`，运行时只有管理 CRUD 引用这些模型，没有推理侧读取。提示词实际取磁盘 Markdown，模型实际取 Settings；后台修改默认模型、提示词内容、启停状态均不会改变模型调用。

建议：实现经过校验的运行时配置解析、层级优先级与缓存失效，或将后台明确标记为配置草稿，避免用户误以为保存即生效。

### A11 · P2 · Langfuse 没有埋点，SDK 参数也不兼容【静态确认 + 本地 SDK 检查】

位置：`backend/app/core/langfuse.py:12`；`backend/uv.lock` 中 Langfuse 4.15.4；`deploy/docker-compose.yml`。

`get_langfuse` 没有业务调用方，审阅/聊天/检索没有 trace 或 generation 写入。当前本地 Langfuse 构造签名不含代码传入的 `enabled` 参数；构造异常还会被静默吞掉而返回 None。Compose 使用 Langfuse 服务端 2，进一步存在版本适配需要核查。

本地凭据也未配置。因此仅启动容器或补充密钥，都不足以获得链路追踪。建议先选择并验证 SDK/服务端兼容组合，再接入真实调用和 shutdown flush，初始化失败应有可观察日志。

### A12 · P2 · MCP 外部工具客户端未接入；服务端传输和生命周期不完整【静态确认/部分运行时检查】

位置：`backend/app/mcp/client.py`、`backend/app/mcp/server.py:62`、`backend/app/main.py:83`。

没有业务代码调用 `mcp_client_manager.connect_all` 或 `call_tool`，Agent 工具注册表也未动态加载外部 MCP 工具。打开 MCP_ENABLED 只能触发服务端挂载，不能让 Agent 使用外部服务。

服务端注释描述 SSE `/api/mcp/sse`，实际返回 Streamable HTTP app。本地构建出的子应用路由为 `/mcp`，叠加父挂载后是 `/api/mcp/mcp`；未见父应用 lifespan 启动 MCP session manager。需在修复生命周期后做真实客户端握手验收；本次未声称已完成握手验证。客户端缓存的是异步上下文管理器实例，重复进入同一实例也存在复用问题。

MCP 当前关闭可以是合理选择；它不是“改一个开关就可用”的完整功能。

### A13 · P1 · RAG 指标 CI 门禁的启用条件与新供应商配置不匹配【静态确认】

位置：`.github/workflows/ci.yml:104`；`backend/app/core/config.py:47`、`:176`。

门禁条件读取 `env.SILICONFLOW_API_KEY`，但 secret 只定义在该 step 自身的 env 中，应将判定使用的环境值提升到 job 级或单独输出是否配置。后续 Skip notice 步骤同样看不到前一步的局部 env，不能可靠判断是否真的配置了 secret。

即使修正条件，CI 仍只传旧 SiliconFlow key，而新默认推理地址已经是 DeepSeek，embedding/rerank 缺独立地址时也会回退到该地址。本地用不含凭据的 Settings 探针确认：仅提供旧配置名时，effective_llm_base_url 仍是 DeepSeek。旧 key 兼容链和当前 CI 的完整评测部署不再一致。

建议：显式配置 CI 的推理/embedding/rerank 三类地址、模型和凭据，明确 legacy 优先级；验证有 secret 时确实执行指标门禁，无 secret 时只执行静态门禁。

### A14 · P2 · 限流未启用，现有实现也不适合作为可靠并发限流【静态确认】

位置：`backend/app/core/config.py:125`、`backend/app/middlewares/ratelimit.py`、`frontend/nginx.conf`。

本地有效配置和默认值均关闭限流。启用后计数使用 GET → 加一 → SET，非原子操作，并发请求会丢计数；实现为固定分钟窗口，注释所称滑动窗口不准确。代码只用 request.client.host，没有用户维度；当前 Uvicorn 只默认信任受信任来源的转发头，需验证 Docker 代理 IP 是否受信，否则可能把 Nginx 后所有用户合并为同一 IP。

登录锁按用户标识限制短窗口并发，不等价于防密码尝试或模型成本限流。建议使用原子 Redis 计数/Lua、分接口预算，并先配置可信代理再启用。

### A15 · P2 · Docker 默认解析链声明了 OCR/.doc 支持，但镜像没有系统依赖【静态确认】

位置：`backend/Dockerfile`、`backend/app/services/document_parse.py`。

镜像安装 Python 包，但没有安装 LibreOffice、Poppler、Tesseract 和中文字库。旧 `.doc` 依赖 LibreOffice；扫描 PDF 的本地 OCR 依赖后两项。默认引擎列表包含这些引擎，却会因二进制缺失而跳过/失败。cloud_ocr 默认也不启用；本地 `.env` 已启用它，不能据此推断默认 Docker 部署支持 OCR。

建议：明确轻量镜像和完整解析镜像的能力边界；启动时探测可用引擎；验证中文扫描件和 `.doc`。云 OCR 还限制前 N 页，不能把截取结果当完整合同。

## 其他实际缺陷与稳定性风险

### A16 · P2 · 合同聊天只读取前 8000 字，没有接知识库检索【静态确认】

位置：`backend/app/services/contract_context.py:30`、`:45`；`backend/app/services/chat_service.py`。

聊天缓存直接截断 `[:8000]`，后续条款不会进入上下文；聊天调用链没有 RAG 搜索。长合同尾部条款问答及法规依据问答的能力因此有限，不能认为审阅链有 RAG 就代表聊天也有。

建议：按问题检索合同全文片段，并在需要制度依据时调用法规 RAG；上下文缺失时给出明确提示。无须无条件把全文塞进模型。

### A17 · P2 · 前端退出没有撤销服务端会话，refresh 功能未接入【静态确认】

位置：`frontend/src/stores/auth.ts:65`、`frontend/src/api/auth.ts`、`frontend/src/views/Layout.vue:44`；`backend/app/api/auth.py`。

前端退出仅清 localStorage，没有调用后端 `/auth/logout`；已复制的 token 仍可能继续请求并滑动续期。登录返回 refresh_token，但前端没有保存和调用刷新接口；闲置超过 access token 有效期后只能重新登录。

建议：显式退出先撤销服务端会话，再清本地状态；区分用户退出和 401 本地清理；若要提供长期登录，再设计安全的 refresh 存储和并发刷新流程。

### A18 · P2 · 审阅证据与最终摘要没有完整持久化【静态确认】

位置：`backend/app/services/review_service.py:155`、`backend/app/models/review.py`、`backend/app/api/sessions.py:125`。

Agent 产出 `evidence_refs`，但 ReviewResult 表/写入及历史响应没有保存引用；summary、suggestion、review_status 只通过 end 事件传送。任务始终写 completed，无法从历史区分“执行完成但审阅 incomplete”与完整核验。刷新后不能恢复完整结论和依据。

建议：持久化最终摘要、审阅完整性、来源标识/条文定位及必要诊断，区分运行终态与结论完整性；用迁移升级现有库。

### A19 · P2 · Nginx 合同上传仍受默认 1 MB 限制【静态确认】

位置：`frontend/nginx.conf:12`、`:19`。

仅头像 location 配置了 6m；合同上传位于通用 `/api/`，server/http 未设置上传大小，会受 Nginx 默认请求体上限影响。较大合同经部署前端可能 413，但直连后端成功；后端保存流也没有合同专用大小上限。

建议：设置一致的合同上传大小、页数和解析预算；前端展示限制；后端流式计数拒绝超限文件。不要仅无限放大 Nginx 上限。

### A20 · P2 · async 路由内执行同步解析/存储/数据库操作，阻塞事件循环【静态确认】

位置：`backend/app/api/contracts.py`、`backend/app/api/comparisons.py`、`backend/app/services/document_parse.py`、`backend/app/core/storage.py`。

上传直接在 async 路由执行文档解析、同步 OSS 请求；比对执行 python-docx 和 SequenceMatcher；`.doc` 转换可能同步等 120 秒；本地 OCR 可逐页运行。会阻塞同 worker 的 SSE/其他请求。聊天已有部分 to_thread 处理，但其他核心入口没有。

建议：阻塞 I/O/解析移入线程或受控工作队列，重 CPU 任务考虑进程；避免跨线程并发共享同一 SQLAlchemy Session。用上传/解析和聊天同时进行的压测验证。

### A21 · P2 · Qdrant 故障会阻断 BM25 降级，即使本地索引存在【静态确认】

位置：`backend/app/rag/retrievers/hybrid.py`、`backend/app/rag/service.py`。

先 await query_points 成功后才执行 BM25；任一集合失败还会让上层 gather 抛异常。不能把当前混合检索理解为 dense 故障自动退 sparse。BM25 缺失时又直接创建空索引，缺少启动能力告警。

建议：分别处理两路失败，显式记录降级与证据缺口；对于不能提供完整依据的审阅保持 incomplete；增加 dense/sparse 单路故障测试。

### A22 · P2 · 看板部分统计口径错误，且可匿名读取【静态确认】

位置：`backend/app/api/dashboard.py`。

total_reviewed_amount 汇总所有上传合同金额，不限定已审阅合同；departments 将全部会话计为 comparison，review/verification 恒为 0；service_departments 固定为 1，served_faculty_students 直接复用账户数。全部接口没有用户/管理员依赖，配合当前中间件可匿名读取。

建议：按真实任务类型和终态统计；明确用户看板与全局管理员看板的可见范围；尚无组织数据时显示未接入，而非伪造部门指标。

### A23 · P2 · 默认双 worker 下性能指标不共享，并发预算也按进程翻倍【静态确认】

位置：`backend/Dockerfile:24`、`backend/app/core/metrics.py`、`backend/app/rag/client.py`。

生产启动两个 worker，但指标保存在进程内 `_buckets`；多次查询可能命中不同窗口，不能视为全系统 P95。LLM Semaphore 同样每进程独立，配置 4 实际部署总上限可能是 8；聊天保留槽也只在单进程内生效。

建议：指标汇总到共享采集系统；明确并发配置按 worker 还是全局，必要时使用共享限额；部署文档写清实际预算。

### A24 · P2 · 会话参数校验模型存在但未被实际列表接口使用【静态确认】

位置：`backend/app/schemas/session.py` 的 ListSessionRequest；`backend/app/api/sessions.py:46`。

路由接受任意 str session_type、任意 page/page_size，再直接 `SessionTypeEnum(session_type)`。无效类型可能变成 500，负分页/极大分页不受 schema 约束。已有 Pydantic 请求模型没有接入路由。

建议：直接用枚举和 Query 范围校验；为不合法输入返回 422，而不是内部错误。

### A25 · P2 · 重用比对会话时任务关联文件 ID 不更新【静态确认】

位置：`backend/app/api/comparisons.py` 的已有 ComparisonTask 更新分支；`backend/app/api/sessions.py` 的比对历史。

找到已有 task 后仅更新 diff_summary/diff_result，不更新 standard_file_id/comparison_file_id；本次响应展示新文件，但历史仍读取旧文件 ID，可能出现结果与合同标题/下载链接不一致。相等段落的 cmp_index 也直接用标准文件索引，发生前置插入后会错位。

建议：更新任务关联文件和会话元数据；按两侧真实索引映射；增加同会话换文件以及前置插入后相等段落的用例。

### A26 · P2 · CI 未接入前端测试/lint，部署任务是占位且不等待 RAG 门禁【静态确认】

位置：`.github/workflows/ci.yml:62`、`:75`。

前端 job 只执行 build，不执行当前已有的 npm test/npm run lint。deploy 仅 echo，没有实际部署；其 needs 也不包含 rag-eval。以后接入真实部署时可能在 RAG 失败前发布。

建议：将已存在的前端检查纳入 CI，真实部署显式依赖全部质量门禁。占位 deploy 不能作为项目已实现自动发布的证据。

### A27 · P2 · 数据库升级和生产错误响应仍有缺口【静态确认】

位置：`backend/app/main.py:34`、`backend/app/core/exceptions.py`。

启动只调用 metadata.create_all，不会迁移已有表的字段/约束；继续新增证据或摘要字段时必须引入可审查的迁移。统一 500 响应直接拼接异常字符串，可能向调用者暴露路径、SQL 和数据库细节。鉴权、下载和对象归属问题修好后仍需收敛生产错误输出。

建议：建立版本化迁移和升级前验证；客户端只返回通用错误与追踪 ID，详细异常写受控日志。

## 功能启用判断

| 能力 | 当前判断 | 处理建议 |
| --- | --- | --- |
| 身份验证与权限 | 开关开启，但存在匿名/跨用户漏洞 | 首先修后端权限，不是重复打开开关 |
| 工具调用、专家证据审计、Multi-Query、证据精排 | 本地开关已开，调用链存在 | 本次不因“功能存在”就建议再次启用；真实效果需在线验收 |
| BM25 | 本地文件存在，服务懒加载 | 增加索引版本/文档数和双路健康信息 |
| 限流 | 本地和默认关闭 | 修原子性/可信代理/预算后再开 |
| 后台模型/提示词管理 | CRUD 存在，推理没有读取 | 补运行时配置解析 |
| Langfuse | 未配置、未埋点、SDK 构造不兼容 | 修接线和兼容性后启用 |
| 云 OCR | 本地引擎列表已开；默认部署未开 | 验证可用性与页数完整性，完善能力说明 |
| 本地 OCR、LibreOffice | 默认链包含，但 Docker 缺系统程序 | 提供完整解析镜像或明确关闭 |
| MCP | 本地关闭，客户端/传输/生命周期接线不完整 | 需要外部集成时先修复再开启 |
| refresh、服务端 logout | 后端有接口，前端未接 | 按产品会话策略完成接入 |
| CAS | 只有跳转预留；没有看到 ticket 验证和回调换 token 的完整链路 | 不应只填 CAS_SERVER_URL 就宣称统一登录可用 |
| CI RAG 指标门禁 | 静态门禁可跑，指标条件/供应商变量需修 | 明确验证 secret 存在和缺失两条分支 |
| 自动部署 | 占位 | 需要发布能力时实现并绑定全部门禁 |

## 建议修复顺序与验收

1. A01–A04：封住匿名管理、账户接管、合同泄露和跨用户访问；对每个接口增加匿名/普通用户/管理员/他人对象矩阵测试。
2. A05–A08：修删除事务、审阅锁、审阅强制意图、超时和取消；开启数据库外键执行回归，验证旧结果不会被失败请求删除。
3. A09、A16、A18、A25：补齐核心结果准确性、长合同上下文、证据持久化与历史一致性。
4. A10–A15、A19–A27：完成配置接线、部署能力、可靠限流、可观测性和 CI；再执行容器启动、真实模型与知识库验收。

后续必须验证的集成场景：两个用户交叉访问；MySQL 外键下删除；同时发起两次审阅；审阅中断/超时/模型不可用；备注不是审阅命令；DOCX 表格变更；长合同尾部问答；刷新恢复结论和证据；超过 1 MB 的合同经 Nginx 上传；Qdrant 单路故障；双 worker 指标与限额；CI secret 有/无两种配置。

本次仅排查并交付报告，没有自动改动安全策略、启用外部服务或提交/推送代码。通过的现有测试说明原有测试集无回归，不构成上述未覆盖场景正确性的证明。
