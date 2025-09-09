#!/usr/bin/env python3
"""
Find most popular podcast episodes from your YouTube subscriptions.
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, List

import requests
from youtube_auth import get_youtube_token

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
CACHE_DIR = ".cache"

def get_cache_key(data: str) -> str:
    """Generate cache key from data string."""
    return hashlib.md5(data.encode()).hexdigest()[:16]

def load_cache(cache_path: str, max_age: str = "day") -> List[Dict]:
    """Load cached data if valid."""
    if not os.path.exists(cache_path):
        return None
    
    try:
        with open(cache_path, 'r') as f:
            cache_data = json.load(f)
        
        cached_time = datetime.fromisoformat(cache_data["timestamp"])
        now = datetime.now(timezone.utc)
        
        if max_age == "day":
            max_delta = timedelta(hours=24)
        elif max_age == "week":
            max_delta = timedelta(days=7)
        else:  # month
            max_delta = timedelta(days=30)
        
        if now - cached_time < max_delta:
            return cache_data["data"]
    except (json.JSONDecodeError, KeyError, ValueError):
        pass
    
    return None

def save_cache(cache_path: str, data: List[Dict]):
    """Save data to cache."""
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    
    cache_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data
    }
    
    with open(cache_path, 'w') as f:
        json.dump(cache_data, f)



def get_subscriptions(access_token: str, max_channels: int = 50, use_cache: bool = True) -> List[Dict]:
    """Get user's YouTube subscriptions."""
    cache_key = get_cache_key(f"subscriptions_{max_channels}")
    cache_path = os.path.join(CACHE_DIR, f"subscriptions_{cache_key}.json")
    
    if use_cache:
        cached_data = load_cache(cache_path, "week")
        if cached_data:
            print("Using cached subscriptions")
            return cached_data
    
    headers = {"Authorization": f"Bearer {access_token}"}
    subscriptions = []
    next_page_token = None
    
    while len(subscriptions) < max_channels:
        params = {"part": "snippet", "mine": "true", "maxResults": 50}
        if next_page_token:
            params["pageToken"] = next_page_token
        
        try:
            response = requests.get(f"{YOUTUBE_API_BASE}/subscriptions", headers=headers, params=params)
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                print("\n⚠ Cannot access subscriptions. This could be due to:")
                print("1. YouTube Data API v3 not enabled in Google Cloud Console")
                print("2. OAuth scope missing (needs youtube.readonly)")
                print("3. API quota exceeded")
                print("\nTry: python youtube_auth.py --clear")
                sys.exit(1)
            raise
        
        data = response.json()
        subscriptions.extend(data.get("items", []))
        
        next_page_token = data.get("nextPageToken")
        if not next_page_token:
            break
    
    result = subscriptions[:max_channels]
    if use_cache:
        save_cache(cache_path, result)
    return result

def get_rss_podcasts(channel_id: str, published_after: datetime, max_results: int = 10) -> List[Dict]:
    """Get podcast episodes from RSS feed (no quota cost)."""
    try:
        import feedparser
    except ImportError:
        print("  ⚠ feedparser not installed. Run: pip install feedparser")
        return []
    
    try:
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        print(f"  Fetching RSS: {rss_url}")
        feed = feedparser.parse(rss_url)
        
        if not hasattr(feed, 'entries') or not feed.entries:
            print(f"  ⚠ No RSS entries found")
            return []
        
        print(f"  Found {len(feed.entries)} RSS entries")
        videos = []
        podcast_keywords = ['podcast', 'episode', 'show', 'ep ', '#']
        
        for entry in feed.entries[:max_results * 2]:
            try:
                pub_date = datetime.fromisoformat(entry.published.replace('Z', '+00:00'))
                title_lower = entry.title.lower()
                
                # More lenient podcast detection
                is_podcast = any(word in title_lower for word in podcast_keywords)
                
                if pub_date >= published_after:
                    videos.append({
                        "id": {"videoId": entry.yt_videoid},
                        "snippet": {
                            "title": entry.title,
                            "publishedAt": entry.published,
                            "channelTitle": getattr(entry, 'author', 'Unknown')
                        },
                        "is_podcast": is_podcast
                    })
                    print(f"    {'✓' if is_podcast else '○'} {entry.title[:50]}...")
                
                if len(videos) >= max_results:
                    break
            except Exception as e:
                print(f"  ⚠ Error parsing entry: {e}")
                continue
        
        # Return all videos, not just podcast-filtered ones
        return videos
    except Exception as e:
        print(f"  ⚠ RSS error: {e}")
        return []

def search_channel_podcasts(access_token: str, channel_id: str, published_after: datetime, max_results: int = 10, use_cache: bool = True, rss_only: bool = False) -> List[Dict]:
    """Search for podcast episodes from a channel."""
    published_after_str = published_after.isoformat().replace("+00:00", "Z")
    cache_key = get_cache_key(f"podcasts_{channel_id}_{published_after_str}_{max_results}")
    cache_path = os.path.join(CACHE_DIR, f"podcasts_{cache_key}.json")
    
    if use_cache:
        cached_data = load_cache(cache_path)
        if cached_data:
            return cached_data
    
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {
        "part": "snippet",
        "channelId": channel_id,
        "type": "video",
        "order": "date",
        "publishedAfter": published_after_str,
        "maxResults": max_results,
        "q": "podcast OR episode OR show"
    }
    
    # Try RSS first if enabled (no quota cost)
    if rss_only:
        return get_rss_podcasts(channel_id, published_after, max_results)
    
    try:
        response = requests.get(f"{YOUTUBE_API_BASE}/search", headers=headers, params=params)
        response.raise_for_status()
        result = response.json().get("items", [])
        if use_cache:
            save_cache(cache_path, result)
        return result
    except requests.exceptions.HTTPError:
        # Fallback to RSS on API error
        print(f"  API failed, trying RSS for channel...")
        return get_rss_podcasts(channel_id, published_after, max_results)

