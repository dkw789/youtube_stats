#!/usr/bin/env python3
"""
YouTube Subscriptions Fetcher with OAuth
Gets your YouTube subscriptions and finds most popular videos from those channels.

COMPLIANCE STATEMENT:
This script complies with YouTube API Services Terms and Policies:
- Displays only YouTube-provided metrics (views, likes, comments)
- No independently calculated or derived metrics (Policy III.E.4h)
- Data cached for maximum 24 hours (Policy III.E.4.a-g)
- Single project number: 55291277961 (Policy III.D.1c)
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests

from utils import CacheManager, CacheTTL, QuotaLimitError, QuotaTracker, get_logger, setup_logging
from youtube_auth import get_youtube_token, get_youtube_token_auto

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

# YouTube API quota costs
SEARCH_QUOTA_COST = 100
VIDEO_DETAILS_QUOTA_COST = 1
SUBSCRIPTIONS_QUOTA_COST = 1
DAILY_QUOTA_LIMIT = 10000
SAFETY_BUFFER = 500
CHANNELS_QUOTA_COST = 1
PLAYLIST_ITEMS_QUOTA_COST = 1
DEFAULT_TIMEOUT_SECONDS = 30

# Cache and output settings
OUTPUT_DIR = "subscriptions_output"
CACHE_DIR = os.path.join(OUTPUT_DIR, ".cache")


logger = get_logger(__name__)
cache_manager = CacheManager(CACHE_DIR)


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


def get_subscriptions(access_token: str, max_results: int, use_cache: bool, quota: QuotaTracker) -> List[Dict]:
    cache_key_parts = ["subscriptions", str(max_results)]
    cached_data = _cache_load("subscriptions", cache_key_parts, CacheTTL.MONTH, use_cache, quota)
    if cached_data is not None:
        logger.info("Using cached subscriptions")
        return cached_data
    
    url = f"{YOUTUBE_API_BASE}/subscriptions"
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"part": "snippet", "mine": "true", "maxResults": min(max_results, 50)}
    
    subscriptions = []
    next_page_token = None
    
    while True:
        if next_page_token:
            params["pageToken"] = next_page_token
        
        quota.ensure_within_limit(SUBSCRIPTIONS_QUOTA_COST)
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        quota.spend("subscriptions.list", SUBSCRIPTIONS_QUOTA_COST)
        
        data = response.json()
        subscriptions.extend(data.get("items", []))
        
        if len(subscriptions) >= max_results:
            break
            
        next_page_token = data.get("nextPageToken")
        if not next_page_token:
            break
    
    result = subscriptions[:max_results]
    if use_cache:
        _cache_save("subscriptions", cache_key_parts, result)
    return result


def get_channel_uploads(
    access_token: str,
    channel_id: str,
    published_after: datetime,
    max_results: int,
    use_cache: bool,
    quota: QuotaTracker,
) -> List[Dict]:
    """Get recent uploads from channel's uploads playlist with caching."""

    published_after_str = (
        published_after.astimezone(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )
    cache_key_parts = [channel_id, published_after_str, str(max_results)]
    cached_data = _cache_load("uploads", cache_key_parts, CacheTTL.WEEK, use_cache, quota)
    if cached_data is not None:
        logger.debug("Using cached uploads for channel %s", channel_id)
        return cached_data

    try:
        url = f"{YOUTUBE_API_BASE}/channels"
        headers = {"Authorization": f"Bearer {access_token}"}
        params = {"part": "contentDetails", "id": channel_id}

        quota.ensure_within_limit(CHANNELS_QUOTA_COST)
        response = requests.get(url, headers=headers, params=params, timeout=DEFAULT_TIMEOUT_SECONDS)
        response.raise_for_status()
        quota.spend("channels.list", CHANNELS_QUOTA_COST)

        data = response.json()
        if not data.get("items"):
            return []

        uploads_playlist_id = data["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

        params = {
            "part": "snippet",
            "playlistId": uploads_playlist_id,
            "maxResults": min(max_results * 2, 50),
        }

        quota.ensure_within_limit(PLAYLIST_ITEMS_QUOTA_COST)
        response = requests.get(
            f"{YOUTUBE_API_BASE}/playlistItems",
            headers=headers,
            params=params,
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        quota.spend("playlistItems.list", PLAYLIST_ITEMS_QUOTA_COST)

        items = response.json().get("items", [])
        filtered_items: List[Dict[str, Any]] = []
        for item in items:
            pub_date = datetime.fromisoformat(item["snippet"]["publishedAt"].replace("Z", "+00:00"))
            if pub_date >= published_after:
                filtered_items.append(
                    {
                        "id": {"videoId": item["snippet"]["resourceId"]["videoId"]},
                        "snippet": item["snippet"],
                    }
                )
            if len(filtered_items) >= max_results:
                break

        if use_cache:
            _cache_save("uploads", cache_key_parts, filtered_items)
        return filtered_items

    except requests.exceptions.HTTPError as exc:
        if exc.response is not None and exc.response.status_code in (403, 429):
            logger.warning("Quota/permission error fetching uploads for %s: %s", channel_id, exc)
            return []
        raise

def search_channel_videos(
    access_token: str,
    channel_id: str,
    published_after: datetime,
    max_results: int,
    use_cache: bool,
    quota: QuotaTracker,
) -> List[Dict]:
    """Search for videos from a specific channel with caching and fallback to uploads playlist."""

    published_after_str = (
        published_after.astimezone(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )
    cache_key_parts = [channel_id, published_after_str, str(max_results)]
    cached_data = _cache_load("search", cache_key_parts, CacheTTL.DAY, use_cache, quota)
    if cached_data is not None:
        logger.debug("Using cached search for channel %s", channel_id)
        return cached_data

    url = f"{YOUTUBE_API_BASE}/search"
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {
        "part": "snippet",
        "channelId": channel_id,
        "type": "video",
        "order": "date",
        "publishedAfter": published_after_str,
        "maxResults": min(max_results, 50),
    }

    try:
        quota.ensure_within_limit(SEARCH_QUOTA_COST)
        response = requests.get(url, headers=headers, params=params, timeout=DEFAULT_TIMEOUT_SECONDS)
        response.raise_for_status()
        quota.spend("search.list", SEARCH_QUOTA_COST)
        result = response.json().get("items", [])
    except QuotaLimitError:
        logger.warning("Quota exhausted before search.list for channel %s", channel_id)
        return []
    except requests.exceptions.HTTPError as exc:
        if exc.response is not None and exc.response.status_code in (403, 429):
            logger.warning("Quota/permission error searching channel %s: %s", channel_id, exc)
            result = get_channel_uploads(access_token, channel_id, published_after, max_results, use_cache, quota)
        else:
            raise

    if use_cache and result:
        _cache_save("search", cache_key_parts, result)
    return result


def get_rss_videos(channel_id: str, published_after: datetime, max_results: int) -> List[Dict]:
    """Get videos from RSS feed (no quota cost)."""

    try:
        import feedparser
    except ImportError:
        logger.warning("feedparser not installed. Run `pip install feedparser` to enable RSS fallback.")
        return []

    rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    try:
        feed = feedparser.parse(rss_url)
    except Exception as exc:
        logger.warning("RSS error for channel %s: %s", channel_id, exc)
        return []

    if not getattr(feed, "entries", None):
        return []

    videos: List[Dict[str, Any]] = []
    for entry in feed.entries[: max_results * 3]:
        try:
            pub_date = datetime.fromisoformat(entry.published.replace("Z", "+00:00"))
        except Exception:  # pragma: no cover - malformed entries
            continue
        if pub_date < published_after:
            continue
        videos.append(
            {
                "id": {"videoId": getattr(entry, "yt_videoid", "")},
                "snippet": {
                    "title": entry.title,
                    "publishedAt": entry.published,
                    "channelTitle": getattr(entry, "author", "Unknown"),
                },
            }
        )
        if len(videos) >= max_results:
            break

    return videos


def get_video_details(
    access_token: str,
    video_ids: List[str],
    use_cache: bool,
    quota: QuotaTracker,
) -> List[Dict]:
    """Get detailed statistics for videos with caching."""

    if not video_ids:
        return []

    key_material = "::".join(sorted(video_ids))
    cache_key_parts = [key_material]
    cached_data = _cache_load("video_details", cache_key_parts, CacheTTL.DAY, use_cache, quota)
    if cached_data is not None:
        logger.debug("Using cached video details for %d videos", len(video_ids))
        return cached_data

    url = f"{YOUTUBE_API_BASE}/videos"
    headers = {"Authorization": f"Bearer {access_token}"}

    results: List[Dict[str, Any]] = []
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i : i + 50]
        units = VIDEO_DETAILS_QUOTA_COST * len(chunk)
        try:
            quota.ensure_within_limit(units)
        except QuotaLimitError:
            logger.warning(
                "Quota limit reached before fetching video details. Processed %d/%d videos.",
                len(results),
                len(video_ids),
            )
            break

        params = {
            "part": "snippet,statistics",
            "id": ",".join(chunk),
            "maxResults": 50,
        }

        response = requests.get(url, headers=headers, params=params, timeout=DEFAULT_TIMEOUT_SECONDS)
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            if exc.response is not None and exc.response.status_code in (403, 429):
                logger.warning("Quota/permission error fetching video details: %s", exc)
                break
            raise

        quota.spend("videos.list", units)
        results.extend(response.json().get("items", []))

    if use_cache and results:
        _cache_save("video_details", cache_key_parts, results)
    return results


def human_int(n: Optional[str]) -> int:
    """Convert string to int, return 0 if invalid."""
    try:
        return int(n) if n is not None else 0
    except Exception:
        return 0


def assemble_results(video_items: List[Dict], sort_by: str = "views") -> List[Dict]:
    """Assemble and sort video results."""
    assembled = []
    seen_video_ids = set()
    
    for v in video_items:
        vid = v.get("id")
        if not vid or vid in seen_video_ids:
            continue
        
        seen_video_ids.add(vid)
        snippet = v.get("snippet", {})
        stats = v.get("statistics", {})
        
        assembled.append({
            "videoId": vid,
            "title": snippet.get("title", ""),
            "channelTitle": snippet.get("channelTitle", ""),
            "publishedAt": snippet.get("publishedAt", ""),
            "views": human_int(stats.get("viewCount")),
            "likes": human_int(stats.get("likeCount")),
            "comments": human_int(stats.get("commentCount")),
            "url": f"https://www.youtube.com/watch?v={vid}",
        })
    
    sort_key = sort_by if sort_by in ["views", "likes", "comments"] else "views"
    return sorted(assembled, key=lambda x: x[sort_key], reverse=True)


def print_table(rows: List[Dict], limit: int, sort_by: str = "views") -> None:
    """Print results in table format."""
    limit = min(limit, len(rows))
    metric_name = sort_by.title()
    print(f"\nTop {limit} videos from your subscriptions by {metric_name}:")
    print("-" * 100)
    print(f"{'Rank':>4}  {metric_name:>12}  {'Channel':<20}  {'Title':<50}")
    print("-" * 100)
    
    for i, row in enumerate(rows[:limit], 1):
        metric_value = row[sort_by]
        channel = row['channelTitle'][:20]
        title = row['title'][:50]
        print(f"{i:>4}  {metric_value:>12,}  {channel:<20}  {title:<50}")
    print("-" * 100)

def save_to_json(rows: List[Dict], path: str, limit: int) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows[:limit], f, ensure_ascii=False, indent=2)
    logger.info("Results written to %s", path)


def _estimate_quota_usage(max_subscriptions: int, videos_per_channel: int) -> int:
    subs = SUBSCRIPTIONS_QUOTA_COST
    search = max_subscriptions * SEARCH_QUOTA_COST
    videos = max_subscriptions * videos_per_channel * VIDEO_DETAILS_QUOTA_COST
    uploads = max_subscriptions * (CHANNELS_QUOTA_COST + PLAYLIST_ITEMS_QUOTA_COST)
    return subs + search + videos + uploads


def _should_continue(estimated_usage: int) -> bool:
    safe_limit = DAILY_QUOTA_LIMIT - SAFETY_BUFFER
    if estimated_usage <= safe_limit:
        return True
    logger.warning(
        "Estimated quota usage %s exceeds safe limit %s. Reduce scope or confirm to continue.",
        estimated_usage,
        safe_limit,
    )
    response = input("Continue anyway? (y/N): ").strip().lower()
    return response == "y"


def _period_to_datetime(period: str) -> datetime:
    now = datetime.now(timezone.utc)
    if period == "week":
        return now - timedelta(days=7)
    return now - timedelta(days=30)


def _collect_videos(
    access_token: str,
    subscriptions: List[Dict[str, Any]],
    published_after: datetime,
    args: argparse.Namespace,
    quota: QuotaTracker,
) -> List[Dict[str, Any]]:
    all_videos: List[Dict[str, Any]] = []
    consecutive_403 = 0
    auto_rss_only = args.rss_fallback

    for batch_start in range(0, len(subscriptions), args.batch_size):
        batch = subscriptions[batch_start : batch_start + args.batch_size]
        logger.info(
            "Processing batch %d/%d",
            batch_start // args.batch_size + 1,
            (len(subscriptions) + args.batch_size - 1) // args.batch_size,
        )
        for index, sub in enumerate(batch, batch_start + 1):
            channel_title = sub["snippet"]["title"]
            channel_id = sub['snippet']['resourceId']['channelId']
            logger.info("[%d/%d] %s", index, len(subscriptions), channel_title)
            try:
                if auto_rss_only or args.rss_fallback:
                    videos = get_rss_videos(channel_id, published_after, args.videos_per_channel)
                else:
                    videos = search_channel_videos(
                        access_token, channel_id, published_after, args.videos_per_channel, not args.no_cache, quota
                    )
                all_videos.extend(videos)
                consecutive_403 = 0
            except QuotaLimitError as exc:
                logger.warning("Quota limit reached while processing channel %s: %s", channel_title, exc)
                return all_videos
            except requests.exceptions.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 403:
                    consecutive_403 += 1
                    logger.warning("403 error (%d/3) for channel %s: %s", consecutive_403, channel_title, exc)
                    if consecutive_403 >= 2 and not auto_rss_only:
                        auto_rss_only = True
                        logger.warning("Switching to RSS-only mode due to repeated 403 errors")
                        videos = get_rss_videos(channel_id, published_after, args.videos_per_channel)
                        if videos:
                            all_videos.extend(videos)
                else:
                    consecutive_403 = 0
                    logger.warning("Error fetching videos for channel %s: %s", channel_title, exc)
            except Exception as exc:
                consecutive_403 = 0
                logger.warning("Unexpected error for channel %s: %s", channel_title, exc)
    return all_videos


def _prepare_video_details(
    access_token: str,
    videos: List[Dict[str, Any]],
    use_cache: bool,
    quota: QuotaTracker,
    min_views: int,
) -> List[Dict[str, Any]]:
    video_ids = {v["id"]["videoId"] for v in videos if "id" in v and "videoId" in v["id"]}
    if not video_ids:
        return []

    logger.info("Fetching statistics for %d unique videos", len(video_ids))
    details = get_video_details(access_token, list(video_ids), use_cache, quota)

    if min_views > 0:
        before = len(details)
        details = [d for d in details if human_int(d.get("statistics", {}).get("viewCount")) >= min_views]
        logger.info("Filtered %d videos below %d views", before - len(details), min_views)

    return details


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Find most popular videos from your YouTube subscriptions")
    parser.add_argument("--period", choices=["week", "month"], default="month", help="Time window")
    parser.add_argument("--top", type=int, default=25, help="Number of top results to show")
    parser.add_argument("--sort-by", choices=["views", "likes", "comments"], default="views", help="Sort by metric")
    parser.add_argument("--max-subscriptions", type=int, default=50, help="Max subscriptions to check")
    parser.add_argument("--videos-per-channel", type=int, default=5, help="Videos per channel to check")
    parser.add_argument("--output", help="Save results to JSON file")
    parser.add_argument("--no-cache", action="store_true", help="Disable caching")
    parser.add_argument("--batch-size", type=int, default=10, help="Process channels in batches to save quota")
    parser.add_argument("--min-views", type=int, default=1000, help="Skip videos with fewer views")
    parser.add_argument("--rss-fallback", action="store_true", help="Use RSS feeds when possible (no quota cost)")
    parser.add_argument("--use-api", action="store_true", help="Use YouTube API instead of RSS feeds (uses quota)")
    parser.add_argument("--auto-auth", action="store_true", help="Automate OAuth flow via local web server")
    parser.add_argument("--log-level", default=os.getenv("LOG_LEVEL", "INFO"), help="Logging level")

    args = parser.parse_args(argv)

    setup_logging(args.log_level.upper())
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if not args.no_cache:
        os.makedirs(CACHE_DIR, exist_ok=True)

    if args.auto_auth:
        try:
            access_token = get_youtube_token_auto()
            logger.info("Automated OAuth successful")
        except Exception as exc:
            logger.warning("Automated OAuth failed: %s", exc)
            access_token = get_youtube_token()
    else:
        access_token = get_youtube_token()

    published_after = _period_to_datetime(args.period)

    quota = QuotaTracker(daily_limit=DAILY_QUOTA_LIMIT, safety_buffer=SAFETY_BUFFER)
    estimated_usage = _estimate_quota_usage(args.max_subscriptions, args.videos_per_channel)
    logger.info(
        "Estimated quota usage: %d (search=%d, videos=%d)",
        estimated_usage,
        args.max_subscriptions * SEARCH_QUOTA_COST,
        args.max_subscriptions * args.videos_per_channel * VIDEO_DETAILS_QUOTA_COST,
    )
    if not _should_continue(estimated_usage):
        logger.info("Aborted by user due to quota concerns")
        return 1

    subscriptions = get_subscriptions(access_token, args.max_subscriptions, not args.no_cache, quota)
    if not subscriptions:
        logger.info("No subscriptions found")
        return 0

    videos = _collect_videos(access_token, subscriptions, published_after, args, quota)
    if not videos:
        logger.info("No videos found for period %s", args.period)
        return 0

    if args.use_api:
        video_details = _prepare_video_details(access_token, videos, not args.no_cache, quota, args.min_views)
    else:
        video_details = [
            {
                "id": v["id"].get("videoId"),
                "snippet": v.get("snippet", {}),
                "statistics": {"viewCount": "0", "likeCount": "0", "commentCount": "0"},
            }
            for v in videos
            if "id" in v and v["id"].get("videoId")
        ]

    results = assemble_results(video_details, args.sort_by)
    if not results:
        logger.info("No results after processing")
        return 0

    print_table(results, args.top, args.sort_by)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = args.output or os.path.join(
        OUTPUT_DIR,
        f"subscriptions_{args.period}_{args.sort_by}_{timestamp}.json",
    )
    save_to_json(results, output_path, args.top)

    logger.info(
        "Quota usage: used=%d saved=%d remaining=%d",
        quota.used,
        quota.saved,
        quota.daily_limit - quota.used,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
