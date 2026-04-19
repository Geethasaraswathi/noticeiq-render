from werkzeug.utils import secure_filename
import os

from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from datetime import datetime
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "noticeiq-secret-key"
DB_NAME = "noticeiq.db"
ADMIN_SECRET_CODE = "NOTICEIQADMIN2026"
UPLOAD_FOLDER = os.path.join("static", "uploads")
ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "gif", "doc", "docx", "ppt", "pptx", "xls", "xlsx", "txt"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            department TEXT,
            year TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS notices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            department TEXT NOT NULL,
            year TEXT NOT NULL,
            category TEXT NOT NULL,
            priority TEXT NOT NULL,
            created_at TEXT NOT NULL,
            posted_by TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS notice_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            notice_id INTEGER NOT NULL,
            file_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            FOREIGN KEY (notice_id) REFERENCES notices (id) ON DELETE CASCADE
        )
    """)

    columns = [col[1] for col in cur.execute("PRAGMA table_info(notices)").fetchall()]
    if "attachment_name" not in columns:
        cur.execute("ALTER TABLE notices ADD COLUMN attachment_name TEXT")
    if "attachment_path" not in columns:
        cur.execute("ALTER TABLE notices ADD COLUMN attachment_path TEXT")

    cur.execute("SELECT COUNT(*) FROM users")
    count = cur.fetchone()[0]

    if count == 0:
        users = [
            (
                "Admin",
                "admin@noticeiq.com",
                generate_password_hash("admin123"),
                "admin",
                "All",
                "All",
            ),
            (
                "Geetha",
                "student@noticeiq.com",
                generate_password_hash("student123"),
                "student",
                "CSE",
                "3",
            ),
        ]

        cur.executemany("""
            INSERT INTO users (name, email, password, role, department, year)
            VALUES (?, ?, ?, ?, ?, ?)
        """, users)

    conn.commit()
    conn.close()


def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                flash("Please login first.")
                return redirect(url_for("login"))

            if role and session.get("role") != role:
                flash("You are not allowed to access that page.")
                return redirect(url_for("dashboard"))

            return f(*args, **kwargs)
        return wrapped
    return decorator


@app.route("/")
def home():
    return render_template("home.html", title="NoticeIQ - Home")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip()
        password = request.form["password"].strip()
        role = request.form["role"].strip()
        department = request.form["department"].strip()
        year = request.form["year"].strip()
        admin_secret = request.form.get("admin_secret", "").strip()

        if role == "admin":
            if admin_secret != ADMIN_SECRET_CODE:
                flash("Wrong Secret Code! Admin account not allowed.")
                return redirect(url_for("register"))

        hashed_password = generate_password_hash(password)

        conn = get_db_connection()

        existing_user = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        if existing_user:
            conn.close()
            flash("Email already registered.")
            return redirect(url_for("register"))

        conn.execute("""
            INSERT INTO users (name, email, password, role, department, year)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, email, hashed_password, role, department, year))

        conn.commit()
        conn.close()

        flash("Registration successful.")
        return redirect(url_for("login"))

    return render_template("register.html", title="Register")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip()
        password = request.form["password"].strip()

        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["role"] = user["role"]
            session["department"] = user["department"]
            session["year"] = user["year"]

            flash("Login successful.")
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.")

    return render_template("login.html", title="Login")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.")
    return redirect(url_for("home"))


@app.route("/dashboard")
@login_required()
def dashboard():
    if session.get("role") == "admin":
        return redirect(url_for("admin_dashboard"))
    return redirect(url_for("student_dashboard"))


@app.route("/admin")
@login_required(role="admin")
def admin_dashboard():
    search = request.args.get("search", "").strip()

    query = """
        SELECT * FROM notices
        WHERE 1=1
    """
    params = []

    if search:
        query += " AND (title LIKE ? OR content LIKE ? OR department LIKE ? OR category LIKE ? OR priority LIKE ?)"
        params.extend([
            f"%{search}%",
            f"%{search}%",
            f"%{search}%",
            f"%{search}%",
            f"%{search}%"
        ])

    query += """
        ORDER BY
        CASE priority
            WHEN 'High' THEN 1
            WHEN 'Medium' THEN 2
            ELSE 3
        END,
        datetime(created_at) DESC
    """

    conn = get_db_connection()
    notices = conn.execute(query, params).fetchall()
    conn.close()

    return render_template(
        "admin_dashboard.html",
        title="Admin Dashboard",
        notices=notices,
        search=search
    )


