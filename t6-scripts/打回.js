// 打回：给当前笔记 frontmatter 加 status: rejected，笔记留在待审核，供手动重新编辑
module.exports = async (params) => {
    const { app } = params;
    const file = app.workspace.getActiveFile();
    if (!file) { new Notice("没有打开的笔记"); return; }
    if (!file.path.startsWith("00-待审核/")) { new Notice("当前笔记不在待审核文件夹"); return; }

    const content = await app.vault.read(file);
    let newContent;
    if (content.startsWith("---")) {
        const end = content.indexOf("\n---", 3);
        if (end !== -1) {
            newContent = content.slice(0, end) + "\nstatus: rejected" + content.slice(end);
        } else {
            newContent = content;
        }
    } else {
        newContent = "---\nstatus: rejected\n---\n\n" + content;
    }
    await app.vault.modify(file, newContent);
    new Notice("已标记打回（status: rejected）");
};
