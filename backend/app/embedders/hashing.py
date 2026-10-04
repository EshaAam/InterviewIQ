"""HashEmbedder — deterministic, offline, no model download.

This is the algorithm `FakeProvider.embed` has always used, lifted into the
embedder seam so there is one implementation rather than two. The test suite
depends on its exact output (cosine assertions in `test_providers.py` and
`test_evaluation_quality.py`), so the hash, the dimension and the
normalisation must not drift.

What it is: the hashing trick. Tokenise, hash each token to one of `dim`
buckets, count, L2-normalise. Texts sharing words get a positive cosine; texts
sharing none get ~0. That is enough to make the deterministic grading pass
*meaningful* offline instead of merely present — but it matches on words, not
meaning, which is exactly why it is not good enough for retrieval. See
`LocalEmbedder`.
"""

from __future__ import annotations

import hashlib
import math
import re

_TOKEN = re.compile(r"[a-z0-9]+")


class HashEmbedder:
    """A deterministic bag-of-words stand-in for a real embedding model."""

    def __init__(self, *, dim: int = 64) -> None:
        self.dim = dim
        self.name = f"hash-{dim}"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_one(t) for t in texts]

    def embed_one(self, text: str) -> list[float]:
        vals = [0.0] * self.dim
        for token in _TOKEN.findall(text.lower()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            vals[int.from_bytes(digest[:4], "big") % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vals)) or 1.0
        return [v / norm for v in vals]
