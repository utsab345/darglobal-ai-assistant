from __future__ import annotations

import gzip
import io
import json
import logging
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

from app.utils.text import clean_text, make_id, normalize_block

logger = logging.getLogger(__name__)

CHALLENGE_MARKERS = (
    'incapsula',
    '_incapsula_resource',
    'just a moment',
    'enable javascript and cookies',
    'cf-challenge',
    'attention required! | cloudflare',
    'access denied',
    'request unsuccessful',
)


class FetchError(RuntimeError):
    pass


@dataclass
class ScrapedDocument:
    id: str
    source: str
    url: str
    title: str
    content: str
    scraped_at: str
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FetchResult:
    url: str
    status_code: int
    text: str
    content_type: str
    blocked: bool
    error: str | None = None


class RobotsPolicy:
    def __init__(self, base_url: str, user_agent: str, timeout: float) -> None:
        self.base_url = base_url
        self.user_agent = user_agent
        self.timeout = timeout
        self.parser = RobotFileParser()
        self.status = 'unknown'
        self.robots_url = urljoin(base_url, '/robots.txt')

    def load(self) -> None:
        try:
            response = requests.get(
                self.robots_url,
                timeout=self.timeout,
                headers={'User-Agent': self.user_agent, 'Accept': 'text/plain,*/*'},
            )
            if response.status_code >= 400:
                self.status = f'unavailable ({response.status_code})'
                self.parser.parse([])
                return
            text = response.text
            lowered = text.lower()
            if '<html' in lowered or any(marker in lowered for marker in CHALLENGE_MARKERS):
                self.status = 'unavailable (non-robots response)'
                self.parser.parse([])
                return
            self.parser.parse(text.splitlines())
            self.status = 'loaded'
        except requests.RequestException as exc:
            self.status = f'unavailable ({type(exc).__name__})'
            self.parser.parse([])

    def can_fetch(self, url: str) -> bool:
        try:
            return self.parser.can_fetch(self.user_agent, url)
        except Exception:
            return True


