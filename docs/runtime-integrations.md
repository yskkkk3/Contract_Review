# 运行时配置与集成

本轮将后台配置接入了真实模型调用和提示词加载，并完成 Langfuse、外部 MCP、前端会话、CI 与可选 SSH 发布流程。没有修改本地 `.env`，没有启用服务器发布，没有迁移或清理现有业务数据。

## 后台模型配置

进入管理员页面的“模型配置”：填写用途、模型名称、供应商标签、API 地址和密钥引用，保存为默认配置。已有配置可“设为默认”或停用。

| 用途 | 使用入口 |
| --- | --- |
| review | 专家工具循环、质检、仲裁和完整性审计 |
| chat | 聊天流、合同元信息抽取、MCP 合同问答 |
| intent | 条款分发、意图识别、Multi-Query、证据复核 |
| embedding | RAG 查询向量及知识库构建向量 |
| rerank | 供应商精排接口 |

每次聊天/审阅/上传请求读取一次数据库配置快照。后台保存后的下一次请求生效；正在执行的任务保持原模型与提示词快照。多 worker 独立读取数据库，避免进程缓存造成更新延迟。知识库构建、检索评测、smoke 脚本和独立 MCP 推理同样读取后台配置；数据库未初始化表时使用环境配置，数据库本身不可达时需要先恢复数据库或显式配置本地 SQLite 环境。

每个用途只有启用的默认模型参与推理。设置新默认会清除该用途其他默认标记；没有启用默认配置时，回退到 `.env`。`provider` 是展示标签，调用统一通过 OpenAI 兼容 SDK，精排使用供应商 HTTP 扩展接口。

API 地址：推理/embedding 填 OpenAI 兼容基础地址；rerank 填完整接口 URL。密钥字段只接受空值或 `env:VARIABLE_NAME`，例如 `env:LLM_API_KEY`；实际值保留在进程环境或项目根 `.env` 中。空引用使用该用途的环境密钥。接口不返回实际密钥，也不接受把明文密钥存进数据库。

温度、top_p 使用后台值。max_tokens 是上限：短任务原有更小输出预算仍保留，避免设置一个全局大值后放大所有辅助请求。`LLM_ALLOWED_MODELS` 仍约束后台选中的推理模型。

更换 embedding 模型时必须保持 `EMBEDDING_DIMENSIONS` 与模型一致，并重建对应向量库和 BM25；原向量与新向量不可混用。构建脚本与检索请求已使用同一配置来源，但不会自动删除/重建用户知识库。

## 后台提示词

管理员页面“Prompt 管理”可从内置模板列表创建覆盖版本，编辑、启用、停用或删除。模板名必须精确对应 Markdown 文件名，例如 `chat`、`specialist_base`、`gate`、`arbitration`、`router`、`contract_extract`、`rag_query_expansion` 或 `risk_dims/财务与付款`。内置文件仍为最终兜底。

匹配顺序：当前合同类型优先于全局；相同范围按 `override > org > system`；遗留重复记录以 ID 较新的版本优先。正常后台操作会停用同名、同层级、同合同范围的其他版本，便于切换旧版本。

派生层必须关联同名、相容合同范围的有效父层：org 的父层为 system，override 的父层为 org；父层停用后派生层也不再参与推理。删除被派生版本引用的父模板返回 409。

当前用户表没有组织成员关系，因此非空 `organization_id` 返回 422；不会把某组织的模板错误应用给所有用户。页面提供全局和合同类型覆盖，原层级字段仍可通过经过校验的 API 使用。

合同类型范围应用于审阅图内全部模板和聊天系统提示词。Multi-Query 缓存键包含选中的提示词及模型配置，后台更新后不会继续复用旧改写结果。

## Langfuse

SDK 约束为 `langfuse>=4.15,<5`，使用 `tracing_enabled`、`base_url`、`start_as_current_observation` 和 `propagate_attributes`。审阅、聊天以 session_id 关联 trace，包含模型 generation、工具、embedding、精排和 RAG 检索子操作；可获得耗时、错误状态、模型名称及供应商返回的 token usage。

默认不向 trace 写入合同正文、提示词正文、模型答案或密钥；当前记录结构和计数。业务故障正常抛出，观测初始化/上报失败只写日志；应用退出会 flush 并关闭 SDK。

本地自托管改为可选的 Langfuse v4 stack，包含 web/worker、PostgreSQL、ClickHouse、MinIO、Redis，主应用不再强制依赖观测服务启动：

```bash
docker compose --env-file .env -f deploy/docker-compose.yml --profile observability up -d --build
```

本地服务字段见 `.env.example` 的 `LF_*`。在 `http://localhost:13000` 创建项目，将项目 public/secret key 写入根 `.env` 的 `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`。容器内使用 `LANGFUSE_HOST=http://langfuse:3000`；后端在宿主机运行时使用可达的宿主机地址。

也可仅设置兼容的远端 Langfuse 服务地址与项目密钥，不启动本地 profile。代码接入不等于已有外部服务已连通。

原 `cr_langfuse_db` v2 卷保留；v4 使用独立卷，不自动迁移历史 trace。需要保留旧观测数据时，按官方迁移流程单独处理。

