import os, sqlite3, uuid, subprocess, platform, shutil, tempfile
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, abort
from werkzeug.utils import secure_filename
import fitz

BASE = os.path.abspath(os.path.dirname(__file__))
UPLOAD_DIR = os.path.join(BASE, "uploads")
PROCESSED_DIR = os.path.join(BASE, "processed")
DB_PATH = os.path.join(BASE, "xerox.db")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-before-deployment")
app.config["MAX_CONTENT_LENGTH"] = 40 * 1024 * 1024
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
# Demo rate only. Change these in the admin/business configuration before real use.
BW_RATE = float(os.environ.get("BW_RATE", "1.00"))
COLOR_RATE = float(os.environ.get("COLOR_RATE", "5.00"))

def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with db() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY, customer TEXT NOT NULL,
            original_file TEXT NOT NULL, output_file TEXT NOT NULL,
            page_range TEXT NOT NULL, pages INTEGER NOT NULL, copies INTEGER NOT NULL,
            color TEXT NOT NULL, sides TEXT NOT NULL, paper TEXT NOT NULL,
            layout INTEGER NOT NULL, amount REAL NOT NULL, payment_status TEXT NOT NULL,
            status TEXT NOT NULL, created_at TEXT NOT NULL
        )""")
        # Migrate databases created by the older version that stored a phone number.
        cols = [r["name"] for r in con.execute("PRAGMA table_info(orders)")]
        if "phone" in cols:
            con.execute("ALTER TABLE orders RENAME TO orders_old")
            con.execute("""CREATE TABLE orders (
                id TEXT PRIMARY KEY, customer TEXT NOT NULL,
                original_file TEXT NOT NULL, output_file TEXT NOT NULL,
                page_range TEXT NOT NULL, pages INTEGER NOT NULL, copies INTEGER NOT NULL,
                color TEXT NOT NULL, sides TEXT NOT NULL, paper TEXT NOT NULL,
                layout INTEGER NOT NULL, amount REAL NOT NULL, payment_status TEXT NOT NULL,
                status TEXT NOT NULL, created_at TEXT NOT NULL
            )""")
            con.execute("""INSERT INTO orders SELECT id, customer, original_file, output_file,
                page_range, pages, copies, color, sides, paper, layout, amount,
                payment_status, status, created_at FROM orders_old""")
            con.execute("DROP TABLE orders_old")
init_db()

# ---------------------------------------------------------------- file types
PDF_EXT = {".pdf"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".webp"}
WORD_EXT = {".doc", ".docx", ".odt", ".rtf", ".txt"}
ALLOWED_EXT = PDF_EXT | IMAGE_EXT | WORD_EXT

def find_soffice():
    for name in ("soffice", "libreoffice"):
        found = shutil.which(name)
        if found: return found
    for path in (r"C:\Program Files\LibreOffice\program\soffice.exe",
                 r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
                 "/Applications/LibreOffice.app/Contents/MacOS/soffice"):
        if os.path.exists(path): return path
    return None

def word_to_pdf(source, dest):
    """Convert a Word/OpenDocument/RTF/TXT file to PDF. Tries LibreOffice, then MS Word (docx2pdf)."""
    soffice = find_soffice()
    if soffice:
        with tempfile.TemporaryDirectory() as tmp:
            profile = "file:///" + os.path.join(tmp, "profile").replace("\\", "/").lstrip("/")
            try:
                subprocess.run([soffice, f"-env:UserInstallation={profile}", "--headless",
                                "--convert-to", "pdf", "--outdir", tmp, source],
                               check=True, capture_output=True, timeout=120)
            except Exception:
                pass
            produced = os.path.join(tmp, os.path.splitext(os.path.basename(source))[0] + ".pdf")
            if os.path.exists(produced):
                shutil.move(produced, dest)
                return
    try:  # Windows with Microsoft Word installed (.doc/.docx only)
        from docx2pdf import convert
        convert(source, dest)
        if os.path.exists(dest): return
    except Exception:
        pass
    raise ValueError("Could not convert this Word file. The shop PC needs LibreOffice "
                     "(free) or Microsoft Word installed - or upload the file as a PDF.")

def image_to_pdf(source, dest):
    """Place each image (every frame of a multi-page TIFF/GIF) centred on an A4 page.
    Pillow is used so WEBP/GIF/BMP/TIFF work, phone-photo rotation (EXIF) is honoured,
    and transparent images are flattened onto white."""
    from PIL import Image, ImageOps, ImageSequence
    import io
    out = fitz.open()
    with Image.open(source) as im:
        for frame in ImageSequence.Iterator(im):
            fr = ImageOps.exif_transpose(frame.copy())
            if fr.mode in ("RGBA", "LA", "P"):
                fr = fr.convert("RGBA")
                bg = Image.new("RGB", fr.size, (255, 255, 255))
                bg.paste(fr, mask=fr.split()[-1])
                fr = bg
            else:
                fr = fr.convert("RGB")
            buf = io.BytesIO(); fr.save(buf, "PNG")
            w, h = (842, 595) if fr.width > fr.height else (595, 842)
            page = out.new_page(width=w, height=h)
            page.insert_image(fitz.Rect(18, 18, w - 18, h - 18), stream=buf.getvalue(), keep_proportion=True)
            if len(out) >= 100: break
    out.save(dest, garbage=4, deflate=True)
    out.close()

def normalise_to_pdf(source, ext, dest):
    if ext in PDF_EXT:
        shutil.copyfile(source, dest)
    elif ext in IMAGE_EXT:
        image_to_pdf(source, dest)
    else:
        word_to_pdf(source, dest)

def parse_ranges(value, total):
    value = (value or "").strip()
    if not value or value.lower() == "all":
        return list(range(total))
    chosen = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            a, b = int(a), int(b)
            if a > b: a, b = b, a
            if a < 1 or b > total: raise ValueError("Page range is outside the document.")
            chosen.update(range(a-1, b))
        else:
            n = int(part)
            if n < 1 or n > total: raise ValueError("Page number is outside the document.")
            chosen.add(n-1)
    result = sorted(chosen)
    if not result: raise ValueError("Select at least one page.")
    return result

def make_output(source, output, selected, layout):
    src = fitz.open(source)
    out = fitz.open()
    if layout == 1:
        for i in selected:
            out.insert_pdf(src, from_page=i, to_page=i)
    else:
        # N-up: place 2, 4, 6 or 8 source pages on each A4 sheet.
        cols = 2 if layout in (2, 6) else 2
        rows = layout // cols
        sheet = fitz.open()
        page = sheet.new_page(width=595, height=842)
        cell_w, cell_h = page.rect.width / cols, page.rect.height / rows
        for pos, i in enumerate(selected):
            slot = pos % layout
            if slot == 0 and pos > 0:
                page = sheet.new_page(width=595, height=842)
            rect = fitz.Rect((slot % cols)*cell_w, (slot // cols)*cell_h,
                             (slot % cols + 1)*cell_w, (slot // cols + 1)*cell_h)
            page.show_pdf_page(rect, src, i, keep_proportion=True)
        out = sheet
    out.save(output, garbage=4, deflate=True)
    out.close()
    src.close()

@app.route("/")
def index():
    return render_template("index.html")

@app.post("/quote")
def quote():
    f = request.files.get("document")
    if not f or not f.filename:
        flash("Please choose a file to print.")
        return redirect(url_for("index"))
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED_EXT:
        flash("Unsupported file type. Upload a PDF, an image (JPG, PNG, WEBP, GIF, BMP, TIFF) or a Word file (DOC, DOCX, ODT, RTF, TXT).")
        return redirect(url_for("index"))
    safe = secure_filename(f.filename) or f"upload{ext}"
    token = uuid.uuid4().hex
    stored = f"{token}_{safe}"
    path = os.path.join(UPLOAD_DIR, stored)
    pdf_path = os.path.join(UPLOAD_DIR, f"{token}_source.pdf")
    f.save(path)
    try:
        customer = request.form.get("customer", "").strip()
        if not customer:
            raise ValueError("Enter your name.")
        try:
            normalise_to_pdf(path, ext, pdf_path)
            doc = fitz.open(pdf_path)
            total = doc.page_count
            doc.close()
        except ValueError:
            raise
        except Exception:
            raise ValueError("This file looks damaged or could not be read.")
        if total < 1:
            raise ValueError("The document has no pages.")
        selected = parse_ranges(request.form.get("page_range"), total)
        copies = max(1, min(100, int(request.form.get("copies", "1"))))
        color = request.form.get("color", "bw")
        sides = request.form.get("sides", "single")
        paper = request.form.get("paper", "A4")
        layout = int(request.form.get("layout", "1"))
        if color not in ("bw", "color") or sides not in ("single", "double") or paper not in ("A4", "A3") or layout not in (1,2,4,6,8):
            raise ValueError("Invalid print option.")
        output_name = f"{token}_print.pdf"
        output_path = os.path.join(PROCESSED_DIR, output_name)
        make_output(pdf_path, output_path, selected, layout)
        effective_sheets = (len(selected) + layout - 1) // layout
        rate = COLOR_RATE if color == "color" else BW_RATE
        # Double-sided pricing is charged per physical sheet; simple estimate.
        physical = (effective_sheets + 1) // 2 if sides == "double" else effective_sheets
        amount = round(physical * copies * rate, 2)
        order_id = token[:10].upper()
        with db() as con:
            con.execute("""INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (order_id, customer, stored, output_name,
                 request.form.get("page_range", "all"), len(selected), copies,
                 color, sides, paper, layout, amount, "PENDING", "AWAITING_PAYMENT",
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        return render_template("payment.html", order_id=order_id, amount=amount)
    except Exception as e:
        for p in (path, pdf_path):
            try: os.remove(p)
            except OSError: pass
        flash(str(e))
        return redirect(url_for("index"))

@app.post("/demo-pay/<order_id>")
def demo_pay(order_id):
    # Demo only: replace with verified Razorpay/Cashfree webhook flow before launch.
    with db() as con:
        con.execute("UPDATE orders SET payment_status='DEMO_PAID', status='PAID_WAITING_PRINT' WHERE id=? AND payment_status='PENDING'", (order_id,))
    flash("Demo payment recorded. No real money was charged.")
    return redirect(url_for("track", order_id=order_id))

@app.route("/track/<order_id>")
def track(order_id):
    with db() as con:
        order = con.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if not order: abort(404)
    return render_template("track.html", order=order)

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        if request.form.get("password") != ADMIN_PASSWORD:
            flash("Incorrect admin password.")
            return redirect(url_for("admin"))
        return redirect(url_for("dashboard", key=ADMIN_PASSWORD))
    return render_template("admin_login.html")

@app.route("/admin/<key>")
def dashboard(key):
    if key != ADMIN_PASSWORD: abort(403)
    with db() as con:
        orders = con.execute("SELECT * FROM orders ORDER BY created_at DESC").fetchall()
    return render_template("dashboard.html", orders=orders, key=key)

@app.post("/admin/<key>/status/<order_id>")
def update_status(key, order_id):
    if key != ADMIN_PASSWORD: abort(403)
    status = request.form.get("status")
    allowed = {"PAID_WAITING_PRINT", "PRINTING", "READY_FOR_PICKUP", "COMPLETED", "CANCELLED"}
    if status not in allowed: abort(400)
    with db() as con:
        con.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
    return redirect(url_for("dashboard", key=key))

@app.post("/admin/<key>/print/<order_id>")
def print_order(key, order_id):
    if key != ADMIN_PASSWORD: abort(403)
    with db() as con:
        order = con.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if not order or order["payment_status"] not in ("DEMO_PAID", "PAID"): abort(400)
    path = os.path.join(PROCESSED_DIR, order["output_file"])
    try:
        if platform.system() == "Windows":
            os.startfile(path, "print")
        else:
            subprocess.run(["lp", path], check=True, capture_output=True, text=True)
        with db() as con:
            con.execute("UPDATE orders SET status='PRINTING' WHERE id=?", (order_id,))
        flash("Print job sent to the shop computer's default printer. Check printer queue.")
    except Exception as e:
        flash("Could not send to printer. Ensure a printer is installed and configured. " + str(e))
    return redirect(url_for("dashboard", key=key))

@app.route("/file/<kind>/<name>")
def get_file(kind, name):
    folder = UPLOAD_DIR if kind == "uploads" else PROCESSED_DIR if kind == "processed" else None
    if not folder: abort(404)
    return send_from_directory(folder, name, as_attachment=False)

@app.errorhandler(413)
def too_large(_):
    return "File too large. Maximum upload size is 40 MB.", 413

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
