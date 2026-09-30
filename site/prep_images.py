import base64, json, os
from pathlib import Path
from PIL import Image

shots = Path(os.environ["TEMP"]) / "shots"
out = Path(__file__).parent
items = {
    "main": ("15_main.png", 820),
    "player": ("3_player_single.png", 1000),
    "editor": ("4_editor.png", 1000),
    "results": ("16_results.png", 1000),
    "attempt": ("17_attempt.png", 1000),
    "multiline": ("14_multiline.png", 1000),
}
data = {}
for key, (name, width) in items.items():
    src = shots / name
    with Image.open(src) as img:
        img = img.convert("RGB")
        h = round(img.height * width / img.width)
        img = img.resize((width, h), Image.LANCZOS)
        tmp = out / f"_{key}.jpg"
        img.save(tmp, "JPEG", quality=78, optimize=True, progressive=True)
    blob = tmp.read_bytes()
    data[key] = "data:image/jpeg;base64," + base64.b64encode(blob).decode()
    print(f"{key}: {len(blob)/1024:.0f} КБ")
    tmp.unlink()

qr = Path(r"C:\Python\MaxTest\maxtest\resources\donate_qr.png")
with Image.open(qr) as img:
    img = img.convert("RGB")
    img = img.resize((300, round(img.height * 300 / img.width)), Image.LANCZOS)
    tmp = out / "_qr.png"
    img.save(tmp, "PNG", optimize=True)
blob = tmp.read_bytes()
data["qr"] = "data:image/png;base64," + base64.b64encode(blob).decode()
print(f"qr: {len(blob)/1024:.0f} КБ")
tmp.unlink()

(out / "images.json").write_text(json.dumps(data), encoding="utf-8")
print("итого base64:", sum(len(v) for v in data.values()) // 1024, "КБ")
