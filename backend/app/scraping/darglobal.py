from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.utils.text import (
    clean_text,
    extract_emails,
    extract_phones,
    extract_price,
    make_id,
    normalize_block,
)

from .base import BaseScraper, ScrapedDocument

logger = logging.getLogger(__name__)

EXCLUDED_PATHS = (
    '/pay-online',
    '/success',
    '/thank-you',
    '/bookyourunit',
    '/internship',
    '/careers',
    '/live-all-in',
    '/landing-page',
    '/landingpage',
    '/win-a-trip',
    '/broker-contest',
    '/dar-global-exclusive',
    '/darglobal-exclusive',
    '/privacy-policy',
    '/terms',
    '/cookie',
    '/become-a-broker',
    '/become-an-agent',
)

PRIORITY_PATTERNS = (
    '/about',
    '/faq',
    '/projects',
    '/marea',
    '/neptune',
    '/dg1',
    '/aida',
    '/the-astera',
    '/astera',
    '/urban-oasis',
    '/w-residences',
    '/davinci-tower',
    '/tierra-viva',
    '/les-vagues',
    '/one-of-one',
    '/trump',
    '/aida-360',
    '/insights',
    '/press',
    '/blog',
    '/hospitality',
    '/commercial',
    '/luxury-golf-communities',
    '/why-invest',
    '/insignia',
    '/dg-circle',
    '/exclusive-membership',
    '/development-management',
    '/partners',
    '/investor',
)

LOCATION_PATTERNS = (
    'Dubai',
    'Abu Dhabi',
    'Ras Al Khaimah',
    'RAK',
    'Muscat',
    'Oman',
    'Riyadh',
    'Jeddah',
    'Saudi Arabia',
    'Doha',
    'Qatar',
    'London',
    'United Kingdom',
    'UK',
    'Benahavis',
    'Benahavís',
    'Costa del Sol',
    'Marbella',
    'Spain',
    'Simaisma',
    'AIDA',
    'Al Marjan Island',
)

PROPERTY_TYPES = (
    'Villa',
    'Apartment',
    'Penthouse',
    'Residence',
    'Hotel',
    'Townhouse',
    'Plot',
    'Mansion',
    'Branded Residence',
    'Golf Community',
)

STATUS_PATTERNS = (
    'Off-plan',
    'Off plan',
    'Ready to move',
    'Ready',
    'Under construction',
    'Coming soon',
    'Sold out',
    'Launching soon',
)


