"""Text from uploaded PDF / Word / text files."""
import io
import re

from pypdf import PdfReader

PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
ALLOWED = {
    ".pdf": PDF,
    ".docx": DOCX,
    ".txt": "text/plain",
    ".md": "text/plain",
}


def mime_for(filename: str) -> str | None:
    name = filename.lower()
    return next((m for ext, m in ALLOWED.items() if name.endswith(ext)), None)


def text_of(data: bytes, mime: str) -> str:
    try:
        if mime == PDF:
            reader = PdfReader(io.BytesIO(data))
            text = "\n".join((p.extract_text() or "") for p in reader.pages)
            # Icon fonts come out as junk like "/envel⌢pe"
            text = re.sub(r"/[a-z⌢]+(?=\S)", "", text)
        elif mime == DOCX:
            import docx
            d = docx.Document(io.BytesIO(data))
            text = "\n".join(p.text for p in d.paragraphs)
        else:
            text = data.decode("utf-8", errors="ignore")
    except Exception:  # noqa: BLE001
        return ""
    return re.sub(r"\n{3,}", "\n\n", text).strip()
