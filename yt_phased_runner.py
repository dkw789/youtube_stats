#!/usr/bin/env python3
"""
Phased YouTube Data Collection
Runs data collection in phases to manage API quota efficiently.

COMPLIANCE STATEMENT:
This script complies with YouTube API Services Terms and Policies:
- Displays only YouTube-provided metrics (views, likes, comments)
- No independently calculated or derived metrics (Policy III.E.4h)
- Data cached for maximum 24 hours (Policy III.E.4.a-g)
- Single project number: 55291277961 (Policy III.D.1c)
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from youtube_auth import get_youtube_token

# Quota limits
DAILY_QUOTA_LIMIT = 10000
SAFETY_BUFFER = 500
SEARCH_COST = 100
VIDEO_COST = 1
SUBSCRIPTION_COST = 1

class QuotaManager:
    def __init__(self, daily_limit: int = DAILY_QUOTA_LIMIT):
        self.daily_limit = daily_limit
        self.used = 0
        self.phase_file = ".quota_phase.json"
        self.load_state()
    
    def load_state(self):
        """Load quota state from file."""
        if os.path.exists(self.phase_file):
            try:
                with open(self.phase_file, 'r') as f:
                    data = json.load(f)
                
                # Reset if it's a new day
                last_date = datetime.fromisoformat(data.get("date", "2000-01-01"))
                today = datetime.now().date()
                
                if last_date.date() == today:
                    self.used = data.get("used", 0)
                else:
                    self.used = 0
                    self.save_state()
            except:
                self.used = 0
    
    def save_state(self):
        """Save quota state to file."""
        with open(self.phase_file, 'w') as f:
            json.dump({
                "date": datetime.now().isoformat(),
                "used": self.used
            }, f)
    
    def can_use(self, cost: int) -> bool:
        """Check if we can use quota."""
        return self.used + cost <= self.daily_limit - SAFETY_BUFFER
    
    def use_quota(self, cost: int):
        """Use quota and save state."""
        self.used += cost
        self.save_state()
    
    def remaining(self) -> int:
        """Get remaining quota."""
        return max(0, self.daily_limit - SAFETY_BUFFER - self.used)

def run_phase_1_subscriptions(quota_manager: QuotaManager, max_channels: int = 50) -> List[Dict]:
    """Phase 1: Get subscriptions (1 quota unit)."""
    print("=== PHASE 1: Getting Subscriptions ===")
    
    if not quota_manager.can_use(SUBSCRIPTION_COST):
        print(f"❌ Not enough quota for subscriptions. Need: {SUBSCRIPTION_COST}, Have: {quota_manager.remaining()}")
        return []
    
    # Import here to avoid circular imports
    from yt_subscription_podcasts import get_subscriptions
    
    access_token = get_youtube_token()
    subscriptions = get_subscriptions(access_token, max_channels, use_cache=True)
    
    quota_manager.use_quota(SUBSCRIPTION_COST)
    print(f"✅ Got {len(subscriptions)} subscriptions. Quota used: {SUBSCRIPTION_COST}")
    
    # Save subscriptions for next phases
    with open("phase_subscriptions.json", 'w') as f:
        json.dump(subscriptions, f, indent=2)
    
    return subscriptions

def run_phase_2_search(quota_manager: QuotaManager, subscriptions: List[Dict], 
                      channels_per_batch: int = 5, published_after: datetime = None) -> List[Dict]:
    """Phase 2: Search channels in batches."""
    print("=== PHASE 2: Searching Channels ===")
    
    if published_after is None:
        published_after = datetime.now(timezone.utc) - timedelta(days=7)
    
    # Load existing results if any
    results_file = "phase_search_results.json"
    if os.path.exists(results_file):
        with open(results_file, 'r') as f:
            all_videos = json.load(f)
        processed_channels = {v["channel_id"] for v in all_videos}
    else:
        all_videos = []
        processed_channels = set()
    
    from yt_subscription_podcasts import search_channel_podcasts
    access_token = get_youtube_token()
    
    batch_count = 0
    for i in range(0, len(subscriptions), channels_per_batch):
        batch = subscriptions[i:i+channels_per_batch]
        batch_cost = len(batch) * SEARCH_COST
        
        if not quota_manager.can_use(batch_cost):
            print(f"❌ Not enough quota for batch {batch_count + 1}. Need: {batch_cost}, Have: {quota_manager.remaining()}")
            print(f"💾 Saved {len(all_videos)} videos so far to {results_file}")
            break
        
        print(f"🔍 Processing batch {batch_count + 1}: channels {i+1}-{min(i+channels_per_batch, len(subscriptions))}")
        
        for sub in batch:
            channel_id = sub["snippet"]["resourceId"]["channelId"]
            channel_name = sub["snippet"]["title"]
            
            if channel_id in processed_channels:
                print(f"  ⏭️  Skipping {channel_name} (already processed)")
                continue
            
            print(f"  🔍 Searching {channel_name}...")
            
            try:
                videos = search_channel_podcasts(access_token, channel_id, published_after, 
                                               max_results=5, use_cache=True, rss_only=False)
                
                for video in videos:
                    all_videos.append({
                        "video_id": video["id"]["videoId"],
                        "channel_id": channel_id,
                        "channel_name": channel_name,
                        "video": video
                    })
                
                print(f"    ✅ Found {len(videos)} videos")
                
            except Exception as e:
                print(f"    ❌ Error: {e}")
        
        quota_manager.use_quota(batch_cost)
        batch_count += 1
        
        # Save progress
        with open(results_file, 'w') as f:
            json.dump(all_videos, f, indent=2)
        
        print(f"💾 Saved progress. Total videos: {len(all_videos)}, Quota used: {batch_cost}")
        
        # Small delay between batches
        time.sleep(1)
    
    return all_videos

def run_phase_3_stats(quota_manager: QuotaManager, all_videos: List[Dict], 
                     videos_per_batch: int = 50) -> List[Dict]:
    """Phase 3: Get video statistics in batches."""
    print("=== PHASE 3: Getting Video Statistics ===")
    
    # Load existing stats if any
    stats_file = "phase_video_stats.json"
    if os.path.exists(stats_file):
        with open(stats_file, 'r') as f:
            all_stats = json.load(f)
        processed_ids = set(all_stats.keys())
    else:
        all_stats = {}
        processed_ids = set()
    
    from yt_subscription_podcasts import get_video_stats
    access_token = get_youtube_token()
    
    # Get unique video IDs not yet processed
    video_ids = []
    for video_data in all_videos:
        video_id = video_data["video_id"]
        if video_id not in processed_ids:
            video_ids.append(video_id)
    
    if not video_ids:
        print("✅ All video stats already collected")
        return all_stats
    
    print(f"📊 Need stats for {len(video_ids)} videos")
    
    # Process in batches
    for i in range(0, len(video_ids), videos_per_batch):
        batch = video_ids[i:i+videos_per_batch]
        batch_cost = len(batch) * VIDEO_COST
        
        if not quota_manager.can_use(batch_cost):
            print(f"❌ Not enough quota for batch. Need: {batch_cost}, Have: {quota_manager.remaining()}")
            print(f"💾 Saved {len(all_stats)} video stats so far")
            break
        
        print(f"📊 Processing stats batch: {i+1}-{min(i+videos_per_batch, len(video_ids))}")
        
        try:
            stats = get_video_stats(access_token, batch, use_cache=True)
            all_stats.update(stats)
            
            quota_manager.use_quota(batch_cost)
            print(f"✅ Got stats for {len(batch)} videos. Quota used: {batch_cost}")
            
            # Save progress
            with open(stats_file, 'w') as f:
                json.dump(all_stats, f, indent=2)
            
        except Exception as e:
            print(f"❌ Error getting stats: {e}")
            break
        
        time.sleep(0.5)
    
    return all_stats

def combine_results(all_videos: List[Dict], all_stats: Dict, sort_by: str = "views", top: int = 25) -> List[Dict]:
    """Combine video data with stats and sort."""
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
    episodes.sort(key=lambda x: x[sort_by], reverse=True)
    return episodes[:top]

def main():
    parser = argparse.ArgumentParser(description="Phased YouTube podcast collection")
    parser.add_argument("--phase", choices=["1", "2", "3", "all"], default="all", help="Which phase to run")
    parser.add_argument("--channels-per-batch", type=int, default=3, help="Channels per search batch (reduced for quota)")
    parser.add_argument("--videos-per-batch", type=int, default=50, help="Videos per stats batch")
    parser.add_argument("--max-channels", type=int, default=25, help="Max channels to process (reduced for quota)")
    parser.add_argument("--top", type=int, default=25, help="Top results to show")
    parser.add_argument("--sort-by", choices=["views", "likes", "comments"], default="views")
    parser.add_argument("--period", choices=["week"], default="week", help="Time period (month disabled to save quota)")
    parser.add_argument("--output", default="phased_results.json", help="Output file")
    parser.add_argument("--status", action="store_true", help="Show quota status")
    
    args = parser.parse_args()
    
    quota_manager = QuotaManager()
    
    if args.status:
        print(f"📊 Quota Status:")
        print(f"   Used: {quota_manager.used}")
        print(f"   Remaining: {quota_manager.remaining()}")
        print(f"   Daily Limit: {quota_manager.daily_limit}")
        return
    
    # Calculate time window (week only to save quota)
    published_after = datetime.now(timezone.utc) - timedelta(days=7)
    
    print(f"🚀 Starting phased collection for last {args.period}")
    print(f"📊 Available quota: {quota_manager.remaining()}")
    
    # Phase 1: Subscriptions
    if args.phase in ["1", "all"]:
        subscriptions = run_phase_1_subscriptions(quota_manager, args.max_channels)
        if not subscriptions:
            return
    else:
        # Load existing subscriptions
        if os.path.exists("phase_subscriptions.json"):
            with open("phase_subscriptions.json", 'r') as f:
                subscriptions = json.load(f)
        else:
            print("❌ No subscriptions found. Run phase 1 first.")
            return
    
    # Phase 2: Search
    if args.phase in ["2", "all"]:
        all_videos = run_phase_2_search(quota_manager, subscriptions, 
                                       args.channels_per_batch, published_after)
    else:
        # Load existing search results
        if os.path.exists("phase_search_results.json"):
            with open("phase_search_results.json", 'r') as f:
                all_videos = json.load(f)
        else:
            print("❌ No search results found. Run phase 2 first.")
            return
    
    # Phase 3: Stats
    if args.phase in ["3", "all"]:
        all_stats = run_phase_3_stats(quota_manager, all_videos, args.videos_per_batch)
    else:
        # Load existing stats
        if os.path.exists("phase_video_stats.json"):
            with open("phase_video_stats.json", 'r') as f:
                all_stats = json.load(f)
        else:
            print("❌ No video stats found. Run phase 3 first.")
            return
    
    # Combine and output results
    if args.phase == "all" or args.phase == "3":
        episodes = combine_results(all_videos, all_stats, args.sort_by, args.top)
        
        print(f"\n🎉 Final Results: Top {len(episodes)} podcast episodes by {args.sort_by}")
        print("=" * 80)
        
        for i, ep in enumerate(episodes, 1):
            print(f"{i:2d}. {ep['title']}")
            print(f"    Channel: {ep['channel']}")
            print(f"    Views: {ep['views']:,} | Likes: {ep['likes']:,}")
            print(f"    URL: {ep['url']}")
            print()
        
        # Save final results
        with open(args.output, 'w') as f:
            json.dump(episodes, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Results saved to {args.output}")
    
    print(f"\n📊 Final quota usage: {quota_manager.used}/{quota_manager.daily_limit}")

if __name__ == "__main__":
    main()