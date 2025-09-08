## YouTube Most Popular (Recent)

Find most-viewed YouTube videos published in the last week or month. Uses YouTube Data API v3.

### Prerequisites

- A YouTube Data API key. Create one in Google Cloud Console.
- Python 3.9+

### Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Either set the env var...
export YOUTUBE_API_KEY=YOUR_API_KEY_HERE

# ...or create a .env file in the project root:
echo "YOUTUBE_API_KEY=YOUR_API_KEY_HERE" > .env
```

### Usage

```bash
python yt_most_popular.py --period week --region US --top 25
```

Options:

- `--period`: `week` (default) or `month`
- `--region`: Region code like `US`, `GB`, `IN` (default: `US`)
- `--max-results`: How many videos to fetch before ranking (default: 100)
- `--top`: How many top results to display/output (default: 25)
- `--sort-by`: Sort by `views` (default), `likes`, or `comments`
- `--topic-id`: Optional Freebase topic ID to filter by topic
- `--query`: Custom search query (default: broad search)
- `--podcast`: Search specifically for podcast content
- `--published-after`: Override ISO8601 timestamp, e.g. `2025-01-01T00:00:00Z`
- `--api-key`: Provide API key via CLI instead of `YOUTUBE_API_KEY`
- `--csv`: Path to write CSV
- `--json`: Path to write JSON
- `--md`: Path to write Markdown
- `--no-cache`: Disable caching (force fresh API calls)
- `--clear-cache`: Clear all cached data before running

Examples:

```bash
# Top 25 videos by views published in the past week in US
python yt_most_popular.py --period week --region US --top 25

# Top 50 most liked videos in the past month
python yt_most_popular.py --period month --sort-by likes --top 50

# Top videos by comments in India, save to multiple formats
python yt_most_popular.py --period month --region IN --sort-by comments --top 50 \
  --csv top_comments.csv --json top_comments.json --md top_comments.md

# Most popular podcasts this month
python yt_most_popular.py --period month --podcast --top 25 --csv podcasts.csv

# Most liked podcasts in the past week
python yt_most_popular.py --period week --podcast --sort-by likes --top 20

# Explicit publishedAfter window
python yt_most_popular.py --published-after 2025-01-01T00:00:00Z --top 20
```

### Notes

- The script first searches for videos ordered by view count within the window, then fetches statistics and re-sorts by `viewCount` to ensure accuracy.
- **Quota protection**: The script tracks API usage and stops before exceeding the 10,000 daily free tier limit (with 500 unit safety buffer).
- **Caching**: API responses are cached for 24 hours to save quota on repeated runs. Use `--no-cache` to force fresh data.
- Environment variables are automatically loaded from a local `.env` file if present (via `python-dotenv`).

### Troubleshooting

- 403 Forbidden from YouTube API:
  - Ensure the YouTube Data API v3 is enabled for your project in Google Cloud.
  - Verify the API key is correct and unrestricted or properly restricted (HTTP referrers or IPs).
  - Check quota usage. Reduce `--max-results` or try later.
  - If the error shows `reason=keyInvalid`, recreate a key; for `quotaExceeded`, wait or request more quota.

- macOS urllib3 OpenSSL warning (LibreSSL):
  - This is a warning from urllib3 v2 on older LibreSSL. Consider using a newer Python (e.g., via `pyenv`) or ignore if requests still works.

