from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
from pathlib import Path
import sqlite3, csv, json, os, secrets, time
from datetime import datetime

ROOT = Path(__file__).resolve().parent
DB_DIR = ROOT / "DB"
UPLOAD_DIR = ROOT / "uploads"
INSTANCE_DIR = ROOT / "instance"
for folder in (DB_DIR, UPLOAD_DIR, INSTANCE_DIR):
    folder.mkdir(exist_ok=True)

app = Flask(__name__, instance_path=str(INSTANCE_DIR))
app.config["SECRET_KEY"] = os.environ.get("VSV_SECRET_KEY") or secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024
APP_DB = INSTANCE_DIR / "site.sqlite3"
ALLOWED_EXTENSIONS = {".csv", ".json", ".txt"}
# Configure these credentials with environment variables before deployment.
ADMIN_USER = os.environ.get("VSV_ADMIN_USER", "vsvulskytropuhq")
ADMIN_PASSWORD_HASH = os.environ.get("VSV_ADMIN_PASSWORD_HASH")
# First-run fallback: replace this with a generated hash via the instructions in README.
if not ADMIN_PASSWORD_HASH:
    ADMIN_PASSWORD_HASH = "pbkdf2:sha256:600000$f824490ffa9051fd$d6a861e9dfd2d406d76b876b7e1e5c8275b254cb77f223579442705f0f5132d2"