class DarGlobalScraper(BaseScraper):
    source_name = 'dar_global'
    base_url = 'https://darglobal.co.uk'
    allowed_domains = ('darglobal.co.uk', 'www.darglobal.co.uk')

    FALLBACK_URLS = (
        'https://darglobal.co.uk/',
        'https://darglobal.co.uk/about',
        'https://darglobal.co.uk/faq',
        'https://darglobal.co.uk/projects',
        'https://darglobal.co.uk/insights',
        'https://darglobal.co.uk/press',
        'https://darglobal.co.uk/blog',
        'https://darglobal.co.uk/marea',
        'https://darglobal.co.uk/neptune',
        'https://darglobal.co.uk/dg1',
        'https://darglobal.co.uk/aida-360',
        'https://darglobal.co.uk/one-of-one',
    )

    def discover_urls(self) -> list[str]:
        urls: list[str] = []
        for sitemap in ('https://darglobal.co.uk/sitemap.xml', 'https://darglobal.co.uk/sitemap_index.xml'):
            urls.extend(self.parse_sitemap(sitemap))
        if not urls:
            urls.extend(self.FALLBACK_URLS)
        urls.extend(self.FALLBACK_URLS)

        filtered: list[str] = []
        seen: set[str] = set()
        for url in urls:
            parsed = urlparse(url)
            path = parsed.path.rstrip('/').lower() or '/'
            if not self.is_allowed_url(url):
                continue
            if any(path.startswith(excluded) or excluded in path for excluded in EXCLUDED_PATHS):
                continue
            if path in ('/pay-online/status',):
                continue
            normalized = f'https://darglobal.co.uk{parsed.path.rstrip("/") or "/"}'
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            filtered.append(normalized)

        def score(url: str) -> tuple[int, int]:
            path = urlparse(url).path.lower()
            if path == '/' or path == '':
                return (0, len(path))
            for index, pattern in enumerate(PRIORITY_PATTERNS):
                if pattern in path:
                    return (index + 1, len(path))
            return (100, len(path))

        filtered.sort(key=score)
        return filtered

    def parse_page(self, url: str, html_text: str) -> ScrapedDocument | None:
        soup = self.soup(html_text)
        title = normalize_block(soup.title.get_text(' ', strip=True) if soup.title else '')
        if not title:
            title = normalize_block(self.meta_content(soup, ('og:title', 'twitter:title'))) or url
        h1 = soup.find('h1')
        h1_text = normalize_block(h1.get_text(' ', strip=True)) if h1 else ''
        meta_description = self.meta_content(soup, ('description', 'og:description'))
        content = self.extract_visible_text(soup)
        if len(content) < 80:
            return None

        project_name = h1_text or self.meta_content(soup, ('og:title',)) or title
        location = self._extract_location(content, title)
        property_type = self._extract_property_type(content, title)
        price = extract_price(content)
        status = self._extract_status(content)
        amenities = self._extract_amenities(soup, content)
        contacts = {
            'emails': extract_emails(content),
            'phones': extract_phones(content),
        }
        summary_parts = [
            f'Project: {project_name}' if project_name else '',
            f'Location: {location}' if location else '',
            f'Property type: {property_type}' if property_type else '',
            f'Price: {price}' if price else '',
            f'Status: {status}' if status else '',
            f'Amenities: {", ".join(amenities)}' if amenities else '',
            f'Website summary: {meta_description}' if meta_description else '',
        ]
        summary = '. '.join(part for part in summary_parts if part)
        enriched = clean_text(f'{summary}\n\n{content}')[:20000]
        metadata = {
            'site': 'DarGlobal',
            'source_label': 'DarGlobal',
            'project_name': project_name,
            'description_meta': meta_description,
            'location': location,
            'country': self._extract_country(location),
            'property_type': property_type,
            'price': price,
            'status': status,
            'amenities': amenities,
            'contact_info': contacts,
            'page_path': urlparse(url).path,
            'language': 'en',
        }
        return ScrapedDocument(
            id=make_id(f'{self.source_name}:{url}'),
            source=self.source_name,
            url=url,
            title=title,
            content=enriched,
            scraped_at=self.now_iso(),
            metadata=metadata,
        )

    def coverage_note(self) -> str:
        return (
            'DarGlobal pages are intermittently protected by an Incapsula access challenge. '
            'The scraper uses the public sitemap for discovery and records blocked pages without attempting to bypass protections. '
            'Existing verified page captures are preserved across runs.'
        )

    def _extract_location(self, content: str, title: str) -> str | None:
        haystack = f'{title} {content[:4000]}'
        found: list[str] = []
        for location in LOCATION_PATTERNS:
            if re.search(rf'\b{re.escape(location)}\b', haystack, re.IGNORECASE):
                found.append(location)
        if not found:
            match = re.search(r'\b([A-Z][A-Za-z\-]+(?: [A-Z][A-Za-z\-]+)*),\s*(United Arab Emirates|UAE|Saudi Arabia|Qatar|Oman|Spain|United Kingdom|UK)\b', haystack)
            if match:
                return normalize_block(f'{match.group(1)}, {match.group(2)}')
            return None
        unique: list[str] = []
        for item in found:
            if item not in unique:
                unique.append(item)
        return ', '.join(unique[:3])

    def _extract_country(self, location: str | None) -> str | None:
        if not location:
            return None
        countries = ('United Arab Emirates', 'UAE', 'Saudi Arabia', 'Qatar', 'Oman', 'Spain', 'United Kingdom', 'UK')
        for country in countries:
            if country.lower() in location.lower():
                return country
        return None

    def _extract_property_type(self, content: str, title: str) -> str | None:
        haystack = f'{title} {content[:4000]}'
        for property_type in PROPERTY_TYPES:
            if re.search(rf'\b{re.escape(property_type)}\b', haystack, re.IGNORECASE):
                return property_type
        return None

    def _extract_status(self, content: str) -> str | None:
        for status in STATUS_PATTERNS:
            if re.search(rf'\b{re.escape(status)}\b', content, re.IGNORECASE):
                return status
        return None

    def _extract_amenities(self, soup: BeautifulSoup, content: str) -> list[str]:
        headings = ('amenities', 'facilities', 'features', 'highlights', 'lifestyle')
        items: list[str] = []
        for heading in soup.find_all(['h2', 'h3', 'h4', 'strong']):
            text = normalize_block(heading.get_text(' ', strip=True)).lower()
            if not any(word in text for word in headings):
                continue
            sibling = heading.find_next_sibling()
            hops = 0
            while sibling and hops < 4:
                if sibling.name in ('ul', 'ol'):
                    for li in sibling.find_all('li'):
                        value = normalize_block(li.get_text(' ', strip=True))
                        if 2 < len(value) < 120:
                            items.append(value)
                    break
                sibling = sibling.find_next_sibling()
                hops += 1
            if items:
                break
        if not items:
            match = re.search(r'(?:amenities|facilities|features)\s*[:\-]\s*([^\n]{10,240})', content, re.IGNORECASE)
            if match:
                items = [part.strip() for part in re.split(r'[,;|]', match.group(1)) if part.strip()]
        unique: list[str] = []
        for item in items:
            if item not in unique:
                unique.append(item)
        return unique[:15]
