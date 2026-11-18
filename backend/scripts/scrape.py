import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.scraping.service import run_scrape
from app.rag.ingest import build_knowledge_base
from app.core.logging import setup_logging
from app.core.config import settings


def main():
    parser = argparse.ArgumentParser(description='Run initial scraping and build knowledge base')
    parser.add_argument('--sites', nargs='+', default=['dar_global', 'wasalt'], choices=['dar_global', 'wasalt'])
    parser.add_argument('--max-pages', type=int, default=None)
    parser.add_argument('--no-build-kb', action='store_true')
    args = parser.parse_args()
    setup_logging(settings.log_level)
    results = run_scrape(args.sites, max_pages_per_site=args.max_pages)
    print(json.dumps({'scrape_results': results}, indent=2))
    if not args.no_build_kb:
        kb = build_knowledge_base()
        print(json.dumps({'kb_stats': kb}, indent=2))


if __name__ == '__main__':
    main()
