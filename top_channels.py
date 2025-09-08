#!/usr/bin/env python3
"""
Find YouTube Channels with Most Subscribers
Searches for popular channels and ranks them by subscriber count.
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

# YouTube API quota costs
SEARCH_QUOTA_COST = 100  # per search request
CHANNEL_DETAILS_QUOTA_COST = 1  # per channel details request
DAILY_QUOTA_LIMIT = 10000  # free tier limit
SAFETY_BUFFER = 500  # reserve some quota for safety

# Cache settings
CACHE_DIR = ".cache"
CACHE_EXPIRY_HOURS = 24  # Cache expires after 24 hours


def get_api_key() -> str:
    """Get YouTube API key from environment or .env file."""
    load_dotenv()
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        raise SystemExit("Missing API key. Set YOUTUBE_API_KEY in your .env file.")
    return api_key


def get_cache_path(cache_key: str, endpoint: str) -> str:
    """Get the file path for a cache entry."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, f"{endpoint}_{cache_key}.json")


def is_cache_valid(cache_path: str) -> bool:
    """Check if cache file exists and is not expired."""
    if not os.path.exists(cache_path):
        return False
    
    file_age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(cache_path))
    return file_age.total_seconds() < (CACHE_EXPIRY_HOURS * 3600)


def load_from_cache(cache_path: str) -> Optional[Dict]:
    """Load data from cache file."""
    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save_to_cache(cache_path: str, data: Dict) -> None:
    """Save data to cache file."""
    try:
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Warning: Failed to save cache: {e}")


def cached_api_request(url: str, params: Dict, endpoint: str, quota_tracker: Optional[Dict[str, int]] = None, no_cache: bool = False) -> Dict:
    """Make API request with caching."""
    if no_cache:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    
    # Create cache key from parameters (excluding API key)
    cache_params = {k: v for k, v in params.items() if k != 'key'}
    cache_key = str(hash(str(sorted(cache_params.items()))))
    cache_path = get_cache_path(cache_key, endpoint)
    
    # Try to load from cache first
    if is_cache_valid(cache_path):
        cached_data = load_from_cache(cache_path)
        if cached_data:
            print(f"Using cached data for {endpoint}")
            if quota_tracker:
                quota_tracker["saved"] = quota_tracker.get("saved", 0) + 1
            return cached_data
    
    # Make API request
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    
    data = resp.json()
    
    # Save to cache
    save_to_cache(cache_path, data)
    
    return data


def search_channels(api_key: str, query: str, max_results: int, quota_tracker: Optional[Dict[str, int]] = None, no_cache: bool = False) -> List[Dict]:
    """Search for channels by query."""
    url = f"{YOUTUBE_API_BASE}/search"
    params = {
        "key": api_key,
        "part": "snippet",
        "type": "channel",
        "q": query,
        "maxResults": min(max_results, 50),  # API limit
        "order": "relevance"
    }
    
    channels = []
    next_page_token = None
    
    while len(channels) < max_results:
        if next_page_token:
            params["pageToken"] = next_page_token
        
        # Check quota
        if quota_tracker:
            estimated_cost = SEARCH_QUOTA_COST
            if quota_tracker.get("used", 0) + estimated_cost > DAILY_QUOTA_LIMIT - SAFETY_BUFFER:
                print(f"Quota limit reached. Used: {quota_tracker.get('used', 0)}")
                break
        
        data = cached_api_request(url, params, "search", quota_tracker, no_cache)
        
        # Track quota usage
        if quota_tracker:
            quota_tracker["used"] = quota_tracker.get("used", 0) + SEARCH_QUOTA_COST
        
        items = data.get("items", [])
        channels.extend(items)
        
        if len(channels) >= max_results:
            break
            
        next_page_token = data.get("nextPageToken")
        if not next_page_token:
            break
    
    return channels[:max_results]


