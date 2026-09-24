// 合并进已有笔记：把当前笔记正文追加到目标笔记（弹窗选目标），删原笔记，并更新目标索引
module.exports = async (params) => {
    const { app, quickAddApi } = params;
    // 知识库 vault 根目录：从 Obsidian 读取，避免写死本机绝对路径
    const VAULT_ROOT = app.vault.adapter.basePath || "";
    const file = app.workspace.getActiveFile();
    if (!file) { new Notice("没有打开的笔记"); return; }
    if (!file.path.startsWith("00-待审核/")) { new Notice("当前笔记不在待审核文件夹"); return; }

    // 读当前笔记正文（去掉 frontmatter）
    const content = await app.vault.read(file);
    const body = content.replace(/^---\n[\s\S]*?\n---\n?/, "").trim();

    // 列出可合并的目标笔记（01/02/03 目录）
    const targets = app.vault.getMarkdownFiles().filter((f) => {
        return f.path.startsWith("01-") || f.path.startsWith("02-") || f.path.startsWith("03-");
    });
    if (targets.length === 0) { new Notice("没有可合并的目标笔记"); return; }
    const target = await quickAddApi.suggester(targets.map((f) => f.path), targets);
    if (!target) return;

    // 追加到目标笔记末尾
    const targetContent = await app.vault.read(target);
    const date = new Date().toISOString().slice(0, 10);
    const block = "\n\n---\n\n## 补充（" + date + "）\n\n" + body;
    await app.vault.modify(target, targetContent + block);

    // 删原笔记
    await app.vault.trash(file, false);
    new Notice("已合并到 " + target.path);

    try {
        await fetch("http://127.0.0.1:8765/index", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ path: VAULT_ROOT + "/" + target.path }),
        });
    } catch (e) {}
};