def get_video_stats(access_token: str, video_ids: List[str], use_cache: bool = True) -> Dict[str, Dict]:
    """Get statistics for videos."""
    cache_key = get_cache_key(f"stats_{'_'.join(sorted(video_ids))}")
    cache_path = os.path.join(CACHE_DIR, f"stats_{cache_key}.json")
    
    if use_cache:
        cached_data = load_cache(cache_path)
        if cached_data:
            return {item["id"]: item for item in cached_data}
    
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {
        "part": "statistics,snippet",
        "id": ",".join(video_ids)
    }
    
    try:
        response = requests.get(f"{YOUTUBE_API_BASE}/videos", headers=headers, params=params)
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 403:
            print(f"⚠ API quota exceeded or forbidden. Got {len(cache_items)} videos so far.")
            if cache_items:  # Return partial results if we have some
                if use_cache:
                    save_cache(cache_path, cache_items)
                return {item["id"]: item for item in cache_items}
            return {}
        raise
    
    stats = {}
    cache_items = []
    for item in response.json().get("items", []):
        video_data = {
            "id": item["id"],
            "views": int(item["statistics"].get("viewCount", 0)),
            "likes": int(item["statistics"].get("likeCount", 0)),
            "comments": int(item["statistics"].get("commentCount", 0)),
            "duration": item["snippet"].get("duration", ""),
            "title": item["snippet"]["title"],
            "channel": item["snippet"]["channelTitle"],
            "published": item["snippet"]["publishedAt"]
        }
        stats[item["id"]] = video_data
        cache_items.append(video_data)
    
    if use_cache:
        save_cache(cache_path, cache_items)
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
    parser.add_argument("--limit-channels", type=int, default=15, help="Limit channels to save quota")
    parser.add_argument("--channel-ids", help="Comma-separated channel IDs to check (bypasses subscriptions)")
    
    args = parser.parse_args()
    
    use_cache = not args.no_cache
    
    if args.clear_cache:
        import shutil
        if os.path.exists(CACHE_DIR):
            shutil.rmtree(CACHE_DIR)
            print("Cache cleared")
    
    # Calculate time window (week only to save quota)
    now = datetime.now(timezone.utc)
    published_after = now - timedelta(days=7)
    
    print(f"Finding podcast episodes from last {args.period}...")
    
    # Get access token via shared session manager
    if args.no_auth or args.rss_only:
        access_token = None
        print("Skipping authentication (RSS-only mode)")
    else:
        access_token = get_youtube_token()
    
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
        subscriptions = get_subscriptions(access_token, max_channels, use_cache)
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
            videos = search_channel_podcasts(access_token, channel_id, published_after, args.videos_per_channel, use_cache, args.rss_only)
        for video in videos:
            all_videos.append({
                "video_id": video["id"]["videoId"],
                "channel_name": channel_name,
                "video": video
            })
    
    if not all_videos:
        print("No videos found!")
        if args.rss_only:
            print("Try different channel IDs or extend the time period")
        return
    
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
            import csv
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
        
        return
    
    # Get video statistics (costs quota)
    print(f"Fetching video statistics for {len(all_videos)} videos...")
    print(f"Estimated quota cost: {len(all_videos)} units")
    video_ids = [v["video_id"] for v in all_videos]
    
    # Process in batches of 50 (API limit)
    all_stats = {}
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        print(f"Processing batch {i//50 + 1}/{(len(video_ids) + 49)//50}...")
        try:
            stats = get_video_stats(access_token, batch, use_cache)
            all_stats.update(stats)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                print(f"⚠ API quota exceeded at batch {i//50 + 1}. Using {len(all_stats)} videos.")
                break
            raise
    
    # Combine data and sort
    episodes = []
    for video_data in all_videos:
        video_id = video_data["video_id"]
        if video_id in all_stats:
            stats = all_stats[video_id]
            episodes.append({
                "title": stats["title"],
                "channel": stats["channel"],
                "views": stats["views"],
                "likes": stats["likes"],
                "comments": stats["comments"],
                "published": stats["published"],
                "url": f"https://www.youtube.com/watch?v={video_id}"
            })
    
    # Sort by chosen criteria
    episodes.sort(key=lambda x: x[args.sort_by], reverse=True)
    top_episodes = episodes[:args.top]
    
    # Display results
    print(f"\nTop {len(top_episodes)} podcast episodes by {args.sort_by}:")
    print("=" * 80)
    
    for i, ep in enumerate(top_episodes, 1):
        print(f"{i:2d}. {ep['title']}")
        print(f"    Channel: {ep['channel']}")
        print(f"    Views: {ep['views']:,} | Likes: {ep['likes']:,} | Comments: {ep['comments']:,}")
        print(f"    Published: {ep['published'][:10]}")
        print(f"    URL: {ep['url']}")
        print()
    
    # Save to files if requested
    if args.csv:
        import csv
        with open(args.csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['title', 'channel', 'views', 'likes', 'comments', 'published', 'url'])
            writer.writeheader()
            writer.writerows(top_episodes)
        print(f"Results saved to {args.csv}")
    
    if args.json:
        with open(args.json, 'w', encoding='utf-8') as f:
            json.dump(top_episodes, f, indent=2, ensure_ascii=False)
        print(f"Results saved to {args.json}")

if __name__ == "__main__":
    main()