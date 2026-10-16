"""Make generated PDFs look like phone photos (slight rotation, shadow, blur, noise, JPEG).

Use this to test Gemini on imperfect inputs without printing anything:
  python datagen/scanify.py data/testset/case_012 --out data/photos/case_012

Better still for the demo video: print a few documents, stamp and sign them, and photograph them.
"""
from __future__ import annotations

import argparse
import random
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFilter


def photo(png: bytes, rng: random.Random) -> Image.Image:
    from io import BytesIO

    img = Image.open(BytesIO(png)).convert("RGB")
    w, h = img.size
    # warm paper tone and an uneven shadow
    shade = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(shade)
    for i in range(0, w, 8):
        d.line([(i, 0), (i, h)], fill=int(40 * i / w * rng.uniform(0.6, 1.2)))
    img = Image.composite(Image.new("RGB", (w, h), (205, 198, 185)), img, shade)
    img = img.rotate(rng.uniform(-3, 3), expand=True, fillcolor=(90, 90, 95))
    img = img.filter(ImageFilter.GaussianBlur(rng.uniform(0.4, 1.0)))
    noise = Image.effect_noise(img.size, rng.uniform(6, 14)).convert("RGB")
    return Image.blend(img, noise, 0.06)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case_dir")
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    rng, out = random.Random(a.seed), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for pdf in sorted(Path(a.case_dir).glob("*.pdf")):
        with pymupdf.open(pdf) as doc:
            for n, page in enumerate(doc, 1):
                photo(page.get_pixmap(dpi=130).tobytes("png"), rng).save(out / f"{pdf.stem}_p{n}.jpg", quality=72)
    print(f"photos written to {out}")


if __name__ == "__main__":
    main()
