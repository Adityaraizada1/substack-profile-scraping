# Substack Profile Scraper

A simple automation tool to scrape user profiles and social links from Substack's explore page.

## What It Does

1. Opens Substack's explore page
2. Scrolls to load more profiles
3. Opens each user profile
4. Gets their subscriber count and social media links
5. Saves everything to a CSV file

## Requirements

- Python 3.8+
- Playwright browser automation library

## Setup

### 1. Create a virtual environment (optional but recommended)

```bash
cd /Users/aadi/Documents/automated_testing
python -m venv venv
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install playwright
playwright install chromium
```

## How to Use

### Run the scraper

```bash
python substack_scraper.py
```

The browser will open automatically, scrape profiles, and save results to `substack_profiles.csv`.

## Configuration

Edit `scraper_config.ini` to customize the scraper:

### Scraper Settings

```ini
[scraper]
max_profiles = 200          # How many profiles to collect
scroll_times = 5            # How many times to scroll (more = more profiles)
max_subscribers = 30000     # Skip profiles with more subscribers than this
min_subscribers = 0         # Skip profiles with fewer subscribers than this
```

### Browser Settings

```ini
[browser]
headless = false            # true = no browser window (faster)
timeout_ms = 60000          # Page load timeout
page_wait_ms = 3000         # Wait after page loads
request_delay_ms = 3000     # Delay between requests (prevents rate limiting)
error_delay_ms = 10000      # Wait after errors
```

### Output Settings

```ini
[output]
format = csv                # csv or json
filename = substack_profiles
output_dir = /Users/aadi/Documents/automated_testing
```

### Filter Settings

```ini
[filters]
platforms =                 # Leave empty for all, or: twitter,instagram,tiktok
require_social_links = false  # true = only collect profiles with social links
```

## Output

The scraper creates `substack_profiles.csv` with these columns:

| Column | Description |
|--------|-------------|
| Username | Substack username |
| Profile URL | Link to their profile |
| Subscribers | Number of subscribers |
| Twitter | Twitter/X profile URL |
| Instagram | Instagram profile URL |
| TikTok | TikTok profile URL |
| LinkedIn | LinkedIn profile URL |
| Facebook | Facebook profile URL |
| YouTube | YouTube channel URL |
| Linktree | Linktree URL |
| Threads | Threads profile URL |
| Bluesky | Bluesky profile URL |
| GitHub | GitHub profile URL |
| Medium | Medium profile URL |
| Other | Other links |
| Scraped At | When the data was collected |

## Examples

### Scrape only small creators (under 5K subscribers)

```ini
max_subscribers = 5000
```

### Only get Twitter and Instagram links

```ini
platforms = twitter,instagram
```

### Run faster without browser window

```ini
headless = true
```

### Only collect profiles that have social links

```ini
require_social_links = true
```

## Troubleshooting

**Browser doesn't open?**
- Run `playwright install chromium` again

**Timeout errors?**
- Increase `timeout_ms` in config
- Check your internet connection

**No profiles found?**
- Increase `scroll_times` to load more content
