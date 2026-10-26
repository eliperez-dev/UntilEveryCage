"""Retile NASA's reusable August 2004 Blue Marble composite, z0-5 only.

Source: https://science.nasa.gov/earth/earth-observatory/blue-marble-next-generation/base-map/
Use: https://www.nasa.gov/nasa-brand-center/images-and-media/
Requires Pillow, used only for asset preparation, not by the application.
"""
from pathlib import Path
import hashlib
import io
import json
import math
import sys

frontend = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(frontend.parent / 'target/frontend-ui-qa/world-image-tools'))
from PIL import Image

source = frontend.parent / 'target/frontend-ui-qa/nasa-world-200408-5400.jpg'
image = Image.open(source).convert('RGB')
size = 8192
mesh = []
for y in range(0, size, 16):
    def source_y(pixel):
        latitude = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * pixel / size))))
        return (90 - latitude) / 180 * image.height
    top, bottom = source_y(y), source_y(min(size, y + 16))
    mesh.append(((0, y, size, min(size, y + 16)), (0, top, 0, bottom, image.width, bottom, image.width, top)))
mercator = image.transform((size, size), Image.Transform.MESH, mesh, Image.Resampling.BICUBIC)

def tile_id(z, x, y):
    count = 1 << z
    value = (count * count - 1) // 3
    step = count // 2
    while step:
        rx, ry = bool(x & step), bool(y & step)
        value += step * step * ((3 * int(rx)) ^ int(ry))
        if not ry:
            if rx:
                x, y = step - 1 - x, step - 1 - y
            x, y = y, x
        step //= 2
    return value

chunks = [bytearray() for _ in range(6)]
positions = {}
tiles = [None] * 1365
for z in range(6):
    count = 1 << z
    level = mercator.resize((256 * count, 256 * count), Image.Resampling.LANCZOS)
    for x in range(count):
        for y in range(count):
            tile = level.crop((256 * x, 256 * y, 256 * (x + 1), 256 * (y + 1)))
            buffer = io.BytesIO()
            tile.save(buffer, format='WEBP', quality=60, method=4)
            data = buffer.getvalue()
            digest = hashlib.sha256(data).hexdigest()
            if digest not in positions:
                chunk = z
                positions[digest] = [chunk, len(chunks[chunk]), len(data)]
                chunks[chunk].extend(data)
            tiles[tile_id(z, x, y)] = positions[digest]

assets = []
directory = frontend / 'public/world-baseline'
directory.mkdir(exist_ok=True)
for index, data in enumerate(chunks):
    digest = hashlib.sha256(data).hexdigest()
    name = f"satellite-z{index}.{digest[:12]}.bin"
    (directory / name).write_bytes(data)
    assets.append(dict(file=name, bytes=len(data), sha256=digest, zoom=index))
manifest = dict(source='NASA Blue Marble Next Generation, August 2004, 5400x2700', source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), assets=assets, tiles=tiles)
(frontend / 'src/map/assets/worldSatelliteManifest.json').write_text(json.dumps(manifest, separators=(',', ':')), encoding='utf-8')
print(json.dumps(dict(assets=assets, totalBytes=sum(len(chunk) for chunk in chunks))))
