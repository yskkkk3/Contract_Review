# IntelliJ IDEA 本地启动

## 已配置环境

- IDEA：`D:/AboutJava/IntelliJ IDEA 2025.3.2`
- Python：`backend/.venv/Scripts/python.exe`（Python 3.12.15）
- Node.js：`D:/软件下载/node.exe`（Node 22）
- 数据库：Windows 本机 MySQL 8，数据库 `contract_review`
- Redis：虚拟机 `192.168.59.100:6379`
- Qdrant：通过 SSH 隧道访问虚拟机 `127.0.0.1:6333`
- 环境变量：项目根目录 `.env`（已被 Git 忽略）
- 模型：DeepSeek 负责推理，阿里云百炼负责 Embedding、Rerank 和可选 OCR

## IDEA 启动

1. 使用 IDEA 打开项目根目录 `E:/CloneProjects/contract-review`。
2. 等待 Python 和 JavaScript 索引完成。
3. 在右上角运行配置中选择 `Full Stack`。
4. 点击运行按钮，同时启动：
   - `Backend (FastAPI)`：`http://127.0.0.1:8080`
   - `Frontend (Vue)`：`http://127.0.0.1:5173`
5. 后端 Swagger：`http://127.0.0.1:8080/docs`。

单独调试后端时选择 `Backend (FastAPI)`；单独调试前端时选择 `Frontend (Vue)`。

## Qdrant SSH 隧道

虚拟机固定为 `192.168.59.100` 后，在 IDEA 中先运行
`Qdrant SSH Tunnel`。该配置等价于：

```powershell
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:6333:127.0.0.1:6333 root@192.168.59.100
```

保持该运行配置不停止，后端即可通过 `http://127.0.0.1:6333` 使用虚拟机
中的 Qdrant。

## 切换到虚拟机服务

根目录 `.env` 已配置好模型地址和模型名。启动模型能力前只需填写：

- `LLM_API_KEY`：DeepSeek API Key。
- `EMBEDDING_API_KEY`：阿里云百炼 API Key。
- `RERANK_API_KEY`：填写与上一项相同的百炼 API Key。

数据库使用本机 MySQL；Redis 与 Qdrant 使用虚拟机服务。

切换时同时注意：

- MySQL：`DATABASE_URL` 留空时使用 `MYSQL_*` 配置。
- Redis：保持 `REDIS_FAKE=false`。
- Qdrant：保持 `QDRANT_LOCATION` 留空，并先启动 SSH 隧道。
- 合同审阅和问答需要 DeepSeek Key；知识库构建需要百炼 Key。
- 当前项目没有 RabbitMQ 依赖。

## 千问 OCR 与 OSS

- 千问 OCR 默认复用 `EMBEDDING_API_KEY`，模型为
  `qwen-vl-ocr-latest`。
- 云端 OCR 会把扫描页发送到百炼，默认不启用。明确允许上传合同页时，在
  `DOC_PARSER_ENGINES` 末尾加入 `cloud_ocr`。
- OSS 配置入口已预留在 `.env`。提供 Endpoint、Bucket、AccessKey ID 和
  AccessKey Secret 后，才能将 `STORAGE_BACKEND` 从 `local` 切换为 `oss`。

## 验证命令

```powershell
cd E:\CloneProjects\contract-review\backend
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\ruff.exe check app tests scripts run_dev.py

cd ..\frontend
npm run build
```
