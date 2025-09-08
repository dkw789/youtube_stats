#!/usr/bin/env python3
"""
Simple YouTube Subscriptions Fetcher
Uses manual authorization code input to avoid redirect URI issues.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv

# OAuth 2.0 settings
OAUTH_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

# YouTube API quota costs
SEARCH_QUOTA_COST = 100  # per search request
VIDEO_DETAILS_QUOTA_COST = 1  # per video details request
SUBSCRIPTIONS_QUOTA_COST = 1  # per subscriptions request
DAILY_QUOTA_LIMIT = 10000  # free tier limit
SAFETY_BUFFER = 500  # reserve some quota for safety


def get_oauth_credentials() -> Tuple[str, str]:
    """Get OAuth client ID and secret from JSON file or environment."""
    load_dotenv()
    
    # Try to find and read from JSON file
    json_files = [f for f in os.listdir('.') if f.startswith('client_secret_') and f.endswith('.json')]
    
    if json_files:
        json_file = json_files[0]
        print(f"Found OAuth credentials file: {json_file}")
        try:
            with open(json_file, 'r') as f:
                creds_data = json.load(f)
            
            if "installed" in creds_data:
                client_data = creds_data["installed"]
            elif "web" in creds_data:
                client_data = creds_data["web"]
            else:
                raise ValueError("Invalid credentials file format")
            
            client_id = client_data["client_id"]
            client_secret = client_data["client_secret"]
            
            print(f"Loaded credentials from {json_file}")
            return client_id, client_secret
            
        except Exception as e:
            print(f"Error reading {json_file}: {e}")
    
    # Fallback to environment variables
    client_id = os.getenv("YOUTUBE_CLIENT_ID")
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")
    
    if not client_id or not client_secret:
        print("Missing OAuth credentials!")
        print("Please ensure you have a client_secret_*.json file or set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET")
        sys.exit(1)
    
    return client_id, client_secret


def get_authorization_url(client_id: str) -> str:
    """Generate OAuth authorization URL with manual redirect."""
    params = {
        "client_id": client_id,
        "redirect_uri": "http://localhost",
        "scope": OAUTH_SCOPE,
        "response_type": "code",
        "access_type": "offline",
        "prompt": "consent"
    }
    
    param_string = "&".join([f"{k}={v}" for k, v in params.items()])
    return f"https://accounts.google.com/o/oauth2/v2/auth?{param_string}"


def get_access_token(client_id: str, client_secret: str, auth_code: str) -> str:
    """Exchange authorization code for access token."""
    url = "https://oauth2.googleapis.com/token"
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": auth_code,
        "grant_type": "authorization_code",
        "redirect_uri": "http://localhost"  # Match your JSON file
    }
    
    response = requests.post(url, data=data)
    response.raise_for_status()
    
    token_data = response.json()
    return token_data["access_token"]


def get_subscriptions(access_token: str, max_results: int = 50, quota_tracker: Optional[Dict[str, int]] = None) -> List[Dict]:
    """Get user's YouTube subscriptions."""
    url = f"{YOUTUBE_API_BASE}/subscriptions"
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {
        "part": "snippet",
        "mine": "true",
        "maxResults": min(max_results, 50)
    }
    
    subscriptions = []
    next_page_token = None
    
    while True:
        if next_page_token:
            params["pageToken"] = next_page_token
        
        # Check quota before making request
        if quota_tracker:
            estimated_cost = SUBSCRIPTIONS_QUOTA_COST
            if quota_tracker.get("used", 0) + estimated_cost > DAILY_QUOTA_LIMIT - SAFETY_BUFFER:
                print(f"Quota limit reached. Used: {quota_tracker.get('used', 0)}")
                break
        
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        
        # Track quota usage
        if quota_tracker:
            quota_tracker["used"] = quota_tracker.get("used", 0) + SUBSCRIPTIONS_QUOTA_COST
        
        data = response.json()
        subscriptions.extend(data.get("items", []))
        
        if len(subscriptions) >= max_results:
            break
            
        next_page_token = data.get("nextPageToken")
        if not next_page_token:
            break
    
    return subscriptions[:max_results]


def search_channel_videos(access_token: str, channel_id: str, published_after: datetime, 
                         max_results: int = 10, quota_tracker: Optional[Dict[str, int]] = None) -> List[Dict]:
    """Search for videos from a specific channel published after a date."""
    url = f"{YOUTUBE_API_BASE}/search"
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {
        "part": "snippet",
        "channelId": channel_id,
        "type": "video",
        "order": "viewCount",
        "publishedAfter": published_after.isoformat() + "Z",
        "maxResults": min(max_results, 50)
    }
    
    # Check quota before making request
    if quota_tracker:
        estimated_cost = SEARCH_QUOTA_COST
        if quota_tracker.get("used", 0) + estimated_cost > DAILY_QUOTA_LIMIT - SAFETY_BUFFER:
            print(f"Quota limit reached. Used: {quota_tracker.get('used', 0)}")
            return []
    
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    
    # Track quota usage
    if quota_tracker:
        quota_tracker["used"] = quota_tracker.get("used", 0) + SEARCH_QUOTA_COST
    
    return response.json().get("items", [])


