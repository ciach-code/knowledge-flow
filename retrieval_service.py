#!/usr/bin/env python3
"""知识库检索去重服务（T5）

纯 Python 标准库实现，零第三方依赖。
- SQLite 存储笔记向量（归一化后的 float 序列）
- /search：给定文本 → 查 Top-N 相似笔记，按阈值分级
    >0.9 疑似重复（duplicate_suspect=true）、0.6~0.9 相关、<0.6 无关
- /index：批量建索引（无 body）或增量索引单条（body 带 path）
- /health：健康检查

用法：
    python retrieval_service.py           # 启动服务
    python retrieval_service.py --index   # 批量建索引后退出
"""

import json
import os
import re
import sqlite3
import struct
import sys
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

OLLAMA_URL = "http://127.0.0.1:11434/api/embed"
EMBED_MODEL = "bge-m3"
# 路径可配置：优先读环境变量；默认约定 vault 与本仓库同级、数据库在脚本旁
HERE = os.path.dirname(os.path.abspath(__file__))
VAULT_DIR = os.environ.get(
    "KNOWLEDGE_VAULT_DIR",
    os.path.normpath(os.path.join(HERE, "..", "knowledgebase")),
)
DB_PATH = os.environ.get("KNOWLEDGE_DB_PATH", os.path.join(HERE, "vector_index.db"))
PORT = 8765
TOP_N = 5
HIGH_THRESHOLD = 0.9
MID_THRESHOLD = 0.6
# 只索引「已归档」目录，跳过待审核/速记箱
INDEX_FOLDERS = ["01-对话沉淀", "02-项目复盘", "03-概念卡片"]

_sync_lock = threading.Lock()  # 索引同步锁，避免并发写库/重建缓存竞争