def db_conn():
    conn = sqlite3.connect(APP_DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db_conn() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS removal_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, contact TEXT NOT NULL, details TEXT DEFAULT '',
            created_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'À traiter'
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, event TEXT NOT NULL, created_at TEXT NOT NULL
        )""")
init_db()

def log_event(event):
    with db_conn() as conn:
        conn.execute("INSERT INTO audit_log(event, created_at) VALUES (?, ?)",
                     (event[:200], datetime.utcnow().isoformat(timespec="seconds") + "Z"))

def admin_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin_login"))
        return fn(*args, **kwargs)
    return wrapped

def allowed_file(filename):
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS

def iter_records():
    """Read only explicitly uploaded CSV/JSON/TXT files in DB; ignore hidden and unsupported files."""
    for path in sorted(DB_DIR.iterdir()):
        if not path.is_file() or path.name.startswith(".") or path.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        try:
            if path.suffix.lower() == ".csv":
                with path.open("r", encoding="utf-8-sig", newline="") as f:
                    for row in csv.DictReader(f):
                        yield path.name, {str(k): str(v) for k, v in row.items() if k is not None}
            elif path.suffix.lower() == ".json":
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            yield path.name, {str(k): str(v) for k, v in item.items()}
                elif isinstance(data, dict):
                    rows = data.get("records", [data])
                    if isinstance(rows, list):
                        for item in rows:
                            if isinstance(item, dict):
                                yield path.name, {str(k): str(v) for k, v in item.items()}
            elif path.suffix.lower() == ".txt":
                with path.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            yield path.name, {"Texte": line}
        except (OSError, UnicodeError, json.JSONDecodeError, csv.Error):
            continue

@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cache-Control"] = "no-store"
    return response

@app.route("/")
def index():
    empty_criteria = {"prenom": "", "nom": "", "annee": "", "ville": "", "code_postal": "", "reference": ""}
    return render_template("index.html", result_count=None, criteria=empty_criteria, results=[])


def normalize_text(value):
    import unicodedata
    value = unicodedata.normalize("NFKD", str(value or "").casefold())
    return "".join(ch for ch in value if not unicodedata.combining(ch)).replace("-", "_").replace(" ", "_")


SEARCH_ALIASES = {
    "prenom": {"prenom", "first_name", "firstname", "given_name"},
    "nom": {"nom", "last_name", "lastname", "surname", "family_name"},
    "annee": {"annee", "year", "annee_naissance", "birth_year"},
    "ville": {"ville", "city", "commune"},
    "code_postal": {"code_postal", "postal_code", "postcode", "zip", "zipcode"},
    "reference": {"reference", "ref", "numero_dossier", "num_dossier", "record_id", "id_dossier"},
}

# Seuls les champs listés ci-dessus participent à la recherche et sont affichés.
# Les numéros de téléphone, e-mails, dates de naissance complètes, adresses et secrets
# ne sont volontairement pas indexés par ce formulaire.

@app.post("/search")
def search():
    criteria = {key: request.form.get(key, "").strip() for key in SEARCH_ALIASES}
    criteria = {key: value[:120] for key, value in criteria.items()}
    active = {key: value for key, value in criteria.items() if value}
    if not active:
        flash("Remplis au moins un critère pour lancer la recherche.", "warning")
        return render_template("index.html", result_count=0, criteria=criteria, results=[])

    results = []
    for filename, row in iter_records():
        normalized_row = {normalize_text(key): str(value or "").strip() for key, value in row.items()}
        matched_fields = {}
        all_match = True
        for criterion, query_value in active.items():
            aliases = SEARCH_ALIASES[criterion]
            found_value = None
            for field_name, field_value in normalized_row.items():
                if field_name in aliases and query_value.casefold() in field_value.casefold():
                    found_value = field_value
                    break
            if found_value is None:
                all_match = False
                break
            matched_fields[criterion] = found_value
        if all_match:
            # N'affiche que les champs non sensibles correspondant aux critères autorisés.
            labels = {"prenom": "Prénom", "nom": "Nom", "annee": "Année", "ville": "Ville", "code_postal": "Code postal", "reference": "Référence"}
            results.append({"source": filename, "fields": [(labels[key], value) for key, value in matched_fields.items()]})
        if len(results) >= 100:
            break
    return render_template("index.html", result_count=len(results), criteria=criteria, results=results)

@app.route("/retrait", methods=["GET", "POST"])
def retrait():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        contact = request.form.get("contact", "").strip()
        details = request.form.get("details", "").strip()
        if not name or not contact:
            flash("Le nom et un moyen de contact sont requis pour traiter la demande.", "warning")
        elif len(name) > 120 or len(contact) > 200 or len(details) > 1000:
            flash("Certains champs sont trop longs.", "warning")
        else:
            with db_conn() as conn:
                conn.execute("INSERT INTO removal_requests(name, contact, details, created_at) VALUES (?, ?, ?, ?)",
                             (name, contact, details, datetime.utcnow().isoformat(timespec="seconds") + "Z"))
            flash("Demande enregistrée. Un administrateur devra la vérifier et la traiter.", "success")
            return redirect(url_for("retrait"))
    return render_template("retrait.html")

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if secrets.compare_digest(username, ADMIN_USER) and check_password_hash(ADMIN_PASSWORD_HASH, password):
            session.clear()
            session["admin"] = True
            log_event("Connexion administrateur")
            return redirect(url_for("admin"))
        time.sleep(0.6)
        flash("Identifiants incorrects.", "error")
    return render_template("admin_login.html")

@app.post("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/admin")
@admin_required
def admin():
    with db_conn() as conn:
        requests_list = conn.execute("SELECT * FROM removal_requests ORDER BY id DESC").fetchall()
        logs = conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 12").fetchall()
    db_files = [p.name for p in sorted(DB_DIR.iterdir()) if p.is_file() and not p.name.startswith(".")]
    return render_template("admin.html", requests_list=requests_list, db_files=db_files, logs=logs)

@app.post("/admin/upload")
@admin_required
def upload():
    uploaded = request.files.get("database")
    if not uploaded or not uploaded.filename:
        flash("Choisis un fichier à importer.", "warning")
        return redirect(url_for("admin"))
    filename = secure_filename(uploaded.filename)
    if not filename or not allowed_file(filename):
        flash("Formats autorisés : CSV, JSON ou TXT.", "error")
        return redirect(url_for("admin"))
    target = DB_DIR / filename
    if target.exists():
        flash("Un fichier porte déjà ce nom. Renomme le fichier avant de le réimporter.", "warning")
        return redirect(url_for("admin"))
    uploaded.save(target)
    log_event("Import de fichier : " + filename)
    flash("Fichier importé dans DB.", "success")
    return redirect(url_for("admin"))

@app.post("/admin/removal/<int:request_id>")
@admin_required
def update_removal(request_id):
    status = request.form.get("status", "À traiter")
    if status not in {"À traiter", "En cours", "Traité"}:
        status = "À traiter"
    with db_conn() as conn:
        conn.execute("UPDATE removal_requests SET status=? WHERE id=?", (status, request_id))
    log_event(f"Mise à jour demande de retrait #{request_id}")
    flash("Statut de la demande mis à jour.", "success")
    return redirect(url_for("admin"))

@app.post("/admin/delete-db")
@admin_required
def delete_db():
    filename = request.form.get("filename", "")
    safe_name = secure_filename(filename)
    target = DB_DIR / safe_name
    if target.is_file() and target.suffix.lower() in ALLOWED_EXTENSIONS:
        target.unlink()
        log_event("Suppression de fichier : " + safe_name)
        flash("Fichier retiré de DB.", "success")
    else:
        flash("Fichier introuvable ou format non autorisé.", "error")
    return redirect(url_for("admin"))

if __name__ == "__main__":
    print("\\n  VS & VUSLKY — serveur local")
    print("  Ouvre http://127.0.0.1:5000 dans ton navigateur.")
    print("  Arrêt : Ctrl+C\\n")
    app.run(host="127.0.0.1", port=5000, debug=False)
