"""
Substack Profile Scraper
Automates scraping user profiles and social links from Substack leaderboard pages.
Filters by subscriber count and saves to CSV with proper rate limiting.

Features:
- Scrapes from multiple leaderboard URLs (configurable via leaderboard_urls.txt)
- Scrolls to load all ~100 profiles per leaderboard page
- Resume capability - skips already scraped profiles
- Crash recovery - reads existing CSV to avoid duplicates
- Live CSV updates as profiles are scraped
"""

import csv
import json
import time
import random
import configparser
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from playwright.sync_api import sync_playwright


def load_config(config_path: str = "scraper_config.ini") -> dict:
    """Load configuration from INI file."""
    config = configparser.ConfigParser()
    config.read(config_path)
    
    return {
        # Scraper settings
        "max_profiles": config.getint("scraper", "max_profiles", fallback=1000),
        "max_subscribers": config.getint("scraper", "max_subscribers", fallback=50000),
        "min_subscribers": config.getint("scraper", "min_subscribers", fallback=0),
        
        # Browser settings
        "headless": config.getboolean("browser", "headless", fallback=False),
        "timeout_ms": config.getint("browser", "timeout_ms", fallback=60000),
        "page_wait_ms": config.getint("browser", "page_wait_ms", fallback=3000),
        "scroll_wait_ms": config.getint("browser", "scroll_wait_ms", fallback=2000),
        "request_delay_ms": config.getint("browser", "request_delay_ms", fallback=3000),
        "error_delay_ms": config.getint("browser", "error_delay_ms", fallback=10000),
        
        # Output settings
        "format": config.get("output", "format", fallback="csv"),
        "filename": config.get("output", "filename", fallback="substack_profiles"),
        "output_dir": config.get("output", "output_dir", fallback="."),
        
        # Filter settings
        "platforms": [p.strip() for p in config.get("filters", "platforms", fallback="").split(",") if p.strip()],
        "require_social_links": config.getboolean("filters", "require_social_links", fallback=False),
        
        # Concurrent scraping settings
        "concurrent_profiles": config.getint("scraper", "concurrent_profiles", fallback=3),
    }


