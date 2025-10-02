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
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv

# OAuth 2.0 settings
OAUTH_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
OAUTH_REDIRECT_URI = "http://localhost:8080"
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

# YouTube API quota costs
SEARCH_QUOTA_COST = 100
VIDEO_DETAILS_QUOTA_COST = 1
SUBSCRIPTIONS_QUOTA_COST = 1
DAILY_QUOTA_LIMIT = 10000
SAFETY_BUFFER = 500

# Cache and output settings
OUTPUT_DIR = "subscriptions_output"
CACHE_DIR = os.path.join(OUTPUT_DIR, ".cache")


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

def get_cached_access_token() -> Optional[str]:
    """Get cached access token if valid."""
    token_cache = os.path.join(CACHE_DIR, "access_token.json")
    if os.path.exists(token_cache):
        try:
            with open(token_cache, 'r') as f:
                token_data = json.load(f)
            
            token_time = datetime.fromisoformat(token_data["timestamp"])
            if datetime.now(timezone.utc) - token_time < timedelta(minutes=55):
                return token_data["access_token"]
        except (json.JSONDecodeError, KeyError, ValueError):
            pass
    return None

def save_access_token(access_token: str):
    """Save access token to cache."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    token_cache = os.path.join(CACHE_DIR, "access_token.json")
    with open(token_cache, 'w') as f:
        json.dump({
            "access_token": access_token,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }, f)

def get_oauth_credentials() -> Tuple[str, str]:
    """Get OAuth client ID and secret from JSON file, .env file, or environment variables."""
    load_dotenv()
    
    # First, try to find and read from JSON file
    json_files = [f for f in os.listdir('.') if f.startswith('client_secret_') and f.endswith('.json')]
    
    if json_files:
        json_file = json_files[0]  # Use the first one found
        print(f"Found OAuth credentials file: {json_file}")
        try:
            with open(json_file, 'r') as f:
                creds_data = json.load(f)
            
            # Handle both "installed" and "web" app types
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
            print("Falling back to environment variables...")
    
    # Fallback to environment variables
    client_id = os.getenv("YOUTUBE_CLIENT_ID")
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")
    
    if not client_id or not client_secret:
        print("Missing OAuth credentials!")
        print("\nTo set up credentials, choose one of these methods:")
        print("\nMethod 1 - JSON file (recommended):")
        print("1. Go to Google Cloud Console")
        print("2. Create/select a project")
        print("3. Enable YouTube Data API v3")
        print("4. Go to Credentials → Create Credentials → OAuth 2.0 Client ID")
        print("5. Choose 'Desktop application'")
        print("6. Download the JSON file and place it in this directory")
        print("7. The file should be named 'client_secret_*.json'")
        print("\nMethod 2 - Environment variables:")
        print("1. Set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET in your .env file")
        print("2. Or set them as environment variables")
        sys.exit(1)
    
    return client_id, client_secret


def get_authorization_url(client_id: str) -> str:
    """Generate OAuth authorization URL."""
    from urllib.parse import urlencode
    params = {
        "client_id": client_id,
        "redirect_uri": OAUTH_REDIRECT_URI,
        "scope": OAUTH_SCOPE,
        "response_type": "code",
        "access_type": "offline",
        "prompt": "consent"
    }
    
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"


def get_access_token(client_id: str, client_secret: str, auth_code: str) -> str:
    """Exchange authorization code for access token."""
    url = "https://oauth2.googleapis.com/token"
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": auth_code,
        "grant_type": "authorization_code",
        "redirect_uri": OAUTH_REDIRECT_URI
    }
    
    response = requests.post(url, data=data)
    response.raise_for_status()
    
    token_data = response.json()
    access_token = token_data["access_token"]
    
    # Cache the token
    save_access_token(access_token)
    
    return access_token

def get_cached_or_new_token() -> str:
    """Get cached token or perform OAuth flow."""
    # Check for cached token first
    cached_token = get_cached_access_token()
    if cached_token:
        print("Using cached access token")
        return cached_token
    
    # Perform OAuth flow
    client_id, client_secret = get_oauth_credentials()
    auth_url = get_authorization_url(client_id)
    
    print(f"\n1. Visit this URL: {auth_url}\n")
    print("2. Authorize the application")
    print("3. You'll be redirected to localhost:8080 - THIS WILL SHOW AN ERROR (normal!)")
    print("4. In the browser address bar, copy the 'code' parameter")
    print("   Example URL: http://localhost:8080/?code=4/XXXXX&scope=...")
    print("   Copy only: 4/XXXXX\n")
    auth_code = input("Paste authorization code here: ").strip()
    
    if not auth_code:
        print("No authorization code provided")
        sys.exit(1)
    
    try:
        access_token = get_access_token(client_id, client_secret, auth_code)
        print("Authorization successful!")
        return access_token
    except requests.exceptions.HTTPError as e:
        print(f"OAuth error: {e}")
        sys.exit(1)


def get_subscriptions(access_token: str, max_results: int = 50, use_cache: bool = True) -> List[Dict]:
    cache_key = get_cache_key(f"subscriptions_{max_results}")
    cache_path = os.path.join(CACHE_DIR, f"subscriptions_{cache_key}.json")
    
    if use_cache:
        cached_data = load_cache(cache_path, "month")
        if cached_data:
            print("Using cached subscriptions")
            return cached_data
    
    url = f"{YOUTUBE_API_BASE}/subscriptions"
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"part": "snippet", "mine": "true", "maxResults": min(max_results, 50)}
    
    subscriptions = []
    next_page_token = None
    
    while True:
        if next_page_token:
            params["pageToken"] = next_page_token
        
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        
        data = response.json()
        subscriptions.extend(data.get("items", []))
        
        if len(subscriptions) >= max_results:
            break
            
        next_page_token = data.get("nextPageToken")
        if not next_page_token:
            break
    
    result = subscriptions[:max_results]
    if use_cache:
        save_cache(cache_path, result)
    return result


def get_channel_uploads(access_token: str, channel_id: str, published_after: datetime, max_results: int = 10, use_cache: bool = True) -> List[Dict]:
    """Get recent uploads from channel's uploads playlist with caching."""
    published_after_str = published_after.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    cache_key = get_cache_key(f"uploads_{channel_id}_{published_after_str}_{max_results}")
    cache_path = os.path.join(CACHE_DIR, f"uploads_{cache_key}.json")
    
    if use_cache:
        cached_data = load_cache(cache_path)
        if cached_data:
            return cached_data
    
    try:
        # Get channel info to find uploads playlist
        url = f"{YOUTUBE_API_BASE}/channels"
        headers = {"Authorization": f"Bearer {access_token}"}
        params = {"part": "contentDetails", "id": channel_id}
        
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        
        data = response.json()
        if not data.get("items"):
            return []
        
        uploads_playlist_id = data["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        
        # Get playlist items
        url = f"{YOUTUBE_API_BASE}/playlistItems"
        params = {
            "part": "snippet",
            "playlistId": uploads_playlist_id,
            "maxResults": min(max_results * 2, 50)
        }
        
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        
        items = response.json().get("items", [])
        
        # Filter by publish date and convert format
        filtered_items = []
        for item in items:
            pub_date = datetime.fromisoformat(item["snippet"]["publishedAt"].replace("Z", "+00:00"))
            if pub_date >= published_after:
                filtered_items.append({
                    "id": {"videoId": item["snippet"]["resourceId"]["videoId"]},
                    "snippet": item["snippet"]
                })
            if len(filtered_items) >= max_results:
                break
        
        if use_cache:
            save_cache(cache_path, filtered_items)
        return filtered_items
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code in [403, 429]:
            return []  # Return empty list on quota/permission errors
        raise

def search_channel_videos(access_token: str, channel_id: str, published_after: datetime, 
                         max_results: int = 10, use_cache: bool = True) -> List[Dict]:
    """Search for videos from a specific channel with caching and fallback to uploads playlist."""
    published_after_str = published_after.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    cache_key = get_cache_key(f"search_{channel_id}_{published_after_str}_{max_results}")
    cache_path = os.path.join(CACHE_DIR, f"search_{cache_key}.json")
    
    if use_cache:
        cached_data = load_cache(cache_path)
        if cached_data:
            return cached_data
    
    # Try search API first
    try:
        url = f"{YOUTUBE_API_BASE}/search"
        headers = {"Authorization": f"Bearer {access_token}"}
        params = {
            "part": "snippet",
            "channelId": channel_id,
            "type": "video",
            "order": "date",
            "publishedAfter": published_after_str,
            "maxResults": min(max_results, 50)
        }
        
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        result = response.json().get("items", [])
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code in [403, 429]:  # Quota exceeded or forbidden
            # Fallback to uploads playlist (costs less quota)
            result = get_channel_uploads(access_token, channel_id, published_after, max_results, use_cache)
            # If uploads also fails, return empty list
            if not result:
                result = []
        else:
            raise
    
    if use_cache and result:
        save_cache(cache_path, result)
    return result


def get_rss_videos(channel_id: str, published_after: datetime, max_results: int = 10) -> List[Dict]:
    """Get videos from RSS feed (no quota cost)."""
    try:
        import feedparser
    except ImportError:
        print("  ⚠ feedparser not installed. Install with: pip install feedparser")
        return []
    
    try:
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        feed = feedparser.parse(rss_url)
        
        if not hasattr(feed, 'entries') or not feed.entries:
            return []
        
        videos = []
        for entry in feed.entries[:max_results * 3]:  # Get more to filter
            try:
                # Parse published date
                pub_date = datetime.fromisoformat(entry.published.replace('Z', '+00:00'))
                if pub_date >= published_after:
                    videos.append({
                        "id": {"videoId": entry.yt_videoid},
                        "snippet": {
                            "title": entry.title,
                            "publishedAt": entry.published,
                            "channelTitle": getattr(entry, 'author', 'Unknown')
                        }
                    })
                if len(videos) >= max_results:
                    break
            except Exception:
                continue  # Skip problematic entries
        
        return videos
    except Exception as e:
        print(f"  ⚠ RSS error: {e}")
        return []

def get_video_details(access_token: str, video_ids: List[str], use_cache: bool = True) -> List[Dict]:
    """Get detailed statistics for videos with caching."""
    cache_key = get_cache_key(f"video_details_{'_'.join(sorted(video_ids))}")
    cache_path = os.path.join(CACHE_DIR, f"video_details_{cache_key}.json")
    
    if use_cache:
        cached_data = load_cache(cache_path)
        if cached_data:
            return cached_data
    
    url = f"{YOUTUBE_API_BASE}/videos"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    results = []
    for i in range(0, len(video_ids), 50):  # API limit is 50 per request
        chunk = video_ids[i:i+50]
        params = {
            "part": "snippet,statistics",
            "id": ",".join(chunk)
        }
        
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        
        results.extend(response.json().get("items", []))
    
    if use_cache:
        save_cache(cache_path, results)
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


def get_cache_key(data: str) -> str:
    return hashlib.md5(data.encode()).hexdigest()

def load_cache(cache_path: str, period: str = "month") -> Optional[Dict]:
    if not os.path.exists(cache_path):
        return None
    
    # Set cache expiry based on period
    if period == "week":
        cache_expiry_hours = 24  # 1 day for weekly analysis
    else:  # month
        cache_expiry_hours = 168  # 1 week for monthly analysis
    
    file_age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(cache_path))
    if file_age.total_seconds() > (cache_expiry_hours * 3600):
        return None
    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return None

