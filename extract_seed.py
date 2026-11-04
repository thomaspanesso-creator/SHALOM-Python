"""Generate seed_services.py from the original Java DataInitializer."""
import re
from pathlib import Path

JAVA = Path(r"C:\Users\garav\Downloads\SHALOM-Java-main\SHALOM-Java-main\src\main\java\com\shalom\config\DataInitializer.java")
OUT = Path(__file__).resolve().parents[1] / "shalom" / "seed_services.py"

text = JAVA.read_text(encoding="utf-8")

calls = re.findall(
    r'agregarServicio\(\s*"([^"]*)"\s*,\s*"([^"]*)"\s*,\s*([\d_]+)\s*,\s*(\d+)\s*,\s*"([^"]*)"\s*,',
    text,
)
images = dict(re.findall(r'case\s+"([^"]+)"\s*->\s*"([^"]+)"\s*;', text))

print(f"services: {len(calls)}, images: {len(images)}")

lines = [
    '"""Seed data for the service catalog (ported from DataInitializer.java)."""',
    "",
    "SERVICES = [",
]
missing = []
for name, desc, price, duration, category in calls:
    image = images.get(name)
    if image is None:
        missing.append(name)
        image = "corte-cabello-dama.jpg"
    lines.append("    {")
    lines.append(f"        'name': {name!r},")
    lines.append(f"        'description': {desc!r},")
    lines.append(f"        'price': {int(price.replace('_', ''))},")
    lines.append(f"        'duration': {int(duration)},")
    lines.append(f"        'category': {category!r},")
    lines.append(f"        'image': '/img/servicios/{image}',")
    lines.append("    },")
lines.append("]")
lines.append("")

OUT.write_text("\n".join(lines), encoding="utf-8")
print("missing images:", missing)
