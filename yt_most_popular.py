#!/usr/bin/env python3
import argparse
import csv
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv
from requests import HTTPError, Response


YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

# YouTube API quota costs
SEARCH_QUOTA_COST = 100  # per search request
VIDEO_DETAILS_QUOTA_COST = 1  # per video details request
DAILY_QUOTA_LIMIT = 10000  # free tier limit
SAFETY_BUFFER = 500  # reserve some quota for safety

# Cache settings
CACHE_DIR = ".cache"
CACHE_EXPIRY_HOURS = 24  # Cache expires after 24 hours


def iso8601(dt: datetime) -> str:
	"""Return UTC ISO8601 string acceptable by YouTube API."""
	return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def compute_published_after(period: str) -> datetime:
	period = period.lower()
	if period == "week":
		return datetime.now(timezone.utc) - timedelta(days=7)
	if period == "month":
		return datetime.now(timezone.utc) - timedelta(days=30)
	raise ValueError("period must be 'week' or 'month'")


def batched(iterable: List[str], size: int) -> List[List[str]]:
	return [iterable[i : i + size] for i in range(0, len(iterable), size)]


def get_cache_key(params: Dict) -> str:
	"""Generate a cache key from API parameters."""
	# Remove timestamp-sensitive fields and create hash
	cache_params = {k: v for k, v in params.items() if k not in ['key', 'pageToken']}
	param_str = json.dumps(cache_params, sort_keys=True)
	return hashlib.md5(param_str.encode()).hexdigest()


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
		# Skip caching, make direct API request
		resp = requests.get(url, params=params, timeout=30)
		try:
			resp.raise_for_status()
		except HTTPError as e:
			message, reason = parse_api_error(resp)
			raise SystemExit(
				f"YouTube API error during {endpoint}: {message} (reason={reason}). "
				"Check API key validity, API enablement (YouTube Data API v3), and key restrictions."
			) from e
		return resp.json()
	
	cache_key = get_cache_key(params)
	cache_path = get_cache_path(cache_key, endpoint)
	
	# Try to load from cache first
	if is_cache_valid(cache_path):
		cached_data = load_from_cache(cache_path)
		if cached_data:
			print(f"Using cached data for {endpoint} (saved quota units)")
			if quota_tracker:
				quota_tracker["saved"] = quota_tracker.get("saved", 0) + 1
			return cached_data
	
	# Make API request
	resp = requests.get(url, params=params, timeout=30)
	try:
		resp.raise_for_status()
	except HTTPError as e:
		message, reason = parse_api_error(resp)
		raise SystemExit(
			f"YouTube API error during {endpoint}: {message} (reason={reason}). "
			"Check API key validity, API enablement (YouTube Data API v3), and key restrictions."
		) from e
	
	data = resp.json()
	
	# Save to cache
	save_to_cache(cache_path, data)
	
	return data


def search_videos(
	api_key: str,
	region_code: str,
	published_after: datetime,
	max_results: int,
	topic_id: Optional[str] = None,
	query: Optional[str] = None,
	quota_tracker: Optional[Dict[str, int]] = None,
	no_cache: bool = False,
) -> List[Dict]:
	"""Search for videos ordered by viewCount, published after a time.

	Returns a list of search items with id.videoId.
	"""
	url = f"{YOUTUBE_API_BASE}/search"
	params = {
		"key": api_key,
		"type": "video",
		"order": "date",  # Use 'date' instead of 'viewCount' for recent videos
		"publishedAfter": iso8601(published_after),
		"maxResults": 50,  # API max per page
		"regionCode": region_code,
		"q": query or "a|e|i|o|u",  # Broad search - most videos contain vowels
	}
	if topic_id:
		params["topicId"] = topic_id

	items: List[Dict] = []
	next_page_token: Optional[str] = None
	while True:
		if next_page_token:
			params["pageToken"] = next_page_token
		
		# Check quota before making request
		if quota_tracker:
			estimated_cost = SEARCH_QUOTA_COST
			if quota_tracker.get("used", 0) + estimated_cost > DAILY_QUOTA_LIMIT - SAFETY_BUFFER:
				print(f"Quota limit reached. Used: {quota_tracker.get('used', 0)}, "
				      f"would need: {estimated_cost}, limit: {DAILY_QUOTA_LIMIT - SAFETY_BUFFER}")
				break
		
		# Use cached API request
		data = cached_api_request(url, params, "search", quota_tracker, no_cache)
		
		# Track quota usage (only if not cached)
		if quota_tracker and not quota_tracker.get("saved", 0):
			quota_tracker["used"] = quota_tracker.get("used", 0) + SEARCH_QUOTA_COST
		items.extend(data.get("items", []))
		
		# Debug: Print search results info
		print(f"Search request returned {len(data.get('items', []))} items, total so far: {len(items)}")
		if not data.get("items"):
			print(f"Debug: Search response keys: {list(data.keys())}")
			if "error" in data:
				print(f"Debug: API error in response: {data['error']}")
		
		if len(items) >= max_results:
			return items[:max_results]
		next_page_token = data.get("nextPageToken")
		if not next_page_token:
			break
	return items