def get_channel_details(api_key: str, channel_ids: List[str], quota_tracker: Optional[Dict[str, int]] = None, no_cache: bool = False) -> List[Dict]:
    """Get detailed statistics for channels."""
    url = f"{YOUTUBE_API_BASE}/channels"
    results = []
    
    # Process in chunks of 50 (API limit)
    for i in range(0, len(channel_ids), 50):
        chunk = channel_ids[i:i+50]
        
        # Check quota
        if quota_tracker:
            estimated_cost = CHANNEL_DETAILS_QUOTA_COST * len(chunk)
            if quota_tracker.get("used", 0) + estimated_cost > DAILY_QUOTA_LIMIT - SAFETY_BUFFER:
                print(f"Quota limit reached. Used: {quota_tracker.get('used', 0)}")
                break
        
        params = {
            "key": api_key,
            "part": "snippet,statistics",
            "id": ",".join(chunk)
        }
        
        data = cached_api_request(url, params, "channels", quota_tracker, no_cache)
        
        # Track quota usage
        if quota_tracker:
            quota_tracker["used"] = quota_tracker.get("used", 0) + CHANNEL_DETAILS_QUOTA_COST * len(chunk)
        
        results.extend(data.get("items", []))
    
    return results


def human_int(n: Optional[str]) -> int:
    """Convert string to int, return 0 if invalid."""
    try:
        return int(n) if n is not None else 0
    except Exception:
        return 0


def format_subscriber_count(count: int) -> str:
    """Format subscriber count in human-readable format."""
    if count >= 1_000_000_000:
        return f"{count / 1_000_000_000:.1f}B"
    elif count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    elif count >= 1_000:
        return f"{count / 1_000:.1f}K"
    else:
        return str(count)


def assemble_channel_results(channel_items: List[Dict]) -> List[Dict]:
    """Assemble and sort channel results by subscriber count."""
    assembled = []
    seen_channel_ids = set()
    
    for channel in channel_items:
        channel_id = channel.get("id")
        if not channel_id or channel_id in seen_channel_ids:
            continue
        
        seen_channel_ids.add(channel_id)
        snippet = channel.get("snippet", {})
        stats = channel.get("statistics", {})
        
        subscriber_count = human_int(stats.get("subscriberCount"))
        view_count = human_int(stats.get("viewCount"))
        video_count = human_int(stats.get("videoCount"))
        
        assembled.append({
            "channelId": channel_id,
            "title": snippet.get("title", ""),
            "description": snippet.get("description", "")[:200] + "..." if len(snippet.get("description", "")) > 200 else snippet.get("description", ""),
            "publishedAt": snippet.get("publishedAt", ""),
            "subscriberCount": subscriber_count,
            "viewCount": view_count,
            "videoCount": video_count,
            "url": f"https://www.youtube.com/channel/{channel_id}",
            "customUrl": snippet.get("customUrl", ""),
        })
    
    # Sort by subscriber count (descending)
    return sorted(assembled, key=lambda x: x["subscriberCount"], reverse=True)


def print_table(rows: List[Dict], limit: int) -> None:
    """Print results in table format."""
    limit = min(limit, len(rows))
    print(f"\nTop {limit} channels by subscriber count:")
    print("-" * 120)
    print(f"{'Rank':>4}  {'Subscribers':>12}  {'Channel':<25}  {'Videos':>8}  {'Views':>12}  {'URL'}")
    print("-" * 120)
    
    for i, row in enumerate(rows[:limit], 1):
        subscribers = format_subscriber_count(row['subscriberCount'])
        title = row['title'][:25]
        videos = format_subscriber_count(row['videoCount'])
        views = format_subscriber_count(row['viewCount'])
        url = row['url']
        
        print(f"{i:>4}  {subscribers:>12}  {title:<25}  {videos:>8}  {views:>12}  {url}")
    print("-" * 120)


