from __future__ import annotations

import hashlib
from typing import Iterator
from urllib.parse import urljoin, urlparse

from litepaperreader.connectors.base import ResourceRef, ResourceMeta, SourceConnector


class WebConnector(SourceConnector):
    """Fetch web pages and scan sitemaps."""

    def __init__(self, user_agent: str | None = None, timeout: float = 30.0):
        self._user_agent = user_agent or "LitePaperReader/1.0"
        self._timeout = timeout
        self._client = None

    def _lazy_client(self):
        if self._client is None:
            import httpx
            self._client = httpx.Client(
                headers={"User-Agent": self._user_agent},
                timeout=self._timeout,
                follow_redirects=True,
            )
        return self._client

    def scan(self, path: str) -> Iterator[ResourceRef]:
        parsed = urlparse(path)
        if not parsed.scheme:
            return
        yield self._ref_for(path)

        sitemap_url = urljoin(path, "/sitemap.xml")
        try:
            client = self._lazy_client()
            resp = client.get(sitemap_url)
            resp.raise_for_status()
            import xml.etree.ElementTree as ET
            root_el = ET.fromstring(resp.content)
            ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            for loc in root_el.iterfind(".//sm:loc", ns):
                url = loc.text.strip()
                if url:
                    yield self._ref_for(url)
        except Exception:
            pass

    def read(self, ref: ResourceRef) -> bytes:
        client = self._lazy_client()
        resp = client.get(ref.resource_path)
        resp.raise_for_status()
        return resp.content

    def metadata(self, ref: ResourceRef) -> ResourceMeta:
        return ResourceMeta(
            path=ref.resource_path,
            content_type="html",
            extra={"url": ref.resource_path},
        )

    def _ref_for(self, url: str) -> ResourceRef:
        chk = hashlib.sha256(url.encode()).hexdigest()[:16]
        return ResourceRef(
            connector="web",
            resource_path=url,
            content_type_hint="html",
            checksum=chk,
            metadata={"url": url},
        )