def fetch_video_stats(api_key: str, video_ids: List[str], quota_tracker: Optional[Dict[str, int]] = None, no_cache: bool = False) -> List[Dict]:
	"""Fetch snippet and statistics for given video IDs."""
	url = f"{YOUTUBE_API_BASE}/videos"
	results: List[Dict] = []
	for chunk in batched(video_ids, 50):
		# Check quota before making request
		if quota_tracker:
			estimated_cost = VIDEO_DETAILS_QUOTA_COST * len(chunk)
			if quota_tracker.get("used", 0) + estimated_cost > DAILY_QUOTA_LIMIT - SAFETY_BUFFER:
				print(f"Quota limit reached. Used: {quota_tracker.get('used', 0)}, "
				      f"would need: {estimated_cost}, limit: {DAILY_QUOTA_LIMIT - SAFETY_BUFFER}")
				break
		
		params = {
			"key": api_key,
			"id": ",".join(chunk),
			"part": "snippet,statistics,contentDetails",
			"maxResults": 50,
		}
		
		# Use cached API request
		payload = cached_api_request(url, params, "videos", quota_tracker, no_cache)
		
		# Track quota usage (only if not cached)
		if quota_tracker and not quota_tracker.get("saved", 0):
			quota_tracker["used"] = quota_tracker.get("used", 0) + VIDEO_DETAILS_QUOTA_COST * len(chunk)
		results.extend(payload.get("items", []))
	return results


def parse_api_error(resp: Response) -> Tuple[str, str]:
	"""Extract message and reason from a YouTube API error response."""
	try:
		payload = resp.json()
		message = payload.get("error", {}).get("message", str(resp.text))
		errors = payload.get("error", {}).get("errors", [])
		reason = errors[0].get("reason") if errors else payload.get("error", {}).get("status", "unknown")
		return message, reason or "unknown"
	except Exception:
		return f"HTTP {resp.status_code} {resp.reason}", "unknown"


def human_int(n: Optional[str]) -> int:
	try:
		return int(n) if n is not None else 0
	except Exception:
		return 0


def assemble_results(video_items: List[Dict], sort_by: str = "views") -> List[Dict]:
	assembled: List[Dict] = []
	seen_video_ids = set()  # Track seen video IDs to avoid duplicates
	
	for v in video_items:
		vid = v.get("id")
		if not vid or vid in seen_video_ids:
			continue  # Skip duplicates
		
		seen_video_ids.add(vid)
		snippet = v.get("snippet", {})
		stats = v.get("statistics", {})
		assembled.append(
			{
				"videoId": vid,
				"title": snippet.get("title", ""),
				"channelTitle": snippet.get("channelTitle", ""),
				"publishedAt": snippet.get("publishedAt", ""),
				"views": human_int(stats.get("viewCount")),
				"likes": human_int(stats.get("likeCount")),
				"comments": human_int(stats.get("commentCount")),
				"url": f"https://www.youtube.com/watch?v={vid}",
			}
		)
	
	# Sort by the specified metric
	sort_key = sort_by if sort_by in ["views", "likes", "comments"] else "views"
	return sorted(assembled, key=lambda x: x[sort_key], reverse=True)


