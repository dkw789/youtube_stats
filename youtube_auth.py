#!/usr/bin/env python3
"""
YouTube OAuth Session Manager
Shared authentication across all YouTube scripts.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import requests
from dotenv import load_dotenv

# OAuth settings
OAUTH_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
OAUTH_REDIRECT_URI = "http://localhost:8080"
GLOBAL_CACHE_DIR = os.path.expanduser("~/.youtube_scripts_cache")

class YouTubeAuth:
    def __init__(self):
        self.cache_dir = GLOBAL_CACHE_DIR
        os.makedirs(self.cache_dir, exist_ok=True)
    
    def get_credentials(self) -> Tuple[str, str]:
        """Get OAuth credentials from JSON file or environment."""
        load_dotenv()
        
        # Try JSON file first
        json_files = [f for f in os.listdir('.') if f.startswith('client_secret_') and f.endswith('.json')]
        if json_files:
            with open(json_files[0], 'r') as f:
                creds = json.load(f)
            client_data = creds.get("installed") or creds.get("web")
            return client_data["client_id"], client_data["client_secret"]
        
        # Fallback to env vars
        client_id = os.getenv("YOUTUBE_CLIENT_ID")
        client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")
        
        if not client_id or not client_secret:
            print("Missing OAuth credentials! Place client_secret_*.json file or set YOUTUBE_CLIENT_ID/YOUTUBE_CLIENT_SECRET")
            sys.exit(1)
        
        return client_id, client_secret
    
    def get_cached_token(self) -> Optional[str]:
        """Get cached access token if valid."""
        token_file = os.path.join(self.cache_dir, "access_token.json")
        if os.path.exists(token_file):
            try:
                with open(token_file, 'r') as f:
                    token_data = json.load(f)
                
                token_time = datetime.fromisoformat(token_data["timestamp"])
                if datetime.now(timezone.utc) - token_time < timedelta(minutes=55):
                    return token_data["access_token"]
            except (json.JSONDecodeError, KeyError, ValueError):
                pass
        return None
    
    def save_token(self, access_token: str):
        """Save access token to cache."""
        token_file = os.path.join(self.cache_dir, "access_token.json")
        with open(token_file, 'w') as f:
            json.dump({
                "access_token": access_token,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }, f)
    
    def get_auth_url(self, client_id: str) -> str:
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
    
    def exchange_code(self, client_id: str, client_secret: str, auth_code: str) -> str:
        """Exchange authorization code for access token."""
        response = requests.post("https://oauth2.googleapis.com/token", data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": auth_code,
            "grant_type": "authorization_code",
            "redirect_uri": OAUTH_REDIRECT_URI
        })
        response.raise_for_status()
        
        access_token = response.json()["access_token"]
        self.save_token(access_token)
        return access_token
    
    def get_token(self) -> str:
        """Get access token (cached or new via OAuth flow)."""
        # Check cache first
        cached_token = self.get_cached_token()
        if cached_token:
            print("✓ Using cached access token")
            return cached_token
        
        # Perform OAuth flow
        print("🔐 YouTube authentication required")
        client_id, client_secret = self.get_credentials()
        auth_url = self.get_auth_url(client_id)
        
        print(f"\n1. Visit: {auth_url}")
        print("\n2. Authorize the application")
        print("3. You'll be redirected to localhost:8080 - ERROR IS NORMAL!")
        print("4. Copy the 'code' from the URL (after code=)")
        print("   Example: http://localhost:8080/?code=4/XXXXX")
        print("   Copy: 4/XXXXX\n")
        
        auth_code = input("Paste authorization code: ").strip()
        if not auth_code:
            print("No code provided")
            sys.exit(1)
        
        try:
            access_token = self.exchange_code(client_id, client_secret, auth_code)
            print("✓ Authentication successful!")
            return access_token
        except requests.exceptions.HTTPError as e:
            print(f"OAuth error: {e}")
            sys.exit(1)
    
    def clear_session(self):
        """Clear cached authentication."""
        token_file = os.path.join(self.cache_dir, "access_token.json")
        if os.path.exists(token_file):
            os.remove(token_file)
            print("✓ Authentication session cleared")

# Global instance
auth = YouTubeAuth()

def get_youtube_token() -> str:
    """Get YouTube access token (main entry point)."""
    return auth.get_token()

def clear_youtube_session():
    """Clear YouTube authentication session."""
    auth.clear_session()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="YouTube Authentication Manager")
    parser.add_argument("--clear", action="store_true", help="Clear cached session")
    parser.add_argument("--test", action="store_true", help="Test authentication")
    
    args = parser.parse_args()
    
    if args.clear:
        clear_youtube_session()
    elif args.test:
        token = get_youtube_token()
        print(f"✓ Got token: {token[:20]}...")
    else:
        print("Usage: python youtube_auth.py --clear | --test")