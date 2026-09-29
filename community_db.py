"""مجتمع الطلاب: مشاركات وتعليقات ولايكات وبلاغات، مخزّنة في SQLite.

باقي الموقع (المستخدمين والتقييمات والواجبات) لسه على ملفات JSON،
والملف ده بيتعامل مع قاعدة community.db جوه DATA_DIR بس.
"""
import os
import sqlite3
from contextlib import contextmanager

POST_MAX = 1000        # أقصى عدد حروف للمشاركة
COMMENT_MAX = 500      # أقصى عدد حروف للتعليق
POSTS_PER_MIN = 3      # حد النشر في الدقيقة للمستخدم الواحد
COMMENTS_PER_MIN = 6   # حد التعليقات في الدقيقة
PAGE_SIZE = 50         # عدد المشاركات المعروضة

_db_path = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    subject    TEXT NOT NULL DEFAULT '',
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_posts_created ON posts (created_at DESC);

CREATE TABLE IF NOT EXISTS comments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id    INTEGER NOT NULL REFERENCES posts (id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL,
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_comments_post ON comments (post_id);

CREATE TABLE IF NOT EXISTS likes (
    post_id INTEGER NOT NULL REFERENCES posts (id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL,
    PRIMARY KEY (post_id, user_id)
);

CREATE TABLE IF NOT EXISTS reports (
    kind       TEXT NOT NULL,      -- 'post' أو 'comment'
    target_id  INTEGER NOT NULL,
    user_id    INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (kind, target_id, user_id)
);
"""


def init_db(data_dir):
    global _db_path
    _db_path = os.path.join(data_dir, "community.db")
    conn = sqlite3.connect(_db_path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


@contextmanager
def _tx():
    conn = sqlite3.connect(_db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ------------------------------------------------------------
#  القراءة
# ------------------------------------------------------------
def list_posts(viewer_id, subject=None):
    """المشاركات الأحدث أولًا، ومعاها التعليقات وعدد اللايكات."""
    sql = """
        SELECT p.id, p.user_id, p.subject, p.body, p.created_at,
               (SELECT COUNT(*) FROM likes l WHERE l.post_id = p.id) AS likes,
               EXISTS (SELECT 1 FROM likes l
                       WHERE l.post_id = p.id AND l.user_id = ?) AS liked,
               (SELECT COUNT(*) FROM reports r
                WHERE r.kind = 'post' AND r.target_id = p.id) AS reports
        FROM posts p
    """
    params = [viewer_id]
    if subject:
        sql += " WHERE p.subject = ?"
        params.append(subject)
    sql += " ORDER BY p.created_at DESC, p.id DESC LIMIT ?"
    params.append(PAGE_SIZE)

    with _tx() as c:
        posts = [dict(r) for r in c.execute(sql, params)]
        by_id = {p["id"]: p for p in posts}
        for p in posts:
            p["comments"] = []
        if by_id:
            marks = ",".join("?" * len(by_id))
            rows = c.execute(
                f"""SELECT c.id, c.post_id, c.user_id, c.body, c.created_at,
                           (SELECT COUNT(*) FROM reports r
                            WHERE r.kind = 'comment' AND r.target_id = c.id) AS reports
                    FROM comments c
                    WHERE c.post_id IN ({marks})
                    ORDER BY c.created_at, c.id""",
                list(by_id),
            )
            for r in rows:
                by_id[r["post_id"]]["comments"].append(dict(r))
    return posts


# ------------------------------------------------------------
#  الكتابة (كل دالة بترجع (نجح؟، رسالة) أو حالة نصية)
# ------------------------------------------------------------
def _clean(body, limit):
    body = (body or "").strip()
    if not body:
        return None, "اكتب حاجة الأول!"
    if len(body) > limit:
        return None, f"النص أطول من {limit} حرف."
    return body, None


def create_post(user_id, subject, body):
    body, err = _clean(body, POST_MAX)
    if err:
        return False, err
    with _tx() as c:
        recent = c.execute(
            "SELECT COUNT(*) FROM posts WHERE user_id = ? "
            "AND created_at > datetime('now', '-60 seconds')",
            (user_id,),
        ).fetchone()[0]
        if recent >= POSTS_PER_MIN:
            return False, "براحة شوية! استنى دقيقة وحاول تاني."
        c.execute(
            "INSERT INTO posts (user_id, subject, body) VALUES (?, ?, ?)",
            (user_id, subject or "", body),
        )
    return True, "اتنشرت مشاركتك!"


def add_comment(user_id, post_id, body):
    body, err = _clean(body, COMMENT_MAX)
    if err:
        return False, err
    with _tx() as c:
        if not c.execute("SELECT 1 FROM posts WHERE id = ?", (post_id,)).fetchone():
            return False, "المشاركة دي اتحذفت."
        recent = c.execute(
            "SELECT COUNT(*) FROM comments WHERE user_id = ? "
            "AND created_at > datetime('now', '-60 seconds')",
            (user_id,),
        ).fetchone()[0]
        if recent >= COMMENTS_PER_MIN:
            return False, "براحة شوية! استنى دقيقة وحاول تاني."
        c.execute(
            "INSERT INTO comments (post_id, user_id, body) VALUES (?, ?, ?)",
            (post_id, user_id, body),
        )
    return True, "اتضاف تعليقك."


def toggle_like(user_id, post_id):
    with _tx() as c:
        if not c.execute("SELECT 1 FROM posts WHERE id = ?", (post_id,)).fetchone():
            return False
        cur = c.execute(
            "DELETE FROM likes WHERE post_id = ? AND user_id = ?", (post_id, user_id)
        )
        if cur.rowcount == 0:
            c.execute(
                "INSERT INTO likes (post_id, user_id) VALUES (?, ?)", (post_id, user_id)
            )
    return True


def delete_post(post_id, user_id, is_admin):
    """بترجع: 'ok' أو 'missing' أو 'forbidden'."""
    with _tx() as c:
        row = c.execute("SELECT user_id FROM posts WHERE id = ?", (post_id,)).fetchone()
        if not row:
            return "missing"
        if row["user_id"] != user_id and not is_admin:
            return "forbidden"
        c.execute(
            "DELETE FROM reports WHERE kind = 'comment' AND target_id IN "
            "(SELECT id FROM comments WHERE post_id = ?)",
            (post_id,),
        )
        c.execute("DELETE FROM reports WHERE kind = 'post' AND target_id = ?", (post_id,))
        c.execute("DELETE FROM posts WHERE id = ?", (post_id,))  # التعليقات واللايكات بتتحذف تلقائيًا
    return "ok"


def delete_comment(comment_id, user_id, is_admin):
    """بترجع (الحالة، post_id)."""
    with _tx() as c:
        row = c.execute(
            "SELECT user_id, post_id FROM comments WHERE id = ?", (comment_id,)
        ).fetchone()
        if not row:
            return "missing", None
        if row["user_id"] != user_id and not is_admin:
            return "forbidden", row["post_id"]
        c.execute("DELETE FROM reports WHERE kind = 'comment' AND target_id = ?", (comment_id,))
        c.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
    return "ok", row["post_id"]


def report(kind, target_id, user_id):
    table = {"post": "posts", "comment": "comments"}.get(kind)
    if not table:
        return False, "نوع البلاغ غير صحيح."
    with _tx() as c:
        if not c.execute(f"SELECT 1 FROM {table} WHERE id = ?", (target_id,)).fetchone():
            return False, "العنصر ده اتحذف."
        cur = c.execute(
            "INSERT OR IGNORE INTO reports (kind, target_id, user_id) VALUES (?, ?, ?)",
            (kind, target_id, user_id),
        )
    if cur.rowcount:
        return True, "وصل البلاغ للأدمن، شكرًا!"
    return True, "أنت بلّغت عن ده قبل كده."