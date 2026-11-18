from __future__ import annotations

import json
import logging
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.utils.text import (
    clean_text,
    extract_emails,
    extract_number,
    extract_phones,
    extract_price,
    make_id,
    normalize_block,
    slug_to_title,
)

from .base import BaseScraper, ScrapedDocument

logger = logging.getLogger(__name__)

STATIC_SITEMAP = 'https://cdn.wasalt.sa/sitemap/static_sitemap_en_sa.xml.gz'
CATEGORY_SITEMAP = 'https://cdn.wasalt.sa/sitemap/category_sitemap_en_sa.xml.gz'
PRODUCT_SITEMAP = 'https://cdn.wasalt.sa/sitemap/product_sitemap_en_sa.xml.gz'
RENTAL_SITEMAP = 'https://cdn.wasalt.sa/sitemap/rental_pdp_sitemap_en_sa.xml.gz'

PRIORITY_CITIES = (
    'riyadh',
    'jeddah',
    'makkah',
    'madinah',
    'dammam',
    'al-khobar',
    'khobar',
    'taif',
    'abha',
    'tabuk',
    'buraidah',
    'hail',
    'jazan',
    'najran',
    'yanbu',
    'jubail',
    'al-ahsa',
    'qatif',
    'al-madinah',
)

PRIORITY_TYPES = ('villas', 'apartments', 'lands', 'properties')

TYPE_MAP = {
    'SingleFamilyResidence': 'Villa',
    'House': 'Villa',
    'Apartment': 'Apartment',
    'Residence': 'Residence',
    'Product': 'Property',
    'RealEstateListing': 'Property',
    'Place': 'Location',
}


def _sample_evenly(urls: list[str], limit: int) -> list[str]:
    if limit <= 0 or not urls:
        return []
    if len(urls) <= limit:
        return list(urls)
    if limit == 1:
        return [urls[0]]
    step = (len(urls) - 1) / (limit - 1)
    indexes = sorted({int(round(index * step)) for index in range(limit)})
    return [urls[index] for index in indexes]


