# AI 对话知识库（knowledge-flow）

把日常与各 AI（ChatGPT / Claude / Gemini 等）的对话一键沉淀为结构化笔记的**本地自动化流水线**。

本地优先、全程仅一个人工审核关卡：浏览器插件捕获对话 → n8n 编排 → 本地大模型（Ollama）摘要 → 本地向量去重 → 写入 Obsidian 待审核 → QuickAdd 一键归档。

## 模块

| 路径 | 说明 |
|---|---|
| `browser-extension/` | Chrome/Edge Manifest V3 插件，`Alt+S` 捕获当前对话，POST 到本地 n8n webhook |
| `n8n_workflow_capture.json` | n8n 工作流（Webhook → Ollama 摘要 → 写入 Obsidian）|
| `retrieval_service.py` | 本地向量检索去重服务（SQLite + Ollama embedding，端口 8765）|
| `update_workflow_js.py` | 维护 n8n 摘要 Code 节点的 JS 代码，改完跑一次即可 |
| `t6-scripts/` | Obsidian QuickAdd 归档脚本：确认新建 / 合并 / 判定重复丢弃 / 打回 |

## 依赖（均为本地服务）

- **Ollama**：摘要模型 `qwen2.5:7b`，Embedding 模型 `bge-m3`
- **n8n**：本地工作流编排（默认端口 5678）
- **Obsidian**：知识库本体，需装 Local REST API、QuickAdd、Templater 插件
- **Syncthing**（可选）：PC ↔ 手机双端同步

## 配置（环境变量）

| 环境变量 | 用途 | 默认值 |
|---|---|---|
| `KNOWLEDGE_VAULT_DIR` | Obsidian vault 根目录 | 与本仓库同级的 `knowledgebase/` |
| `KNOWLEDGE_DB_PATH` | 向量索引 SQLite 文件路径 | 脚本旁的 `vector_index.db` |
| `SYNCTHING_API_KEY` | 写入 Obsidian 的 Local REST API Key | 无（需自行设置）|

> 说明：`retrieval_service.py` 默认假设 vault 与本仓库**同级**（`<仓库>/../knowledgebase`）。若 vault 在别处，请用 `KNOWLEDGE_VAULT_DIR` 指定；`n8n_workflow_capture.json` 的写入节点改为用 `SYNCTHING_API_KEY` 环境变量读取 Key，不再硬编码明文。

## 启动

1. 启动 Ollama：`ollama serve`
2. 启动 n8n，导入 `n8n_workflow_capture.json`
3. 启动检索服务：`python retrieval_service.py`
4. 浏览器加载 `browser-extension/`，按 `Alt+S` 捕获
5. Obsidian 里用 `t6-scripts/` 的 QuickAdd 脚本归档

## 说明

- 仅供个人本地使用，不对外发布。
- 所有本地服务均绑定 `127.0.0.1`，不对外暴露。
