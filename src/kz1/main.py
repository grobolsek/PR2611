"""KZ-1 Scraper (BeautifulSoup version).

=====================================
Fetches the Slovenian Criminal Code from pisrs.si and parses it into:

{
  "člen 1":  { "title": "Uveljavljanje kazenske odgovornosti",
               "section": {"1": "...", "2": "...", "3": "..."} },
  "člen 2":  { "title": "Ni kaznivega dejanja in kazni brez zakona",
               "section": {"1": "..."} },
  "člen 15a": { ... },
  ...
}

"""

import json
import logging
import re
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

URL = "https://pisrs.si/api/datoteke/integracije/358153123"

# Matches "1. člen", "15.a člen", "36.a člen" (with possible &nbsp; inside)
ARTICLE_RE = re.compile(r"^(\d+)\.?\s*([a-z])?\s*člen$")

# Matches leading section marker like "(1) " or "(2a) "
SECTION_RE = re.compile(r"^\((\d+[a-z]?)\)\s*")


def fetch_html(url: str) -> str:
    """Fetch HTML content from the given URL with a User-Agent header."""
    if not url.startswith(("http://", "https://")):
        raise ValueError("URL must start with 'http://' or 'https://'")

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})  # noqa: S310
    with urllib.request.urlopen(req) as resp:  # noqa: S310
        raw = resp.read()
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def normalize(text: str) -> str:
    """Replace non-breaking spaces and strip."""
    return text.replace("\xa0", " ").strip()


def parse(html: str) -> dict:
    """Parse KZ-1 HTML and return a dict keyed by article identifier."""
    soup = BeautifulSoup(html, "html.parser")

    clen_tags = soup.find_all("p", class_="clen")

    result: dict = {}

    for i, tag in enumerate(clen_tags):
        text = normalize(tag.get_text(" ", strip=True))
        m = ARTICLE_RE.match(text)
        if not m:
            continue  # it's a title tag, will be picked up when we process the number tag

        num = m.group(1)  # "15"
        letter = m.group(2) or ""  # "a" or ""
        num_key = num + letter  # "15a" or "15"

        # Title is the previous p.clen, unless it itself is an article number
        title = ""
        if i > 0:
            prev = normalize(clen_tags[i - 1].get_text(" ", strip=True))
            if not ARTICLE_RE.match(prev):
                title = prev

        # Collect <p class="odstavek"> siblings until the next p.clen
        sections: dict = {}
        for sibling in tag.find_next_siblings("p"):
            sibling_classes = sibling.get("class") or []

            if "clen" in sibling_classes:
                break  # next article starts here

            if "odstavek" in sibling_classes:
                raw = normalize(sibling.get_text(" ", strip=True))
                sm = SECTION_RE.match(raw)
                if sm:
                    sec_num = sm.group(1)
                    sec_text = raw[sm.end() :].strip()
                    sections[sec_num] = sec_text
                else:
                    # No "(N)" marker → single-paragraph article, key = "1"
                    sections.setdefault("1", raw)

        result[f"člen {num_key}"] = {
            "title": title,
            "section": sections,
        }

    return result


def scrape(*, force: bool = False) -> None:
    """Fetch, parse, and save KZ-1 to kz1.json.

    Args:
        force (bool): if file exists it will not scrape again.
    """
    project_root = Path(__file__).parents[2]
    existing = next(project_root.rglob("kz1.json"), None)

    if existing and not force:
        logger.info("kz1.json already exists: %s", existing)
        return

    html = fetch_html(URL)
    data = parse(html)

    out = project_root / "kz1.json"
    with out.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
