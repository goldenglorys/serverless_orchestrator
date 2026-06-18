"""
Fetches https://www.himanshustwts.com/chinese-frontier/catalog.md,
parses every entry, deduplicates against Supabase, and inserts only new rows.

Runs as a Vercel serverless function (GET /api/scrape_chinese_frontier).
Also callable as a plain function via run_scrape_and_sync() from alpha_pinger.
"""

import json
import logging
import re
import sys
import os
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from typing import Any, Dict, List, Set, Tuple

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CATALOG_URL = "https://www.himanshustwts.com/chinese-frontier/catalog.md"
TABLE = "chinese_frontier"


# ── Markdown parser ────────────────────────────────────────────────────────────

def extract_first_link(body: str) -> Tuple[str, str]:
    """Return (link_text, link_url) for the first parenthesised link in body."""
    # Matches: (LinkText, https://...) or (LinkText:ID, https://...)
    match = re.search(r'\(([^,()\n]+?),\s*(https?://[^\s,;)]+)', body)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    # Fallback: bare URL anywhere in body
    url_match = re.search(r'https?://\S+', body)
    if url_match:
        return "Link", url_match.group(0).rstrip(')')
    return "", ""


def extract_date(link_url: str, body: str) -> str:
    """Derive a human-readable date from an arXiv URL or body text."""
    if link_url:
        m = re.search(r'arxiv\.org/(?:abs|pdf)/(\d{4})\.\d+', link_url)
        if m:
            code = m.group(1)
            year = "20" + code[:2]
            month = int(code[2:]) - 1
            months = ["Jan","Feb","Mar","Apr","May","Jun",
                      "Jul","Aug","Sep","Oct","Nov","Dec"]
            if 0 <= month < 12:
                return f"{months[month]} {year}"
    # Try to pull a year from body like "arXiv:2405..." or "(May 2024)"
    year_match = re.search(r'\b(20\d{2})\b', body)
    if year_match:
        return year_match.group(1)
    return ""


def clean_description(body: str) -> str:
    """Strip link parentheses from the body to get a clean description."""
    # Remove all (...link...) blocks
    cleaned = re.sub(r'\([^()]*https?://[^()]*\)', '', body)
    # Remove stray semicolons left behind by multi-link entries
    cleaned = re.sub(r';\s*$', '', cleaned.strip())
    return cleaned.strip().rstrip('.')


VERTICALS = {
    "Architecture", "Pre-training", "Reinforcement Learning", "Post-training",
    "Alignment", "Safety", "Multimodal", "Agents", "Long-context", "Inference",
    "Serving", "Embeddings", "Retrieval", "Code", "Domain", "Evaluation",
    "Training Systems", "Data", "General",
}

def parse_catalog(markdown: str) -> List[Dict[str, Any]]:
    """Parse catalog.md into a list of structured entry dicts."""
    lines = markdown.splitlines()
    entries = []
    company = "Uncategorized"
    vertical = "General"
    in_lab_map = False
    has_lab_map = "## Lab-wise Innovation Map" in markdown

    for line in lines:
        # Enter the Lab-wise section
        if re.match(r'^##\s+Lab-wise Innovation Map\s*$', line, re.I):
            in_lab_map = True
            company = "Uncategorized"
            continue

        # Exit at the next ## heading after entering
        if has_lab_map and in_lab_map and re.match(r'^##\s+', line) and \
                not re.match(r'^##\s+Lab-wise Innovation Map\s*$', line, re.I):
            break

        if has_lab_map and not in_lab_map:
            continue

        # ### Company heading
        lab_match = re.match(r'^###\s+(.+)$', line)
        if lab_match:
            company = lab_match.group(1).strip()
            continue

        # - **Technique** — [Vertical.] Description. (link)
        bullet = re.match(r'^-\s+\*\*(.+?)\*\*\s+—\s+(.+)$', line)
        if not bullet:
            continue

        technique = bullet.group(1).strip()
        body = bullet.group(2).strip()

        # The vertical is the first token before the first period if it matches
        vert_match = re.match(r'^([^.]+?)\.\s+(.+)$', body, re.DOTALL)
        if vert_match and vert_match.group(1).strip() in VERTICALS:
            vertical = vert_match.group(1).strip()
            body = vert_match.group(2).strip()
        # else: keep the current vertical from previous entry in same company

        link_text, link_url = extract_first_link(body)
        date = extract_date(link_url, body)
        description = clean_description(body)

        entries.append({
            "company_lab": company,
            "technique_research": technique,
            "vertical": vertical,
            "description": description,
            "link_url": link_url,
            "link_text": link_text,
            "date": date,
        })

    logger.info(f"Parsed {len(entries)} entries from catalog.md")
    return entries


# ── Supabase helpers ───────────────────────────────────────────────────────────

def get_existing_keys(supabase_client) -> Set[Tuple[str, str]]:
    """Return set of (company_lab, technique_research) already in Supabase."""
    try:
        resp = supabase_client.table(TABLE).select("company_lab,technique_research").execute()
        return {(r["company_lab"], r["technique_research"]) for r in (resp.data or [])}
    except Exception as e:
        logger.error(f"Failed to fetch existing keys: {e}")
        return set()


def insert_entries(supabase_client, entries: List[Dict[str, Any]]) -> Dict[str, int]:
    stats = {"inserted": 0, "failed": 0}
    now = datetime.utcnow().isoformat()
    for entry in entries:
        entry["created_at"] = now

    for i in range(0, len(entries), 50):
        chunk = entries[i:i + 50]
        try:
            supabase_client.table(TABLE).insert(chunk).execute()
            stats["inserted"] += len(chunk)
        except Exception as e:
            logger.error(f"Insert chunk failed: {e}")
            stats["failed"] += len(chunk)
    return stats


# ── Main callable ──────────────────────────────────────────────────────────────

def run_scrape_and_sync() -> Dict[str, Any]:
    import httpx
    from utils.notion_supabase_sync import supabase_client

    # 1. Fetch catalog.md
    logger.info(f"Fetching {CATALOG_URL}")
    try:
        resp = httpx.get(CATALOG_URL, timeout=30.0, follow_redirects=True,
                         headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        markdown = resp.text
    except Exception as e:
        logger.error(f"Failed to fetch catalog.md: {e}")
        return {"status": "error", "error": str(e)}

    # 2. Parse
    scraped = parse_catalog(markdown)
    if not scraped:
        return {"status": "error", "error": "Parsed 0 entries"}

    # 3. Dedup
    existing = get_existing_keys(supabase_client)
    new_entries = [
        e for e in scraped
        if (e["company_lab"], e["technique_research"]) not in existing
    ]
    logger.info(f"Scraped {len(scraped)}, existing {len(existing)}, new {len(new_entries)}")

    # 4. Insert
    if not new_entries:
        return {"status": "success", "scraped": len(scraped), "inserted": 0, "duplicates": len(scraped)}

    stats = insert_entries(supabase_client, new_entries)

    return {
        "status": "success",
        "scraped": len(scraped),
        "inserted": stats["inserted"],
        "failed": stats["failed"],
        "duplicates": len(scraped) - len(new_entries),
    }


# ── Vercel handler ─────────────────────────────────────────────────────────────

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            result = run_scrape_and_sync()
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(result, indent=2).encode())
        except Exception as e:
            logger.error(f"Handler error: {e}")
            self.send_response(500)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "error", "error": str(e)}).encode())