参考：[Langfuse 兼容性](https://langfuse.com/docs/compatibility)、[官方自托管 Compose](https://github.com/langfuse/langfuse/blob/main/docker-compose.yml)。本项目仅使用观测功能，不自动启用 Langfuse 的 AI 功能。

## MCP

启用前在根 `.env` 设置：

```dotenv
MCP_ENABLED=true
MCP_SERVER_URLS=https://tools.example.com/mcp
MCP_TOOL_TIMEOUT=30
MCP_HEADERS_ENV=EXTERNAL_MCP_HEADERS
```

`EXTERNAL_MCP_HEADERS` 的实际 JSON 请求头放在本地 `.env` 或进程环境，不放代码/数据库。无需鉴权的外部服务可将 MCP_HEADERS_ENV 留空。

启动时分页发现工具，工具名以服务器和原名称的稳定摘要命名，避免跨服务器/本地工具冲突。工具追加到专家 Agent 的原工具集。每次调用新建并关闭 transport + ClientSession，允许重复调用；超时或服务故障回喂给模型，不影响本地工具注册。

默认采用 Streamable HTTP；以 `/sse` 结尾的地址使用兼容 SSE。外部工具返回文本不自动记为“已核验法规证据”，必须通过既有来源与质检规则。

本系统的服务端入口为 `/api/mcp/`（含结尾斜杠），父应用负责启动 SDK session manager。客户端需要携带有效的本系统 Bearer token。对外部署需在 `MCP_ALLOWED_HOSTS` 追加实际 Host；Origin 仍按 FRONTEND_URL 校验。

参考：[MCP ASGI 挂载生命周期](https://py.sdk.modelcontextprotocol.io/run/asgi/)。依赖已约束 `mcp>=2.2,<3`，使用 v2 的 input_schema、next_cursor、is_error 字段。

## 前端登录会话

登录同时保存 access/refresh token。普通 HTTP 请求遇到 401 时共享一次 refresh 请求，每个业务请求只重试一次；refresh 请求本身不走同一重试拦截器。SSE 只在建连收到 401、尚未消费事件时刷新并重连，不重放已开始的模型回答。

退出立即清除本地身份和头像，再使用捕获的令牌请求服务端撤销会话。如果 access 已过期，则使用捕获的 refresh 换取令牌，仅用于撤销，不写回本地。刷新期间退出或切换账户，迟到的响应不会恢复旧身份。网络不可达时本地仍退出，但服务端撤销需服务恢复或令牌到期。

## CI 与暂不启用的发布流程

前端 CI 现在执行 lint、31 个原有测试及新增会话测试、类型检查和构建。Docker job 另外检查默认/observability Compose 配置与部署脚本语法。发布等待 lint、pytest、frontend-build、docker-build、rag-eval 全部通过。

RAG gate 的 secret 判定提升到 job 环境，完整检索步骤显式提供 SiliconFlow 推理、embedding 和 rerank 地址及模型；`RAG_EVAL_LLM_MODEL` 可覆盖评测推理模型。未配置 secret 时仍执行 golden 静态门禁。

发布默认关闭，本次没有设置 `DEPLOY_ENABLED`、配置生产凭据或执行服务器操作。准备启用时：

1. Linux 主机准备 Docker Compose v2（支持 `up --wait`）、Bash、flock、tar 和可用的 SSH 登录账号。
2. 创建专用部署目录，例如 `/opt/contract-review/shared/.env`，将实际应用配置放入该文件。部署目录仅支持绝对路径中的字母、数字、下划线、斜线和连字符。
3. GitHub production Environment 添加 secrets：`DEPLOY_HOST`、`DEPLOY_USER`、`DEPLOY_SSH_KEY`、`DEPLOY_KNOWN_HOSTS`。known_hosts 使用预先核验的主机公钥，不使用自动信任 keyscan。
4. 仓库变量设置 `DEPLOY_PATH=/opt/contract-review`、`DEPLOY_PROJECT=deploy`；有现存 Compose 项目时必须使用其原项目名以保留原 volumes。production Environment 可设置审批规则。
5. 需要发布时再把仓库变量 `DEPLOY_ENABLED` 设为 `true`。只在 main 的 push 事件执行；PR 不发布。

发布将经过检查的 commit 用 git archive 打包，经 SCP 上传到 releases/SHA，关联 shared/.env 后构建并等待健康检查。成功才切换 current 软链接；失败时尝试从上一版本源代码重新部署。若 current 是普通目录则拒绝覆盖；flock 防止并发发布。不自动删 volume、清业务文件或运行数据库迁移。回滚保护代码版本，不保证外部系统或未来数据库迁移可逆。

本轮移除了未被使用的 `review_stream_timeout` 设置；没有新增整个审阅任务的超时。聊天流、上游 HTTP、工具调用和证据审计各自的超时仍保留。

## 本次验证范围

- 后端 305 个离线测试通过，新增用例覆盖配置实际参与 SDK 调用、默认切换、提示词范围/版本、SSE 上下文、知识库任务配置来源、凭据引用、MCP 真实 SDK 内存握手与重复工具调用、观测故障隔离。
- 前端 39 个测试通过，包含并发刷新、刷新失败、退出/切换账户后的迟到响应、SSE 建连刷新、过期令牌退出；lint、类型检查和生产构建通过。
- ruff、golden 静态门禁、uv 锁文件一致性检查、Bash 语法和 CI/Compose YAML 结构检查通过。
- 没有 Docker 运行环境，未验证实际容器启动；没有连接真实 Langfuse/外部 MCP/模型供应商或 Linux 发布服务器。Windows Git Bash 不能替代 Linux 的 flock/软链接部署验收，未将本机模拟当作真实发布成功。
- 自动部署保持关闭；本地 `.env`、已有数据和用户原有的 `backend/run_dev.py` 修改未改变。
