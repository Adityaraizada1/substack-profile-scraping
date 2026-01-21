# Substack Profile Scraper

A fast automation tool to scrape user profiles and social links from Substack leaderboards with concurrent processing and live dashboard.

## Quick Start

```bash
./start.sh
```

This single command will:
1. Start the live dashboard server at http://localhost:8080
2. Open the dashboard in your browser
3. Run the scraper with concurrent batch processing
4. Save results to `substack_profiles.csv`

## Features

- ⚡ **Concurrent Scraping** - Processes up to 100 profiles in parallel
- 📊 **Live Dashboard** - Real-time updates at http://localhost:8080
- 🏷️ **Category Labels** - Profiles organized by category (Technology, Culture, etc.)
- 🔄 **Resume Support** - Skips already scraped profiles on restart
- 📁 **Multiple Leaderboards** - Scrapes from 11 category pages

## Setup

### 1. Create virtual environment

```bash
python -m venv venv
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install playwright
playwright install chromium
```

### 3. Run

```bash
./start.sh
```

Or run components separately:

```bash
# Terminal 1: Start dashboard
python3 live_server.py

# Terminal 2: Run scraper
source venv/bin/activate && python substack_scraper.py
```

## Configuration

Edit `scraper_config.ini`:

```ini
[scraper]
max_profiles = 200          # Total profiles to collect
concurrent_profiles = 100   # Profiles to scrape in parallel (speed)
max_subscribers = 0         # 0 = unlimited
min_subscribers = 1000      # Skip small accounts

[browser]
headless = true             # true = faster (no browser window)
request_delay_ms = 1500     # Delay between batches
```

## Leaderboard URLs

Edit `leaderboard_urls.txt` to add/remove categories:

```
https://substack.com/leaderboard/technology/rising
https://substack.com/leaderboard/culture/rising
https://substack.com/leaderboard/business/rising
# Add more URLs here...
```

## Output

`substack_profiles.csv` contains:

| Column | Description |
|--------|-------------|
| Username | Substack username |
| Profile URL | Link to profile |
| Subscribers | Subscriber count |
| Twitter, Instagram, etc. | Social media links |
| Category | Leaderboard category |

## Live Dashboard

Open http://localhost:8080 to see:
- Profile cards with category badges
- Filter by status (Accepted/Rejected)
- Filter by category dropdown
- Search by username
- Auto-refresh every 3 seconds

## Troubleshooting

**Port 8080 in use?**
```bash
lsof -ti:8080 | xargs kill -9
```

**Browser doesn't open?**
```bash
playwright install chromium
```

