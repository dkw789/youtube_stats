#!/usr/bin/env python3
"""
YouTube OAuth Session Manager
Shared authentication across all YouTube scripts.

COMPLIANCE STATEMENT:
This module complies with YouTube API Services Terms and Policies:
- Single project authentication (Policy III.D.1c)
- Token caching for 55 minutes maximum
- Project Number: 55291277961
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import requests
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

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
        """Get cached access token if valid and not expired."""
        token_file = os.path.join(self.cache_dir, "access_token.json")
        if os.path.exists(token_file):
            try:
                with open(token_file, 'r') as f:
                    token_data = json.load(f)
                
                # Check if token has expired
                now = datetime.now(timezone.utc)
                if "expires_at" in token_data:
                    expires_at = datetime.fromisoformat(token_data["expires_at"])
                    if now < expires_at:
                        return token_data["access_token"]
                    return None
                
                # Fallback to old timestamp-based check (for backward compatibility)
                token_time = datetime.fromisoformat(token_data["timestamp"])
                if now - token_time < timedelta(minutes=55):
                    return token_data["access_token"]
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.debug(f"Error reading token cache: {e}")
        return None
    
    def save_token(self, access_token: str, expires_in: int = 3600):
        """Save access token to cache with expiration.
        
        Args:
            access_token: The OAuth access token
            expires_in: Time in seconds until token expires (default: 1 hour)
        """
        token_file = os.path.join(self.cache_dir, "access_token.json")
        now = datetime.now(timezone.utc)
        with open(token_file, 'w') as f:
            json.dump({
                "access_token": access_token,
                "timestamp": now.isoformat(),
                "expires_at": (now + timedelta(seconds=expires_in - 300)).isoformat()  # 5 min buffer
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
        
        token_data = response.json()
        access_token = token_data["access_token"]
        expires_in = int(token_data.get("expires_in", 3600))  # Default to 1 hour if not provided
        self.save_token(access_token, expires_in)
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
    
    def clear_session(self):
        """Clear cached authentication."""
        token_file = os.path.join(self.cache_dir, "access_token.json")
        if os.path.exists(token_file):
            os.remove(token_file)
            print("✓ Authentication session cleared")

    def run_local_server(self) -> str:
        """Automate OAuth via local server (preferred when GUI is available)."""
        load_dotenv()
        creds_path = self._resolve_client_secret_file()
        flow = InstalledAppFlow.from_client_secrets_file(
            os.path.abspath(creds_path),
            scopes=[OAUTH_SCOPE],
            redirect_uri=OAUTH_REDIRECT_URI,
        )
        creds = flow.run_local_server(host="localhost", port=8080)
        token = creds.token
        # Get the token's expiration time (default to 1 hour if not provided)
        expires_in = (creds.expiry - datetime.now(timezone.utc)).total_seconds() if creds.expiry else 3600
        self.save_token(token, int(expires_in))
        return token

    def _resolve_client_secret_file(self) -> str:
        """Locate client_secret JSON file for automated OAuth."""
        candidates = [f for f in os.listdir('.') if f.startswith('client_secret_') and f.endswith('.json')]
        if candidates:
            return candidates[0]
        explicit = os.getenv("YOUTUBE_CLIENT_SECRET_FILE")
        if explicit and os.path.exists(explicit):
            return explicit
        raise FileNotFoundError(
            "No client_secret JSON file found. Place client_secret_*.json in project or set YOUTUBE_CLIENT_SECRET_FILE."
        )

# Global instance
auth = YouTubeAuth()

def get_youtube_token() -> str:
    """Get YouTube access token (main entry point)."""
    return auth.get_token()

def get_youtube_token_auto() -> str:
    """Get YouTube access token using automated local-server flow."""
    return auth.run_local_server()

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