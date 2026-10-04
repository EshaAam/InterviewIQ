"""Chunking policy and knowledge-base ingestion.

Chunk boundaries silently decide retrieval quality — a passage cut mid-
explanation retrieves for neither half — so the chunker is tested as a pure
function, independently of any database or embedder.

The ingestion tests run on SQLite, which has no pgvector. That is deliberate:
it exercises the JSON fallback in `app.db.types.Vector` on every run, so the
dialect split cannot rot unnoticed between the rarer Postgres CI runs.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.embedders import HashEmbedder
from app.models import KB_EMBEDDING_DIM, KBChunk, KBDocument
from app.services.chunking import (
    chunk_markdown,
    estimate_tokens,
    parse_front_matter,
)
from app.services.kb_ingest import MixedEmbeddingModels, ingest_kb

DOC = """---
title: Python
topic: python
license: hand-written
url: https://example.test/python
---

# Python

Intro paragraph.

## The GIL

Only one thread runs bytecode at a time.

### Releasing it

Blocking I/O releases the lock.

## Generators

They yield lazily.
"""


def write_kb(directory, name: str, body: str):
    path = directory / name
    path.write_text(body, encoding="utf-8")
    return path


# --- front matter ----------------------------------------------------------


def test_front_matter_is_parsed_and_stripped():
    meta, body = parse_front_matter(DOC)
    assert meta.title == "Python"
    assert meta.topic == "python"
    assert meta.license == "hand-written"
    assert meta.url == "https://example.test/python"
    assert body.lstrip().startswith("# Python")


def test_front_matter_defaults_the_optional_fields():
    meta, _ = parse_front_matter("---\ntitle: T\ntopic: t\n---\n\nbody\n")
    assert meta.url == ""
    assert meta.license == ""


@pytest.mark.parametrize(
    "raw, message",
    [
        ("# No front matter\n", "must start with"),
        ("---\ntitle: T\n---\n\nbody\n", "missing topic"),
        ("---\ntitle: T\ntopic: t\n", "never closed"),
        ("---\ntitle T\ntopic: t\n---\n", "not 'key: value'"),
    ],
)
def test_malformed_front_matter_says_what_is_wrong(raw, message):
    with pytest.raises(ValueError, match=message):
        parse_front_matter(raw)


# --- chunking --------------------------------------------------------------


def test_heading_path_tracks_nesting():
    _, body = parse_front_matter(DOC)
    paths = [c.heading_path for c in chunk_markdown(body, root_title="Python")]
    assert "Python > The GIL" in paths
    assert "Python > The GIL > Releasing it" in paths
    assert "Python > Generators" in paths


def test_a_deeper_heading_does_not_leak_into_its_sibling():
    """`## Generators` must not inherit `### Releasing it` from the section above."""
    _, body = parse_front_matter(DOC)
    generators = [c for c in chunk_markdown(body) if c.heading_path.endswith("Generators")]
    assert generators and all("Releasing" not in c.heading_path for c in generators)


def test_the_heading_path_leads_the_chunk_text():
    """It has to be in the text, not just the metadata, or it never reaches the
    embedding — and headings carry terms the body often omits."""
    _, body = parse_front_matter(DOC)
    chunk = next(c for c in chunk_markdown(body) if c.heading_path.endswith("The GIL"))
    assert chunk.text.startswith("Python > The GIL")


def test_ordinals_are_sequential_from_zero():
    _, body = parse_front_matter(DOC)
    chunks = chunk_markdown(body)
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))


def test_a_hash_inside_a_code_fence_is_not_a_heading():
    """A shell comment is not a section break."""
    body = "## Real heading\n\n```bash\n# not a heading\nls -la\n```\n\nAfter.\n"
    paths = {c.heading_path for c in chunk_markdown(body, root_title="T")}
    assert paths == {"Real heading"}


def test_a_code_fence_is_never_split_across_chunks():
    """Half a code example is useless in both halves."""
    code = "\n".join(f"line_{i} = {i}" for i in range(120))
    body = f"## Example\n\n```python\n{code}\n```\n"
    chunks = chunk_markdown(body, max_tokens=50, overlap_tokens=10)
    fenced = [c for c in chunks if "```" in c.text]
    assert len(fenced) == 1
    assert fenced[0].text.count("```") == 2


def test_long_sections_are_split_into_windows():
    paragraphs = "\n\n".join(f"Paragraph {i}. " + "word " * 60 for i in range(10))
    body = f"## Long\n\n{paragraphs}\n"
    chunks = chunk_markdown(body, max_tokens=200, overlap_tokens=40)
    assert len(chunks) > 1
    assert all(c.heading_path == "Long" for c in chunks)


def test_windows_overlap_so_a_boundary_is_retrievable_from_either_side():
    paragraphs = "\n\n".join(f"Unique marker {i}. " + "filler " * 40 for i in range(8))
    chunks = chunk_markdown(f"## S\n\n{paragraphs}\n", max_tokens=150, overlap_tokens=60)
    assert len(chunks) > 1
    # Something from the tail of one window opens the next.
    assert any(
        any(line in chunks[i + 1].text for line in chunks[i].text.splitlines() if line.strip())
        for i in range(len(chunks) - 1)
    )


def test_an_oversized_single_block_is_emitted_whole_not_cut():
    body = "## S\n\n" + "word " * 2000 + "\n"
    chunks = chunk_markdown(body, max_tokens=50, overlap_tokens=10)
    assert len(chunks) == 1


def test_an_empty_body_produces_no_chunks():
    assert chunk_markdown("\n\n") == []


def test_token_estimate_is_recorded():
    chunks = chunk_markdown("## S\n\nsome text here\n")
    assert chunks[0].token_estimate == estimate_tokens(chunks[0].text)


# --- ingestion -------------------------------------------------------------


async def test_ingest_creates_documents_and_chunks(db_session, tmp_path):
    write_kb(tmp_path, "python.md", DOC)
    report = await ingest_kb(db_session, HashEmbedder(dim=KB_EMBEDDING_DIM), kb_dir=tmp_path)

    assert report.ingested == ["python.md"]
    assert report.chunks_written > 0
    assert report.chunks_per_topic == {"python": report.chunks_written}

    document = await db_session.scalar(select(KBDocument))
    assert document.title == "Python"
    assert document.license == "hand-written"
    assert len(document.content_hash) == 64


async def test_embeddings_round_trip_through_the_sqlite_fallback(db_session, tmp_path):
    """`Vector` degrades to JSON off Postgres; the values must survive intact."""
    write_kb(tmp_path, "python.md", DOC)
    await ingest_kb(db_session, HashEmbedder(dim=KB_EMBEDDING_DIM), kb_dir=tmp_path)

    chunk = await db_session.scalar(select(KBChunk))
    assert chunk.embedding is not None
    assert len(chunk.embedding) == KB_EMBEDDING_DIM
    assert all(isinstance(v, float) for v in chunk.embedding)
    assert chunk.embedding_model == f"hash-{KB_EMBEDDING_DIM}"


async def test_a_second_run_on_unchanged_files_is_a_no_op(db_session, tmp_path):
    """The property that makes this safe to run on every deploy."""
    write_kb(tmp_path, "python.md", DOC)
    embedder = HashEmbedder(dim=KB_EMBEDDING_DIM)
    first = await ingest_kb(db_session, embedder, kb_dir=tmp_path)

    second = await ingest_kb(db_session, embedder, kb_dir=tmp_path)
    assert second.ingested == []
    assert second.skipped == ["python.md"]
    assert second.chunks_written == 0
    # And nothing was duplicated.
    assert second.chunks_per_topic == first.chunks_per_topic


async def test_changed_content_replaces_the_old_chunks(db_session, tmp_path):
    path = write_kb(tmp_path, "python.md", DOC)
    embedder = HashEmbedder(dim=KB_EMBEDDING_DIM)
    await ingest_kb(db_session, embedder, kb_dir=tmp_path)

    path.write_text(DOC + "\n## Added section\n\nNew material.\n", encoding="utf-8")
    report = await ingest_kb(db_session, embedder, kb_dir=tmp_path)

    assert report.ingested == ["python.md"]
    # One document, not two - `source` is the natural key.
    assert await db_session.scalar(select(func.count(KBDocument.id))) == 1
    total = await db_session.scalar(select(func.count(KBChunk.id)))
    assert total == report.chunks_per_topic["python"]
    paths = await db_session.scalars(select(KBChunk.heading_path))
    assert any("Added section" in p for p in paths)


async def test_force_re_ingests_unchanged_files(db_session, tmp_path):
    write_kb(tmp_path, "python.md", DOC)
    embedder = HashEmbedder(dim=KB_EMBEDDING_DIM)
    await ingest_kb(db_session, embedder, kb_dir=tmp_path)

    report = await ingest_kb(db_session, embedder, kb_dir=tmp_path, force=True)
    assert report.ingested == ["python.md"]
    assert report.skipped == []


async def test_ingest_refuses_to_mix_embedding_models(db_session, tmp_path):
    """A cosine between vectors from two models is a meaningless number that
    still sorts, so a mixed index fails silently rather than loudly."""
    write_kb(tmp_path, "python.md", DOC)
    await ingest_kb(db_session, HashEmbedder(dim=KB_EMBEDDING_DIM), kb_dir=tmp_path)

    with pytest.raises(MixedEmbeddingModels, match=f"hash-{KB_EMBEDDING_DIM}"):
        await ingest_kb(db_session, HashEmbedder(dim=KB_EMBEDDING_DIM // 2), kb_dir=tmp_path)


class _SameWidthOtherModel(HashEmbedder):
    """A different model that happens to emit the same width — the realistic
    swap, e.g. bge-small for another 384-dimension encoder."""

    def __init__(self) -> None:
        super().__init__(dim=KB_EMBEDDING_DIM)
        self.name = "other-384-model"


async def test_force_allows_a_deliberate_re_embed_with_a_new_model(db_session, tmp_path):
    write_kb(tmp_path, "python.md", DOC)
    await ingest_kb(db_session, HashEmbedder(dim=KB_EMBEDDING_DIM), kb_dir=tmp_path)

    report = await ingest_kb(db_session, _SameWidthOtherModel(), kb_dir=tmp_path, force=True)

    assert report.embedding_model == "other-384-model"
    models = set(await db_session.scalars(select(KBChunk.embedding_model).distinct()))
    assert models == {"other-384-model"}


async def test_a_model_of_the_wrong_width_is_refused_at_the_write(db_session, tmp_path):
    """Changing the embedding width is a migration, not a config change.

    `force` overrides the mixed-model guard, but it cannot override the column:
    a `vector(384)` cannot hold a 192-wide vector, and finding that out at query
    time — after an ingest run has written thousands of rows — is far worse than
    failing on the first insert.
    """
    write_kb(tmp_path, "python.md", DOC)

    narrow = HashEmbedder(dim=KB_EMBEDDING_DIM // 2)
    with pytest.raises(Exception, match="expected a 384-dimension vector, got 192"):
        await ingest_kb(db_session, narrow, kb_dir=tmp_path, force=True)


async def test_a_removed_file_is_reported_but_not_deleted(db_session, tmp_path):
    """Phase 4 questions will cite chunks; a citation must not rot because
    someone renamed a file."""
    path = write_kb(tmp_path, "python.md", DOC)
    embedder = HashEmbedder(dim=KB_EMBEDDING_DIM)
    await ingest_kb(db_session, embedder, kb_dir=tmp_path)

    path.unlink()
    write_kb(tmp_path, "other.md", DOC.replace("topic: python", "topic: other"))
    report = await ingest_kb(db_session, embedder, kb_dir=tmp_path)

    assert report.orphaned == ["python.md"]
    assert await db_session.scalar(select(func.count(KBDocument.id))) == 2


async def test_multiple_topics_are_counted_separately(db_session, tmp_path):
    write_kb(tmp_path, "python.md", DOC)
    write_kb(tmp_path, "sql.md", DOC.replace("topic: python", "topic: sql"))
    report = await ingest_kb(db_session, HashEmbedder(dim=KB_EMBEDDING_DIM), kb_dir=tmp_path)

    assert set(report.chunks_per_topic) == {"python", "sql"}
    assert sum(report.chunks_per_topic.values()) == report.chunks_written


async def test_a_missing_kb_directory_says_where_it_looked(db_session, tmp_path):
    with pytest.raises(FileNotFoundError, match="no knowledge base directory"):
        await ingest_kb(db_session, HashEmbedder(dim=KB_EMBEDDING_DIM), kb_dir=tmp_path / "absent")
