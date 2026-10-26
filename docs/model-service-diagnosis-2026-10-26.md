# 模型调用故障定位与修复（2026-10-26）

**已证实两个问题：当前中转没有可靠执行关闭思考参数；项目原有失败处理会放大调用。**
502 的具体服务端根因仍需服务商按请求日志查明，不能将所有失败解释为余额、并发或某个 JSON 参数。
本轮已修复项目能控制的部分。当前接口仍不能通过完整专业效果验收。

## 排查结论

1. 模型名有效。用当前凭证读取 `/v1/models`，列表有 `deepseek-v4.1-flash`，不是凭空拼出的名称。
2. 对上轮同一条真实 Gate 请求串行做四组对照，提示词约 9,074 字符。256 token 的原请求一次正常结束；
   1024 token 的 Schema、JSON Object、单独关闭思考三种请求均返回 `finish_reason=length`。
   后三次含 1,818～4,721 字符的 `reasoning_content`，且原样重复出现在 `content`，最终正文长度为 0。
3. 因为这些是串行请求，问题不只出现在本地多专家并发时；单纯降低并发不能解决思考模式控制失效。
4. 修复主要失败处理后，仅复测一个真实 IP 专家，保留原完整合同上下文、工具与知识库。
   两次请求均明确带 `thinking.type=disabled` 和 `reasoning_effort=low`；第一次仍返回 9,393 字符思考内容后调用工具，
   第二次达到 4096 token 上限，返回 16,024 字符思考内容，`content` 与思考内容完全重复，没有最终答案。
5. 本次单专家复测约 105.9 秒，新代码识别第二次响应为 `LLMOutputTruncated`，未启动后续完整性复核。
   没有用半截响应生成风险点，也没有重复整份合同批次。

DeepSeek 的[思考模式文档](https://api-docs.deepseek.com/guides/thinking_mode/)
定义了 `thinking.type=disabled`，并将思考内容与最终 `content` 分开。
FlashCoding 的[兼容接口说明](https://doc.flashcoding.ai/api/openai.html)同时说明，模型和参数能力取决于账户及渠道。
因此应请服务商确认当前模型所路由渠道的实际参数支持和转换，而不是继续仅按“兼容 OpenAI”判断。

## 已修复的项目问题

- **502 被当作格式问题重试**：`chat_structured` 现在只对明确的格式不支持错误降级；
  上游 5xx、限流和连接失败不再触发另一轮格式请求。SDK 原有的有限重试仍保留。
- **截断被当作正常结果解析**：非流式响应出现 `finish_reason=length` 直接给出明确异常，
  保留 usage 统计，不解析为完整 JSON，也不执行被截断的工具调用。
- **工具审阅未传思考策略**：工具循环开始传递现有短结构化任务配置，包含显式关闭思考和推理强度设置。
  服务商是否执行参数仍须看实际响应。
- **失败后继续花费**：专家服务失败或输出截断后，不再启动完整性复核；Gate 遇到这类失败后，
  停止后续模型修复，保留已核验结果并继续执行确定性法律保护，最终标记未完成。
- **连续失败保护**：按非流式 SDK 客户端/模型维护进程内保护窗口；默认连续 3 次临时失败后暂停 30 秒，
  窗口后只允许一个恢复探测。不同客户端/模型分别计数，嵌入服务不受该保护状态影响。

配置项已写入 `backend/.env.example`，无需新增依赖：

```dotenv
LLM_CIRCUIT_FAILURE_THRESHOLD=3
LLM_CIRCUIT_COOLDOWN_SECONDS=30
```

阈值为 0 可以关闭保护。这些修复用于避免错误结果与故障放大，不能让不执行参数的上游自动恢复。
真实 `.env`、模型凭证及业务数据库没有改动，代码尚未提交、推送。

## 可以直接发给中转支持的材料

以下材料只包含定位信息，不含密钥、完整合同或模型思考正文；本轮没有代用户向外发送。
服务商的[联系支持说明](https://doc.flashcoding.ai/help/contact.html)建议提供请求标识、SDK 版本和最小上下文。

```text
问题：deepseek-v4.1-flash 忽略关闭思考，返回思考内容并重复到正文，耗尽输出预算；此前完整批次还有多次502。
日期与时区：2026-10-26，Asia/Shanghai；下述单专家复测于12:09:06结束，耗时约106秒。
协议与路径：OpenAI Chat Completions，POST /v1/chat/completions
服务：https://flashcoding.ai/v1
模型：deepseek-v4.1-flash（同一凭证的 /v1/models 列表中存在）
SDK：openai 2.54.0，Python 3.12.15，Windows
关键请求JSON字段：
  thinking: {"type":"disabled"}
  reasoning_effort: "low"
  max_tokens: 4096
  tools: 4个工具定义
第二次返回：model仍为deepseek-v4.1-flash，finish_reason=length，reasoning_content长16024字符；
  content与reasoning_content完全相同，缺少最终答案。

第一次响应中的请求标识（原样）：
11d112ce-432b-4d58-b760-bf2d24b0b615, 8dc1d42a-cb9f-496f-a4bd-208990d21128, a2f7b09c-eb7a-444f-a4af-b074cdcb56f1
第二次响应中的请求标识（原样）：
e4639b37-78bf-4a84-aeec-578f8fc604af, 8ad20437-c369-4936-89ce-9b9a2fc70649, d517dc60-4558-4b35-adaf-96e99c311ead

请核对：
1. 两次请求被分配到哪些上游渠道？是否覆盖或忽略了thinking.type？
2. 当前该模型应如何关闭思考？为什么思考内容被重复拼进content？
3. 2026-10-26约11:31～11:47的完整批次105次502，对应的上游状态、渠道错误和请求限制是什么？
4. 请提供能同时支持非思考、工具调用与可靠JSON回复的稳定渠道/配置。

说明：上述两个请求标识用于定位思考控制与内容重复，不冒称它们本身返回502。
```

## 后续处理

可先让中转方修正参数透传与渠道；也可以切换到官方 API，绕开当前中转。
官方切换步骤见 [DeepSeek 官方迁移说明](deepseek-official-migration-2026-10-26.md)。
配置后先验证最终 JSON 与工具多轮，再复测同一完整合同，最后恢复 12 类专业效果验收。
OCR 漏段属于另一条解析链，仍需单独修复。
