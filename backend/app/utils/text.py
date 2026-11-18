from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from typing import Iterable

TAG_RE = re.compile(r'<[^>]+>')
WS_RE = re.compile(r'[ \t\u00a0\u200b]+')
NL_RE = re.compile(r'\n{3,}')
EMAIL_RE = re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}')
PHONE_RE = re.compile(r'(?:\+?\d[\d\s\-().]{7,}\d)')
PRICE_RE = re.compile(
    r'((?:AED|SAR|USD|GBP|EUR|QAR|OMR|CHF|£|\$|€)\s?[0-9][0-9,\.]*(?:\s?(?:M|K|million|billion))?)'
    r'|([0-9][0-9,\.]{3,}\s?(?:SAR|AED|USD|GBP|EUR|QAR|OMR))',
    re.IGNORECASE,
)
SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?])\s+(?=[A-Z0-9“"\'(])')


def clean_text(value: str | None) -> str:
    if value is None:
        return ''
    text = html.unescape(str(value))
    text = TAG_RE.sub(' ', text)
    text = unicodedata.normalize('NFKC', text)
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = WS_RE.sub(' ', text)
    lines = [line.strip() for line in text.split('\n')]
    text = '\n'.join(line for line in lines if line)
    text = NL_RE.sub('\n\n', text)
    return text.strip()


def normalize_block(value: str | None) -> str:
    return ' '.join(clean_text(value).split())


def clean_lines(values: Iterable[str], min_length: int = 2) -> list[str]:
    seen: set[str] = set()
    lines: list[str] = []
    for value in values:
        line = normalize_block(value)
        if len(line) < min_length or line in seen:
            continue
        seen.add(line)
        lines.append(line)
    return lines


def chunk_text(text: str, chunk_size: int = 900, overlap: int = 150) -> list[str]:
    cleaned = clean_text(text)
    if not cleaned:
        return []
    chunk_size = max(120, chunk_size)
    overlap = max(0, min(overlap, chunk_size // 2))
    if len(cleaned) <= chunk_size:
        return [cleaned]
    chunks: list[str] = []
    start = 0
    length = len(cleaned)
    while start < length:
        end = min(start + chunk_size, length)
        if end < length:
            window = cleaned[start:end]
            boundary = max(window.rfind('. '), window.rfind('! '), window.rfind('? '), window.rfind('\n'))
            if boundary >= int(chunk_size * 0.55):
                end = start + boundary + 1
        chunk = cleaned[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= length:
            break
        next_start = max(0, end - overlap)
        if next_start <= start:
            next_start = start + max(1, chunk_size - overlap)
        start = next_start
    return chunks


def make_id(value: str) -> str:
    return hashlib.sha1(value.encode('utf-8')).hexdigest()[:16]


def content_hash(value: str) -> str:
    return hashlib.sha256(normalize_block(value).encode('utf-8')).hexdigest()


def extract_emails(text: str) -> list[str]:
    return sorted(set(EMAIL_RE.findall(text or '')))[:5]


def extract_phones(text: str) -> list[str]:
    cleaned = []
    for value in PHONE_RE.findall(text or ''):
        digits = re.sub(r'\D', '', value)
        if 8 <= len(digits) <= 16:
            cleaned.append(normalize_block(value))
    return sorted(set(cleaned))[:5]


def extract_price(text: str) -> str | None:
    match = PRICE_RE.search(text or '')
    if not match:
        return None
    return normalize_block(match.group(0))[:80]


def extract_number(text: str, labels: list[str]) -> int | None:
    for label in labels:
        match = re.search(rf'{label}\s*[:\-]?\s*([0-9][0-9,]*)', text or '', re.IGNORECASE)
        if match:
            try:
                return int(match.group(1).replace(',', ''))
            except ValueError:
                continue
    return None


def slug_to_title(value: str) -> str:
    value = value.replace('-', ' ').replace('_', ' ')
    return ' '.join(word.capitalize() for word in value.split())


def sentence_split(text: str) -> list[str]:
    return [part.strip() for part in SENTENCE_SPLIT_RE.split(text) if part.strip()]
