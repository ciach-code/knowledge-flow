#!/usr/bin/env python3
"""唯一入口：维护 n8n 捕获工作流「Ollama摘要」Code 节点的 jsCode，跑一次重新生成 n8n_workflow_capture.json。

以后改提示词/代码都只改这里（JS 变量），然后跑 `python update_workflow_js.py` 即可；
原来的 n8n_code_node.js（手动复制粘贴用的副本）已删除，避免多处维护导致漂移。

改动历史：
- 摘要 → 详细总结：改 Prompt + temperature=0.3 + num_predict=2048
- 去掉模型常带的整篇 ```markdown 围栏
- related_notes 改为可点击 wikilink（[[文件名|标题 · 相似度]]）
- title 用 JSON 引号包裹，避免 YAML 特殊字符破坏 frontmatter
- 2026-09-19：加反编造「最高原则」——只提炼原文，禁止虚构例子/代码/命令/数字/步骤，没有则写「原文未提及」
"""
import json
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "n8n_workflow_capture.json")
BAK = os.path.join(HERE, "n8n_workflow_capture.json.bak")

JS = r"""const N = String.fromCharCode(10);
const item = $input.all()[0];
const body = item.json.body || {};
const raw = body.raw_text || '';

const prompt =
  '请阅读下面的对话内容，写一份【详细总结】。' +
  '【最高原则】只能基于原文已有的信息进行提炼、重组和压缩，严禁编造、补充、推测或扩展原文中不存在的任何内容。' +
  '尤其不要为了显得详细而虚构例子、代码、命令、数字、步骤或结论；原文没有的细节，在对应位置写「原文未提及」或直接省略该小节。宁可短而真，不要长而假。' +
  '按以下结构输出：' +
  '1) 背景和要解决的问题（仅据原文概括）；' +
  '2) 核心结论与关键论证过程（仅据原文概括）；' +
  '3) 原文出现的具体细节（代码、命令、数字、步骤、文件名、工具名等，逐条原样保留并确保每条都能在原文中找到出处；没有则写「原文未提及」）；' +
  '4) 我的理解、启示或可复用经验（可基于原文提炼，但不得引入原文没有的事实）；' +
  '5) 建议的分类标签（2-4个）。' +
  '用 Markdown 输出，但不要用代码块把整篇包起来。对话内容：' + raw;

let content = raw;
try {
  const sumResult = await this.helpers.httpRequest({
    method: 'POST',
    url: 'http://127.0.0.1:11434/api/generate',
    body: {
      model: 'qwen2.5:7b',
      prompt: prompt,
      stream: false,
      options: { temperature: 0.3, num_predict: 2048 }
    },
    json: true
  });
  content = (sumResult.response || '').trim();
  // 去掉模型常带的整篇代码块围栏（```markdown ... ```）
  if (/^```/i.test(content)) {
    content = content.replace(/^```(?:markdown|md)?\s*/i, '').replace(/\s*```\s*$/, '');
  }
} catch (e) {}

// 检索去重：用总结正文做查询，写 related_notes / duplicate_suspect
let related = [];
let dup = false;
try {
  const q = content.length > 8000 ? content.slice(0, 8000) : content;
  const searchResult = await this.helpers.httpRequest({
    method: 'POST',
    url: 'http://127.0.0.1:8765/search',
    body: { text: q },
    json: true
  });
  related = searchResult.related_notes || [];
  dup = searchResult.duplicate_suspect || false;
} catch (e) {}

// related_notes 存成可点击 wikilink：[[文件名|标题 · 相似度]]
function wiki(r) {
  const base = String(r.path || '').replace(/\\/g, '/').split('/').pop().replace(/\.md$/i, '');
  let alias = String(r.title || '').replace(/[\[\]|]/g, ' ').replace(/\s+/g, ' ').trim();
  if (r.score != null) {
    const s = Math.round(r.score * 100) / 100;
    alias = alias ? alias + ' · ' + s : String(s);
  }
  if (!base) return '';
  return alias && alias !== base ? '[[' + base + '|' + alias + ']]' : '[[' + base + ']]';
}
const relStr = JSON.stringify(related.map(wiki));

const fm = '---' + N
  + 'source: ' + (body.source || '') + N
  + 'title: ' + JSON.stringify(body.title || '') + N
  + 'duplicate_suspect: ' + dup + N
  + 'related_notes: ' + relStr + N
  + '---' + N + N;

return [{ json: { response: fm + content + N } }];
"""


def main():
    shutil.copyfile(SRC, BAK)

    with open(SRC, encoding="utf-8") as f:
        wf = json.load(f)

    hit = 0
    for node in wf.get("nodes", []):
        if node.get("name") == "Ollama摘要":
            # 强制重建为 Code 节点：历史上有过 httpRequest 内联写法（有坑），
            # 这里一并把 type/typeVersion/parameters 全部重置为正确形态。
            node["type"] = "n8n-nodes-base.code"
            node["typeVersion"] = 2
            node["parameters"] = {
                "mode": "runOnceForAllItems",
                "jsCode": JS,
            }
            hit += 1

    if hit != 1:
        raise SystemExit(f"未找到唯一节点，命中 {hit} 个（预期 1）")

    with open(SRC, "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"OK：已更新 {hit} 个节点，原文件备份到 {BAK}")


if __name__ == "__main__":
    main()
