"""Second brain: BM25 search over his files in data/knowledge (PDF/DOCX/PPTX/CSV/TXT/MD)."""
from __future__ import annotations

import csv
import io
import math
import re
from pathlib import Path

from .. import config

TEXT_EXT = {".txt", ".md", ".markdown", ".log", ".json"}
SUPPORTED = TEXT_EXT | {".pdf", ".docx", ".pptx", ".csv"}
_cache: dict = {"sig": None, "chunks": [], "df": {}, "avg": 0.0}


def extract_text(path: Path) -> str:
    ext = path.suffix.lower()
    try:
        if ext in TEXT_EXT:
            return path.read_text(encoding="utf-8", errors="replace")
        if ext == ".csv":
            raw = path.read_text(encoding="utf-8", errors="replace")
            rows = list(csv.reader(io.StringIO(raw)))
            return "\n".join(" | ".join(cell.strip() for cell in row) for row in rows)
        if ext == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            return "\n\n".join((page.extract_text() or "") for page in reader.pages)
        if ext == ".docx":
            import docx
            doc = docx.Document(str(path))
            parts = [p.text for p in doc.paragraphs]
            for table in doc.tables:
                for row in table.rows:
                    parts.append(" | ".join(c.text for c in row.cells))
            return "\n".join(parts)
        if ext == ".pptx":
            from pptx import Presentation
            prs = Presentation(str(path))
            parts = []
            for i, slide in enumerate(prs.slides, 1):
                parts.append(f"[Slide {i}]")
                for shape in slide.shapes:
                    if shape.has_text_frame:
                        parts.append(shape.text_frame.text)
            return "\n".join(parts)
    except Exception as exc:
        return f"(could not read {path.name}: {type(exc).__name__})"
    return ""


def chunk(text: str, size: int = 900, overlap: int = 150) -> list[str]:
    text = re.sub(r"[ \t]+", " ", text).strip()
    if not text:
        return []
    paras = [p.strip() for p in re.split(r"\n\s*\n|\n(?=\[Slide )", text) if p.strip()]
    chunks, cur = [], ""
    for para in paras:
        while len(para) > size:
            cut = para.rfind(". ", 0, size)
            cut = cut + 1 if cut > size * 0.4 else size
            piece, para = para[:cut], para[max(0, cut - overlap):]
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(piece.strip())
        if len(cur) + len(para) + 1 > size and cur:
            chunks.append(cur)
            cur = cur[-overlap:] + "\n" + para if overlap and len(cur) > overlap else para
        else:
            cur = (cur + "\n" + para).strip()
    if cur:
        chunks.append(cur)
    return chunks


def _tok(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def files() -> list[Path]:
    root = config.data("knowledge")
    if not root.exists():
        return []
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED)


def _index():
    paths = files()
    sig = tuple((str(p), p.stat().st_mtime, p.stat().st_size) for p in paths)
    if _cache["sig"] == sig:
        return _cache
    chunks, df = [], {}
    for path in paths:
        for i, piece in enumerate(chunk(extract_text(path))):
            toks = _tok(piece)
            if not toks:
                continue
            tf: dict[str, int] = {}
            for tok in toks:
                tf[tok] = tf.get(tok, 0) + 1
            for tok in tf:
                df[tok] = df.get(tok, 0) + 1
            chunks.append({"file": path.name, "n": i, "text": piece, "tf": tf, "len": len(toks)})
    avg = sum(c["len"] for c in chunks) / len(chunks) if chunks else 0.0
    _cache.update(sig=sig, chunks=chunks, df=df, avg=avg)
    return _cache


def search(query: str, k: int = 4) -> list[dict]:
    idx = _index()
    chunks, df, avg = idx["chunks"], idx["df"], idx["avg"] or 1.0
    q = _tok(query)
    n = len(chunks)
    scored = []
    for c in chunks:
        score = 0.0
        for term in q:
            f = c["tf"].get(term)
            if not f:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            score += idf * f * 2.5 / (f + 1.5 * (0.25 + 0.75 * c["len"] / avg))
        if score > 0:
            scored.append((score, c))
    scored.sort(key=lambda s: -s[0])
    return [{"file": c["file"], "score": round(s, 3), "text": c["text"]} for s, c in scored[:k]]


def save_upload(name: str, content: bytes) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._ -]", "_", Path(name).name)[:120] or "file"
    target = config.data("knowledge", safe)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return target