class WasaltScraper(BaseScraper):
    source_name = 'wasalt'
    base_url = 'https://wasalt.sa/en'
    allowed_domains = ('wasalt.sa', 'www.wasalt.sa', 'cdn.wasalt.sa')

    def discover_urls(self) -> list[str]:
        static_urls = self.parse_sitemap(STATIC_SITEMAP)
        category_urls = self.parse_sitemap(CATEGORY_SITEMAP)
        product_urls = self.parse_sitemap(PRODUCT_SITEMAP)
        rental_urls = self.parse_sitemap(RENTAL_SITEMAP)

        selected: list[str] = ['https://wasalt.sa/en']

        for url in static_urls:
            path = urlparse(url).path.lower()
            if path in ('/en', '/en/'):
                continue
            if '/s/wasalt-business' in path or '/s/masterplan' in path:
                selected.append(url)

        priority_categories = [
            url
            for url in category_urls
            if any(city in url.lower() for city in PRIORITY_CITIES)
            and any(kind in url.lower() for kind in PRIORITY_TYPES)
        ]
        selected.extend(_sample_evenly(priority_categories, 30))

        recent_products = [url for url in product_urls if '/property/sale/' in url][:40]
        diverse_products = _sample_evenly(
            [url for url in product_urls if '/property/sale/' in url][40:],
            40,
        )
        selected.extend(recent_products)
        selected.extend(diverse_products)
        selected.extend(_sample_evenly(rental_urls, 12))

        filtered: list[str] = []
        seen: set[str] = set()
        for url in selected:
            parsed = urlparse(url)
            if not self.is_allowed_url(url):
                continue
            path = parsed.path
            if not path.startswith('/en'):
                continue
            if path.startswith('/search') or '/ar' in path.split('/'):
                continue
            normalized = f'https://wasalt.sa{path.rstrip("/") or "/en"}'
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            filtered.append(normalized)
        return filtered

    def parse_page(self, url: str, html_text: str) -> ScrapedDocument | None:
        soup = self.soup(html_text)
        title = normalize_block(soup.title.get_text(' ', strip=True) if soup.title else '')
        meta_description = self.meta_content(soup, ('description', 'og:description'))
        structured = self._json_ld(soup)
        if '/property/' in urlparse(url).path or '/dailyrental/' in urlparse(url).path:
            document = self._parse_property(url, soup, title, meta_description, structured)
            if document:
                return document
        return self._parse_generic(url, soup, title, meta_description)

    def coverage_note(self) -> str:
        return (
            'Bounded sample of public English Wasalt pages discovered through the published sitemaps. '
            'The sitemaps contain tens of thousands of listings; this dataset samples recent and geographically diverse pages '
            'rather than mirroring the full marketplace.'
        )

    def _json_ld(self, soup: BeautifulSoup) -> list[dict]:
        items: list[dict] = []
        for script in soup.find_all('script', attrs={'type': 'application/ld+json'}):
            raw = script.string or script.get_text()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except ValueError:
                continue
            if isinstance(payload, list):
                items.extend([item for item in payload if isinstance(item, dict)])
            elif isinstance(payload, dict):
                if isinstance(payload.get('@graph'), list):
                    items.extend([item for item in payload['@graph'] if isinstance(item, dict)])
                items.append(payload)
        return items

    def _parse_property(
        self,
        url: str,
        soup: BeautifulSoup,
        title: str,
        meta_description: str,
        structured: list[dict],
    ) -> ScrapedDocument | None:
        property_node = next(
            (item for item in structured if str(item.get('@type')) in TYPE_MAP and item.get('@type') != 'BreadcrumbList'),
            None,
        )
        breadcrumbs = next((item for item in structured if item.get('@type') == 'BreadcrumbList'), None)
        breadcrumb_names = []
        if breadcrumbs:
            for entry in breadcrumbs.get('itemListElement', []):
                name = normalize_block(entry.get('name', '')) if isinstance(entry, dict) else ''
                if name:
                    breadcrumb_names.append(name)

        description_html = property_node.get('description', '') if property_node else ''
        description = clean_text(description_html)
        name = normalize_block(property_node.get('name', '')) if property_node else ''
        name = name or title

        address = property_node.get('address', {}) if property_node else {}
        locality = normalize_block(address.get('addressLocality', '')) if isinstance(address, dict) else ''
        region = normalize_block(address.get('addressRegion', '')) if isinstance(address, dict) else ''
        country = normalize_block(address.get('addressCountry', '')) if isinstance(address, dict) else ''
        location_parts = [part for part in (locality, region, country) if part]
        location = ', '.join(dict.fromkeys(location_parts)) or self._location_from_breadcrumbs(breadcrumb_names)

        property_type = TYPE_MAP.get(str(property_node.get('@type')), 'Property') if property_node else 'Property'
        price = self._price_from_node(property_node) or extract_price(description)
        bedrooms = self._int_value(property_node.get('numberOfBedrooms')) if property_node else None
        if bedrooms is None:
            bedrooms = extract_number(description, ['bedrooms', 'bedroom'])
        area = self._area_from_node(property_node) if property_node else None
        if area is None:
            match = re.search(r'([0-9][0-9,\.]*)\s*(?:SQM|sqm|m²|sq\.? ?m)', description)
            area = match.group(1) if match else None
        status = 'For rent' if '/dailyrental/' in url or '/rent' in urlparse(url).path else 'For sale'

        visible = self.extract_visible_text(soup, max_length=12000)
        detail_parts = [
            f'Property: {name}',
            f'Location: {location}' if location else '',
            f'Property type: {property_type}',
            f'Listing status: {status}',
            f'Price: {price}' if price else '',
            f'Bedrooms: {bedrooms}' if bedrooms is not None else '',
            f'Area: {area} SQM' if area else '',
            f'Description: {description}' if description else '',
            f'Breadcrumbs: {" > ".join(breadcrumb_names)}' if breadcrumb_names else '',
            f'Page summary: {meta_description}' if meta_description else '',
        ]
        content = clean_text('\n'.join(part for part in detail_parts if part) + '\n\n' + visible)[:20000]
        if len(content) < 120:
            return None

        metadata = {
            'site': 'Wasalt',
            'source_label': 'Wasalt',
            'project_name': name,
            'description_meta': meta_description or description[:240],
            'location': location,
            'country': country or 'Saudi Arabia',
            'property_type': property_type,
            'price': price,
            'bedrooms': bedrooms,
            'area_sqm': area,
            'status': status,
            'amenities': [],
            'contact_info': {
                'emails': extract_emails(visible),
                'phones': extract_phones(visible),
            },
            'page_path': urlparse(url).path,
            'listing_id': self._listing_id(url),
            'breadcrumbs': breadcrumb_names,
            'language': 'en',
        }
        return ScrapedDocument(
            id=make_id(f'{self.source_name}:{url}'),
            source=self.source_name,
            url=url,
            title=title or name,
            content=content,
            scraped_at=self.now_iso(),
            metadata=metadata,
        )

    def _parse_generic(
        self,
        url: str,
        soup: BeautifulSoup,
        title: str,
        meta_description: str,
    ) -> ScrapedDocument | None:
        content = self.extract_visible_text(soup)
        if len(content) < 120:
            return None
        path = urlparse(url).path
        property_type = next((kind.rstrip('s').title() for kind in PRIORITY_TYPES if kind in path), None)
        location = self._location_from_path(path)
        price = extract_price(content)
        heading = soup.find('h1')
        heading_text = normalize_block(heading.get_text(' ', strip=True)) if heading else ''
        name = heading_text or title
        detail_parts = [
            f'Page: {name}',
            f'Location: {location}' if location else '',
            f'Property type: {property_type}' if property_type else '',
            f'Price information: {price}' if price else '',
            f'Page summary: {meta_description}' if meta_description else '',
        ]
        enriched = clean_text('\n'.join(part for part in detail_parts if part) + '\n\n' + content)[:20000]
        metadata = {
            'site': 'Wasalt',
            'source_label': 'Wasalt',
            'project_name': name,
            'description_meta': meta_description,
            'location': location,
            'country': 'Saudi Arabia',
            'property_type': property_type,
            'price': price,
            'status': None,
            'amenities': [],
            'contact_info': {
                'emails': extract_emails(content),
                'phones': extract_phones(content),
            },
            'page_path': path,
            'language': 'en',
        }
        return ScrapedDocument(
            id=make_id(f'{self.source_name}:{url}'),
            source=self.source_name,
            url=url,
            title=title or name,
            content=enriched,
            scraped_at=self.now_iso(),
            metadata=metadata,
        )

    def _price_from_node(self, node: dict | None) -> str | None:
        if not node:
            return None
        offers = node.get('offers')
        candidates = offers if isinstance(offers, list) else [offers] if isinstance(offers, dict) else []
        for offer in candidates:
            if not isinstance(offer, dict):
                continue
            price = offer.get('price') or offer.get('lowPrice')
            currency = offer.get('priceCurrency') or 'SAR'
            if price:
                return normalize_block(f'{price} {currency}')
        return None

    def _area_from_node(self, node: dict) -> str | None:
        floor_size = node.get('floorSize')
        if isinstance(floor_size, dict):
            value = floor_size.get('value')
            unit = floor_size.get('unitText') or 'SQM'
            if value:
                return normalize_block(f'{value} {unit}')
        return None

    def _int_value(self, value) -> int | None:
        if value is None:
            return None
        match = re.search(r'[0-9]+', str(value))
        return int(match.group(0)) if match else None

    def _listing_id(self, url: str) -> str | None:
        match = re.search(r'-([0-9]{4,})$', urlparse(url).path)
        return match.group(1) if match else None

    def _location_from_breadcrumbs(self, names: list[str]) -> str | None:
        candidates = [name for name in names if ' for ' not in name.lower() and name.lower() not in ('homepage', 'home')]
        if not candidates:
            return None
        return ', '.join(candidates[-3:])

    def _location_from_path(self, path: str) -> str | None:
        match = re.search(r'-in-([a-z0-9\-]+)$', path)
        if match:
            return slug_to_title(match.group(1))
        return None