@app.route("/post-notice", methods=["GET", "POST"])
@login_required(role="admin")
def post_notice():
    if request.method == "POST":
        title = request.form["title"].strip()
        content = request.form["content"].strip()
        department = request.form["department"].strip()
        year = request.form["year"].strip()
        category = request.form["category"].strip()
        priority = request.form["priority"].strip()
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        posted_by = session.get("name", "Admin")

        attachments = request.files.getlist("attachment")

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO notices
            (title, content, department, year, category, priority, created_at, posted_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (title, content, department, year, category, priority, created_at, posted_by))

        notice_id = cur.lastrowid

        for attachment in attachments:
            if attachment and attachment.filename:
                if not allowed_file(attachment.filename):
                    conn.close()
                    flash("Invalid file type. Upload PDF, image, doc, ppt, xls or txt files only.")
                    return redirect(url_for("post_notice"))

                original_name = secure_filename(attachment.filename)
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
                saved_name = f"{timestamp}_{original_name}"
                save_path = os.path.join(app.config["UPLOAD_FOLDER"], saved_name)
                attachment.save(save_path)

                file_path = f"uploads/{saved_name}"

                cur.execute("""
                    INSERT INTO notice_files (notice_id, file_name, file_path)
                    VALUES (?, ?, ?)
                """, (notice_id, original_name, file_path))

        conn.commit()
        conn.close()

        flash("Notice posted successfully.")
        return redirect(url_for("admin_dashboard"))

    return render_template("post_notice.html", title="Post Notice")


@app.route("/edit-notice/<int:notice_id>", methods=["GET", "POST"])
@login_required(role="admin")
def edit_notice(notice_id):
    conn = get_db_connection()
    notice = conn.execute(
        "SELECT * FROM notices WHERE id = ?", (notice_id,)
    ).fetchone()

    if not notice:
        conn.close()
        flash("Notice not found.")
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        title = request.form["title"].strip()
        content = request.form["content"].strip()
        department = request.form["department"].strip()
        year = request.form["year"].strip()
        category = request.form["category"].strip()
        priority = request.form["priority"].strip()

        conn.execute("""
            UPDATE notices
            SET title = ?, content = ?, department = ?, year = ?, category = ?, priority = ?
            WHERE id = ?
        """, (title, content, department, year, category, priority, notice_id))

        conn.commit()
        conn.close()

        flash("Notice updated successfully.")
        return redirect(url_for("admin_dashboard"))

    conn.close()
    return render_template("edit_notice.html", title="Edit Notice", notice=notice)


@app.route("/student")
@login_required(role="student")
def student_dashboard():
    search = request.args.get("search", "").strip()
    category = request.args.get("category", "").strip()
    priority = request.args.get("priority", "").strip()

    department = session.get("department")
    year = session.get("year")

    query = """
        SELECT * FROM notices
        WHERE (department = ? OR department = 'All')
          AND (year = ? OR year = 'All')
    """
    params = [department, year]

    if search:
        query += " AND (title LIKE ? OR content LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])

    if category:
        query += " AND category = ?"
        params.append(category)

    if priority:
        query += " AND priority = ?"
        params.append(priority)

    query += """
        ORDER BY
        CASE priority
            WHEN 'High' THEN 1
            WHEN 'Medium' THEN 2
            ELSE 3
        END,
        datetime(created_at) DESC
    """

    conn = get_db_connection()
    notices = conn.execute(query, params).fetchall()
    conn.close()

    now = datetime.now()
    processed_notices = []

    for notice in notices:
        created_at_dt = datetime.strptime(notice["created_at"], "%Y-%m-%d %H:%M:%S")
        is_new = (now - created_at_dt).days < 1

        processed_notices.append({
            "id": notice["id"],
            "title": notice["title"],
            "content": notice["content"],
            "department": notice["department"],
            "year": notice["year"],
            "category": notice["category"],
            "priority": notice["priority"],
            "created_at": notice["created_at"],
            "is_new": is_new,
            "attachment_name": notice["attachment_name"] if "attachment_name" in notice.keys() else None,
            "attachment_path": notice["attachment_path"] if "attachment_path" in notice.keys() else None
        })

    return render_template(
        "student_dashboard.html",
        title="Student Dashboard",
        notices=processed_notices,
        search=search,
        category=category,
        priority=priority,
        department=department,
        year=year
    )


@app.route("/notice/<int:notice_id>")
@login_required()
def view_notice(notice_id):
    conn = get_db_connection()
    notice = conn.execute(
        "SELECT * FROM notices WHERE id = ?", (notice_id,)
    ).fetchone()

    if not notice:
        conn.close()
        flash("Notice not found.")
        return redirect(url_for("dashboard"))

    files = conn.execute(
        "SELECT * FROM notice_files WHERE notice_id = ?",
        (notice_id,)
    ).fetchall()

    conn.close()

    return render_template("view_notice.html", title="View Notice", notice=notice, files=files)


@app.route("/delete/<int:notice_id>")
@login_required(role="admin")
def delete_notice(notice_id):
    conn = get_db_connection()

    files = conn.execute(
        "SELECT file_path FROM notice_files WHERE notice_id = ?",
        (notice_id,)
    ).fetchall()

    for file in files:
        full_path = os.path.join("static", file["file_path"])
        if os.path.exists(full_path):
            os.remove(full_path)

    conn.execute("DELETE FROM notice_files WHERE notice_id = ?", (notice_id,))
    conn.execute("DELETE FROM notices WHERE id = ?", (notice_id,))
    conn.commit()
    conn.close()

    flash("Notice deleted successfully.")
    return redirect(url_for("admin_dashboard"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True)