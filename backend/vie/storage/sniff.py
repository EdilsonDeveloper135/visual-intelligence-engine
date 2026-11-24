"""Magic-byte content detection (the declared type and extension are never trusted)."""

from __future__ import annotations


def sniff(data: bytes) -> str | None:
    head = data[:64]
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in (b"heic", b"heix", b"mif1", b"msf1", b"heim", b"heis", b"avif"):
            return "image/heic"
        return "video/quicktime" if brand == b"qt  " else "video/mp4"
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return "video/webm"
    stripped = head.lstrip().lower()
    if stripped.startswith((b"<svg", b"<?xml", b"<!doctype", b"<html", b"<script")):
        return "text/markup"
    return None


VIDEO_TYPES = {"video/mp4", "video/webm", "video/quicktime"}
SUPPORTED_UPLOAD = {"image/png", "image/jpeg", "image/webp", "application/pdf"} | VIDEO_TYPES
EXTENSIONS = {"image/png": {".png"}, "image/jpeg": {".jpg", ".jpeg", ".jfif"}, "image/webp": {".webp"},
              "application/pdf": {".pdf"}, "video/mp4": {".mp4", ".m4v"}, "video/webm": {".webm"},
              "video/quicktime": {".mov", ".mp4"}}
