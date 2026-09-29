import os
import json
import tempfile
import threading
from datetime import datetime, timezone

import cloudinary
import cloudinary.uploader
from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_bcrypt import Bcrypt
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user,
)

from icons import icon
import community_db as cdb

# تحميل ملف .env محليًا (على Render مش محتاجه)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")

bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

cloudinary.config(
    cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
    api_key=os.environ.get("CLOUDINARY_API_KEY"),
    api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
)

# ============================================================
#  المواد الدراسية (مصدر واحد للقوائم في كل الصفحات)
# ============================================================
SUBJECTS = [
    {"name": "رياضيات", "icon": "calculator"},
    {"name": "علوم", "icon": "flask"},
    {"name": "لغة عربية", "icon": "book-open"},
    {"name": "إنجليزي", "icon": "languages"},
    {"name": "تاريخ", "icon": "globe"},
    {"name": "فلسفه", "icon": "brain"},
]
SUBJECT_ICONS = {s["name"]: s["icon"] for s in SUBJECTS}


@app.context_processor
def inject_globals():
    return {"SUBJECTS": SUBJECTS, "SUBJECT_ICONS": SUBJECT_ICONS, "icon": icon}


# ============================================================
#  تخزين البيانات في ملفات JSON
# ============================================================
DATA_DIR = os.environ.get(
    "DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
)
os.makedirs(DATA_DIR, exist_ok=True)

_lock = threading.RLock()


def _path(name):
    return os.path.join(DATA_DIR, f"{name}.json")


