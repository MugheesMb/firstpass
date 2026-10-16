"""Turn uploads (PDF or image) into page PNGs. Gemini reads the PNGs, so box coordinates
it returns line up exactly with what the evidence viewer shows."""
from __future__ import annotations

import pymupdf

from ..config import settings

IMAGE_MIMES = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/heic"}


def is_pdf(filename: str, mime: str | None) -> bool:
    return (mime or "").lower() == "application/pdf" or filename.lower().endswith(".pdf")


def to_pngs(data: bytes, filename: str, mime: str | None = None, dpi: int | None = None) -> list[bytes]:
    dpi = dpi or settings.render_dpi
    if is_pdf(filename, mime):
        out = []
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            for page in doc:
                out.append(page.get_pixmap(dpi=dpi).tobytes("png"))
        return out
    # Images (phone photos): normalise to PNG via PyMuPDF so every page is the same format.
    with pymupdf.open(stream=data, filetype=_img_type(filename, mime)) as doc:
        pdf_bytes = doc.convert_to_pdf()
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        return [p.get_pixmap(dpi=dpi).tobytes("png") for p in doc]


def page_png(data: bytes, filename: str, page: int, mime: str | None = None) -> bytes:
    pages = to_pngs(data, filename, mime)
    return pages[max(0, min(page - 1, len(pages) - 1))]


def page_count(data: bytes, filename: str, mime: str | None = None) -> int:
    if is_pdf(filename, mime):
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            return doc.page_count
    return 1


def _img_type(filename: str, mime: str | None) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in {"jpg", "jpeg", "png", "webp"}:
        return ext
    if mime and "/" in mime:
        return mime.split("/", 1)[1]
    return "png"

