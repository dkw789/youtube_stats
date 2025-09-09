# YouTube Data Collection Scripts

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

- **Smart caching**: 24-hour cache with automatic expiration
- **Quota tracking**: Cross-session quota usage monitoring
- **Progress saving**: Resume interrupted collections
- **Batch processing**: Efficient API usage patterns
- **Error recovery**: Graceful handling of API limits
- **Multi-format output**: JSON, CSV, Markdown support