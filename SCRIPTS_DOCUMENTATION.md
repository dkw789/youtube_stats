# YouTube Analytics Scripts Documentation

This project contains several Python scripts for analyzing YouTube data using the YouTube Data API v3. All scripts include quota protection, caching, and multiple output formats.

## Table of Contents

1. [yt_most_popular.py](#yt_most_popularpy) - Find most popular videos
2. [youtube_subscriptions.py](#youtube_subscriptionspy) - Analyze your subscriptions
3. [simple_subscriptions.py](#simple_subscriptionspy) - Simplified subscriptions script
4. [top_channels.py](#top_channelspy) - Find channels with most subscribers
5. [Setup and Configuration](#setup-and-configuration)
6. [Common Features](#common-features)
7. [Troubleshooting](#troubleshooting)

---

## yt_most_popular.py

**Purpose**: Find the most popular YouTube videos published within a specific time window (week or month).

### Features
- Search for videos by time period (week/month)
- Sort by views, likes, or comments
- Support for different regions
- Podcast-specific search
- Quota protection and caching
- Multiple output formats (CSV, JSON, Markdown)

### Usage

```bash
# Basic usage - most viewed videos this week
python yt_most_popular.py --period week --top 25

# Most liked videos this month
python yt_most_popular.py --period month --sort-by likes --top 50

# Find popular podcasts
python yt_most_popular.py --period month --podcast --top 30

# Search specific content
python yt_most_popular.py --period week --query "gaming" --top 20

# Save to multiple formats
python yt_most_popular.py --period month --top 50 --csv results.csv --json results.json --md results.md
```

### Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--period` | Time window: `week` or `month` | `week` |
| `--region` | Region code (US, GB, IN, etc.) | `US` |
| `--max-results` | Videos to fetch before ranking | `100` |
| `--top` | Number of top results to show | `25` |
| `--sort-by` | Sort by: `views`, `likes`, `comments` | `views` |
| `--query` | Custom search query | Broad search |
| `--podcast` | Search specifically for podcasts | `False` |
| `--published-after` | Custom ISO8601 timestamp | Auto-calculated |
| `--csv` | Save results to CSV file | None |
| `--json` | Save results to JSON file | None |
| `--md` | Save results to Markdown file | None |
| `--no-cache` | Disable caching | `False` |
| `--clear-cache` | Clear cache before running | `False` |

### Environment Variables

```bash
# .env file
YOUTUBE_API_KEY=your_api_key_here
YT_PERIOD=month
YT_REGION=US
YT_TOP=25
YT_SORT_BY=views
YT_QUERY=gaming
YT_CSV_PATH=results.csv
YT_JSON_PATH=results.json
YT_MD_PATH=results.md
```

### Example Output

```
Top 25 videos by Views:
--------------------------------------------------------------------------------
        Views  Title
--------------------------------------------------------------------------------
  12,345,678  Amazing Video Title Here
   9,876,543  Another Great Video
   8,765,432  Popular Content
```

---

## youtube_subscriptions.py

**Purpose**: Find the most popular videos from your YouTube subscriptions using OAuth authentication.

### Features
- OAuth 2.0 authentication
- Automatic subscription fetching
- Channel-specific video search
- Quota tracking and protection
- Caching support

### Prerequisites

1. **OAuth Setup Required**:
   - Google Cloud Console project
   - YouTube Data API v3 enabled
   - OAuth 2.0 Client ID created
   - JSON credentials file or environment variables

2. **Credentials File**:
   - Download `client_secret_*.json` from Google Cloud Console
   - Place in project directory
   - Or set `YOUTUBE_CLIENT_ID` and `YOUTUBE_CLIENT_SECRET` in `.env`

### Usage

```bash
# Basic usage
python youtube_subscriptions.py --period month --top 25

# Most liked videos from subscriptions
python youtube_subscriptions.py --period week --sort-by likes --top 20

# Check more subscriptions and save results
python youtube_subscriptions.py --period month --max-subscriptions 100 --top 50 --json my_subscriptions.json
```

### Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--period` | Time window: `week` or `month` | `month` |
| `--top` | Number of top results to show | `25` |
| `--sort-by` | Sort by: `views`, `likes`, `comments` | `views` |
| `--max-subscriptions` | Max subscriptions to check | `50` |
| `--videos-per-channel` | Max videos per channel | `10` |
| `--json` | Save results to JSON file | None |
| `--no-browser` | Don't open browser automatically | `False` |

### OAuth Flow

1. Script opens browser for Google OAuth
2. Sign in with your YouTube account
3. Grant permissions to the application
4. Copy authorization code from redirect URL
5. Paste code into terminal
6. Script fetches your subscriptions and analyzes videos

### Example Output

```
Found 50 subscriptions
[1/50] Checking MrBeast...
  Found 8 videos
[2/50] Checking PewDiePie...
  Found 5 videos
...

Top 25 videos from your subscriptions by Views:
----------------------------------------------------------------------------------------------------
Rank  Views        Channel              Title
----------------------------------------------------------------------------------------------------
   1  12,345,678   MrBeast              Amazing Video Title
   2   9,876,543   PewDiePie            Another Great Video
```

---

## simple_subscriptions.py

**Purpose**: Simplified version of the subscriptions script that uses manual authorization code input to avoid redirect URI issues.

### Features
- Manual authorization code input
- No localhost redirect requirements
- Same functionality as main subscriptions script
- Better error handling for OAuth issues

### Usage

```bash
# Basic usage
python simple_subscriptions.py --period month --top 25

# With custom parameters
python simple_subscriptions.py --period week --sort-by likes --top 30 --json results.json
```

### Command Line Options

Same as `youtube_subscriptions.py` but without `--no-browser` option.

### Authorization Process

1. Script displays authorization URL
2. Manually visit URL in browser
3. Sign in and grant permissions
4. Copy authorization code from the page
5. Paste code into terminal

---

## top_channels.py

**Purpose**: Find YouTube channels with the most subscribers by searching and ranking channels.

### Features
- Channel search by query
- Subscriber count ranking
- Channel statistics (views, videos, subscribers)
- Human-readable number formatting
- Multiple output formats

### Usage

```bash
# Find top channels overall
python top_channels.py --top 25

# Search for specific types of channels
python top_channels.py --query "gaming" --top 30

# Save to multiple formats
python top_channels.py --query "music" --top 50 --csv music_channels.csv --json music_channels.json --md music_channels.md
```

### Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--query` | Search query for channels | `popular channels` |
| `--max-results` | Max channels to search for | `100` |
| `--top` | Number of top results to show | `25` |
| `--csv` | Save results to CSV file | None |
| `--json` | Save results to JSON file | None |
| `--md` | Save results to Markdown file | None |
| `--no-cache` | Disable caching | `False` |
| `--clear-cache` | Clear cache before running | `False` |

### Example Output

```
Top 25 channels by subscriber count:
------------------------------------------------------------------------------------------------------------------------
Rank  Subscribers  Channel                   Videos    Views        URL
------------------------------------------------------------------------------------------------------------------------
   1        432.0M  MrBeast                  897       94.4B        https://www.youtube.com/channel/UCX6OQ3DkcsbYNE6H8uQQuVA
   2        192.0M  YouTube Movies           0         0            https://www.youtube.com/channel/UClgRkhTL3_hImCAmdLfDE4g
   3        136.0M  Kids Diana Show          1.4K      118.8B       https://www.youtube.com/channel/UCk8GzjMOrta8yxDcKfylJYw
```

---

## Setup and Configuration

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Get YouTube API Key

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create or select a project
3. Enable YouTube Data API v3
4. Create credentials (API Key)
5. Add to `.env` file:

```bash
YOUTUBE_API_KEY=your_api_key_here
```

### 3. OAuth Setup (for subscriptions scripts)

1. In Google Cloud Console, create OAuth 2.0 Client ID
2. Choose "Desktop application"
3. Add redirect URI: `http://localhost`
4. Download JSON file or add to `.env`:

```bash
YOUTUBE_CLIENT_ID=your_client_id_here
YOUTUBE_CLIENT_SECRET=your_client_secret_here
```

### 4. Environment Variables

Create a `.env` file in the project directory:

```bash
# Required
YOUTUBE_API_KEY=your_api_key_here

# Optional - OAuth credentials
YOUTUBE_CLIENT_ID=your_client_id_here
YOUTUBE_CLIENT_SECRET=your_client_secret_here

# Optional - Default settings
YT_PERIOD=month
YT_REGION=US
YT_TOP=25
YT_SORT_BY=views
```

---

## Common Features

### Quota Protection

All scripts include quota tracking and protection:

- **Daily Limit**: 10,000 units (free tier)
- **Safety Buffer**: 500 units reserved
- **Cost Tracking**: Shows estimated and actual usage
- **Automatic Stopping**: Prevents exceeding limits

### Caching

- **Automatic Caching**: API responses cached for 24 hours
- **Cache Directory**: `.cache/` folder
- **Quota Savings**: Significant reduction in API calls
- **Cache Management**: `--no-cache` and `--clear-cache` options

### Output Formats

All scripts support multiple output formats:

- **Console**: Formatted table display
- **CSV**: Spreadsheet-compatible format
- **JSON**: Structured data format
- **Markdown**: Documentation-friendly format

### Error Handling

- **API Errors**: Detailed error messages with troubleshooting
- **Quota Limits**: Graceful handling of quota exceeded
- **Network Issues**: Timeout and retry logic
- **Invalid Data**: Robust parsing with fallbacks

---

## Troubleshooting

### Common Issues

#### 1. API Key Issues

**Error**: `Missing API key` or `403 Forbidden`

**Solutions**:
- Verify API key is correct in `.env` file
- Ensure YouTube Data API v3 is enabled
- Check API key restrictions in Google Cloud Console

#### 2. OAuth Issues

**Error**: `Access blocked` or `403 access_denied`

**Solutions**:
- Add your email as a test user in OAuth consent screen
- Ensure redirect URI matches (`http://localhost`)
- Check that OAuth client is in "Testing" mode

#### 3. Quota Issues

**Error**: `Quota exceeded`

**Solutions**:
- Reduce `--max-results` parameter
- Use caching (don't use `--no-cache`)
- Wait for daily quota reset
- Consider upgrading to paid quota

#### 4. No Results Found

**Possible Causes**:
- Time window too narrow (try `--period month`)
- Search query too specific
- Region restrictions
- API not fully enabled

#### 5. Cache Issues

**Error**: `Failed to save cache`

**Solutions**:
- Check write permissions in project directory
- Clear cache with `--clear-cache`
- Use `--no-cache` to bypass caching

### Getting Help

1. **Check Logs**: Scripts provide detailed output and error messages
2. **Verify Setup**: Ensure all prerequisites are met
3. **Test API**: Try simple queries first
4. **Check Quotas**: Monitor usage in Google Cloud Console

### Performance Tips

1. **Use Caching**: Don't disable caching unless necessary
2. **Batch Operations**: Use appropriate `--max-results` values
3. **Time Windows**: Use `month` for better results than `week`
4. **Specific Queries**: More specific queries often return better results

---

## File Structure

```
youtube_most_popular/
├── yt_most_popular.py              # Main video analysis script
├── youtube_subscriptions.py        # OAuth-based subscriptions script
├── simple_subscriptions.py         # Simplified subscriptions script
├── top_channels.py                 # Channel ranking script
├── requirements.txt                # Python dependencies
├── README.md                       # Basic project documentation
├── oauth_setup_guide.md           # OAuth setup instructions
├── SCRIPTS_DOCUMENTATION.md       # This documentation file
├── .env                           # Environment variables (create this)
├── .cache/                        # Cache directory (auto-created)
└── client_secret_*.json           # OAuth credentials (download from Google)
```

---

## Examples

### Find Most Popular Gaming Videos This Month

```bash
python yt_most_popular.py --period month --query "gaming" --top 30 --csv gaming_videos.csv
```

### Get Most Liked Videos from Your Subscriptions

```bash
python youtube_subscriptions.py --period month --sort-by likes --top 25 --json my_favorites.json
```

### Find Top Music Channels

```bash
python top_channels.py --query "music" --top 50 --csv music_channels.csv --json music_channels.json
```

### Find Popular Podcasts

```bash
python yt_most_popular.py --period month --podcast --top 20 --md podcasts.md
```

This documentation covers all the scripts in your YouTube analytics project. Each script is designed to be robust, efficient, and user-friendly with comprehensive error handling and multiple output options.
