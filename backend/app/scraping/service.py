from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings

from .darglobal import DarGlobalScraper
from .wasalt import WasaltScraper

logger = logging.getLogger(__name__)

SCRAPER_MAP = {
    'dar_global': DarGlobalScraper,
    'wasalt': WasaltScraper,
}


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def run_scrape(
    sites: list[str],
    max_pages_per_site: int | None = None,
    force: bool = False,
) -> list[dict]:
    settings.raw_data_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    for site in sites:
        scraper_class = SCRAPER_MAP.get(site)
        if not scraper_class:
            continue
        scraper = scraper_class(
            raw_dir=settings.raw_data_dir,
            max_pages=max_pages_per_site or settings.scrape_max_pages_per_site,
            rate_limit_seconds=settings.scrape_rate_limit_seconds,
            timeout_seconds=settings.scrape_timeout_seconds,
            user_agent=settings.scrape_user_agent,
            refresh_days=settings.scrape_refresh_days,
        )
        logger.info('Starting scrape for %s', site)
        stats = scraper.scrape(force=force)
        results.append(stats)
        logger.info(
            'Finished scrape for %s: saved=%s skipped=%s blocked=%s attempted=%s',
            site,
            stats.get('documents_saved'),
            stats.get('documents_skipped'),
            stats.get('pages_blocked'),
            stats.get('pages_attempted'),
        )

    summary = {
        'ran_at': datetime.now(timezone.utc).isoformat(),
        'sites': sites,
        'results': results,
        'document_counts': count_documents(),
        'coverage': [result.get('coverage_note') for result in results],
    }
    _write_json(settings.raw_data_dir / 'last_scrape_summary.json', summary)
    return results


def count_documents() -> dict[str, int]:
    counts: dict[str, int] = {}
    for site in SCRAPER_MAP:
        directory = settings.raw_data_dir / site
        if not directory.exists():
            counts[site] = 0
            continue
        counts[site] = len(
            [
                path
                for path in directory.glob('*.json')
                if path.name != 'last_scrape_stats.json'
            ]
        )
    return counts


def get_scrape_stats() -> dict:
    summary_path = settings.raw_data_dir / 'last_scrape_summary.json'
    if summary_path.exists():
        try:
            data = json.loads(summary_path.read_text(encoding='utf-8'))
            data['document_counts'] = count_documents()
            return data
        except (OSError, ValueError):
            pass
    results = []
    for site in SCRAPER_MAP:
        path = settings.raw_data_dir / site / 'last_scrape_stats.json'
        if path.exists():
            try:
                results.append(json.loads(path.read_text(encoding='utf-8')))
            except (OSError, ValueError):
                continue
    return {
        'ran_at': None,
        'results': results,
        'document_counts': count_documents(),
        'coverage': [result.get('coverage_note') for result in results],
    }
