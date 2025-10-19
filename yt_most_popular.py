#!/usr/bin/env python3
"""
YouTube Most Popular Videos Finder

COMPLIANCE STATEMENT:
This script complies with YouTube API Services Terms and Policies:
- Displays only YouTube-provided metrics (views, likes, comments)
- No independently calculated or derived metrics (Policy III.E.4h)
- Data cached for maximum 24 hours (Policy III.E.4.a-g)
- Single project number: 55291277961 (Policy III.D.1c)
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv
from requests import Response

from utils import CacheManager, CacheTTL, QuotaLimitError, QuotaTracker, get_logger, setup_logging
from youtube_auth import get_youtube_token


YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

# YouTube API quota costs
SEARCH_QUOTA_COST = 100
VIDEO_DETAILS_QUOTA_COST = 1
DAILY_QUOTA_LIMIT = 10000
SAFETY_BUFFER = 500
DEFAULT_TIMEOUT_SECONDS = 30

# Cache settings
CACHE_DIR = os.path.join(".cache", "most_popular")


logger = get_logger(__name__)
cache_manager = CacheManager(CACHE_DIR)


def iso8601(dt: datetime) -> str:
    """Return UTC ISO8601 string acceptable by YouTube API."""
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

# REMOVED: compute_engagement_rate() function
# Violates YouTube API Policy III.E.4h(iii) - cannot offer independently calculated metrics
# API client displays only YouTube-provided data: views, likes, comments

def compute_published_after(period: str) -> datetime:
    period = period.lower()
    if period == "week":
        return datetime.now(timezone.utc) - timedelta(days=7)
    if period == "month":
        return datetime.now(timezone.utc) - timedelta(days=30)
    raise ValueError("period must be 'week' or 'month'")


def batched(iterable: List[str], size: int) -> List[List[str]]:
    return [iterable[i : i + size] for i in range(0, len(iterable), size)]


def _cache_key(*parts: str) -> str:
    return "::".join(parts)


def _cache_load(namespace: str, key_parts: List[str], ttl: CacheTTL, use_cache: bool, quota: Optional[QuotaTracker]) -> Optional[Any]:
    if not use_cache:
        return None
    payload = cache_manager.load(namespace, _cache_key(*key_parts), ttl)
    if payload is not None and quota is not None:
        quota.record_saved()
    return payload


def _cache_save(namespace: str, key_parts: List[str], payload: Any) -> None:
    cache_manager.save(namespace, _cache_key(*key_parts), payload)


def _build_headers(access_token: Optional[str]) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    return headers


def _request_json(
    namespace: str,
    key_parts: List[str],
    url: str,
    params: Dict[str, Any],
    headers: Dict[str, str],
    ttl: CacheTTL,
    use_cache: bool,
    quota: Optional[QuotaTracker],
    quota_cost: int,
    quota_action: str,
) -> Dict[str, Any]:
    cached = _cache_load(namespace, key_parts, ttl, use_cache, quota)
    if cached is not None:
        return cached

    if quota is not None and quota_cost:
        quota.ensure_within_limit(quota_cost)

    try:
        response = requests.get(url, params=params, headers=headers, timeout=DEFAULT_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.exceptions.HTTPError as exc:
        message, reason = parse_api_error(exc.response)
        raise SystemExit(
            f"YouTube API error during {quota_action}: {message} (reason={reason}). "
            "Check API credentials, enablement (YouTube Data API v3), and quota settings."
        ) from exc

    data = response.json()

    if quota is not None and quota_cost:
        quota.spend(quota_action, quota_cost)

    if use_cache:
        _cache_save(namespace, key_parts, data)

    return data


def search_videos(
    api_key: Optional[str],
    access_token: Optional[str],
    region_code: str,
    published_after: datetime,
    max_results: int,
    topic_id: Optional[str],
    query: Optional[str],
    quota: QuotaTracker,
    use_cache: bool,
) -> List[Dict]:
    """Search for recently published videos and return API search items."""

    if max_results <= 0:
        return []

    base_params: Dict[str, Any] = {
        "type": "video",
        "order": "date",
        "publishedAfter": iso8601(published_after),
        "maxResults": 50,
        "regionCode": region_code,
        "q": query or "a|e|i|o|u",
    }
    if api_key:
        base_params["key"] = api_key
    if topic_id:
        base_params["topicId"] = topic_id

    headers = _build_headers(access_token)
    url = f"{YOUTUBE_API_BASE}/search"

    items: List[Dict[str, Any]] = []
    next_page_token: Optional[str] = None

    while len(items) < max_results:
        params = dict(base_params)
        if next_page_token:
            params["pageToken"] = next_page_token

        key_parts = [json.dumps({k: v for k, v in params.items() if k != "key"}, sort_keys=True)]

        try:
            data = _request_json(
                namespace="search",
                key_parts=key_parts,
                url=url,
                params=params,
                headers=headers,
                ttl=CacheTTL.DAY,
                use_cache=use_cache,
                quota=quota,
                quota_cost=SEARCH_QUOTA_COST,
                quota_action="search.list",
            )
        except QuotaLimitError as exc:
            logger.warning("Quota limit reached during search.list: %s", exc)
            break

        page_items = data.get("items", [])
        items.extend(page_items)
        logger.debug("search.list returned %d items (total=%d)", len(page_items), len(items))

        if len(items) >= max_results:
            break

        next_page_token = data.get("nextPageToken")
        if not next_page_token:
            break

    return items[:max_results]


def fetch_video_stats(
    api_key: Optional[str],
    access_token: Optional[str],
    video_ids: List[str],
    quota: QuotaTracker,
    use_cache: bool,
) -> List[Dict]:
    """Fetch snippet and statistics for given video IDs."""

    if not video_ids:
        return []

    headers = _build_headers(access_token)
    url = f"{YOUTUBE_API_BASE}/videos"
    results: List[Dict[str, Any]] = []

    for chunk in batched(video_ids, 50):
        params: Dict[str, Any] = {
            "id": ",".join(chunk),
            "part": "snippet,statistics,contentDetails",
            "maxResults": 50,
        }
        if api_key:
            params["key"] = api_key

        key_parts = ["::".join(sorted(chunk))]
        cost = VIDEO_DETAILS_QUOTA_COST * len(chunk)

        try:
            data = _request_json(
                namespace="videos",
                key_parts=key_parts,
                url=url,
                params=params,
                headers=headers,
                ttl=CacheTTL.DAY,
                use_cache=use_cache,
                quota=quota,
                quota_cost=cost,
                quota_action="videos.list",
            )
        except QuotaLimitError as exc:
            logger.warning("Quota limit reached during videos.list: %s", exc)
            break

        chunk_items = data.get("items", [])
        results.extend(chunk_items)
        logger.debug("videos.list returned %d items (total=%d)", len(chunk_items), len(results))

    return results


def parse_api_error(resp: Optional[Response]) -> Tuple[str, str]:
    """Extract message and reason from a YouTube API error response."""
    if resp is None:
        return ("Unknown response", "unknown")
    try:
        payload = resp.json()
        message = payload.get("error", {}).get("message", str(resp.text))
        errors = payload.get("error", {}).get("errors", [])
        reason = errors[0].get("reason") if errors else payload.get("error", {}).get("status", "unknown")
        return message, reason or "unknown"
    except Exception:
        return (f"HTTP {resp.status_code} {resp.reason}", "unknown")


def human_int(n: Optional[str]) -> int:
    try:
        return int(n) if n is not None else 0
    except Exception:
        return 0


def assemble_results(video_items: List[Dict], sort_by: str = "views") -> List[Dict]:
    assembled: List[Dict] = []
    seen_video_ids = set()  # Track seen video IDs to avoid duplicates

    for v in video_items:
        vid = v.get("id")
        if not vid or vid in seen_video_ids:
            continue  # Skip duplicates

        seen_video_ids.add(vid)
        snippet = v.get("snippet", {})
        stats = v.get("statistics", {})
        assembled.append(
            {
                "videoId": vid,
                "title": snippet.get("title", ""),
                "channelTitle": snippet.get("channelTitle", ""),
                "publishedAt": snippet.get("publishedAt", ""),
                "views": human_int(stats.get("viewCount")),
                "likes": human_int(stats.get("likeCount")),
                "comments": human_int(stats.get("commentCount")),
                "url": f"https://www.youtube.com/watch?v={vid}",
            }
        )

    # Sort by the specified metric
    sort_key = sort_by if sort_by in ["views", "likes", "comments"] else "views"
    return sorted(assembled, key=lambda x: x[sort_key], reverse=True)


def print_table(rows: List[Dict], limit: int, sort_by: str = "views") -> None:
    limit = min(limit, len(rows))
    metric_name = sort_by.title()
    print(f"Top {limit} videos by {metric_name}:")
    print("-" * 80)
    print(f"{metric_name:>12}  {'Title':.60}")
    print("-" * 80)
    for row in rows[:limit]:
        metric_value = row[sort_by]
        print(f"{metric_value:>12,d}  {row['title'][:60]}")
    print("-" * 80)


def write_csv(rows: List[Dict], path: str, limit: int) -> None:
    fieldnames = ["videoId", "title", "channelTitle", "publishedAt", "views", "likes", "comments", "url"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows[:limit]:
            writer.writerow(row)


def write_json(rows: List[Dict], path: str, limit: int) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows[:limit], f, ensure_ascii=False, indent=2)


def write_markdown(rows: List[Dict], path: str, limit: int, sort_by: str = "views") -> None:
    with open(path, "w", encoding="utf-8") as f:
        metric_name = sort_by.title()
        f.write(f"# YouTube Most Popular Videos (by {metric_name})\n\n")
        f.write(f"Top {min(limit, len(rows))} videos by {metric_name}:\n\n")
        f.write(f"| Rank | {metric_name} | Title | Channel | Published |\n")
        f.write("|------|-------|-------|---------|-----------|\n")
        for i, row in enumerate(rows[:limit], 1):
            title = row['title'].replace('|', '\\|')[:60]
            channel = row['channelTitle'].replace('|', '\\|')[:30]
            published = row['publishedAt'][:10]
            metric_value = row[sort_by]
            f.write(f"| {i} | {metric_value:,} | [{title}]({row['url']}) | {channel} | {published} |\n")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find most viewed YouTube videos published recently (week or month).",
    )
    parser.add_argument("--period", choices=["week", "month"], default=os.getenv("YT_PERIOD", "week"), help="Time window (env: YT_PERIOD)")
    parser.add_argument("--region", default=os.getenv("YT_REGION", "US"), help="Region code (env: YT_REGION)")
    parser.add_argument("--max-results", type=int, default=int(os.getenv("YT_MAX_RESULTS", "100")), help="Videos to fetch (env: YT_MAX_RESULTS)")
    parser.add_argument("--top", type=int, default=int(os.getenv("YT_TOP", "25")), help="Top results to show (env: YT_TOP)")
    parser.add_argument("--sort-by", choices=["views", "likes", "comments"], default=os.getenv("YT_SORT_BY", "views"), help="Sort results by metric (env: YT_SORT_BY)")
    parser.add_argument("--topic-id", default=os.getenv("YT_TOPIC_ID"), help="Topic ID (env: YT_TOPIC_ID)")
    parser.add_argument("--query", default=os.getenv("YT_QUERY"), help="Search query (env: YT_QUERY)")
    parser.add_argument("--podcast", action="store_true", help="Search for podcast content specifically")
    parser.add_argument("--published-after", default=os.getenv("YT_PUBLISHED_AFTER"), help="ISO8601 timestamp (env: YT_PUBLISHED_AFTER)")
    parser.add_argument("--api-key", default=os.getenv("YOUTUBE_API_KEY"), help="API key (env: YOUTUBE_API_KEY)")
    parser.add_argument("--csv", default=os.getenv("YT_CSV_PATH"), help="CSV path (env: YT_CSV_PATH)")
    parser.add_argument("--json", dest="json_out", default=os.getenv("YT_JSON_PATH"), help="JSON path (env: YT_JSON_PATH)")
    parser.add_argument("--md", default=os.getenv("YT_MD_PATH"), help="Markdown path (env: YT_MD_PATH)")
    parser.add_argument("--no-cache", action="store_true", help="Disable caching (force fresh API calls)")
    parser.add_argument("--clear-cache", action="store_true", help="Clear all cached data before running")
    parser.add_argument("--log-level", default=os.getenv("LOG_LEVEL", "INFO"), help="Logging level (env: LOG_LEVEL)")
    return parser.parse_args(argv)


def resolve_credentials(api_key_arg: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    api_key = api_key_arg or os.getenv("YOUTUBE_API_KEY")
    if api_key:
        return api_key, None
    access_token = get_youtube_token()
    return None, access_token


def clear_cache() -> None:
    """Clear all cached data."""
    cache_manager.clear_all()
    logger.info("Cache cleared")


def main(argv: Optional[List[str]] = None) -> int:
    load_dotenv()
    args = parse_args(argv)
    setup_logging(args.log_level.upper())

    use_cache = not args.no_cache

    if args.clear_cache:
        clear_cache()

    api_key, access_token = resolve_credentials(args.api_key)

    quota = QuotaTracker(daily_limit=DAILY_QUOTA_LIMIT, safety_buffer=SAFETY_BUFFER)

    estimated_search_requests = max(1, (max(1, args.max_results) + 49) // 50)
    estimated_search_cost = estimated_search_requests * SEARCH_QUOTA_COST
    estimated_video_cost = min(args.max_results, 200) * VIDEO_DETAILS_QUOTA_COST
    total_estimated = estimated_search_cost + estimated_video_cost

    logger.info(
        "Estimated quota usage: %d (search=%d, videos=%d)",
        total_estimated,
        estimated_search_cost,
        estimated_video_cost,
    )

    if total_estimated > quota._max_allowed():  # type: ignore[attr-defined]
        logger.warning(
            "Estimated usage %d exceeds safe limit %d",
            total_estimated,
            quota._max_allowed(),
        )
        response = input("Continue anyway? (y/N): ").strip().lower()
        if response != "y":
            logger.info("Aborted by user due to quota concerns")
            return 1

    if args.published_after:
        try:
            published_after_dt = datetime.fromisoformat(args.published_after.replace("Z", "+00:00")).astimezone(timezone.utc)
        except Exception as exc:
            raise SystemExit("--published-after must be ISO8601, e.g. 2025-01-01T00:00:00Z") from exc
    else:
        published_after_dt = compute_published_after(args.period)

    search_query = args.query
    if args.podcast:
        search_query = "podcast" if not search_query else f"{search_query} podcast"

    logger.info(
        "Searching after %s (region=%s, max_results=%d, query=%s)",
        iso8601(published_after_dt),
        args.region,
        args.max_results,
        search_query or "(default)",
    )

    search_items = search_videos(
        api_key=api_key,
        access_token=access_token,
        region_code=args.region,
        published_after=published_after_dt,
        max_results=max(1, args.max_results),
        topic_id=args.topic_id,
        query=search_query,
        quota=quota,
        use_cache=use_cache,
    )

    logger.info("Search returned %d items", len(search_items))
    video_ids = [it.get("id", {}).get("videoId") for it in search_items if it.get("id", {}).get("videoId")]
    unique_video_ids = list(dict.fromkeys(filter(None, video_ids)))
    logger.info("Extracted %d video IDs (%d unique)", len(video_ids), len(unique_video_ids))

    if not unique_video_ids:
        print("No videos found.")
        print("Possible causes: API not enabled, key restrictions, limited results, or quota exhaustion.")
        return 0

    video_items = fetch_video_stats(api_key, access_token, unique_video_ids, quota, use_cache)
    rows = assemble_results(video_items, args.sort_by)

    print(f"\nFinal quota usage: {quota.used} units")
    if quota.saved > 0:
        print(f"Quota saved by caching: {quota.saved} requests")

    print_table(rows, args.top, args.sort_by)

    if args.csv:
        write_csv(rows, args.csv, args.top)
        print(f"Wrote CSV: {args.csv}")
    if args.json_out:
        write_json(rows, args.json_out, args.top)
        print(f"Wrote JSON: {args.json_out}")
    if args.md:
        write_markdown(rows, args.md, args.top, args.sort_by)
        print(f"Wrote Markdown: {args.md}")

    logger.info(
        "Quota usage summary: used=%d saved=%d remaining=%d",
        quota.used,
        quota.saved,
        quota.daily_limit - quota.used,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())


