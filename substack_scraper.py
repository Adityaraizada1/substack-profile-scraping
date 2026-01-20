"""
Substack Profile Scraper
Automates scraping user profiles and social links from Substack explore page.
Filters by subscriber count and saves to CSV with proper rate limiting.
"""

import csv
import json
import time
import random
import configparser
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright


def load_config(config_path: str = "scraper_config.ini") -> dict:
    """Load configuration from INI file."""
    config = configparser.ConfigParser()
    config.read(config_path)
    
    return {
        # Scraper settings
        "max_profiles": config.getint("scraper", "max_profiles", fallback=50),
        "scroll_times": config.getint("scraper", "scroll_times", fallback=5),
        "max_subscribers": config.getint("scraper", "max_subscribers", fallback=20000),
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
    }


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


def scrape_substack_profiles(config: dict):
    """
    Scrape user profiles and their social links from Substack explore page.
    """
    results = []
    skipped_count = 0
    error_count = 0
    
    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(headless=config["headless"])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        # Main page for explore
        page = context.new_page()
        
        print("🌐 Navigating to Substack explore page...")
        page.goto("https://substack.com/explore", wait_until="domcontentloaded", timeout=config["timeout_ms"])
        time.sleep(config["page_wait_ms"] / 1000)
        
        # Scroll to load more profiles
        print(f"📜 Scrolling page {config['scroll_times']} times to load more profiles...")
        for i in range(config["scroll_times"]):
            page.evaluate("window.scrollBy(0, 1000)")
            time.sleep(config["scroll_wait_ms"] / 1000)
            print(f"   Scroll {i + 1}/{config['scroll_times']}")
        
        # Scroll back to top
        page.evaluate("window.scrollTo(0, 0)")
        time.sleep(1)
        
        # Find all profile links
        print("🔍 Finding user profile links...")
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
        
        print(f"✅ Found {len(profile_links)} unique profile URLs")
        
        # Process each profile
        processed = 0
        for idx, profile_url in enumerate(profile_links, 1):
            if processed >= config["max_profiles"]:
                print(f"\n✅ Reached max profiles limit ({config['max_profiles']})")
                break
                
            print(f"\n👤 [{idx}/{len(profile_links)}] Processing: {profile_url}")
            
            try:
                # Add delay between requests to avoid rate limiting
                if idx > 1:
                    add_random_delay(config["request_delay_ms"])
                
                # Open profile in new tab
                profile_page = context.new_page()
                profile_page.goto(profile_url, wait_until="domcontentloaded", timeout=config["timeout_ms"])
                time.sleep(config["page_wait_ms"] / 1000)
                
                # Check for rate limiting or error page
                page_content = profile_page.content()
                if "too many requests" in page_content.lower() or "rate limit" in page_content.lower():
                    print(f"   ⚠️  Rate limited! Waiting {config['error_delay_ms']/1000}s...")
                    time.sleep(config["error_delay_ms"] / 1000)
                    profile_page.close()
                    error_count += 1
                    continue
                
                # Extract subscriber count
                subscriber_text = profile_page.evaluate("""
                    () => {
                        const subLink = document.querySelector('a[href*="/subscribers"]');
                        return subLink ? subLink.innerText : '';
                    }
                """)
                
                subscriber_count = parse_subscriber_count(subscriber_text)
                print(f"   👥 Subscribers: {subscriber_text} (parsed: {subscriber_count:,})")
                
                # Check subscriber filter
                if config["max_subscribers"] > 0 and subscriber_count > config["max_subscribers"]:
                    print(f"   ⏭️  SKIPPED: {subscriber_count:,} > {config['max_subscribers']:,} max")
                    skipped_count += 1
                    profile_page.close()
                    continue
                
                if config["min_subscribers"] > 0 and subscriber_count < config["min_subscribers"]:
                    print(f"   ⏭️  SKIPPED: {subscriber_count:,} < {config['min_subscribers']:,} min")
                    skipped_count += 1
                    profile_page.close()
                    continue
                
                # Extract social links from data-href attributes
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
                                
                                // Store by platform name (only keep first of each platform)
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
                    skipped_count += 1
                    profile_page.close()
                    continue
                
                # Extract username from URL
                username = profile_url.split("/@")[-1]
                
                profile_data = {
                    "username": username,
                    "profile_url": profile_url,
                    "subscriber_count": subscriber_count,
                    "subscriber_text": subscriber_text.strip(),
                    "social_links": social_links,
                    "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                
                results.append(profile_data)
                processed += 1
                
                print(f"   ✅ COLLECTED: {len(social_links)} social link(s)")
                for platform, url in social_links.items():
                    print(f"      - {platform}: {url}")
                
                profile_page.close()
                
            except Exception as e:
                print(f"   ❌ Error: {e}")
                print(f"   ⏱️  Waiting {config['error_delay_ms']/1000}s after error...")
                time.sleep(config["error_delay_ms"] / 1000)
                error_count += 1
                continue
        
        browser.close()
    
    print(f"\n📊 Summary: Collected {len(results)}, Skipped {skipped_count}, Errors {error_count}")
    return results


def save_to_csv(results: list, config: dict) -> str:
    """Save results to CSV file with proper platform columns."""
    output_path = Path(config["output_dir"]) / f"{config['filename']}.csv"
    
    # Define all possible platform columns
    all_platforms = ["twitter", "instagram", "tiktok", "linkedin", "facebook", 
                     "youtube", "linktree", "threads", "bluesky", "github", "medium", "other"]
    
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        
        # Header with proper platform names
        header = [
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
            "Scraped At"
        ]
        writer.writerow(header)
        
        # Data rows
        for profile in results:
            row = [
                profile["username"],
                profile["profile_url"],
                profile["subscriber_count"],
            ]
            
            # Add each platform's URL (empty string if not found)
            for platform in all_platforms:
                row.append(profile["social_links"].get(platform, ""))
            
            row.append(profile["scraped_at"])
            writer.writerow(row)
    
    return str(output_path)


def save_to_json(results: list, config: dict) -> str:
    """Save results to JSON file."""
    output_path = Path(config["output_dir"]) / f"{config['filename']}.json"
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    
    return str(output_path)


def main():
    print("=" * 60)
    print("🚀 SUBSTACK PROFILE SCRAPER")
    print("=" * 60)
    
    # Load configuration
    config_path = Path(__file__).parent / "scraper_config.ini"
    print(f"📁 Loading config from: {config_path}")
    config = load_config(str(config_path))
    
    # Print configuration
    print("\n⚙️  Configuration:")
    print(f"   Max profiles: {config['max_profiles']}")
    print(f"   Max subscribers: {config['max_subscribers']:,}")
    print(f"   Min subscribers: {config['min_subscribers']:,}")
    print(f"   Request delay: {config['request_delay_ms']}ms")
    print(f"   Output format: {config['format']}")
    print(f"   Headless: {config['headless']}")
    if config["platforms"]:
        print(f"   Platform filter: {', '.join(config['platforms'])}")
    print()
    
    # Run scraper
    results = scrape_substack_profiles(config)
    
    # Save results
    if results:
        if config["format"].lower() == "csv":
            output_file = save_to_csv(results, config)
        else:
            output_file = save_to_json(results, config)
        
        print(f"\n💾 Results saved to: {output_file}")
        
        # Print summary
        print("\n" + "=" * 60)
        print("📊 SCRAPING COMPLETE")
        print("=" * 60)
        print(f"Total profiles collected: {len(results)}")
        
        # Count social links by platform
        platform_counts = {}
        for r in results:
            for platform in r['social_links'].keys():
                platform_counts[platform] = platform_counts.get(platform, 0) + 1
        
        print("\nSocial links by platform:")
        for platform, count in sorted(platform_counts.items(), key=lambda x: -x[1]):
            print(f"   {platform}: {count}")
        
        avg_subscribers = sum(r['subscriber_count'] for r in results) / len(results) if results else 0
        print(f"\nAverage subscriber count: {avg_subscribers:,.0f}")
        
        print("\n📋 Sample Data (first 3):")
        for i, profile in enumerate(results[:3], 1):
            print(f"\n{i}. @{profile['username']} ({profile['subscriber_count']:,} subscribers)")
            for platform, url in list(profile['social_links'].items())[:3]:
                print(f"   - {platform}: {url}")
    else:
        print("\n⚠️ No profiles were scraped matching the criteria.")


if __name__ == "__main__":
    main()
