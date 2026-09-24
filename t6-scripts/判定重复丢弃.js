// 判定重复丢弃：把当前笔记移入 Obsidian 回收站，并删除索引
module.exports = async (params) => {
    const { app } = params;
    const file = app.workspace.getActiveFile();
    if (!file) { new Notice("没有打开的笔记"); return; }
    if (!file.path.startsWith("00-待审核/")) { new Notice("当前笔记不在待审核文件夹"); return; }

    const oldPath = file.path;
    await app.vault.trash(file, false);
    new Notice("已丢弃（移入回收站）");

    try {
        await fetch("http://127.0.0.1:8765/delete", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ path: "D:/knowledgebase/" + oldPath }),
        });
    } catch (e) {}
};