def embed(text):
    """调用 Ollama /api/embed，返回归一化向量"""
    body = json.dumps({"model": EMBED_MODEL, "input": text}).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if "embeddings" in data:
        vec = data["embeddings"][0]
    elif "embedding" in data:
        vec = data["embedding"]
    else:
        raise RuntimeError("Ollama /api/embed 响应无向量字段")
    norm = sum(x * x for x in vec) ** 0.5
    if norm > 0:
        vec = [x / norm for x in vec]
    return vec


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS notes (
            path TEXT PRIMARY KEY,
            title TEXT,
            vector BLOB,
            mtime REAL,
            indexed_at REAL
        )"""
    )
    return conn


def pack_vec(vec):
    return struct.pack("%df" % len(vec), *vec)


def unpack_vec(blob):
    return list(struct.unpack("%df" % (len(blob) // 4), blob))


def iter_md_files():
    for folder in INDEX_FOLDERS:
        root = os.path.join(VAULT_DIR, folder)
        if not os.path.isdir(root):
            continue
        for dirpath, _dirs, files in os.walk(root):
            for fn in files:
                if fn.endswith(".md"):
                    yield os.path.join(dirpath, fn)


def read_title(path):
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    i = 0
    if lines and lines[0].strip() == "---":
        i = 1
        while i < len(lines) and lines[i].strip() != "---":
            i += 1
        i += 1  # 跳过 frontmatter 结束行
    first_text = None
    heading = None
    for line in lines[i:]:
        s = line.strip()
        if not s or s.startswith("```"):
            continue  # 跳过空行和代码围栏
        if s.startswith("#"):
            heading = s.lstrip("#").strip()
            break  # 优先取第一个标题
        if first_text is None:
            first_text = s
    title = heading or first_text
    if title is None:
        return os.path.basename(path)
    title = re.sub(r"[*_`~]+", "", title).strip()  # 去掉行内 markdown 标记
    return title or os.path.basename(path)


def index_all():
    """全量扫描归档目录，增量同步索引（新增/变更/删除），返回变更条数。"""
    with _sync_lock:
        conn = get_db()
        count = 0
        seen = set()
        for path in iter_md_files():
            seen.add(path)
            mtime = os.path.getmtime(path)
            row = conn.execute("SELECT mtime FROM notes WHERE path=?", (path,)).fetchone()
            if row and row[0] == mtime:
                continue  # 文件未变，跳过
            with open(path, encoding="utf-8") as f:
                text = f.read()
            vec = embed(text)
            conn.execute(
                "INSERT OR REPLACE INTO notes(path,title,vector,mtime,indexed_at) VALUES(?,?,?,?,?)",
                (path, read_title(path), pack_vec(vec), mtime, 0),
            )
            count += 1
        # 清理已从磁盘删除的笔记的向量（索引里有但磁盘上已不存在）
        stale = [r[0] for r in conn.execute("SELECT path FROM notes").fetchall() if r[0] not in seen]
        for p in stale:
            conn.execute("DELETE FROM notes WHERE path=?", (p,))
            count += 1
        if count:
            conn.commit()
            invalidate_cache()
        conn.close()
        return count


def index_one(path):
    path = os.path.normpath(path)  # 统一正/反斜杠，匹配 index_all 的存储键
    with _sync_lock:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        vec = embed(text)
        conn = get_db()
        conn.execute(
            "INSERT OR REPLACE INTO notes(path,title,vector,mtime,indexed_at) VALUES(?,?,?,?,?)",
            (path, read_title(path), pack_vec(vec), os.path.getmtime(path), 0),
        )
        conn.commit()
        conn.close()
        invalidate_cache()


def delete_one(path):
    path = os.path.normpath(path)  # 统一正/反斜杠，匹配 index_all 的存储键
    with _sync_lock:
        conn = get_db()
        conn.execute("DELETE FROM notes WHERE path=?", (path,))
        conn.commit()
        conn.close()
        invalidate_cache()


def load_index():
    global _index_cache
    if _index_cache is None:
        conn = get_db()
        rows = conn.execute("SELECT path, title, vector FROM notes").fetchall()
        conn.close()
        _index_cache = [(r[0], r[1], unpack_vec(r[2])) for r in rows]
    return _index_cache


def invalidate_cache():
    global _index_cache
    _index_cache = None


_index_cache = None


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def search(text):
    q = embed(text)
    scored = [(dot(q, v), p, t) for p, t, v in load_index()]
    scored.sort(key=lambda x: -x[0])
    top = scored[:TOP_N]
    duplicate = [x for x in top if x[0] > HIGH_THRESHOLD]
    related = [x for x in top if MID_THRESHOLD < x[0] <= HIGH_THRESHOLD]
    return {
        "duplicate_suspect": len(duplicate) > 0,
        "related_notes": [
            {"path": p, "title": t, "score": round(s, 4)}
            for s, p, t in (duplicate + related)
        ],
        "top": [{"path": p, "title": t, "score": round(s, 4)} for s, p, t in top],
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"ok": True})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            obj = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            obj = {}
        if self.path == "/search":
            text = obj.get("text") or obj.get("query") or ""
            if not text:
                return self._send(400, {"error": "缺少 text 字段"})
            index_all()  # 每次检索前增量同步索引，自愈（只重嵌变更文件，开销≈0）
            self._send(200, search(text))
        elif self.path == "/index":
            path = obj.get("path")
            try:
                if path:
                    index_one(path)
                    self._send(200, {"indexed": path})
                else:
                    n = index_all()
                    self._send(200, {"indexed": n})
            except Exception as e:  # noqa: BLE001
                self._send(500, {"error": str(e)})
        elif self.path == "/delete":
            path = obj.get("path")
            if not path:
                return self._send(400, {"error": "缺少 path 字段"})
            delete_one(path)
            self._send(200, {"deleted": path})
        else:
            self._send(404, {"error": "not found"})

    def log_message(self, *_args):
        pass  # 静默，不刷屏


def main():
    if "--index" in sys.argv:
        n = index_all()
        print(f"已索引 {n} 条笔记")
        return
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"检索服务运行在 http://127.0.0.1:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
