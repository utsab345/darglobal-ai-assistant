import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.scraping.service import get_scrape_stats
from app.rag.ingest import get_kb_stats


def main():
    print(json.dumps({
        'scrape': get_scrape_stats(),
        'knowledge_base': get_kb_stats(),
    }, indent=2))


if __name__ == '__main__':
    main()
