# YouTube Subscriptions OAuth Setup Guide

This guide will help you set up OAuth credentials to access your YouTube subscriptions.

## Step 1: Google Cloud Console Setup

1. **Go to Google Cloud Console**
   - Visit: https://console.cloud.google.com/

2. **Create or Select a Project**
   - Click on the project dropdown at the top
   - Create a new project or select an existing one

3. **Enable YouTube Data API v3**
   - Go to "APIs & Services" → "Library"
   - Search for "YouTube Data API v3"
   - Click on it and press "Enable"

## Step 2: Create OAuth Credentials

1. **Go to Credentials**
   - Navigate to "APIs & Services" → "Credentials"

2. **Create OAuth 2.0 Client ID**
   - Click "Create Credentials" → "OAuth 2.0 Client ID"
   - If prompted, configure the OAuth consent screen first:
     - Choose "External" user type
     - Fill in required fields (App name, User support email, Developer contact)
     - Add your email to test users

3. **Configure OAuth Client**
   - Choose "Desktop application" as the application type
   - Name it something like "YouTube Subscriptions Tool"
   - Click "Create"

4. **Add Redirect URI**
   - In the OAuth client settings, add this redirect URI:
   - `http://localhost:8080`
   - Save the changes

## Step 3: Get Your Credentials

**Method 1: JSON File (Recommended)**
1. **Download the JSON file**
   - From the OAuth client page, click the download button (⬇️)
   - Save the file in your project directory
   - The file will be named something like `client_secret_552912779614-xxxxx.apps.googleusercontent.com.json`

**Method 2: Manual Setup**
1. **Copy Client ID and Client Secret**
   - From the OAuth client page, copy:
     - Client ID
     - Client Secret

2. **Add to .env file**
   - Create or edit your `.env` file in the project directory
   - Add these lines:
   ```
   YOUTUBE_CLIENT_ID=your_client_id_here
   YOUTUBE_CLIENT_SECRET=your_client_secret_here
   ```

## Step 4: Run the Script

```bash
# Install dependencies (if not already done)
pip install -r requirements.txt

# Run the subscriptions script
python youtube_subscriptions.py --period month --top 25

# Or with more options
python youtube_subscriptions.py --period week --sort-by likes --top 30 --json my_subscriptions.json
```

## Step 5: Authorization Process

1. **Script opens browser** (or you can open manually)
2. **Sign in to Google** with your YouTube account
3. **Grant permissions** to the application
4. **Copy authorization code** from the redirect URL
5. **Paste code** into the terminal

## Available Options

- `--period`: `week` or `month` (default: month)
- `--top`: Number of top results to show (default: 25)
- `--sort-by`: Sort by `views`, `likes`, or `comments` (default: views)
- `--max-subscriptions`: Max subscriptions to check (default: 50)
- `--videos-per-channel`: Max videos per channel (default: 10)
- `--json`: Save results to JSON file
- `--no-browser`: Don't open browser automatically

## Example Commands

```bash
# Most viewed videos from subscriptions this month
python youtube_subscriptions.py --period month --top 25

# Most liked videos from subscriptions this week
python youtube_subscriptions.py --period week --sort-by likes --top 20

# Save results to JSON
python youtube_subscriptions.py --period month --top 50 --json subscriptions_results.json

# Check more subscriptions and videos per channel
python youtube_subscriptions.py --period month --max-subscriptions 100 --videos-per-channel 20 --top 30
```

## Troubleshooting

**"Access blocked" error:**
- Make sure you added your email to test users in OAuth consent screen
- The app might need verification for production use

**"Invalid client" error:**
- Check that Client ID and Client Secret are correct in .env file
- Ensure redirect URI is exactly `http://localhost:8080`

**"Quota exceeded" error:**
- Reduce `--max-subscriptions` or `--videos-per-channel`
- Wait for quota reset (daily)

**No videos found:**
- Try a longer time period (month instead of week)
- Increase `--videos-per-channel`
- Check if your subscriptions have recent videos
