"""One-off script to populate test images in the local backup folders."""
import struct, os
from PIL import Image, ImageDraw
from datetime import datetime


def make_exif_bytes(dt: datetime) -> bytes:
    dt_str = dt.strftime("%Y:%m:%d %H:%M:%S").encode() + b"\x00"
    endian = b"II"
    magic  = struct.pack("<H", 42)
    offset = struct.pack("<I", 8)
    ifd_count    = struct.pack("<H", 1)
    entry_tag    = struct.pack("<H", 0x9003)
    entry_type   = struct.pack("<H", 2)
    entry_count  = struct.pack("<I", len(dt_str))
    string_offset = struct.pack("<I", 8 + 2 + 12 + 4)
    entry    = entry_tag + entry_type + entry_count + string_offset
    next_ifd = struct.pack("<I", 0)
    ifd_block = ifd_count + entry + next_ifd + dt_str
    tiff = endian + magic + offset + ifd_block
    return b"Exif\x00\x00" + tiff


def create_image(path: str, label: str, color: tuple, dt: datetime) -> None:
    img  = Image.new("RGB", (400, 300), color=color)
    draw = ImageDraw.Draw(img)
    draw.rectangle([10, 10, 390, 290], outline="white", width=3)
    draw.text((20, 20), label,                   fill="white")
    draw.text((20, 50), dt.strftime("%Y-%m-%d"), fill="white")
    draw.text((20, 80), os.path.basename(path),  fill="white")
    img.save(path, format="JPEG", exif=make_exif_bytes(dt), quality=85)
    print(f"  Created: {path}")


alice = r"C:\Temp\pbo\backups\alice"
bob   = r"C:\Temp\pbo\backups\bob"

files = [
    # Alice – 3 date groups, 5 images
    (alice, "alice_2026_01_10_beach.jpg",     "Alice - January beach trip",          ( 30,  80, 120), datetime(2026, 1, 10, 10, 23,  0)),
    (alice, "alice_2026_01_10_sunset.jpg",    "Alice - January beach sunset",        ( 30,  80, 120), datetime(2026, 1, 10, 18, 45,  0)),
    (alice, "alice_2026_02_14_dinner.jpg",    "Alice - Valentines dinner",           (120,  30,  60), datetime(2026, 2, 14, 20,  5,  0)),
    (alice, "alice_2026_03_22_hike.jpg",      "Alice - Spring hike",                 ( 40, 110,  40), datetime(2026, 3, 22,  9, 15,  0)),
    (alice, "alice_2026_03_22_waterfall.jpg", "Alice - Spring waterfall",            ( 40, 110,  40), datetime(2026, 3, 22, 11, 30,  0)),
    # Bob – 3 date groups, 5 images (March 22 overlaps with Alice to test grouping)
    (bob,   "bob_2026_01_15_snow.jpg",        "Bob - January snow day",              ( 60, 120, 160), datetime(2026, 1, 15,  8,  0,  0)),
    (bob,   "bob_2026_02_20_party.jpg",       "Bob - February party",                (160,  60,  80), datetime(2026, 2, 20, 21, 30,  0)),
    (bob,   "bob_2026_02_20_cake.jpg",        "Bob - February cake",                 (160,  60,  80), datetime(2026, 2, 20, 22,  0,  0)),
    (bob,   "bob_2026_03_22_hike.jpg",        "Bob - Spring hike (same day Alice)",  ( 40, 110,  40), datetime(2026, 3, 22,  9, 20,  0)),
    (bob,   "bob_2026_04_01_april.jpg",       "Bob - April Fools",                   (140,  90,  20), datetime(2026, 4,  1, 12,  0,  0)),
]

for folder, filename, label, color, dt in files:
    create_image(os.path.join(folder, filename), label, color, dt)

print("\nDone – 10 test images created.")