def write_csv(rows: List[Dict], path: str, limit: int) -> None:
    """Write results to CSV file."""
    fieldnames = ["channelId", "title", "description", "publishedAt", "subscriberCount", "viewCount", "videoCount", "url", "customUrl"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows[:limit]:
            writer.writerow(row)


def write_json(rows: List[Dict], path: str, limit: int) -> None:
    """Write results to JSON file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows[:limit], f, ensure_ascii=False, indent=2)


def write_markdown(rows: List[Dict], path: str, limit: int) -> None:
    """Write results to Markdown file."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Top YouTube Channels by Subscribers\n\n")
        f.write(f"Top {min(limit, len(rows))} channels with most subscribers:\n\n")
        f.write("| Rank | Subscribers | Channel | Videos | Views | URL |\n")
        f.write("|------|-------------|---------|--------|-------|-----|\n")
        
        for i, row in enumerate(rows[:limit], 1):
            subscribers = format_subscriber_count(row['subscriberCount'])
            title = row['title'].replace('|', '\\|')
            videos = format_subscriber_count(row['videoCount'])
            views = format_subscriber_count(row['viewCount'])
            url = row['url']
            
            f.write(f"| {i} | {subscribers} | {title} | {videos} | {views} | [{url}]({url}) |\n")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Find YouTube channels with most subscribers")
    parser.add_argument("--query", default="", help="Search query for channels (default: broad search)")
    parser.add_argument("--max-results", type=int, default=100, help="Max channels to search for")
    parser.add_argument("--top", type=int, default=25, help="Number of top results to show")
    parser.add_argument("--api-key", help="YouTube Data API key (or set YOUTUBE_API_KEY)")
    parser.add_argument("--csv", help="Write results to CSV file")
    parser.add_argument("--json", help="Write results to JSON file")
    parser.add_argument("--md", help="Write results to Markdown file")
    parser.add_argument("--no-cache", action="store_true", help="Disable caching")
    parser.add_argument("--clear-cache", action="store_true", help="Clear cache before running")
    
    return parser.parse_args()


def clear_cache() -> None:
    """Clear all cached data."""
    if os.path.exists(CACHE_DIR):
        import shutil
        shutil.rmtree(CACHE_DIR)
        print("Cache cleared.")


def main():
    args = parse_args()
    
    # Clear cache if requested
    if args.clear_cache:
        clear_cache()
    
    # Get API key
    api_key = args.api_key or get_api_key()
    
    # Initialize quota tracker
    quota_tracker = {"used": 0, "saved": 0}
    
    # Calculate estimated quota usage
    estimated_search_requests = (args.max_results + 49) // 50
    estimated_search_cost = estimated_search_requests * SEARCH_QUOTA_COST
    estimated_channel_cost = min(args.max_results, 200) * CHANNEL_DETAILS_QUOTA_COST
    total_estimated = estimated_search_cost + estimated_channel_cost
    
    print(f"Estimated quota usage: {total_estimated} units (search: {estimated_search_cost}, channels: {estimated_channel_cost})")
    print(f"Daily limit: {DAILY_QUOTA_LIMIT} units (safety buffer: {SAFETY_BUFFER})")
    
    if total_estimated > DAILY_QUOTA_LIMIT - SAFETY_BUFFER:
        print(f"WARNING: Estimated usage ({total_estimated}) exceeds safe limit ({DAILY_QUOTA_LIMIT - SAFETY_BUFFER})")
        response = input("Continue anyway? (y/N): ").strip().lower()
        if response != 'y':
            print("Aborted.")
            return 1
    
    # Search for channels
    search_query = args.query or "popular channels"
    print(f"Searching for channels with query: '{search_query}'")
    
    search_results = search_channels(api_key, search_query, args.max_results, quota_tracker, args.no_cache)
    print(f"Found {len(search_results)} channels from search")
    
    if not search_results:
        print("No channels found.")
        return 0
    
    # Get channel IDs
    channel_ids = [item["snippet"]["channelId"] for item in search_results if "channelId" in item["snippet"]]
    print(f"Extracting details for {len(channel_ids)} channels...")
    
    # Get detailed channel information
    channel_details = get_channel_details(api_key, channel_ids, quota_tracker, args.no_cache)
    print(f"Retrieved details for {len(channel_details)} channels")
    
    # Process and sort results
    results = assemble_channel_results(channel_details)
    
    print(f"\nFinal quota usage: {quota_tracker['used']} units")
    if quota_tracker.get('saved', 0) > 0:
        print(f"Quota saved by caching: {quota_tracker['saved']} units")
    
    # Display results
    print_table(results, args.top)
    
    # Save to files if requested
    if args.csv:
        write_csv(results, args.csv, args.top)
        print(f"Wrote CSV: {args.csv}")
    
    if args.json:
        write_json(results, args.json, args.top)
        print(f"Wrote JSON: {args.json}")
    
    if args.md:
        write_markdown(results, args.md, args.top)
        print(f"Wrote Markdown: {args.md}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
