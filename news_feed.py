"""
News Feed - Recupera news crypto da RSS feed.

Fonte: CoinJournal RSS
"""

import logging
import re
import xml.etree.ElementTree as ET
from datetime import timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import List

import requests

logger = logging.getLogger(__name__)

NEWS_FEED_URL = "https://coinjournal.net/news/feed/"
REQUEST_TIMEOUT = 15  # secondi


def _strip_html_tags(text: str) -> str:
    """Rimuove tag HTML e normalizza whitespace."""
    if not text:
        return ""
    cleaned = unescape(text)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def fetch_latest_news(max_chars: int = 4000) -> str:
    """
    Recupera le ultime news dal feed RSS.
    
    Args:
        max_chars: Limite massimo caratteri nell'output
        
    Returns:
        Stringa con news formattate (una per riga)
    """
    try:
        logger.debug(f"Fetch news da {NEWS_FEED_URL}")
        
        response = requests.get(NEWS_FEED_URL, timeout=REQUEST_TIMEOUT)
        if response.status_code != 200:
            logger.warning(f"Failed to fetch news feed: status {response.status_code}")
            return ""

        root = ET.fromstring(response.content)
        channel = root.find("channel")
        if channel is None:
            return ""

        entries: List[str] = []

        for item in channel.findall("item"):
            title = _strip_html_tags(item.findtext("title") or "")
            pub_date_raw = (item.findtext("pubDate") or "").strip()
            summary_raw = item.findtext("description") or ""

            # Pulisci summary
            summary = _strip_html_tags(summary_raw)
            summary = re.sub(
                r"The post .*? appeared first on .*",
                "",
                summary,
                flags=re.IGNORECASE,
            ).strip()

            # Formatta timestamp
            formatted_time = pub_date_raw
            if pub_date_raw:
                try:
                    parsed = parsedate_to_datetime(pub_date_raw)
                    if parsed is not None:
                        if parsed.tzinfo is None:
                            parsed = parsed.replace(tzinfo=timezone.utc)
                        else:
                            parsed = parsed.astimezone(timezone.utc)
                        formatted_time = parsed.strftime("%Y-%m-%d %H:%M:%SZ")
                except Exception:
                    formatted_time = pub_date_raw

            # Costruisci entry
            parts = []
            if formatted_time:
                parts.append(formatted_time)
            if title:
                parts.append(title)

            entry_text = " | ".join(parts)
            if summary:
                entry_text = f"{entry_text}: {summary}" if entry_text else summary

            entry_text = entry_text.strip()
            if not entry_text:
                continue

            # Controlla limite caratteri
            existing_text = "\n".join(entries)
            candidate_text = (
                f"{existing_text}\n{entry_text}" if existing_text else entry_text
            )

            if len(candidate_text) > max_chars:
                remaining = max_chars - len(existing_text)
                if existing_text:
                    remaining -= 1
                if remaining <= 0:
                    break
                truncated = entry_text[:remaining].rstrip()
                if truncated:
                    if len(truncated) < len(entry_text):
                        truncated = truncated.rstrip(" .,;:-") + "..."
                    entries.append(truncated)
                break

            entries.append(entry_text)

        news_count = len(entries)
        logger.info(f"Recuperate {news_count} news")
        
        return "\n".join(entries)

    except Exception as err:
        logger.warning(f"Failed to process news feed: {err}")
        return f"Failed to process news feed: {err}"