def load(name):
    with _lock:
        try:
            with open(_path(name), "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []


def save(name, data):
    with _lock:
        fd, tmp = tempfile.mkstemp(dir=DATA_DIR, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _path(name))


def next_id(items):
    return max((i["id"] for i in items), default=0) + 1


# ============================================================
#  المستخدمين
# ============================================================
class User(UserMixin):
    def __init__(self, d):
        self.id = d["id"]
        self.username = d["username"]
        self.password = d["password"]
        self.role = d.get("role", "user")
        self.profile_pic = d.get("profile_pic")
        self.cover_pic = d.get("cover_pic")


def get_user_by_id(user_id):
    for u in load("users"):
        if str(u["id"]) == str(user_id):
            return User(u)
    return None


def get_user_by_username(username):
    for u in load("users"):
        if u["username"] == username:
            return User(u)
    return None


@login_manager.user_loader
def load_user(user_id):
    return get_user_by_id(user_id)


def ensure_admin():
    admin_name = os.environ.get("ADMIN_USERNAME")
    admin_pass = os.environ.get("ADMIN_PASSWORD")
    if not admin_name or not admin_pass:
        return
    with _lock:
        users = load("users")
        if any(u["username"] == admin_name for u in users):
            return
        users.append({
            "id": next_id(users),
            "username": admin_name,
            "password": bcrypt.generate_password_hash(admin_pass).decode("utf-8"),
            "role": "admin",
            "profile_pic": None,
            "cover_pic": None,
        })
        save("users", users)


ensure_admin()
cdb.init_db(DATA_DIR)  # قاعدة SQLite بتاعة المجتمع


# ============================================================
#  دوال مساعدة
# ============================================================
def with_authors(items):
    """إضافة اسم الشخص اللي رفع العنصر (author) عشان القوالب تعرضه."""
    names = {u["id"]: u["username"] for u in load("users")}
    for i in items:
        i["author"] = names.get(i.get("user_id"), "مجهول")
    return items


def group_by_subject(items):
    """تجميع حسب المادة بترتيب SUBJECTS، والأحدث الأول."""
    grouped = {}
    for s in SUBJECTS:
        rows = [i for i in items if i["subject"] == s["name"]]
        if rows:
            grouped[s["name"]] = rows[::-1]
    for i in reversed(items):
        if i["subject"] not in SUBJECT_ICONS:
            grouped.setdefault(i["subject"], []).append(i)
    return grouped


def is_valid_link(link):
    return bool(link) and link.startswith(("http://", "https://"))


def upload_image(file_storage):
    if file_storage and file_storage.filename != "":
        return cloudinary.uploader.upload(file_storage)["secure_url"]
    return None

def _profile_stats(user_id):
    return (
        sum(1 for r in load("reviews") if r.get("user_id") == user_id),
        sum(1 for h in load("homeworks") if h.get("user_id") == user_id),
    )
# ============================================================
#  الصفحات
# ============================================================
@app.route("/")
@login_required
def home():
    reviews = load("reviews")
    homeworks = load("homeworks")
    stats = {
        "reviews": len(reviews),
        "homeworks": len(homeworks),
        "students": len(load("users")),
    }
    subject_stats = [
        {
            "name": s["name"],
            "icon": s["icon"],
            "reviews": sum(1 for r in reviews if r["subject"] == s["name"]),
            "homeworks": sum(1 for h in homeworks if h["subject"] == s["name"]),
        }
        for s in SUBJECTS
    ]
    students = sorted(
        (
            {
                "id": u["id"],
                "username": u["username"],
                "profile_pic": u.get("profile_pic"),
                "role": u.get("role", "user"),
            }
            for u in load("users")
        ),
        key=lambda s: s["username"].lower(),
    )
    return render_template(
        "index.html", username=current_user.username,
        profile_pic=current_user.profile_pic,
        stats=stats, subject_stats=subject_stats, students=students,
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        if not username or not password:
            flash("يجب ملء جميع الحقول!", "danger")
            return redirect(url_for("register"))

        if get_user_by_username(username):
            flash("اسم المستخدم موجود بالفعل!", "danger")
            return redirect(url_for("register"))

        try:
            profile_pic_url = upload_image(request.files.get("profile_pic"))
            cover_pic_url = upload_image(request.files.get("cover_pic"))
        except Exception:
            flash("تعذر رفع الصور، تأكد من إعدادات Cloudinary أو جرب صورة تانية.", "danger")
            return redirect(url_for("register"))

        hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")

        with _lock:
            users = load("users")
            users.append({
                "id": next_id(users),
                "username": username,
                "password": hashed_password,
                "role": "user",
                "profile_pic": profile_pic_url,
                "cover_pic": cover_pic_url,
            })
            save("users", users)

        flash("تم إنشاء الحساب بنجاح، سجّل دخولك!", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/upload_eva", methods=["GET", "POST"])
@login_required
def upload_review():
    if request.method == "POST":
        review_name = request.form.get("review_name", "").strip()
        review_link = request.form.get("review_link", "").strip()
        subject = request.form.get("subject")

        if not review_name or not review_link or not subject:
            flash("يجب ملء جميع الحقول!", "danger")
            return redirect(url_for("upload_review"))

        if subject not in SUBJECT_ICONS or not is_valid_link(review_link):
            flash("المادة أو الرابط غير صحيح!", "danger")
            return redirect(url_for("upload_review"))

        with _lock:
            reviews = load("reviews")
            reviews.append({
                "id": next_id(reviews),
                "user_id": current_user.id,
                "review_name": review_name,
                "review_link": review_link,
                "subject": subject,
            })
            save("reviews", reviews)

        flash("تم رفع التقييم بنجاح!", "success")
        return redirect(url_for("view_reviews"))

    return render_template("upload_eva.html")


@app.route("/delete_review/<int:review_id>", methods=["POST"])
@login_required
def delete_review(review_id):
    if current_user.role != "admin":
        return "غير مصرح لك بحذف التقييمات", 403

    with _lock:
        reviews = load("reviews")
        if not any(r["id"] == review_id for r in reviews):
            abort(404)
        save("reviews", [r for r in reviews if r["id"] != review_id])

    flash("تم حذف التقييم.", "success")
    return redirect(url_for("view_reviews"))


@app.route("/eva")
@login_required
def view_reviews():
    grouped_reviews = group_by_subject(with_authors(load("reviews")))
    return render_template("eva.html", grouped_reviews=grouped_reviews)


@app.route("/upload_homework", methods=["GET", "POST"])
@login_required
def upload_homework():
    if request.method == "POST":
        homework_name = request.form.get("homework_name", "").strip()
        subject = request.form.get("subject")
        homework_link = request.form.get("homework_link", "").strip()

        if not homework_name or not subject or not homework_link:
            flash("يجب ملء جميع الحقول!", "danger")
            return redirect(url_for("upload_homework"))

        if subject not in SUBJECT_ICONS or not is_valid_link(homework_link):
            flash("المادة أو الرابط غير صحيح!", "danger")
            return redirect(url_for("upload_homework"))

        with _lock:
            homeworks = load("homeworks")
            homeworks.append({
                "id": next_id(homeworks),
                "user_id": current_user.id,
                "homework_name": homework_name,
                "subject": subject,
                "homework_link": homework_link,
            })
            save("homeworks", homeworks)

        flash("تم رفع الواجب بنجاح!", "success")
        return redirect(url_for("view_homeworks"))

    return render_template("upload_homework.html")


@app.route("/homeworks")
@login_required
def view_homeworks():
    grouped_homeworks = group_by_subject(with_authors(load("homeworks")))
    return render_template("homeworks.html", grouped_homeworks=grouped_homeworks)


@app.route("/delete_homework/<int:homework_id>", methods=["POST"])
@login_required
def delete_homework(homework_id):
    if current_user.role != "admin":
        flash("غير مسموح لك بحذف الواجبات!", "danger")
        return redirect(url_for("view_homeworks"))

    with _lock:
        homeworks = load("homeworks")
        if not any(h["id"] == homework_id for h in homeworks):
            abort(404)
        save("homeworks", [h for h in homeworks if h["id"] != homework_id])

    flash("تم حذف الواجب بنجاح!", "success")
    return redirect(url_for("view_homeworks"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        user = get_user_by_username(username)
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for("home"))
        flash("اسم المستخدم أو كلمة المرور غير صحيحة!", "danger")
        return redirect(url_for("login"))
    return render_template("login.html")



@app.route("/profile")
@login_required
def profile():
    my_reviews, my_homeworks = _profile_stats(current_user.id)
    return render_template(
        "profile.html", username=current_user.username,
        profile_pic=current_user.profile_pic, cover_pic=current_user.cover_pic,
        role=current_user.role, my_reviews=my_reviews, my_homeworks=my_homeworks,
        is_own=True,
    )

# ألصق ده في app.py بعد route الـ profile وقبل route الـ logout.
# (لو كنت ضفت edit_profile و change_password قبل كده، امسحهم: مبقوش مستخدمين.)

@app.route("/profile/picture", methods=["POST"])
@login_required
def change_picture():
    file = request.files.get("profile_pic")

    if not file or file.filename == "":
        flash("اختار صورة الأول!", "danger")
        return redirect(url_for("profile"))

    if not (file.mimetype or "").startswith("image/"):
        flash("الملف لازم يكون صورة!", "danger")
        return redirect(url_for("profile"))

    try:
        url = upload_image(file)
    except Exception:
        flash("تعذر رفع الصورة، جرب صورة تانية.", "danger")
        return redirect(url_for("profile"))

    with _lock:
        users = load("users")
        me = next((u for u in users if u["id"] == current_user.id), None)
        if me is None:
            abort(404)
        me["profile_pic"] = url
        save("users", users)

    flash("اتغيرت صورتك.", "success")
    return redirect(url_for("profile"))

@app.route("/user/<int:user_id>")
@login_required
def user_profile(user_id):
    if user_id == current_user.id:
        return redirect(url_for("profile"))
    user = get_user_by_id(user_id)
    if not user:
        abort(404)
    my_reviews, my_homeworks = _profile_stats(user.id)
    return render_template(
        "profile.html", username=user.username,
        profile_pic=user.profile_pic, cover_pic=user.cover_pic,
        role=user.role, my_reviews=my_reviews, my_homeworks=my_homeworks,
        is_own=False,
    )

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# ============================================================
#  المجتمع (SQLite)
# ============================================================
def _ago(ts):
    try:
        then = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return ""
    s = int((datetime.now(timezone.utc) - then).total_seconds())
    if s < 60:
        return "دلوقتي"
    if s < 3600:
        return f"من {s // 60} دقيقة"
    if s < 86400:
        return f"من {s // 3600} ساعة"
    if s < 86400 * 30:
        return f"من {s // 86400} يوم"
    return then.strftime("%Y-%m-%d")


def _decorate(posts):
    """إضافة اسم وصورة صاحب كل مشاركة/تعليق (المستخدمين لسه في JSON)."""
    users = {u["id"]: u for u in load("users")}

    def who(uid):
        u = users.get(uid)
        return (u["username"], u.get("profile_pic")) if u else ("مجهول", None)

    for p in posts:
        p["author"], p["author_pic"] = who(p["user_id"])
        p["ago"] = _ago(p["created_at"])
        for c in p["comments"]:
            c["author"], c["author_pic"] = who(c["user_id"])
            c["ago"] = _ago(c["created_at"])
    return posts


def _back(post_id=None, open_comments=False):
    subject = request.form.get("subject") or None
    args = {}
    if subject in SUBJECT_ICONS:
        args["subject"] = subject
    if post_id and open_comments:
        args["open"] = post_id
    url = url_for("community", **args)
    return redirect(url + (f"#post-{post_id}" if post_id else ""))


@app.route("/community")
@login_required
def community():
    subject = request.args.get("subject") or None
    if subject not in SUBJECT_ICONS:
        subject = None
    posts = _decorate(cdb.list_posts(current_user.id, subject))
    return render_template(
        "community.html", posts=posts, current_subject=subject,
        open_id=request.args.get("open", type=int),
        post_max=cdb.POST_MAX, comment_max=cdb.COMMENT_MAX,
    )


@app.route("/community/post", methods=["POST"])
@login_required
def community_post():
    subject = request.form.get("post_subject", "")
    if subject not in SUBJECT_ICONS:
        subject = ""
    ok, msg = cdb.create_post(current_user.id, subject, request.form.get("body", ""))
    flash(msg, "success" if ok else "danger")
    return redirect(url_for("community"))


@app.route("/community/post/<int:post_id>/comment", methods=["POST"])
@login_required
def community_comment(post_id):
    ok, msg = cdb.add_comment(current_user.id, post_id, request.form.get("body", ""))
    if not ok:
        flash(msg, "danger")
    return _back(post_id, open_comments=True)


@app.route("/community/post/<int:post_id>/like", methods=["POST"])
@login_required
def community_like(post_id):
    if not cdb.toggle_like(current_user.id, post_id):
        abort(404)
    return _back(post_id)


@app.route("/community/post/<int:post_id>/delete", methods=["POST"])
@login_required
def community_delete_post(post_id):
    status = cdb.delete_post(post_id, current_user.id, current_user.role == "admin")
    if status == "missing":
        abort(404)
    if status == "forbidden":
        abort(403)
    flash("اتحذفت المشاركة.", "success")
    return _back()


@app.route("/community/comment/<int:comment_id>/delete", methods=["POST"])
@login_required
def community_delete_comment(comment_id):
    status, post_id = cdb.delete_comment(
        comment_id, current_user.id, current_user.role == "admin"
    )
    if status == "missing":
        abort(404)
    if status == "forbidden":
        abort(403)
    return _back(post_id, open_comments=True)


@app.route("/community/report/<kind>/<int:target_id>", methods=["POST"])
@login_required
def community_report(kind, target_id):
    ok, msg = cdb.report(kind, target_id, current_user.id)
    flash(msg, "success" if ok else "danger")
    return _back(request.form.get("post_id", type=int), open_comments=(kind == "comment"))


if __name__ == "__main__":
    app.run(debug=True)