def get_video_details(access_token: str, video_ids: List[str], quota_tracker: Optional[Dict[str, int]] = None) -> List[Dict]:
    """Get detailed statistics for videos."""
    url = f"{YOUTUBE_API_BASE}/videos"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    results = []
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i:i+50]
        
        # Check quota before making request
        if quota_tracker:
            estimated_cost = VIDEO_DETAILS_QUOTA_COST * len(chunk)
            if quota_tracker.get("used", 0) + estimated_cost > DAILY_QUOTA_LIMIT - SAFETY_BUFFER:
                print(f"Quota limit reached. Used: {quota_tracker.get('used', 0)}")
                break
        
        params = {
            "part": "snippet,statistics",
            "id": ",".join(chunk)
        }
        
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        
        # Track quota usage
        if quota_tracker:
            quota_tracker["used"] = quota_tracker.get("used", 0) + VIDEO_DETAILS_QUOTA_COST * len(chunk)
        
        results.extend(response.json().get("items", []))
    
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


def main():
    parser = argparse.ArgumentParser(description="Find most popular videos from your YouTube subscriptions")
    parser.add_argument("--period", choices=["week", "month"], default="month", help="Time window")
    parser.add_argument("--top", type=int, default=25, help="Number of top results to show")
    parser.add_argument("--sort-by", choices=["views", "likes", "comments"], default="views", help="Sort by metric")
    parser.add_argument("--max-subscriptions", type=int, default=50, help="Max subscriptions to check")
    parser.add_argument("--videos-per-channel", type=int, default=10, help="Max videos per channel")
    parser.add_argument("--json", help="Save results to JSON file")
    
    args = parser.parse_args()
    
    # Calculate time window
    if args.period == "week":
        published_after = datetime.now(timezone.utc) - timedelta(days=7)
    else:
        published_after = datetime.now(timezone.utc) - timedelta(days=30)
    
    print(f"Finding most popular videos from your subscriptions in the past {args.period}")
    print(f"Published after: {published_after.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    
    # Get OAuth credentials
    client_id, client_secret = get_oauth_credentials()
    
    # Get authorization URL
    auth_url = get_authorization_url(client_id)
    print(f"\nPlease visit this URL to authorize the application:")
    print(auth_url)
    print("\nAfter authorizing, you'll see a page with an authorization code.")
    print("Copy that code and paste it below.")
    
    # Get authorization code
    auth_code = input("\nEnter the authorization code: ").strip()
    
    # Get access token
    print("Getting access token...")
    access_token = get_access_token(client_id, client_secret, auth_code)
    
    # Initialize quota tracker
    quota_tracker = {"used": 0, "saved": 0}
    
    # Calculate estimated quota usage
    estimated_subscriptions_cost = 1  # One subscription request
    estimated_search_cost = args.max_subscriptions * SEARCH_QUOTA_COST
    estimated_video_cost = args.max_subscriptions * args.videos_per_channel * VIDEO_DETAILS_QUOTA_COST
    total_estimated = estimated_subscriptions_cost + estimated_search_cost + estimated_video_cost
    
    print(f"Estimated quota usage: {total_estimated} units")
    print(f"Daily limit: {DAILY_QUOTA_LIMIT} units (safety buffer: {SAFETY_BUFFER})")
    
    if total_estimated > DAILY_QUOTA_LIMIT - SAFETY_BUFFER:
        print(f"WARNING: Estimated usage ({total_estimated}) exceeds safe limit ({DAILY_QUOTA_LIMIT - SAFETY_BUFFER})")
        response = input("Continue anyway? (y/N): ").strip().lower()
        if response != 'y':
            print("Aborted.")
            return 1
    
    # Get subscriptions
    print(f"Fetching your subscriptions (max {args.max_subscriptions})...")
    subscriptions = get_subscriptions(access_token, args.max_subscriptions, quota_tracker)
    
    if not subscriptions:
        print("No subscriptions found or error accessing subscriptions.")
        return 0
    
    print(f"Found {len(subscriptions)} subscriptions")
    
    # Get videos from each channel
    all_videos = []
    
    for i, sub in enumerate(subscriptions, 1):
        channel_info = sub["snippet"]
        channel_title = channel_info["title"]
        channel_id = channel_info["resourceId"]["channelId"]
        
        print(f"[{i}/{len(subscriptions)}] Checking {channel_title}...")
        
        try:
            videos = search_channel_videos(access_token, channel_id, published_after, args.videos_per_channel, quota_tracker)
            
            if videos:
                video_ids = [v["id"]["videoId"] for v in videos]
                video_details = get_video_details(access_token, video_ids, quota_tracker)
                
                all_videos.extend(video_details)
                print(f"  Found {len(video_details)} videos")
            else:
                print(f"  No recent videos found")
                
        except Exception as e:
            print(f"  Error: {e}")
            continue
    
    print(f"\nFinal quota usage: {quota_tracker['used']} units")
    
    if not all_videos:
        print("No videos found from your subscriptions in the specified time period.")
        return
    
    # Process and sort results
    results = assemble_results(all_videos, args.sort_by)
    print_table(results, args.top, args.sort_by)
    
    # Save to JSON if requested
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(results[:args.top], f, ensure_ascii=False, indent=2)
        print(f"\nResults saved to {args.json}")


if __name__ == "__main__":
    main()
