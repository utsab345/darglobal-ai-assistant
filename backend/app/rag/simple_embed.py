from __future__ import annotations

import hashlib
import math
import re

import numpy as np

TOKEN_RE = re.compile(r'[A-Za-z0-9]+')

STOPWORDS = {
    'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from', 'has', 'have',
    'in', 'is', 'it', 'its', 'of', 'on', 'or', 'that', 'the', 'to', 'was', 'were',
    'what', 'which', 'who', 'with', 'about', 'me', 'tell', 'please', 'can', 'you',
    'i', 'we', 'our', 'their', 'this', 'these', 'those', 'do', 'does', 'how', 'where',
}


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text or '') if token.lower() not in STOPWORDS]


def embed_texts(texts: list[str], dim: int = 384) -> np.ndarray:
    vectors = np.zeros((len(texts), dim), dtype='float32')
    for row, text in enumerate(texts):
        counts: dict[str, int] = {}
        for token in tokenize(text):
            counts[token] = counts.get(token, 0) + 1
        for token, count in counts.items():
            digest = hashlib.md5(token.encode('utf-8')).hexdigest()
            index = int(digest[:8], 16) % dim
            sign = 1.0 if int(digest[8:10], 16) % 2 == 0 else -1.0
            vectors[row, index] += sign * (1.0 + math.log(count))
        norm = np.linalg.norm(vectors[row])
        if norm > 0:
            vectors[row] /= norm
    return vectors


def embed_query(text: str, dim: int = 384) -> np.ndarray:
    return embed_texts([text], dim=dim)[0]