def load_leaderboard_urls(urls_file: str = "leaderboard_urls.txt") -> list:
    """Load leaderboard URLs from external file."""
    urls = []
    urls_path = Path(urls_file)
    
    if not urls_path.exists():
        print(f"⚠️  URLs file not found: {urls_file}")
        print("   Using default explore page instead")
        return ["https://substack.com/explore"]
    
    with open(urls_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if line and not line.startswith("#"):
                urls.append(line)
    
    print(f"📋 Loaded {len(urls)} leaderboard URLs from {urls_file}")
    return urls


# Category title mapping from URL slugs to display names
CATEGORY_TITLES = {
    "bestseller": "Bestseller",
    "culture": "Culture",
    "technology": "Technology",
    "business": "Business",
    "us-politics": "US Politics",
    "finance": "Finance",
    "food": "Food & Drink",
    "sports": "Sports",
    "art": "Art & Illustration",
    "world-politics": "World Politics",
    "health-politics": "Health & Politics",
    "explore": "Explore",
    "science": "Science",
    "music": "Music",
    "faith": "Faith & Spirituality",
    "climate": "Climate",
    "education": "Education",
    "history": "History",
    "parenting": "Parenting",
    "travel": "Travel",
}


def get_category_title(url_slug: str) -> str:
    """Convert URL category slug to proper display title."""
    return CATEGORY_TITLES.get(url_slug.lower(), url_slug.title())


def parse_subscriber_count(text: str) -> int:
    """Parse subscriber count from text like '276K+ subscribers' or '1.5M subscribers'."""
    if not text:
        return 0
    
    # Remove 'subscribers' and '+' and whitespace
    text = text.lower().replace("subscribers", "").replace("+", "").replace("see", "").strip()
    
    try:
        # Handle K (thousands) and M (millions)
        if "k" in text:
            num = float(text.replace("k", ""))
            return int(num * 1000)
        elif "m" in text:
            num = float(text.replace("m", ""))
            return int(num * 1000000)
        else:
            # Try to parse as regular number (with commas)
            return int(text.replace(",", ""))
    except ValueError:
        return 0


def add_random_delay(base_delay_ms: int, variance: float = 0.3):
    """Add a random delay to avoid detection. Variance is percentage of base delay."""
    min_delay = base_delay_ms * (1 - variance)
    max_delay = base_delay_ms * (1 + variance)
    delay_ms = random.uniform(min_delay, max_delay)
    delay_sec = delay_ms / 1000
    print(f"   ⏱️  Waiting {delay_sec:.1f}s before next request...")
    time.sleep(delay_sec)


def load_existing_profiles(config: dict) -> set:
    """Load existing profile usernames from CSV to avoid duplicates."""
    output_path = Path(config["output_dir"]) / f"{config['filename']}.csv"
    existing_usernames = set()
    
    if output_path.exists():
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                next(reader, None)  # Skip header
                for row in reader:
                    if row and len(row) > 0:
                        existing_usernames.add(row[0].lower())  # Username is first column
            print(f"📂 Found {len(existing_usernames)} existing profiles in CSV")
        except Exception as e:
            print(f"⚠️  Could not read existing CSV: {e}")
    
    return existing_usernames


def get_csv_header():
    """Return CSV header row."""
    return [
        "Username",
        "Profile URL", 
        "Subscribers",
        "Twitter",
        "Instagram",
        "TikTok",
        "LinkedIn",
        "Facebook",
        "YouTube",
        "Linktree",
        "Threads",
        "Bluesky",
        "GitHub",
        "Medium",
        "Other",
        "Scraped At",
        "Category"
    ]


def append_to_csv(profile: dict, config: dict):
    """Append a single profile to CSV file (for live updates)."""
    output_path = Path(config["output_dir"]) / f"{config['filename']}.csv"
    all_platforms = ["twitter", "instagram", "tiktok", "linkedin", "facebook", 
                     "youtube", "linktree", "threads", "bluesky", "github", "medium", "other"]
    
    file_exists = output_path.exists()
    
    with open(output_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        
        # Write header if file is new
        if not file_exists:
            writer.writerow(get_csv_header())
        
        # Write profile row
        row = [
            profile["username"],
            profile["profile_url"],
            profile["subscriber_count"],
        ]
        
        for platform in all_platforms:
            row.append(profile["social_links"].get(platform, ""))
        
        row.append(profile["scraped_at"])
        row.append(profile.get("category", ""))
        writer.writerow(row)


def scroll_and_collect_profiles(page, config: dict, existing_usernames: set, source_url: str) -> list:
    """
    Scroll the leaderboard page to load all profiles (usually ~100).
    Returns list of all unique profile URLs not already scraped.
    """
    all_profile_urls = set()
    no_new_count = 0
    max_no_new = 5  # Stop after 5 scrolls with no new profiles
    scroll_count = 0
    
    print(f"   📜 Scrolling to load all profiles...")
    
    while scroll_count < 50:  # Max 50 scrolls per page
        # Get current profile URLs
        profile_links = page.evaluate("""
            () => {
                const links = document.querySelectorAll('a[href*="/@"]');
                const uniqueUrls = new Set();
                links.forEach(link => {
                    const href = link.href;
                    if (href.includes('/@')) {
                        const match = href.match(/(https:\\/\\/substack\\.com\\/@[^/?]+)/);
                        if (match) {
                            uniqueUrls.add(match[1]);
                        }
                    }
                });
                return Array.from(uniqueUrls);
            }
        """)
        
        new_urls = set(profile_links) - all_profile_urls
        
        if new_urls:
            all_profile_urls.update(new_urls)
            no_new_count = 0
            print(f"      Scroll {scroll_count + 1}: +{len(new_urls)} profiles (total: {len(all_profile_urls)})")
        else:
            no_new_count += 1
            if no_new_count >= max_no_new:
                print(f"      ✅ Finished scrolling - found {len(all_profile_urls)} profiles")
                break
        
        # Scroll down
        page.evaluate("window.scrollBy(0, 800)")
        time.sleep(config["scroll_wait_ms"] / 1000)
        scroll_count += 1
    
    # Filter out already scraped profiles
    new_profile_urls = []
    for url in all_profile_urls:
        username = url.split("/@")[-1].lower()
        if username not in existing_usernames:
            new_profile_urls.append(url)
    
    skipped = len(all_profile_urls) - len(new_profile_urls)
    if skipped > 0:
        print(f"      ⏭️  Skipping {skipped} already scraped profiles")
    
    return new_profile_urls


def scrape_profile(context, profile_url: str, config: dict, source: str) -> dict | None:
    """Scrape a single profile and return profile data or None if skipped/error."""
    try:
        profile_page = context.new_page()
        profile_page.goto(profile_url, wait_until="domcontentloaded", timeout=config["timeout_ms"])
        time.sleep(config["page_wait_ms"] / 1000)
        
        # Check for rate limiting
        page_content = profile_page.content()
        if "too many requests" in page_content.lower() or "rate limit" in page_content.lower():
            print(f"   ⚠️  Rate limited! Waiting {config['error_delay_ms']/1000}s...")
            time.sleep(config["error_delay_ms"] / 1000)
            profile_page.close()
            return None
        
        # Extract subscriber count
        subscriber_text = profile_page.evaluate("""
            () => {
                const subLink = document.querySelector('a[href*="/subscribers"]');
                return subLink ? subLink.innerText : '';
            }
        """)
        
        subscriber_count = parse_subscriber_count(subscriber_text)
        print(f"   👥 Subscribers: {subscriber_text} (parsed: {subscriber_count:,})")
        
        # Check subscriber filters
        if config["max_subscribers"] > 0 and subscriber_count > config["max_subscribers"]:
            print(f"   ⏭️  SKIPPED: {subscriber_count:,} > {config['max_subscribers']:,} max")
            profile_page.close()
            return "skipped"
        
        if config["min_subscribers"] > 0 and subscriber_count < config["min_subscribers"]:
            print(f"   ⏭️  SKIPPED: {subscriber_count:,} < {config['min_subscribers']:,} min")
            profile_page.close()
            return "skipped"
        
        # Extract social links
        social_links = profile_page.evaluate("""
            () => {
                const buttons = document.querySelectorAll('button[data-href]');
                const socialLinks = {};
                const platformMap = {
                    'twitter.com': 'twitter',
                    'x.com': 'twitter',
                    'instagram.com': 'instagram',
                    'facebook.com': 'facebook',
                    'linkedin.com': 'linkedin',
                    'tiktok.com': 'tiktok',
                    'youtube.com': 'youtube',
                    'linktr.ee': 'linktree',
                    'threads.net': 'threads',
                    'bsky.app': 'bluesky',
                    'github.com': 'github',
                    'medium.com': 'medium'
                };
                
                buttons.forEach(btn => {
                    const href = btn.getAttribute('data-href');
                    if (href && href.startsWith('http') && !href.includes('substack.com')) {
                        const urlLower = href.toLowerCase();
                        let platform = 'other';
                        
                        for (const [domain, name] of Object.entries(platformMap)) {
                            if (urlLower.includes(domain)) {
                                platform = name;
                                break;
                            }
                        }
                        
                        if (!socialLinks[platform]) {
                            socialLinks[platform] = href;
                        }
                    }
                });
                return socialLinks;
            }
        """)
        
        # Filter by platforms if specified
        if config["platforms"]:
            social_links = {k: v for k, v in social_links.items() if k.lower() in [p.lower() for p in config["platforms"]]}
        
        # Check if we require social links
        if config["require_social_links"] and not social_links:
            print(f"   ⏭️  SKIPPED: No social links found")
            profile_page.close()
            return "skipped"
        
        profile_data = {
            "username": profile_url.split("/@")[-1],
            "profile_url": profile_url,
            "subscriber_count": subscriber_count,
            "social_links": social_links,
            "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "category": source
        }
        
        profile_page.close()
        return profile_data
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return None


def scrape_profile_batch(browser, profile_urls: list, config: dict, category: str, existing_usernames: set) -> tuple:
    """
    Scrape a batch of profiles concurrently using multiple browser pages.
    Returns tuple of (results, skipped_count, error_count, new_usernames)
    """
    results = []
    skipped_count = 0
    error_count = 0
    new_usernames = set()
    
    # Create separate contexts for each profile to enable parallel loading
    pages = []
    contexts = []
    
    try:
        # Open all pages concurrently
        print(f"   🚀 Opening {len(profile_urls)} profiles in parallel...")
        for profile_url in profile_urls:
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            contexts.append(context)
            pages.append((page, profile_url))
        
        # Navigate all pages at once (they load in parallel)
        for page, profile_url in pages:
            try:
                page.goto(profile_url, wait_until="domcontentloaded", timeout=config["timeout_ms"])
            except Exception as e:
                print(f"      ⚠️ Failed to load {profile_url.split('/@')[-1]}: {e}")
        
        # Wait for pages to load
        time.sleep(config["page_wait_ms"] / 1000)
        
        # Extract data from each page
        for page, profile_url in pages:
            username = profile_url.split("/@")[-1]
            
            if username.lower() in existing_usernames:
                continue
                
            try:
                # Check for rate limiting
                page_content = page.content()
                if "too many requests" in page_content.lower() or "rate limit" in page_content.lower():
                    print(f"      ⚠️ Rate limited on @{username}")
                    error_count += 1
                    continue
                
                # Extract subscriber count
                subscriber_text = page.evaluate("""
                    () => {
                        const subLink = document.querySelector('a[href*="/subscribers"]');
                        return subLink ? subLink.innerText : '';
                    }
                """)
                
                subscriber_count = parse_subscriber_count(subscriber_text)
                
                # Check subscriber filters
                if config["max_subscribers"] > 0 and subscriber_count > config["max_subscribers"]:
                    print(f"      ⏭️ @{username}: {subscriber_count:,} > max")
                    skipped_count += 1
                    continue
                
                if config["min_subscribers"] > 0 and subscriber_count < config["min_subscribers"]:
                    print(f"      ⏭️ @{username}: {subscriber_count:,} < min")
                    skipped_count += 1
                    continue
                
                # Extract social links
                social_links = page.evaluate("""
                    () => {
                        const buttons = document.querySelectorAll('button[data-href]');
                        const socialLinks = {};
                        const platformMap = {
                            'twitter.com': 'twitter', 'x.com': 'twitter',
                            'instagram.com': 'instagram', 'facebook.com': 'facebook',
                            'linkedin.com': 'linkedin', 'tiktok.com': 'tiktok',
                            'youtube.com': 'youtube', 'linktr.ee': 'linktree',
                            'threads.net': 'threads', 'bsky.app': 'bluesky',
                            'github.com': 'github', 'medium.com': 'medium'
                        };
                        
                        buttons.forEach(btn => {
                            const href = btn.getAttribute('data-href');
                            if (href && href.startsWith('http') && !href.includes('substack.com')) {
                                const urlLower = href.toLowerCase();
                                let platform = 'other';
                                for (const [domain, name] of Object.entries(platformMap)) {
                                    if (urlLower.includes(domain)) { platform = name; break; }
                                }
                                if (!socialLinks[platform]) { socialLinks[platform] = href; }
                            }
                        });
                        return socialLinks;
                    }
                """)
                
                # Filter by platforms if specified
                if config["platforms"]:
                    social_links = {k: v for k, v in social_links.items() if k.lower() in [p.lower() for p in config["platforms"]]}
                
                # Check if we require social links
                if config["require_social_links"] and not social_links:
                    skipped_count += 1
                    continue
                
                profile_data = {
                    "username": username,
                    "profile_url": profile_url,
                    "subscriber_count": subscriber_count,
                    "social_links": social_links,
                    "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "category": category
                }
                
                results.append(profile_data)
                new_usernames.add(username.lower())
                print(f"      ✅ @{username}: {subscriber_count:,} subs, {len(social_links)} links [{category}]")
                
            except Exception as e:
                print(f"      ❌ @{username}: {e}")
                error_count += 1
                
    finally:
        # Clean up all contexts
        for context in contexts:
            try:
                context.close()
            except:
                pass
    
    return results, skipped_count, error_count, new_usernames


def scrape_leaderboards(config: dict, urls: list):
    """
    Scrape profiles from multiple leaderboard pages with concurrent profile scraping.
    """
    results = []
    skipped_count = 0
    error_count = 0
    total_processed = 0
    
    # Batch size for concurrent scraping
    batch_size = config.get("concurrent_profiles", 5)
    
    # Load existing profiles to avoid duplicates
    existing_usernames = load_existing_profiles(config)
    
    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(headless=config["headless"])
        
        # Navigation context for leaderboard pages
        nav_context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        # Process each leaderboard URL
        for url_idx, leaderboard_url in enumerate(urls, 1):
            if total_processed >= config["max_profiles"]:
                print(f"\n✅ Reached max profiles limit ({config['max_profiles']})")
                break
            
            # Extract category name from URL and get proper title
            category_slug = leaderboard_url.split("/")[-2] if "/rising" in leaderboard_url else "explore"
            category = get_category_title(category_slug)
            
            print(f"\n{'='*60}")
            print(f"📊 [{url_idx}/{len(urls)}] CATEGORY: {category}")
            print(f"   URL: {leaderboard_url}")
            print("="*60)
            
            try:
                page = nav_context.new_page()
                page.goto(leaderboard_url, wait_until="domcontentloaded", timeout=config["timeout_ms"])
                time.sleep(config["page_wait_ms"] / 1000)
                
                # Scroll and collect all profile URLs
                profile_urls = scroll_and_collect_profiles(page, config, existing_usernames, leaderboard_url)
                page.close()
                
                print(f"\n   🔍 Found {len(profile_urls)} new profiles to scrape")
                print(f"   ⚡ Processing in batches of {batch_size} (concurrent)")
                
                # Process profiles in batches
                for batch_start in range(0, len(profile_urls), batch_size):
                    if total_processed >= config["max_profiles"]:
                        break
                    
                    batch_end = min(batch_start + batch_size, len(profile_urls))
                    batch_urls = profile_urls[batch_start:batch_end]
                    
                    print(f"\n   📦 Batch {batch_start//batch_size + 1}: profiles {batch_start+1}-{batch_end}")
                    
                    # Scrape batch concurrently
                    batch_results, batch_skipped, batch_errors, new_users = scrape_profile_batch(
                        browser, batch_urls, config, category, existing_usernames
                    )
                    
                    # Save results immediately
                    for result in batch_results:
                        append_to_csv(result, config)
                        results.append(result)
                        total_processed += 1
                    
                    existing_usernames.update(new_users)
                    skipped_count += batch_skipped
                    error_count += batch_errors
                    
                    # Small delay between batches to avoid rate limiting
                    if batch_end < len(profile_urls):
                        delay = config["request_delay_ms"] / 1000
                        print(f"   ⏱️ Waiting {delay:.1f}s before next batch...")
                        time.sleep(delay)
                
                # Delay between leaderboards
                if url_idx < len(urls):
                    print(f"\n   ⏱️ Waiting 3s before next category...")
                    time.sleep(3)
                    
            except Exception as e:
                print(f"   ❌ Error loading leaderboard: {e}")
                error_count += 1
                continue
        
        nav_context.close()
        browser.close()
    
    print(f"\n📊 Summary: Collected {len(results)}, Skipped {skipped_count}, Errors {error_count}")
    return results


def main():
    print("=" * 60)
    print("🚀 SUBSTACK LEADERBOARD SCRAPER")
    print("=" * 60)
    
    # Load configuration
    config_path = Path(__file__).parent / "scraper_config.ini"
    urls_path = Path(__file__).parent / "leaderboard_urls.txt"
    
    print(f"📁 Loading config from: {config_path}")
    config = load_config(str(config_path))
    
    # Load leaderboard URLs
    urls = load_leaderboard_urls(str(urls_path))
    
    # Print configuration
    print("\n⚙️  Configuration:")
    print(f"   Max profiles: {config['max_profiles']}")
    print(f"   Max subscribers: {config['max_subscribers']:,}")
    print(f"   Min subscribers: {config['min_subscribers']:,}")
    print(f"   Request delay: {config['request_delay_ms']}ms")
    print(f"   Headless: {config['headless']}")
    print(f"   Leaderboards to scrape: {len(urls)}")
    if config["platforms"]:
        print(f"   Platform filter: {', '.join(config['platforms'])}")
    
    # Run scraper
    results = scrape_leaderboards(config, urls)
    
    # Print final summary
    print("\n" + "=" * 60)
    print("📊 SCRAPING COMPLETE")
    print("=" * 60)
    
    if results:
        print(f"Total profiles collected: {len(results)}")
        
        # Count by source/category
        source_counts = {}
        for r in results:
            source = r.get('source', 'unknown')
            source_counts[source] = source_counts.get(source, 0) + 1
        
        print("\nProfiles by category:")
        for source, count in sorted(source_counts.items(), key=lambda x: -x[1]):
            print(f"   {source}: {count}")
        
        # Count social links by platform
        platform_counts = {}
        for r in results:
            for platform in r['social_links'].keys():
                platform_counts[platform] = platform_counts.get(platform, 0) + 1
        
        if platform_counts:
            print("\nSocial links by platform:")
            for platform, count in sorted(platform_counts.items(), key=lambda x: -x[1]):
                print(f"   {platform}: {count}")
        
        avg_subscribers = sum(r['subscriber_count'] for r in results) / len(results) if results else 0
        print(f"\nAverage subscriber count: {avg_subscribers:,.0f}")
    else:
        print("\n⚠️ No new profiles were scraped.")


if __name__ == "__main__":
    main()