class BaseScraper:
    source_name = 'unknown'
    base_url = ''
    allowed_domains: tuple[str, ...] = ()

    def __init__(
        self,
        raw_dir: Path,
        max_pages: int = 80,
        rate_limit_seconds: float = 1.2,
        timeout_seconds: float = 25.0,
        user_agent: str = 'DarGlobalAIAssistant/1.0',
        refresh_days: int = 7,
    ) -> None:
        self.raw_dir = raw_dir
        self.max_pages = max_pages
        self.rate_limit_seconds = rate_limit_seconds
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self.refresh_days = refresh_days
        self.session = requests.Session()
        self.session.headers.update(
            {
                'User-Agent': user_agent,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
            }
        )
        self.robots = RobotsPolicy(base_url, user_agent, timeout_seconds)
        self._last_request_at = 0.0
        self.stats: dict = {}

    def site_dir(self) -> Path:
        path = self.raw_dir / self.source_name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def is_allowed_url(self, url: str) -> bool:
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ('http', 'https'):
                return False
            host = parsed.netloc.lower()
            return any(host == domain or host.endswith('.' + domain) for domain in self.allowed_domains)
        except Exception:
            return False

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.rate_limit_seconds:
            time.sleep(self.rate_limit_seconds - elapsed)
        self._last_request_at = time.monotonic()

    def fetch(self, url: str, attempts: int = 3) -> FetchResult:
        last_error: str | None = None
        for attempt in range(1, attempts + 1):
            self._throttle()
            try:
                response = self.session.get(url, timeout=self.timeout_seconds, allow_redirects=True)
                content_type = response.headers.get('content-type', '')
                text = response.text
                blocked = self.is_challenge(response.status_code, content_type, text)
                if response.status_code in (403, 429) and attempt < attempts:
                    time.sleep(1.5 * attempt)
                    continue
                if response.status_code >= 500 and attempt < attempts:
                    time.sleep(1.5 * attempt)
                    continue
                return FetchResult(
                    url=str(response.url),
                    status_code=response.status_code,
                    text=text,
                    content_type=content_type,
                    blocked=blocked,
                    error=None if response.status_code < 400 else f'HTTP {response.status_code}',
                )
            except requests.RequestException as exc:
                last_error = f'{type(exc).__name__}: {exc}'
                if attempt < attempts:
                    time.sleep(1.5 * attempt)
        raise FetchError(last_error or 'request failed')

    def is_challenge(self, status_code: int, content_type: str, text: str) -> bool:
        if status_code in (401, 403, 429):
            return True
        lowered = (text or '')[:20000].lower()
        if any(marker in lowered for marker in CHALLENGE_MARKERS):
            return True
        if 'text/html' in content_type and len(text) < 600 and '<html' in lowered:
            return True
        return False

    def fetch_xml(self, url: str) -> str:
        result = self.fetch(url)
        if result.blocked:
            raise FetchError(f'blocked while fetching sitemap: {url}')
        raw = result.text
        if raw.lstrip().startswith('<?xml') or '<urlset' in raw[:1000] or '<sitemapindex' in raw[:1000]:
            return raw
        try:
            binary = raw.encode('latin-1', errors='ignore')
            return gzip.decompress(binary).decode('utf-8', errors='ignore')
        except Exception:
            return raw

    def parse_sitemap(self, url: str, max_children: int = 8) -> list[str]:
        try:
            xml_text = self.fetch_xml(url)
        except Exception as exc:
            logger.warning('Sitemap unavailable %s: %s', url, exc)
            return []
        try:
            root = ET.fromstring(xml_text.encode('utf-8', errors='ignore'))
        except ET.ParseError as exc:
            logger.warning('Invalid sitemap %s: %s', url, exc)
            return []
        namespace = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        locs = [element.text.strip() for element in root.findall('.//sm:loc', namespace) if element.text]
        if not locs:
            locs = [element.text.strip() for element in root.findall('.//loc') if element.text]
        if root.tag.endswith('sitemapindex'):
            child_urls = [loc for loc in locs if loc.endswith('.xml') or loc.endswith('.xml.gz')][:max_children]
            collected: list[str] = []
            for child in child_urls:
                collected.extend(self.parse_sitemap(child, max_children=0))
            return collected
        return locs

    def soup(self, html_text: str) -> BeautifulSoup:
        try:
            return BeautifulSoup(html_text, 'lxml')
        except Exception:
            return BeautifulSoup(html_text, 'html.parser')

    def existing_document(self, url: str) -> dict | None:
        path = self.site_dir() / f'{make_id(f"{self.source_name}:{url}")}.json'
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return None

    def is_fresh(self, document: dict) -> bool:
        scraped_at = document.get('scraped_at')
        if not scraped_at:
            return False
        try:
            timestamp = datetime.fromisoformat(scraped_at)
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
        except ValueError:
            return False
        return datetime.now(timezone.utc) - timestamp < timedelta(days=self.refresh_days)

    def save_document(self, document: ScrapedDocument) -> bool:
        path = self.site_dir() / f'{document.id}.json'
        existing = self.existing_document(document.url)
        if existing:
            existing_content = existing.get('content') or ''
            if len(existing_content) > len(document.content) * 1.1:
                return False
        tmp = path.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(document.to_dict(), ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(path)
        return True

    def discover_urls(self) -> list[str]:
        raise NotImplementedError

    def parse_page(self, url: str, html_text: str) -> ScrapedDocument | None:
        raise NotImplementedError

    def coverage_note(self) -> str:
        return 'Bounded public crawl; not a comprehensive mirror of the website.'

    def scrape(self, force: bool = False) -> dict:
        started = datetime.now(timezone.utc)
        errors: list[str] = []
        saved = 0
        skipped = 0
        blocked = 0
        attempted = 0
        parsed = 0
        consecutive_blocks = 0

        self.robots.load()
        try:
            urls = self.discover_urls()
        except Exception as exc:
            logger.exception('URL discovery failed for %s', self.source_name)
            urls = []
            errors.append(f'discovery_failed: {exc}')

        seen: set[str] = set()
        for url in urls:
            if attempted >= self.max_pages:
                break
            normalized = url.split('#')[0].rstrip('/')
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            if not self.is_allowed_url(normalized):
                continue
            if not self.robots.can_fetch(normalized):
                errors.append(f'robots_disallowed: {normalized}')
                continue
            existing = self.existing_document(normalized)
            if existing and not force and self.is_fresh(existing):
                skipped += 1
                continue
            attempted += 1
            try:
                result = self.fetch(normalized)
            except Exception as exc:
                errors.append(f'{normalized}: {exc}')
                continue
            if result.blocked:
                blocked += 1
                consecutive_blocks += 1
                errors.append(f'{normalized}: anti_bot_or_access_challenge')
                if consecutive_blocks >= 4:
                    errors.append('stopped_after_consecutive_access_challenges')
                    break
                continue
            consecutive_blocks = 0
            if result.status_code >= 400:
                errors.append(f'{normalized}: HTTP {result.status_code}')
                continue
            if 'text/html' not in result.content_type and 'application/xhtml+xml' not in result.content_type:
                continue
            document = self.parse_page(result.url, result.text)
            if not document or len(document.content) < 80:
                continue
            parsed += 1
            if self.save_document(document):
                saved += 1
            else:
                skipped += 1

        finished = datetime.now(timezone.utc)
        stats = {
            'site': self.source_name,
            'pages_attempted': attempted,
            'pages_parsed': parsed,
            'pages_scraped': parsed,
            'documents_saved': saved,
            'documents_skipped': skipped,
            'pages_blocked': blocked,
            'discovered_urls': len(urls),
            'errors': errors[:80],
            'robots_status': self.robots.status,
            'robots_url': self.robots.robots_url,
            'started_at': started.isoformat(),
            'finished_at': finished.isoformat(),
            'coverage_note': self.coverage_note(),
        }
        self.stats = stats
        self.save_stats(stats)
        return stats

    def save_stats(self, stats: dict) -> None:
        path = self.site_dir() / 'last_scrape_stats.json'
        tmp = path.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(path)

    def now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def extract_visible_text(self, soup: BeautifulSoup, max_length: int = 20000) -> str:
        for tag in soup(['script', 'style', 'noscript', 'svg', 'iframe', 'header', 'footer', 'nav', 'form', 'button']):
            tag.decompose()
        main = soup.find('main') or soup.find('article') or soup.body or soup
        parts: list[str] = []
        for element in main.find_all(['h1', 'h2', 'h3', 'h4', 'p', 'li', 'td', 'th', 'blockquote']):
            text = normalize_block(element.get_text(' ', strip=True))
            if len(text) < 2:
                continue
            parts.append(text)
        unique: list[str] = []
        seen: set[str] = set()
        for part in parts:
            if part in seen:
                continue
            seen.add(part)
            unique.append(part)
        return clean_text('\n'.join(unique))[:max_length]

    def meta_content(self, soup: BeautifulSoup, names: Iterable[str]) -> str:
        for name in names:
            tag = soup.find('meta', attrs={'property': name}) or soup.find('meta', attrs={'name': name})
            if tag and tag.get('content'):
                return normalize_block(tag['content'])
        return ''

    def link_urls(self, soup: BeautifulSoup, base: str) -> list[str]:
        urls: list[str] = []
        for anchor in soup.select('a[href]'):
            href = (anchor.get('href') or '').strip()
            if not href or href.startswith(('mailto:', 'tel:', 'javascript:', '#')):
                continue
            absolute = urljoin(base, href)
            if self.is_allowed_url(absolute):
                urls.append(absolute.split('#')[0].rstrip('/'))
        return urls
