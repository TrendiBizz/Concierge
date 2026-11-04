import re


def _split_long(paragraph: str, max_chars: int) -> list[str]:
    """Split an over-long paragraph on sentence boundaries, hard-slicing as a last resort."""
    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
    pieces: list[str] = []
    current = ""
    for sentence in sentences:
        if len(sentence) > max_chars:
            if current:
                pieces.append(current)
                current = ""
            for i in range(0, len(sentence), max_chars):
                pieces.append(sentence[i : i + max_chars])
            continue
        if current and len(current) + 1 + len(sentence) > max_chars:
            pieces.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)
    return pieces


def chunk_text(text: str, max_chars: int = 1000, overlap: int = 150) -> list[str]:
    """Split text into chunks of at most ~max_chars, preferring paragraph boundaries.

    Consecutive chunks share up to `overlap` characters of trailing context so an answer
    that straddles a boundary is still retrievable.
    """
    text = text.strip()
    if not text:
        return []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    units: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            units.extend(_split_long(paragraph, max_chars))
        else:
            units.append(paragraph)

    chunks: list[str] = []
    current = ""
    for unit in units:
        if current and len(current) + 2 + len(unit) > max_chars:
            chunks.append(current)
            tail = current[-overlap:] if overlap > 0 else ""
            # Start the next chunk at a word boundary within the overlap.
            if tail and " " in tail:
                tail = tail.split(" ", 1)[1]
            current = f"{tail}\n\n{unit}".strip() if tail else unit
        else:
            current = f"{current}\n\n{unit}" if current else unit
    if current:
        chunks.append(current)
    return chunks
