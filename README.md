# YouTube Data Collection Scripts

**YOUTUBE API COMPLIANCE STATEMENT:**  
This project complies with YouTube API Services Terms and Policies (Project #55291277961):
- ✅ Displays only YouTube-provided metrics (views, likes, comments)
- ✅ No independently calculated or derived metrics (Policy III.E.4h)
- ✅ Data cached for maximum 24 hours (Policy III.E.4.a-g)
- ✅ Single project number for all scripts (Policy III.D.1c)

A collection of Python scripts for finding and analyzing YouTube content using the YouTube Data API v3 and RSS feeds.

## Scripts Overview

### 1. `yt_most_popular.py` - General Popular Videos
Find most-viewed YouTube videos published recently across all channels.

### 2. `yt_subscription_podcasts.py` - Subscription Podcast Finder
Find popular podcast episodes from your YouTube subscriptions.

### 3. `yt_phased_runner.py` - Quota-Managed Collection
Run data collection in phases to efficiently manage API quota limits.

### 4. `youtube_auth.py` - Shared Authentication
Manage OAuth authentication across all scripts with token caching.

### 5. `youtube_subscriptions.py` - Advanced Subscription Manager
Comprehensive subscription management with multiple data sources.

## Prerequisites

- Python 3.9+
- YouTube Data API v3 access (API key or OAuth)
- Optional: `feedparser` for RSS-only mode

## Setup

```bash
# Clone and setup environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt

# For RSS-only features
pip install feedparser
```

### Authentication Setup

**Option 1: API Key (Simple)**
```bash
# Set environment variable
export YOUTUBE_API_KEY=YOUR_API_KEY_HERE

# Or create .env file
echo "YOUTUBE_API_KEY=YOUR_API_KEY_HERE" > .env
```

**Option 2: OAuth (For Subscriptions)**
1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create project and enable YouTube Data API v3
3. Create OAuth 2.0 Client ID (Desktop application)
4. Download `client_secret_*.json` file to project directory
5. Add `http://localhost:8080` as authorized redirect URI

## Usage Examples

### General Popular Videos
```bash
# Top 25 videos from last week
python yt_most_popular.py --period week --top 25

# Most liked videos, save to JSON
python yt_most_popular.py --sort-by likes --json results.json

# Podcast-specific search
python yt_most_popular.py --podcast --period month --top 50
```

### Subscription Podcast Finder
```bash
# With authentication (full features)
python yt_subscription_podcasts.py --period week --top 25 --json podcasts.json

# RSS-only mode (no quota, no auth)
python yt_subscription_podcasts.py --rss-only --channel-ids "UCzQUP1qoWDoEbmsQxvdjxgQ" --json rss_podcasts.json

# Quota-saving options
python yt_subscription_podcasts.py --limit-channels 10 --videos-per-channel 3
```

### Phased Collection (Quota Management)
```bash
# Check quota status
python yt_phased_runner.py --status

# Run all phases with small batches
python yt_phased_runner.py --channels-per-batch 3 --videos-per-batch 25

# Run specific phase
python yt_phased_runner.py --phase 2 --channels-per-batch 5
```

### Authentication Management
```bash
# Test authentication
python youtube_auth.py --test

# Clear cached session
python youtube_auth.py --clear
```

## Quota Management

**YouTube API Quota Costs:**
- Search: 100 units per request
- Video details: 1 unit per video
- Subscriptions: 1 unit per request
- Daily limit: 10,000 units (free tier)

**Quota-Saving Strategies:**
1. **Use RSS mode**: Zero quota cost
2. **Enable caching**: Reuse data for 24 hours
3. **Limit batch sizes**: Process fewer items per run
4. **Use phased approach**: Spread collection across days

## Output Formats

All scripts support multiple output formats:
- **Console**: Formatted table display
- **JSON**: `--json filename.json`
- **CSV**: `--csv filename.csv`
- **Markdown**: `--md filename.md`

## Common Options

- `--period week|month`: Time window for recent content
- `--top N`: Number of results to return
- `--sort-by views|likes|comments`: Sort criteria
- `--no-cache`: Force fresh API calls
- `--clear-cache`: Clear all cached data

## RSS-Only Mode (No Quota)

```bash
# Find channel IDs from YouTube URLs
# Example: https://youtube.com/c/channelname -> UCxxxxxxxxx

# Use RSS feeds only (no authentication needed)
python yt_subscription_podcasts.py --rss-only --no-auth \
  --channel-ids "UCzQUP1qoWDoEbmsQxvdjxgQ,UCBJycsmduvYEL83R_U4JriQ" \
  --period week --json rss_results.json
```

## Troubleshooting

**403 Forbidden Errors:**
- Enable YouTube Data API v3 in Google Cloud Console
- Check API key restrictions
- Verify OAuth scope includes `youtube.readonly`
- Clear auth cache: `python youtube_auth.py --clear`

**Quota Exceeded:**
- Use `--rss-only` mode for zero quota usage
- Reduce `--max-channels` and `--videos-per-channel`
- Use phased collection: `python yt_phased_runner.py`
- Wait for quota reset (daily at midnight Pacific Time)

**OAuth Issues:**
- Localhost redirect error is normal - copy code from URL
- Ensure redirect URI `http://localhost:8080` is configured
- Check OAuth consent screen is published

**No Results Found:**
- Try longer time periods: `--period month`
- Use different channel IDs
- Check if channels have recent uploads
- Verify RSS feeds are available

## File Structure

```
.
├── yt_most_popular.py          # General popular videos
├── yt_subscription_podcasts.py # Subscription podcast finder
├── yt_phased_runner.py         # Quota-managed collection
├── youtube_auth.py             # Shared authentication
├── youtube_subscriptions.py    # Advanced subscription manager
├── requirements.txt            # Python dependencies
├── .env                        # Environment variables (optional)
├── client_secret_*.json        # OAuth credentials (optional)
└── .cache/                     # Cached API responses
```

## Advanced Features

- **Smart caching**: 24-hour cache with automatic expiration (Policy III.E.4.a-g compliant)
- **Quota tracking**: Cross-session quota usage monitoring
- **Progress saving**: Resume interrupted collections
- **Batch processing**: Efficient API usage patterns
- **Error recovery**: Graceful handling of API limits
- **Multi-format output**: JSON, CSV, Markdown support
- **YouTube metrics only**: No derived or calculated metrics (Policy III.E.4h compliant)

## Data Usage & Compliance

**What We Collect:**
- Views (from YouTube API `statistics.viewCount`)
- Likes (from YouTube API `statistics.likeCount`)
- Comments (from YouTube API `statistics.commentCount`)
- Published date (from YouTube API `snippet.publishedAt`)
- Title, channel, URL (from YouTube API `snippet`)

**What We DON'T Calculate:**
- ❌ Engagement rates or ratios
- ❌ Performance scores or rankings beyond YouTube metrics
- ❌ Any derived or independently calculated metrics

**Data Retention:**
- Maximum 24 hours (cache only)
- Automatic expiration and deletion
- No long-term storage
- Research use only

**User Guidelines:**
- Use only for academic research
- Export raw YouTube data for external analysis
- Perform statistical analysis in separate tools (R, Python pandas, etc.)
- Do not modify or derive metrics within the API client

## YouTube API integration walkthrough

This section explains how the scripts integrate with YouTube (OAuth, API calls, RSS fallback), the user flows, and which YouTube API services are called at each step.

### High-level data flow
1. Authenticate (OAuth) or run in RSS-only / manual mode.
2. Obtain list of subscribed channels (subscriptions.list) or use provided channel IDs.
3. For each channel: discover recent videos using search.list (preferred), channels.list + playlistItems.list (uploads playlist fallback), or RSS feed (zero-quota fallback).
4. Gather video statistics using videos.list (snippet + statistics) to compute views/likes/comments.
5. Cache responses to minimize quota usage and assemble sorted results for display/export.

### User flows
- Authenticated (recommended)
  - User provides OAuth credentials (client_secret_*.json or env).
  - App opens browser to Google OAuth consent URL (scope: https://www.googleapis.com/auth/youtube.readonly).
  - Local server / manual code copy captures authorization code and exchanges it at https://oauth2.googleapis.com/token for an access token.
  - The access token is cached (short TTL) and used in Authorization: Bearer <token> headers.
  - Subscriptions are fetched with subscriptions.list (mine=true) to enumerate channels.

- RSS-only / No-auth
  - No OAuth required. The user passes channel IDs via --channel-ids.
  - The script fetches https://www.youtube.com/feeds/videos.xml?channel_id=<id> and parses entries with feedparser.
  - This flow uses zero YouTube Data API quota but lacks view/like/comment stats.

- Manual channel IDs
  - Useful when subscriptions are not accessible or when running RSS-only mode.
  - Bypasses subscriptions.list and proceeds directly to search/playlist/RSS for the provided channels.

### Specific API services called
- OAuth endpoints
  - Authorization URL: https://accounts.google.com/o/oauth2/v2/auth (user consent, response_type=code)
  - Token exchange: https://oauth2.googleapis.com/token (exchange code → access_token)

- YouTube Data API v3 endpoints
  - subscriptions.list
    - Purpose: list the authenticated user's subscriptions (channels)
    - Parameters: part=snippet, mine=true, maxResults=...
    - Used in: authenticated flow to build the channel list.

  - search.list
    - Purpose: find videos on a channel, ordered by date (quick way to discover recent uploads)
    - Parameters: part=snippet, channelId=<id>, type=video, order=date, publishedAfter=..., maxResults=...
    - Cost: relatively high (e.g., scripts treat it as significant quota cost)
    - Used as the primary discovery method when using the API.

  - channels.list
    - Purpose: fetch channel contentDetails to find the uploads playlist ID
    - Parameters: part=contentDetails, id=<channelId>
    - Used when falling back to the uploads playlist method.

  - playlistItems.list
    - Purpose: read the uploads playlist to get recent uploads
    - Parameters: part=snippet, playlistId=<uploads_playlist_id>, maxResults=...
    - Used as a lower-quota fallback when search.list is limited or fails.

  - videos.list
    - Purpose: fetch detailed snippet + statistics for videos
    - Parameters: part=snippet,statistics (and optional contentDetails), id=<comma-separated video IDs>
    - Cost: typically 1 unit per video for statistics; used to obtain view/like/comment counts for ranking.

- RSS feeds (non-API)
  - URL: https://www.youtube.com/feeds/videos.xml?channel_id=<id>
  - Parsed by feedparser to get titles, publish dates, and video IDs.
  - Zero YouTube Data API quota cost but limited metadata (no view/like counts).

### Caching and quota strategies
- Local caching: responses are cached in .cache (or subscriptions_output/.cache) with TTLs to avoid repeated API calls.
- Batch requests: video statistics are requested in batches of up to 50 IDs per videos.list call to respect API limits.
- Quota accounting: scripts estimate and optionally limit requests (e.g., avoid exceeding daily quota).
- Fallback behavior:
  - On HTTP 403/429 or quota issues, scripts fall back to RSS or uploads playlist methods.
  - Consecutive 403s can trigger auto-switch to RSS-only mode for remaining channels.

### Error handling and edge cases
- Missing OAuth scope (must include youtube.readonly) or disabled API → subscriptions access denied (403).
- API quota exceeded → scripts either use cached data, stop, or switch to RSS fallback.
- RSS parsing errors → script logs and continues with other channels.
- Time-window filtering: publishedAfter parameter or RSS entry date filtering to limit to last week/month.

### Data produced and outputs
- For API-enabled runs: each item includes title, channel, publishedAt, views, likes, comments, and URL.
- For RSS-only runs: items include title, channel, publishedAt, and URL (statistics set to 0).
- Outputs: console table, JSON, CSV, or Markdown depending on CLI options.

### Quick mapping (where to look in code)
- Authentication & token caching: youtube_auth.py and youtube_subscriptions.py (get_oauth_credentials, get_access_token, cached token helpers)
- Subscriptions: subscriptions.list usage in get_subscriptions()
- Channel discovery: search.list in search_channel_videos(), channels.list + playlistItems.list in get_channel_uploads()
- RSS parsing: get_rss_videos() / get_rss_podcasts() using feedparser
- Video statistics: videos.list in get_video_details() / get_video_stats()
- Caching: save_cache() / load_cache() functions present across scripts
