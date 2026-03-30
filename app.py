"""
QR Code Generator — Real-time Edition
Run:  python app.py
Open: http://localhost:5000
"""

from flask import Flask, request, jsonify, send_file
import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers.pil import (
    RoundedModuleDrawer, SquareModuleDrawer, CircleModuleDrawer,
    GappedSquareModuleDrawer, HorizontalBarsDrawer, VerticalBarsDrawer
)
from PIL import Image, ImageDraw
import io, base64, re, os

app = Flask(__name__)

def validate_url(url):
    return bool(re.match(r'^https?://(([a-zA-Z0-9\-]+\.)+[a-zA-Z]{2,})(/[^\s]*)?$', url.strip()))

def smart_crop_square(img):
    w, h = img.size; s = min(w, h)
    return img.crop(((w-s)//2, (h-s)//2, (w+s)//2, (h+s)//2))

def circle_mask(size):
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).ellipse((0, 0, size-1, size-1), fill=255)
    return m

def hex_to_rgb(h):
    h = h.lstrip('#')
    if len(h) == 3: h = ''.join(c*2 for c in h)
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

DRAWER_MAP = {
    "rounded": RoundedModuleDrawer, "square": SquareModuleDrawer,
    "circle": CircleModuleDrawer,   "gapped": GappedSquareModuleDrawer,
    "horizontal": HorizontalBarsDrawer, "vertical": VerticalBarsDrawer,
}
EC_MAP = {
    "L": (qrcode.constants.ERROR_CORRECT_L, "~7%",  "Low"),
    "M": (qrcode.constants.ERROR_CORRECT_M, "~15%", "Medium"),
    "Q": (qrcode.constants.ERROR_CORRECT_Q, "~25%", "Quartile"),
    "H": (qrcode.constants.ERROR_CORRECT_H, "~30%", "High"),
}

@app.route("/")
def index():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
    with open(path, encoding="utf-8") as f: return f.read()

@app.route("/generate", methods=["POST"])
def generate():
    url      = request.form.get("url", "").strip()
    fg       = request.form.get("fg_color", "#000000")
    bg       = request.form.get("bg_color", "#ffffff")
    ec_level = request.form.get("ec_level", "H")
    style    = request.form.get("style", "rounded")
    size     = max(200, min(2000, int(request.form.get("size", 900))))
    border   = max(1, min(10,    int(request.form.get("border", 4))))
    ov_shape = request.form.get("ov_shape", "circle")
    ov_frac  = max(0.05, min(0.45, float(request.form.get("ov_fraction", 0.28))))

    if not validate_url(url):
        return jsonify({"error": "Invalid URL — must start with http:// or https://"}), 400

    ec_const, ec_pct, ec_name = EC_MAP.get(ec_level, EC_MAP["H"])
    qr = qrcode.QRCode(version=None, error_correction=ec_const, box_size=10, border=border)
    qr.add_data(url); qr.make(fit=True)
    qr_version = qr.version
    modules    = qr_version * 4 + 17

    DrawerClass = DRAWER_MAP.get(style, RoundedModuleDrawer)
    qr_img = qr.make_image(
        image_factory=StyledPilImage, module_drawer=DrawerClass(),
        fill_color=fg, back_color=bg,
    ).convert("RGBA")
    qr_img = qr_img.resize((size, size), Image.LANCZOS)

    has_overlay = False
    ov_file = request.files.get("overlay_image")
    if ov_file and ov_file.filename:
        try:
            ov = Image.open(ov_file.stream).convert("RGBA")
            ov = smart_crop_square(ov)
            ov_size = int(size * ov_frac)
            ov = ov.resize((ov_size, ov_size), Image.LANCZOS)
            pad = 8; total = ov_size + pad * 2
            canvas = Image.new("RGBA", (total, total), (0,0,0,0))
            bg_rgb = hex_to_rgb(bg)
            if ov_shape == "circle":
                bm = circle_mask(total)
                canvas.paste(Image.new("RGBA", (total, total), bg_rgb+(255,)), mask=bm)
                canvas.paste(ov, (pad, pad), mask=circle_mask(ov_size))
            else:
                ImageDraw.Draw(canvas).rounded_rectangle(
                    [0,0,total-1,total-1], radius=pad*2, fill=bg_rgb+(255,))
                canvas.paste(ov, (pad, pad), mask=ov.split()[3])
            qr_img.paste(canvas, ((size-total)//2, (size-total)//2), mask=canvas.split()[3])
            has_overlay = True
        except: pass

    buf = io.BytesIO()
    qr_img.convert("RGB").save(buf, "PNG", optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode()

    overlay_coverage = round(ov_frac * ov_frac * 100, 1) if has_overlay else 0
    ec_threshold = {"L": 7, "M": 15, "Q": 25, "H": 30}
    scannable = overlay_coverage <= ec_threshold.get(ec_level, 30)

    return jsonify({
        "image": f"data:image/png;base64,{b64}",
        "ec_level": ec_level, "ec_name": ec_name, "ec_pct": ec_pct,
        "url": url, "size": size, "style": style,
        "version": qr_version, "modules": modules,
        "overlay_coverage": overlay_coverage, "scannable": scannable,
    })

@app.route("/download", methods=["POST"])
def download():
    data = request.json.get("image", "")
    b64  = data.split(",")[1] if "," in data else data
    buf  = io.BytesIO(base64.b64decode(b64)); buf.seek(0)
    return send_file(buf, mimetype="image/png", as_attachment=True, download_name="qr_code.png")

if __name__ == "__main__":
    print("\n🔲  QR Code Generator — Real-time Edition → http://localhost:5000\n")
    app.run(debug=True, port=5000)