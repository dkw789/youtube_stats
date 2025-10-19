import os
import logging


# You need: pip install google-auth-oauthlib google-api-python-client
try:
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
except Exception:
    InstalledAppFlow = None
    build = None

API_KEY = os.getenv('YOUTUBE_API_KEY', 'YOUR_API_KEY')  # set env var YOUTUBE_API_KEY
VIDEO_ID = os.getenv('YOUTUBE_VIDEO_ID', 'VIDEO_ID_HERE')  # or set YOUTUBE_VIDEO_ID

# REMOVED: compute_engagement_rate() - violates YouTube API Policy III.E.4h(iii)
