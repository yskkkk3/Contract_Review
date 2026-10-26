# 切换 DeepSeek 官方 API（2026-10-26）

**建议用官方接口做下一轮验证：它能绕开当前 FlashCoding 中转的参数转换和上游调度。**
是否彻底恢复，以完整业务复测为准，不能承诺换地址后专业效果自动达标。
故障证据与本地修复见 [排查报告](model-service-diagnosis-2026-10-26.md)。

## 本地配置

项目通过同一个 OpenAI SDK 客户端接入；不需要安装 DeepSeek 专属 SDK。
在项目根目录本地 `.env` 修改审阅、问答、意图模型配置：

```dotenv
LLM_BASE_URL=https://api.deepseek.com
LLM_API_KEY=填写DeepSeek官方账户的API_Key
LLM_REVIEW_MODEL=deepseek-flash
LLM_CHAT_MODEL=deepseek-flash
LLM_INTENT_MODEL=deepseek-flash
LLM_ALLOWED_MODELS=deepseek-flash
LLM_BRIEF_DISABLE_THINKING=true
MAX_CONCURRENT_LLM=2
```

Key 必须来自 DeepSeek 官方账户，填写在本地 `.env`，无需发到聊天。
FlashCoding 的 Key 和余额用于 FlashCoding 服务，不能直接用于官方接口。
如原来设置了 `LLM_BRIEF_REASONING_EFFORT=low`，可先保留并通过响应确认思考关闭是否生效。
当前完整合同实测中，总并发 4（后台最多 3 路）出现长请求超时；总并发 2 配合
`LLM_CHAT_RESERVED_SLOTS=1` 时，后台审阅实际为单并发并稳定完成。上调前须用完整合同压测，
不能只依据短探针成功。

官方当前模型名为 `deepseek-flash`，其版本映射见
[官方模型说明](https://api-docs.deepseek.com/quick_start/pricing/)。
不要把原中转的名称 `deepseek-v4.1-flash` 原样当作官方模型 ID；模型白名单需与新名称一同更新。

当前数据库没有默认模型覆盖时，以上环境配置直接生效。
如果在后台启用了默认模型，后台配置优先：同时检查 review、chat、intent 三类默认项的
模型名、接口地址和凭证环境变量引用，避免它们仍指向中转。
数据库凭证应使用 `env:LLM_API_KEY` 等环境变量引用，不保存明文 Key。

向量、精排、OCR 使用各自配置。当前这些服务接在百炼，迁移审阅模型不需要替换它们的密钥。
此前的 OCR 正文漏识别不会因为修改上述审阅模型配置自动消失。

## 应用与验证

更新代码、配置后重启后端。先做普通回复、最终 JSON、工具多轮的小样本验证，检查：

- 请求到达官方地址，实际模型与预期一致。
- 关闭思考生效，最终正文有效，不接受 `finish_reason=length` 的截断结果。
- 结构化与工具参数被正确处理，未发生无效的格式重试。

然后从 `backend` 目录执行同一完整业务合同验收，使用新的输出编号：

```powershell
.\.venv\Scripts\python.exe scripts/eval_specializations.py `
  --directory ../.cache/acceptance-deepseek-official-2026-10-26 `
  --types technology --run-id official-01
```

使用新目录会根据官方调用配置构建隔离验收索引；向量仍走已配置的向量服务。
需要保留本机此前下载的公开合同样本。检查输出中的模型请求错误、截断、有效专项核对记录、
Gate 结果及 `review_status`，之后再扩大合同类型。

官方的[思考模式说明](https://api-docs.deepseek.com/guides/thinking_mode/)
和 [JSON 输出说明](https://api-docs.deepseek.com/guides/json_mode/)是参数核对依据。
本轮已完成官方账户配置和真实调用验证，结果见
[DeepSeek 官方专业效果验收](specialization-deepseek-official-acceptance-2026-10-26.md)。
本地 Key 仍只保存在被忽略的 `.env` 中，报告和仓库文件不记录 Key。
