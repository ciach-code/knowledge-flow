// 确认新建：把当前笔记从 00-待审核 移到 01/02/03（弹窗选文件夹），并更新索引
module.exports = async (params) => {
    const { app, quickAddApi } = params;
    // 知识库 vault 根目录：从 Obsidian 读取，避免写死本机绝对路径
    const VAULT_ROOT = app.vault.adapter.basePath || "";
    const file = app.workspace.getActiveFile();
    if (!file) { new Notice("没有打开的笔记"); return; }
    if (!file.path.startsWith("00-待审核/")) { new Notice("当前笔记不在待审核文件夹"); return; }

    const folders = ["01-对话沉淀", "02-项目复盘", "03-概念卡片"];
    const target = await quickAddApi.suggester(folders, folders);
    if (!target) return;

    const newPath = target + "/" + file.name;
    await app.vault.rename(file, newPath);
    new Notice("已归档到 " + target);

    try {
        await fetch("http://127.0.0.1:8765/index", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ path: VAULT_ROOT + "/" + newPath }),
        });
    } catch (e) {}
};