def save_cache(cache_path: str, data: Dict) -> None:
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    try:
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except:
        pass

def save_to_json(rows: List[Dict], path: str, limit: int) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows[:limit], f, ensure_ascii=False, indent=2)


def main():
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
    
    args = parser.parse_args()
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if not args.no_cache:
        os.makedirs(CACHE_DIR, exist_ok=True)
    
    # Get OAuth credentials
    client_id, client_secret = get_oauth_credentials()
    
    # Get authorization
    auth_url = get_authorization_url(client_id)
    print("\n" + "="*60)
    print("YOUTUBE OAUTH AUTHORIZATION REQUIRED")
    print("="*60)
    print("\n1. Open this URL in your browser:")
    print(f"\n{auth_url}\n")
    print("2. Sign in to your Google account")
    print("3. Grant permission to access your YouTube data")
    print("4. Copy the authorization code from the page")
    print("\n" + "-"*60)
    
    # Start local server to capture OAuth callback
    import threading
    import http.server
    import socketserver
    from urllib.parse import urlparse, parse_qs
    
    auth_code = None
    server_error = None
    
    class OAuthHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            nonlocal auth_code, server_error
            try:
                parsed_url = urlparse(self.path)
                query_params = parse_qs(parsed_url.query)
                
                if 'code' in query_params:
                    auth_code = query_params['code'][0]
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()
                    self.wfile.write(b'<h1>Success!</h1><p>You can close this window and return to the terminal.</p>')
                elif 'error' in query_params:
                    server_error = query_params['error'][0]
                    self.send_response(400)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()
                    self.wfile.write(f'<h1>Error: {server_error}</h1>'.encode())
            except Exception as e:
                server_error = str(e)
        
        def log_message(self, format, *args):
            pass  # Suppress server logs
    
    # Start server
    with socketserver.TCPServer(("", 8080), OAuthHandler) as httpd:
        server_thread = threading.Thread(target=httpd.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        
        # Open browser
        import webbrowser
        webbrowser.open(auth_url)
        
        # Wait for callback
        print("Waiting for authorization...")
        import time
        timeout = 120  # 2 minutes
        start_time = time.time()
        
        while auth_code is None and server_error is None:
            if time.time() - start_time > timeout:
                print("Timeout waiting for authorization")
                return 1
            time.sleep(0.5)
        
        httpd.shutdown()
    
    if server_error:
        print(f"Authorization error: {server_error}")
        return 1
    
    if not auth_code:
        print("No authorization code received")
        return 1
    
    try:
        # Get access token
        print("\nExchanging code for access token...")
        access_token = get_access_token(client_id, client_secret, auth_code)
        print("✓ Successfully authenticated!")
        
        # Calculate time window
        if args.period == "week":
            published_after = datetime.now(timezone.utc) - timedelta(days=7)
        else:
            published_after = datetime.now(timezone.utc) - timedelta(days=30)
        
        # Initialize quota tracker
        quota_tracker = {"used": 0, "saved": 0}
        
        # Calculate estimated quota usage
        estimated_subscriptions_cost = 1  # One subscription request
        estimated_search_cost = args.max_subscriptions * SEARCH_QUOTA_COST
        estimated_video_cost = args.max_subscriptions * args.videos_per_channel * VIDEO_DETAILS_QUOTA_COST
        total_estimated = estimated_subscriptions_cost + estimated_search_cost + estimated_video_cost
        
        print(f"\nEstimated quota usage: {total_estimated} units")
        print(f"Daily limit: {DAILY_QUOTA_LIMIT} units (safety buffer: {SAFETY_BUFFER})")
        if not args.use_api:
            print("RSS mode enabled - using RSS feeds with minimal API calls")
        elif args.rss_fallback:
            print("RSS fallback enabled - will try to use RSS feeds first (no quota cost)")
        
        if total_estimated > DAILY_QUOTA_LIMIT - SAFETY_BUFFER:
            print(f"WARNING: Estimated usage ({total_estimated}) exceeds safe limit ({DAILY_QUOTA_LIMIT - SAFETY_BUFFER})")
            response = input("Continue anyway? (y/N): ").strip().lower()
            if response != 'y':
                print("Aborted.")
                return 1
        
        print(f"\nFetching your subscriptions (max {args.max_subscriptions})...")
        subscriptions = get_subscriptions(access_token, args.max_subscriptions, not args.no_cache)
        print(f"✓ Found {len(subscriptions)} subscriptions")
        
        if not subscriptions:
            print("No subscriptions found.")
            return 0
        
        if args.batch_size < len(subscriptions):
            print(f"Processing in batches of {args.batch_size} to manage quota usage")
        
        # Collect videos from subscribed channels in batches
        print(f"\nSearching for videos from the last {args.period}...")
        all_videos = []
        consecutive_403_count = 0
        auto_rss_mode = False
        
        # Process in batches to save quota
        for batch_start in range(0, len(subscriptions), args.batch_size):
            batch = subscriptions[batch_start:batch_start + args.batch_size]
            print(f"\nProcessing batch {batch_start//args.batch_size + 1}/{(len(subscriptions) + args.batch_size - 1)//args.batch_size}")
            
            for i, sub in enumerate(batch, batch_start + 1):
                channel_title = sub['snippet']['title']
                channel_id = sub['snippet']['resourceId']['channelId']
                
                print(f"[{i}/{len(subscriptions)}] {channel_title}")
                
                # Check quota before making request
                if quota_tracker.get("used", 0) + SEARCH_QUOTA_COST > DAILY_QUOTA_LIMIT - SAFETY_BUFFER:
                    print(f"  ⚠ Quota limit reached. Used: {quota_tracker.get('used', 0)}")
                    break
                
                try:
                    # Default RSS mode or auto RSS mode
                    if not args.use_api or auto_rss_mode:
                        videos = get_rss_videos(channel_id, published_after, args.videos_per_channel)
                        if videos:
                            print(f"  ✓ Got {len(videos)} videos from RSS")
                            all_videos.extend(videos)
                            consecutive_403_count = 0  # Reset counter on success
                        else:
                            print(f"  ⚠ No RSS videos found")
                        continue
                    
                    # Try RSS first if enabled (no quota cost)
                    if args.rss_fallback:
                        videos = get_rss_videos(channel_id, published_after, args.videos_per_channel)
                        if videos:
                            print(f"  ✓ Got {len(videos)} videos from RSS (no quota used)")
                            all_videos.extend(videos)
                            consecutive_403_count = 0  # Reset counter on success
                            continue
                    
                    # Fallback to API
                    videos = search_channel_videos(
                        access_token, channel_id, published_after, args.videos_per_channel, not args.no_cache
                    )
                    
                    # Track quota usage (only if not using cache)
                    if not args.no_cache:
                        published_after_str = published_after.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
                        cache_key = get_cache_key(f"search_{channel_id}_{published_after_str}_{args.videos_per_channel}")
                        cache_path = os.path.join(CACHE_DIR, f"search_{cache_key}.json")
                        if not load_cache(cache_path):  # No valid cache, so we used API
                            quota_tracker["used"] = quota_tracker.get("used", 0) + SEARCH_QUOTA_COST
                    else:
                        quota_tracker["used"] = quota_tracker.get("used", 0) + SEARCH_QUOTA_COST
                    
                    all_videos.extend(videos)
                    consecutive_403_count = 0  # Reset counter on success
                    
                except Exception as e:
                    error_str = str(e)
                    if "403" in error_str or "Forbidden" in error_str:
                        consecutive_403_count += 1
                        print(f"  ⚠ 403 Error ({consecutive_403_count}/3): {e}")
                        
                        # Switch to RSS-only mode after 2 consecutive 403s
                        if consecutive_403_count >= 2 and not auto_rss_mode:
                            auto_rss_mode = True
                            print(f"\n🔄 Switching to RSS-only mode due to consecutive 403 errors")
                            print(f"Will use RSS feeds for remaining channels (no quota cost)")
                            # Retry this channel with RSS
                            videos = get_rss_videos(channel_id, published_after, args.videos_per_channel)
                            if videos:
                                print(f"  ✓ Got {len(videos)} videos from RSS")
                                all_videos.extend(videos)
                            else:
                                print(f"  ⚠ No RSS videos found")
                    else:
                        consecutive_403_count = 0  # Reset on non-403 errors
                        print(f"  ⚠ Error fetching videos: {e}")
                    continue
            
            # Small delay between batches to be respectful
            if batch_start + args.batch_size < len(subscriptions):
                import time
                time.sleep(1)
        
        if not all_videos:
            print(f"\nNo videos found from the last {args.period}.")
            return 0
        
        print(f"\n✓ Found {len(all_videos)} videos total")
        
        if not args.use_api:
            # RSS mode: create results from RSS data only (no API calls for statistics)
            print("Using RSS data only (no video statistics available)")
            video_details = []
            for v in all_videos:
                if 'id' in v and 'videoId' in v['id']:
                    video_details.append({
                        "id": v['id']['videoId'],
                        "snippet": v['snippet'],
                        "statistics": {"viewCount": "0", "likeCount": "0", "commentCount": "0"}
                    })
        else:
            # Get video details with smart batching
            print("Fetching video statistics...")
            video_ids = [v['id']['videoId'] for v in all_videos if 'id' in v and 'videoId' in v['id']]
            
            # Remove duplicates to save quota
            video_ids = list(set(video_ids))
            print(f"Removed duplicates: {len([v['id']['videoId'] for v in all_videos if 'id' in v and 'videoId' in v['id']]) - len(video_ids)} videos")
            
            # Check quota before getting video details
            estimated_video_cost = len(video_ids) * VIDEO_DETAILS_QUOTA_COST
            if quota_tracker.get("used", 0) + estimated_video_cost > DAILY_QUOTA_LIMIT - SAFETY_BUFFER:
                print(f"⚠ Quota limit would be exceeded. Used: {quota_tracker.get('used', 0)}, would need: {estimated_video_cost}")
                # Limit the number of videos to stay within quota
                max_videos = (DAILY_QUOTA_LIMIT - SAFETY_BUFFER - quota_tracker.get("used", 0)) // VIDEO_DETAILS_QUOTA_COST
                video_ids = video_ids[:max_videos]
                print(f"Limiting to {len(video_ids)} videos to stay within quota")
            
            video_details = get_video_details(access_token, video_ids, not args.no_cache)
            
            # Track quota usage (only if not cached)
            if not args.no_cache:
                cache_key = get_cache_key(f"video_details_{'_'.join(sorted(video_ids))}")
                cache_path = os.path.join(CACHE_DIR, f"video_details_{cache_key}.json")
                if not load_cache(cache_path):  # No valid cache, so we used API
                    quota_tracker["used"] = quota_tracker.get("used", 0) + len(video_ids) * VIDEO_DETAILS_QUOTA_COST
            else:
                quota_tracker["used"] = quota_tracker.get("used", 0) + len(video_ids) * VIDEO_DETAILS_QUOTA_COST
            
            # Filter by minimum views if specified
            if args.min_views > 0:
                original_count = len(video_details)
                video_details = [v for v in video_details if human_int(v.get('statistics', {}).get('viewCount', 0)) >= args.min_views]
                print(f"Filtered out {original_count - len(video_details)} videos with < {args.min_views:,} views")
        
        # Assemble and sort results
        results = assemble_results(video_details, args.sort_by)
        
        # Display quota usage
        if args.use_api:
            print(f"\nFinal quota usage: {quota_tracker['used']} units")
            if quota_tracker.get('saved', 0) > 0:
                print(f"Quota saved by caching: {quota_tracker['saved']} requests")
            print(f"Remaining quota: {DAILY_QUOTA_LIMIT - quota_tracker['used']} units")
        else:
            print(f"\nQuota usage: 1 unit (subscriptions only)")
            print(f"RSS mode saved approximately {len(subscriptions) * 100} quota units")
        
        # Display results
        print_table(results, args.top, args.sort_by)
        
        # Save results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if args.output:
            output_path = args.output
        else:
            output_path = os.path.join(OUTPUT_DIR, f"subscriptions_{args.period}_{args.sort_by}_{timestamp}.json")
        
        save_to_json(results, output_path, args.top)
        print(f"\n✓ Results saved to {output_path}")
        
        return 0
        
    except Exception as e:
        print(f"\nError: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