def print_table(rows: List[Dict], limit: int, sort_by: str = "views") -> None:
	limit = min(limit, len(rows))
	metric_name = sort_by.title()
	print(f"Top {limit} videos by {metric_name}:")
	print("-" * 80)
	print(f"{metric_name:>12}  {'Title':.60}")
	print("-" * 80)
	for row in rows[:limit]:
		metric_value = row[sort_by]
		print(f"{metric_value:>12,d}  {row['title'][:60]}")
	print("-" * 80)


def write_csv(rows: List[Dict], path: str, limit: int) -> None:
	fieldnames = ["videoId", "title", "channelTitle", "publishedAt", "views", "likes", "comments", "url"]
	with open(path, "w", newline="", encoding="utf-8") as f:
		writer = csv.DictWriter(f, fieldnames=fieldnames)
		writer.writeheader()
		for row in rows[:limit]:
			writer.writerow(row)


def write_json(rows: List[Dict], path: str, limit: int) -> None:
	with open(path, "w", encoding="utf-8") as f:
		json.dump(rows[:limit], f, ensure_ascii=False, indent=2)


def write_markdown(rows: List[Dict], path: str, limit: int, sort_by: str = "views") -> None:
	with open(path, "w", encoding="utf-8") as f:
		metric_name = sort_by.title()
		f.write(f"# YouTube Most Popular Videos (by {metric_name})\n\n")
		f.write(f"Top {min(limit, len(rows))} videos by {metric_name}:\n\n")
		f.write(f"| Rank | {metric_name} | Title | Channel | Published |\n")
		f.write("|------|-------|-------|---------|-----------|\n")
		for i, row in enumerate(rows[:limit], 1):
			title = row['title'].replace('|', '\\|')[:60]
			channel = row['channelTitle'].replace('|', '\\|')[:30]
			published = row['publishedAt'][:10]
			metric_value = row[sort_by]
			f.write(f"| {i} | {metric_value:,} | [{title}]({row['url']}) | {channel} | {published} |\n")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description="Find most viewed YouTube videos published recently (week or month).",
	)
	parser.add_argument("--period", choices=["week", "month"], default=os.getenv("YT_PERIOD", "week"), help="Time window (env: YT_PERIOD)")
	parser.add_argument("--region", default=os.getenv("YT_REGION", "US"), help="Region code (env: YT_REGION)")
	parser.add_argument("--max-results", type=int, default=int(os.getenv("YT_MAX_RESULTS", "100")), help="Videos to fetch (env: YT_MAX_RESULTS)")
	parser.add_argument("--top", type=int, default=int(os.getenv("YT_TOP", "25")), help="Top results to show (env: YT_TOP)")
	parser.add_argument("--sort-by", choices=["views", "likes", "comments"], default=os.getenv("YT_SORT_BY", "views"), help="Sort results by metric (env: YT_SORT_BY)")
	parser.add_argument("--topic-id", default=os.getenv("YT_TOPIC_ID"), help="Topic ID (env: YT_TOPIC_ID)")
	parser.add_argument("--query", default=os.getenv("YT_QUERY"), help="Search query (env: YT_QUERY)")
	parser.add_argument("--podcast", action="store_true", help="Search for podcast content specifically")
	parser.add_argument("--published-after", default=os.getenv("YT_PUBLISHED_AFTER"), help="ISO8601 timestamp (env: YT_PUBLISHED_AFTER)")
	parser.add_argument("--api-key", default=os.getenv("YOUTUBE_API_KEY"), help="API key (env: YOUTUBE_API_KEY)")
	parser.add_argument("--csv", default=os.getenv("YT_CSV_PATH"), help="CSV path (env: YT_CSV_PATH)")
	parser.add_argument("--json", dest="json_out", default=os.getenv("YT_JSON_PATH"), help="JSON path (env: YT_JSON_PATH)")
	parser.add_argument("--md", default=os.getenv("YT_MD_PATH"), help="Markdown path (env: YT_MD_PATH)")
	parser.add_argument("--no-cache", action="store_true", help="Disable caching (force fresh API calls)")
	parser.add_argument("--clear-cache", action="store_true", help="Clear all cached data before running")
	return parser.parse_args(argv)


def get_api_key(cli_key: Optional[str]) -> str:
	key = cli_key or os.getenv("YOUTUBE_API_KEY")
	if not key:
		raise SystemExit("Missing API key. Provide --api-key or set YOUTUBE_API_KEY.")
	return key


