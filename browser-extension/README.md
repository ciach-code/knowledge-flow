# AI 对话知识库捕获 — 浏览器插件（T4-2）

按 `Alt+S` 或点击工具栏图标，把当前 AI 对话（**任意网站**）抓取并 POST 到本地 n8n webhook，经 Ollama 摘要后写入 Obsidian `00-待审核/`。

## 工作原理

点击/快捷键 → background 用 `activeTab` + `scripting` 按需注入抓取函数 → 按 `selectors.json` 匹配当前网站的选择器抓取对话 → `fetch` POST 到 `http://localhost:5678/webhook/capture` → 角标 ✓/✗ + 系统通知反馈。

## 加载（Edge / Chrome）

1. 地址栏输入 `edge://extensions`（Chrome 是 `chrome://extensions`）回车
2. 打开右上角「开发人员模式」
3. 点「加载解压缩的扩展」，选 `D:\knowledge_flow\browser-extension`
4. 出现「AI 对话知识库捕获」即成功；工具栏会多一个图标（建议固定）

## 使用

- 快捷键 `Alt+S`，或直接点工具栏图标
- 成功：图标角标变绿色 `✓`，弹通知「已捕获」
- 失败：角标红色 `✗`，弹通知说明原因
- 若 `Alt+S` 没反应：到 `edge://extensions/shortcuts`（Chrome 同）手动绑定

## 测试（需 n8n 已启动）

1. 先按 `handoff.md` 里的命令启动 n8n
2. 打开 ChatGPT / Claude / Gemini / Kimi / 豆包任一对话页，按 `Alt+S`
3. 看角标 + 通知；摘要模型热态约 22s 出结果
4. 去 Obsidian `00-待审核/` 查看生成的 `YYYY-MM-DD-HHmm-来源.md`

## 新增一个 AI 网站（关键）

只需改 `selectors.json`，**不用改代码、不用重载扩展**，下次触发立即生效：

1. 在 `sites` 数组里加一条
2. `match` 填域名、`message` 填消息元素选择器、`userSelector` / `assistantSelector`（或 `roleAttr`）区分用户与助手
3. 选择器怎么找：在该网站按 F12 → 点元素选择箭头 → 点一条用户消息 → 记下它的 `class` 或 `data-*` 属性

字段说明与现成示例见 `selectors.json`（含 ChatGPT / Claude / Gemini 条目）。**未配置、或配置了但抓到空的网站会自动兜底**：抓页面 `main` 全文（无「用户/助手」标记，但内容能沉淀下来）。

## 注意

- **Kimi / 豆包的选择器是按常见结构填的猜测值，未经实测**——抓到空或抓错，请按上面的方法改成真实选择器
- 网站前端改版会导致选择器失效，改 `selectors.json` 对应条目即可
- 抓取文本超过 15000 字符会自动截断
- 仅供个人本地使用，不发布
