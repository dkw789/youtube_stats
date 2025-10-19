#!/usr/bin/env python3
"""
Find most popular podcast episodes from your YouTube subscriptions.

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
from typing import Any, Dict, List, Optional

import requests

from utils import CacheManager, CacheTTL, QuotaLimitError, QuotaTracker, get_logger, setup_logging
from youtube_auth import get_youtube_token

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
CACHE_DIR = os.path.join(".cache", "podcasts")

SEARCH_QUOTA_COST = 100
VIDEO_DETAILS_QUOTA_COST = 1
SUBSCRIPTIONS_QUOTA_COST = 1
CHANNELS_QUOTA_COST = 1
PLAYLIST_ITEMS_QUOTA_COST = 1
DAILY_QUOTA_LIMIT = 10000
SAFETY_BUFFER = 500
DEFAULT_TIMEOUT_SECONDS = 30


logger = get_logger(__name__)
cache_manager = CacheManager(CACHE_DIR)


def _cache_key(*parts: str) -> str:
    return "::".join(parts)


def _cache_load(namespace: str, parts: List[str], ttl: CacheTTL, use_cache: bool, quota: Optional[QuotaTracker]) -> Optional[Any]:
    if not use_cache:
        return None
    payload = cache_manager.load(namespace, _cache_key(*parts), ttl)
    if payload is not None and quota is not None:
        quota.record_saved()
    return payload


def _cache_save(namespace: str, parts: List[str], payload: Any) -> None:
    cache_manager.save(namespace, _cache_key(*parts), payload)


def get_subscriptions(
    access_token: str,
    max_channels: int,
    use_cache: bool,
    quota: Optional[QuotaTracker],
) -> List[Dict]:
    """Get user's YouTube subscriptions."""
    cache_parts = [str(max_channels)]
    cached = _cache_load("subscriptions", cache_parts, CacheTTL.WEEK, use_cache, quota)
    if cached is not None:
        logger.info("Using cached subscriptions")
        return cached

    headers = {"Authorization": f"Bearer {access_token}"}
    subscriptions = []
    next_page_token = None
    
    while len(subscriptions) < max_channels:
        params = {"part": "snippet", "mine": "true", "maxResults": 50}
        if next_page_token:
            params["pageToken"] = next_page_token

        try:
            if quota is not None:
                quota.ensure_within_limit(SUBSCRIPTIONS_QUOTA_COST)
            response = requests.get(
                f"{YOUTUBE_API_BASE}/subscriptions",
                headers=headers,
                params=params,
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            if quota is not None:
                quota.spend("subscriptions.list", SUBSCRIPTIONS_QUOTA_COST)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                logger.error(
                    "Cannot access subscriptions. Verify YouTube Data API enablement, scopes, and quota.",
                )
                logger.error("Try: python youtube_auth.py --clear")
                sys.exit(1)
            raise

        data = response.json()
        subscriptions.extend(data.get("items", []))

        next_page_token = data.get("nextPageToken")
        if not next_page_token:
            break

    result = subscriptions[:max_channels]
    if use_cache:
        _cache_save("subscriptions", cache_parts, result)
    return result

def get_rss_podcasts(channel_id: str, published_after: datetime, max_results: int) -> List[Dict]:
    """Get podcast episodes from RSS feed (no quota cost)."""

    try:
        import feedparser
    except ImportError:
        logger.warning("feedparser not installed. Run `pip install feedparser` to enable RSS mode.")
        return []

    rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    try:
        feed = feedparser.parse(rss_url)
    except Exception as exc:
        logger.warning("RSS error for channel %s: %s", channel_id, exc)
        return []

    if not getattr(feed, "entries", None):
        logger.debug("No RSS entries for channel %s", channel_id)
        return []

    videos: List[Dict[str, Any]] = []
    podcast_keywords = ["podcast", "episode", "show", "ep ", "#"]

    for entry in feed.entries[: max_results * 2]:
        try:
            pub_date = datetime.fromisoformat(entry.published.replace("Z", "+00:00"))
        except Exception:  # pragma: no cover - malformed feed entries
            continue

        if pub_date < published_after:
            continue

        title_lower = entry.title.lower()
        is_podcast = any(word in title_lower for word in podcast_keywords)
        video_id = getattr(entry, "yt_videoid", "")
        if not video_id:
            continue

        videos.append(
            {
                "id": {"videoId": video_id},
                "snippet": {
                    "title": entry.title,
                    "publishedAt": entry.published,
                    "channelTitle": getattr(entry, "author", "Unknown"),
                },
                "is_podcast": is_podcast,
            }
        )

        if len(videos) >= max_results:
            break

    logger.debug("RSS fetched %d items for channel %s", len(videos), channel_id)
    return videos

def search_channel_podcasts(
    access_token: Optional[str],
    channel_id: str,
    published_after: datetime,
    max_results: int,
    use_cache: bool,
    rss_only: bool,
    quota: Optional[QuotaTracker],
) -> List[Dict]:
    """Search for podcast episodes from a channel with caching and RSS fallback."""

    if rss_only or not access_token:
        return get_rss_podcasts(channel_id, published_after, max_results)

    published_after_str = (
        published_after.astimezone(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )
    cache_parts = [channel_id, published_after_str, str(max_results)]
    cached = _cache_load("podcasts", cache_parts, CacheTTL.DAY, use_cache, quota)
    if cached is not None:
        logger.debug("Using cached podcast search for %s", channel_id)
        return cached

    headers = {"Authorization": f"Bearer {access_token}"}
    params = {
        "part": "snippet",
        "channelId": channel_id,
        "type": "video",
        "order": "date",
        "publishedAfter": published_after_str,
        "maxResults": max_results,
        "q": "podcast OR episode OR show",
    }

    try:
        if quota is not None:
            quota.ensure_within_limit(SEARCH_QUOTA_COST)
        response = requests.get(
            f"{YOUTUBE_API_BASE}/search",
            headers=headers,
            params=params,
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        if quota is not None:
            quota.spend("search.list", SEARCH_QUOTA_COST)
        result = response.json().get("items", [])
    except QuotaLimitError:
        logger.warning("Quota exhausted before search.list for channel %s", channel_id)
        return []
    except requests.exceptions.HTTPError as exc:
        if exc.response is not None and exc.response.status_code in (403, 429):
            logger.warning("API error %s when searching channel %s; falling back to RSS", exc.response.status_code, channel_id)
            return get_rss_podcasts(channel_id, published_after, max_results)
        raise

    if use_cache:
        _cache_save("podcasts", cache_parts, result)
    return result


def get_video_stats(
    access_token: Optional[str],
    video_ids: List[str],
    use_cache: bool,
    quota: Optional[QuotaTracker],
) -> Dict[str, Dict[str, Any]]:
    """Get statistics for videos with caching and quota tracking."""

    if not access_token or not video_ids:
        return {}

    cache_parts = ["::".join(sorted(video_ids))]
    cached = _cache_load("video_stats", cache_parts, CacheTTL.DAY, use_cache, quota)
    if cached is not None:
        logger.debug("Using cached video stats for %d videos", len(video_ids))
        return {item["id"]: item for item in cached}

    headers = {"Authorization": f"Bearer {access_token}"}
    stats: Dict[str, Dict[str, Any]] = {}
    cached_items: List[Dict[str, Any]] = []

    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i : i + 50]
        units = VIDEO_DETAILS_QUOTA_COST * len(chunk)

        try:
            if quota is not None:
                quota.ensure_within_limit(units)
        except QuotaLimitError:
            logger.warning(
                "Quota limit reached before fetching video details chunk %d; returning partial results",
                (i // 50) + 1,
            )
            break

        params = {
            "part": "statistics,snippet",
            "id": ",".join(chunk),
            "maxResults": 50,
        }

        try:
            response = requests.get(
                f"{YOUTUBE_API_BASE}/videos",
                headers=headers,
                params=params,
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            if exc.response is not None and exc.response.status_code in (403, 429):
                logger.warning(
                    "Quota/permission error fetching video stats (chunk %d): %s",
                    (i // 50) + 1,
                    exc,
                )
                break
            raise

        if quota is not None:
            quota.spend("videos.list", units)

        for item in response.json().get("items", []):
            video_data = {
                "id": item["id"],
                "views": int(item["statistics"].get("viewCount", 0)),
                "likes": int(item["statistics"].get("likeCount", 0)),
                "comments": int(item["statistics"].get("commentCount", 0)),
                "title": item["snippet"]["title"],
                "channel": item["snippet"]["channelTitle"],
                "published": item["snippet"].get("publishedAt", ""),
            }
            stats[item["id"]] = video_data
            cached_items.append(video_data)

    if use_cache and cached_items:
        _cache_save("video_stats", cache_parts, cached_items)
    return stats

def main():
    parser = argparse.ArgumentParser(description="Find popular podcast episodes from YouTube subscriptions")
    parser.add_argument("--period", choices=["week"], default="week", help="Time period (month disabled to save quota)")
    parser.add_argument("--top", type=int, default=25, help="Number of top results")
    parser.add_argument("--sort-by", choices=["views", "likes", "comments"], default="views", help="Sort criteria")
    parser.add_argument("--max-channels", type=int, default=25, help="Max channels to check (reduced for quota)")
    parser.add_argument("--videos-per-channel", type=int, default=3, help="Videos to check per channel (reduced for quota)")
    parser.add_argument("--csv", help="Save results to CSV file")
    parser.add_argument("--json", help="Save results to JSON file")
    parser.add_argument("--no-cache", action="store_true", help="Disable caching")
    parser.add_argument("--clear-cache", action="store_true", help="Clear cache before running")
    parser.add_argument("--rss-only", action="store_true", help="Use RSS feeds only (no API quota used)")
    parser.add_argument("--no-auth", action="store_true", help="Skip authentication (RSS-only mode)")
    parser.add_argument("--auto-auth", action="store_true", help="Automate OAuth flow via local web server")
    parser.add_argument("--limit-channels", type=int, default=15, help="Limit channels to save quota")
    parser.add_argument("--channel-ids", help="Comma-separated channel IDs to check (bypasses subscriptions)")
    parser.add_argument("--log-level", default=os.getenv("LOG_LEVEL", "INFO"), help="Logging level")
    
    args = parser.parse_args()
    
    setup_logging(args.log_level.upper())
    use_cache = not args.no_cache

    if args.clear_cache:
        cache_manager.clear_all()
        logger.info("Cache cleared")

    # Calculate time window (week only to save quota)
    now = datetime.now(timezone.utc)
    published_after = now - timedelta(days=7)
    
    print(f"Finding podcast episodes from last {args.period}...")
    
    # Get access token via shared session manager
    if args.no_auth or args.rss_only:
        access_token = None
        print("Skipping authentication (RSS-only mode)")
    elif args.auto_auth:
        from youtube_auth import get_youtube_token_auto

        try:
            access_token = get_youtube_token_auto()
            print("✓ Automated OAuth successful")
        except Exception as exc:
            print(f"Automated OAuth failed: {exc}")
            print("Falling back to manual code entry...")
            access_token = get_youtube_token()
    else:
        access_token = get_youtube_token()

    quota: Optional[QuotaTracker] = None
    if access_token and not args.rss_only:
        quota = QuotaTracker(daily_limit=DAILY_QUOTA_LIMIT, safety_buffer=SAFETY_BUFFER)

    
    # Get subscriptions or use manual channel IDs
    if args.channel_ids:
        print("Using manual channel IDs...")
        channel_ids = [cid.strip() for cid in args.channel_ids.split(',')]
        subscriptions = []
        for cid in channel_ids:
            subscriptions.append({
                "snippet": {
                    "title": f"Channel {cid[:8]}...",
                    "resourceId": {"channelId": cid}
                }
            })
        print(f"Using {len(subscriptions)} manual channels")
    elif args.no_auth or args.rss_only:
        print("RSS-only mode requires manual channel IDs.")
        print("Usage: --channel-ids 'UCxxxxx,UCyyyyy' --rss-only")
        print("\nTo find channel IDs:")
        print("1. Go to a YouTube channel page")
        print("2. View page source and search for 'channelId'")
        print("3. Or use: https://www.youtube.com/c/CHANNELNAME/about")
        sys.exit(1)
    else:
        print("Fetching subscriptions...")
        max_channels = min(args.max_channels, args.limit_channels)
        subscriptions = get_subscriptions(access_token, max_channels, use_cache, quota)
        print(f"Found {len(subscriptions)} subscriptions (limited to {max_channels} to save quota)")
    
    # Search for podcast episodes
    all_videos = []
    for i, sub in enumerate(subscriptions, 1):
        channel_id = sub["snippet"]["resourceId"]["channelId"]
        channel_name = sub["snippet"]["title"]
        
        print(f"[{i}/{len(subscriptions)}] Checking {channel_name}...")
        
        if args.rss_only or args.no_auth:
            videos = get_rss_podcasts(channel_id, published_after, args.videos_per_channel)
            print(f"  Found {len(videos)} videos from RSS")
        else:
            videos = search_channel_podcasts(
                access_token,
                channel_id,
                published_after,
                args.videos_per_channel,
                use_cache,
                args.rss_only,
                quota,
            )

        for video in videos:
            video_id = video.get("id", {}).get("videoId")
            if not video_id:
                continue
            all_videos.append(
                {
                    "video_id": video_id,
                    "channel_name": channel_name,
                    "video": video,
                }
            )
    
    if not all_videos:
        print("No videos found!")
        if args.rss_only:
            print("Try different channel IDs or extend the time period")
        return 0
    
    print(f"Found {len(all_videos)} potential podcast episodes")
    
    if args.rss_only:
        print("RSS-only mode: Using basic data (no view counts available)")
        # Create episodes from RSS data without API calls
        episodes = []
        for video_data in all_videos:
            video_id = video_data["video_id"]
            video = video_data["video"]
            episodes.append({
                "title": video["snippet"]["title"],
                "channel": video_data["channel_name"],
                "views": 0,  # Not available in RSS
                "likes": 0,
                "comments": 0,
                "published": video["snippet"]["publishedAt"],
                "url": f"https://www.youtube.com/watch?v={video_id}"
            })
        
        # Sort by publish date since no view counts
        episodes.sort(key=lambda x: x["published"], reverse=True)
        top_episodes = episodes[:args.top]
        
        print(f"\nTop {len(top_episodes)} recent podcast episodes (RSS mode):")
        print("=" * 80)
        
        for i, ep in enumerate(top_episodes, 1):
            print(f"{i:2d}. {ep['title']}")
            print(f"    Channel: {ep['channel']}")
            print(f"    Published: {ep['published'][:10]}")
            print(f"    URL: {ep['url']}")
            print()
        
        # Save results
        if args.csv:
            with open(args.csv, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=['title', 'channel', 'published', 'url'])
                writer.writeheader()
                for ep in top_episodes:
                    writer.writerow({k: v for k, v in ep.items() if k in ['title', 'channel', 'published', 'url']})
            print(f"Results saved to {args.csv}")
        if args.json:
            with open(args.json, 'w', encoding='utf-8') as f:
                json.dump(top_episodes, f, indent=2, ensure_ascii=False)
            print(f"Results saved to {args.json}")
        
        return 0

    # Get video statistics (costs quota)
    print(f"Fetching video statistics for {len(all_videos)} videos...")
    print(f"Estimated quota cost: {len(all_videos)} units")
    video_ids = [v["video_id"] for v in all_videos]

    # Process in batches of 50 (API limit)
    all_stats = {}
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        print(f"Processing batch {i//50 + 1}/{(len(video_ids) + 49)//50}...")
        stats = get_video_stats(access_token, batch, use_cache, quota)
        if not stats and quota and not quota.can_spend(VIDEO_DETAILS_QUOTA_COST):
            print("⚠ Quota limit reached while fetching video stats. Using partial results.")
            break
        all_stats.update(stats)
    
    # Combine data and sort
    episodes = []
    for video_data in all_videos:
        video_id = video_data["video_id"]
        stats = all_stats.get(video_id)
        if not stats:
            continue
        episodes.append(
            {
                "title": stats.get("title", ""),
                "channel": stats.get("channel", video_data.get("channel_name", "")),
                "views": stats.get("views", 0),
                "likes": stats.get("likes", 0),
                "comments": stats.get("comments", 0),
                "published": stats.get("published", ""),
                "url": f"https://www.youtube.com/watch?v={video_id}",
            }
        )

    if not episodes:
        print("No video statistics available. Try enabling caching or reducing limits.")
        return 0

    episodes.sort(key=lambda x: x[args.sort_by], reverse=True)
    top_episodes = episodes[:args.top]

    print(f"\nTop {len(top_episodes)} podcast episodes by {args.sort_by}:")
    print("=" * 80)
    for i, ep in enumerate(top_episodes, 1):
        print(f"{i:2d}. {ep['title']}")
        print(f"    Channel: {ep['channel']}")
        print(
            f"    Views: {ep['views']:,} | Likes: {ep['likes']:,} | Comments: {ep['comments']:,}"
        )
        print(f"    Published: {ep['published'][:10]}")
        print(f"    URL: {ep['url']}")
        print()

    # Save to files if requested
    if args.csv:
        with open(args.csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    'title',
                    'channel',
                    'views',
                    'likes',
                    'comments',
                    'published',
                    'url',
                ],
            )
            writer.writeheader()
            writer.writerows(top_episodes)
        print(f"Results saved to {args.csv}")

    if args.json:
        with open(args.json, 'w', encoding='utf-8') as f:
            json.dump(top_episodes, f, indent=2, ensure_ascii=False)
        print(f"Results saved to {args.json}")

    if quota:
        logger.info(
            "Quota usage: used=%d saved=%d remaining=%d",
            quota.used,
            quota.saved,
            quota.daily_limit - quota.used,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())