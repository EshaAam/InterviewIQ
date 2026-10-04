"""Split a markdown document into retrievable passages.

Pure functions, no database and no embedder, so the chunking policy is
unit-testable on its own — which matters because chunk boundaries silently
decide retrieval quality. A passage cut in half mid-explanation retrieves for
neither half.

Two decisions worth stating:

**Headings carry the structure, so they carry the path.** A chunk keeps the
trail of headings above it (`Python > Concurrency > The GIL`). That text goes
into the embedding, where it supplies terms the body often omits — a paragraph
explaining a mutex may never use the word "Python" — and it doubles as a
human-readable citation.

**Fenced code is atomic.** A `#` inside a fence is a shell comment, not a
heading, and a code block split across two chunks is useless in both. Both
cases are common enough in a technical KB to be correctness issues rather than
polish.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")

HEADING_SEPARATOR = " > "


@dataclass(frozen=True)
class DocumentMeta:
    """Front-matter: everything needed to attribute a citation."""

    title: str
    topic: str
    url: str = ""
    license: str = ""


@dataclass(frozen=True)
class Chunk:
    ordinal: int
    heading_path: str
    text: str
    token_estimate: int


def estimate_tokens(text: str) -> int:
    """Same ~4-chars-per-token rule the pipeline meters with.

    Deliberately crude: this sizes a prompt budget, and a real tokenizer would
    add a dependency to make a number that is still only an estimate once a
    different model is used.
    """
    return max(1, len(text) // 4)


def parse_front_matter(raw: str) -> tuple[DocumentMeta, str]:
    """Pull a `---` delimited `key: value` header off the top of a document.

    Hand-rolled rather than pulling in a YAML parser: the header is four flat
    string fields, and YAML's surprises (`no` parsing as False, `1.0` as a
    float) are a poor trade for that.
    """
    lines = raw.lstrip().splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("document must start with a '---' front-matter block")

    fields: dict[str, str] = {}
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            body = "\n".join(lines[index + 1 :])
            break
        if not line.strip():
            continue
        key, separator, value = line.partition(":")
        if not separator:
            raise ValueError(f"front-matter line is not 'key: value': {line!r}")
        fields[key.strip().lower()] = value.strip()
    else:
        raise ValueError("front-matter block was never closed with '---'")

    missing = {"title", "topic"} - fields.keys()
    if missing:
        raise ValueError(f"front-matter is missing {', '.join(sorted(missing))}")

    meta = DocumentMeta(
        title=fields["title"],
        topic=fields["topic"],
        url=fields.get("url", ""),
        license=fields.get("license", ""),
    )
    return meta, body


def _blocks(text: str) -> list[str]:
    """Paragraph-sized units, with fenced code kept whole."""
    blocks: list[str] = []
    current: list[str] = []
    in_fence = False
    fence_token = ""

    for line in text.splitlines():
        fence = _FENCE.match(line)
        if fence:
            if not in_fence:
                in_fence, fence_token = True, fence.group(1)
            elif line.strip().startswith(fence_token):
                in_fence = False
            current.append(line)
            continue
        if not line.strip() and not in_fence:
            if current:
                blocks.append("\n".join(current).strip())
                current = []
            continue
        current.append(line)

    if current:
        blocks.append("\n".join(current).strip())
    return [b for b in blocks if b]


def _sections(body: str, root_title: str) -> list[tuple[str, str]]:
    """(heading_path, text) for each heading in document order."""
    sections: list[tuple[str, str]] = []
    stack: list[str] = []
    current: list[str] = []
    in_fence = False
    fence_token = ""

    def flush(path_stack: list[str]) -> None:
        text = "\n".join(current).strip()
        if text:
            path = HEADING_SEPARATOR.join(path_stack) if path_stack else root_title
            sections.append((path, text))

    for line in body.splitlines():
        fence = _FENCE.match(line)
        if fence:
            if not in_fence:
                in_fence, fence_token = True, fence.group(1)
            elif line.strip().startswith(fence_token):
                in_fence = False
            current.append(line)
            continue

        heading = None if in_fence else _HEADING.match(line)
        if heading:
            flush(stack)
            current = []
            level = len(heading.group(1))
            stack = stack[: level - 1]
            stack.append(heading.group(2))
            continue

        current.append(line)

    flush(stack)
    return sections


def _windows(blocks: list[str], *, max_tokens: int, overlap_tokens: int) -> list[str]:
    """Pack blocks into windows of at most `max_tokens`, overlapping slightly.

    The overlap exists so a passage split across a boundary is still retrievable
    from either side: the last block of one window opens the next, which keeps
    the sentence that bridges them intact in at least one chunk.

    A single block larger than the budget is emitted whole rather than cut — an
    oversized code example is still useful, half of one is not.
    """
    windows: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for block in blocks:
        tokens = estimate_tokens(block)
        if current and current_tokens + tokens > max_tokens:
            windows.append("\n\n".join(current))
            carry: list[str] = []
            carried = 0
            for previous in reversed(current):
                previous_tokens = estimate_tokens(previous)
                if carried + previous_tokens > overlap_tokens:
                    break
                carry.insert(0, previous)
                carried += previous_tokens
            current, current_tokens = carry, carried
        current.append(block)
        current_tokens += tokens

    if current:
        windows.append("\n\n".join(current))
    return windows


def chunk_markdown(
    body: str,
    *,
    root_title: str = "",
    max_tokens: int = 400,
    overlap_tokens: int = 50,
) -> list[Chunk]:
    """Split a document body into ordered, heading-tagged passages."""
    chunks: list[Chunk] = []
    for heading_path, text in _sections(body, root_title):
        for window in _windows(
            _blocks(text), max_tokens=max_tokens, overlap_tokens=overlap_tokens
        ):
            # The heading path leads the text so it lands in the embedding and
            # not just the citation.
            full = f"{heading_path}\n\n{window}" if heading_path else window
            chunks.append(
                Chunk(
                    ordinal=len(chunks),
                    heading_path=heading_path,
                    text=full,
                    token_estimate=estimate_tokens(full),
                )
            )
    return chunks