def clear_cache() -> None:
	"""Clear all cached data."""
	if os.path.exists(CACHE_DIR):
		import shutil
		shutil.rmtree(CACHE_DIR)
		print("Cache cleared.")


def main(argv: Optional[List[str]] = None) -> int:
	# Load variables from a local .env file if present
	load_dotenv()
	args = parse_args(argv)
	api_key = get_api_key(args.api_key)

	# Clear cache if requested
	if args.clear_cache:
		clear_cache()

	# Initialize quota tracker
	quota_tracker = {"used": 0, "saved": 0}
	
	# Calculate estimated quota usage
	estimated_search_requests = (max(1, args.max_results) + 49) // 50  # round up
	estimated_search_cost = estimated_search_requests * SEARCH_QUOTA_COST
	estimated_video_cost = min(args.max_results, 200) * VIDEO_DETAILS_QUOTA_COST  # cap at reasonable limit
	total_estimated = estimated_search_cost + estimated_video_cost
	
	print(f"Estimated quota usage: {total_estimated} units (search: {estimated_search_cost}, videos: {estimated_video_cost})")
	print(f"Daily limit: {DAILY_QUOTA_LIMIT} units (safety buffer: {SAFETY_BUFFER})")
	
	if total_estimated > DAILY_QUOTA_LIMIT - SAFETY_BUFFER:
		print(f"WARNING: Estimated usage ({total_estimated}) exceeds safe limit ({DAILY_QUOTA_LIMIT - SAFETY_BUFFER})")
		print("Consider reducing --max-results or --top to stay within free tier.")
		response = input("Continue anyway? (y/N): ").strip().lower()
		if response != 'y':
			print("Aborted.")
			return 1

	if args.published_after:
		try:
			published_after_dt = datetime.fromisoformat(args.published_after.replace("Z", "+00:00")).astimezone(timezone.utc)
		except Exception:
			raise SystemExit("--published-after must be ISO8601, e.g. 2025-01-01T00:00:00Z")
	else:
		published_after_dt = compute_published_after(args.period)

	# Set up search parameters
	search_query = args.query
	if args.podcast:
		search_query = "podcast" if not search_query else f"{search_query} podcast"
	
	print(f"Searching for videos published after: {iso8601(published_after_dt)}")
	print(f"Region: {args.region}, Max results: {args.max_results}")
	if search_query:
		print(f"Search query: {search_query}")
	
	search_items = search_videos(
		api_key=api_key,
		region_code=args.region,
		published_after=published_after_dt,
		max_results=max(1, args.max_results),
		topic_id=args.topic_id,
		query=search_query,
		quota_tracker=quota_tracker,
		no_cache=args.no_cache,
	)
	
	print(f"Total search items found: {len(search_items)}")
	video_ids = [it.get("id", {}).get("videoId") for it in search_items if it.get("id", {}).get("videoId")]
	# Remove duplicates from video_ids
	unique_video_ids = list(dict.fromkeys(video_ids))  # Preserves order while removing duplicates
	print(f"Valid video IDs extracted: {len(video_ids)} (unique: {len(unique_video_ids)})")
	
	if not unique_video_ids:
		print("No videos found. This could be due to:")
		print("1. YouTube Data API v3 not enabled")
		print("2. API key restrictions")
		print("3. No videos in the specified time window/region")
		print("4. API quota exceeded")
		return 0

	video_items = fetch_video_stats(api_key, unique_video_ids, quota_tracker, args.no_cache)
	rows = assemble_results(video_items, args.sort_by)

	print(f"\nFinal quota usage: {quota_tracker['used']} units")
	if quota_tracker.get('saved', 0) > 0:
		print(f"Quota saved by caching: {quota_tracker['saved']} units")
	print_table(rows, args.top, args.sort_by)

	if args.csv:
		write_csv(rows, args.csv, args.top)
		print(f"Wrote CSV: {args.csv}")
	if args.json_out:
		write_json(rows, args.json_out, args.top)
		print(f"Wrote JSON: {args.json_out}")
	if args.md:
		write_markdown(rows, args.md, args.top, args.sort_by)
		print(f"Wrote Markdown: {args.md}")

	return 0


if __name__ == "__main__":
	sys.exit(main())


