#!/usr/bin/env python3
"""
Quick scrape script - Opens browser for login, then scrapes data.
Run this interactively: python quick_scrape.py
"""
import json
import time
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

console = Console()

# Configuration
NETWORK_ID = "mexb078f4z54ia"
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data" / "raw"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def clean_html(html_content):
    """Remove HTML tags from content."""
    if not html_content:
        return ""
    soup = BeautifulSoup(html_content, "html.parser")
    return soup.get_text(separator=" ", strip=True)


def parse_post(post_data):
    """Parse a raw post into structured format."""
    history = post_data.get("history", [{}])
    latest = history[0] if history else {}
    
    # Extract answers
    answers = []
    children = post_data.get("children", [])
    for child in children:
        if child.get("type") in ["i_answer", "s_answer"]:
            answer_type = "instructor" if child.get("type") == "i_answer" else "student"
            child_history = child.get("history", [{}])
            content = child_history[0].get("content", "") if child_history else ""
            answers.append({
                "type": answer_type,
                "content": clean_html(content),
                "created_at": child.get("created", ""),
            })
    
    # Extract followups
    followups = []
    for child in children:
        if child.get("type") == "followup":
            replies = []
            for reply in child.get("children", []):
                if reply.get("type") == "feedback":
                    replies.append({
                        "content": clean_html(reply.get("subject", "")),
                        "created_at": reply.get("created", ""),
                    })
            followups.append({
                "content": clean_html(child.get("subject", "")),
                "created_at": child.get("created", ""),
                "replies": replies,
            })
    
    return {
        "id": post_data.get("id", ""),
        "nr": post_data.get("nr", 0),
        "title": latest.get("subject", ""),
        "content": clean_html(latest.get("content", "")),
        "type": post_data.get("type", ""),
        "folders": post_data.get("folders", []),
        "tags": post_data.get("tags", []),
        "created_at": post_data.get("created", ""),
        "num_favorites": post_data.get("num_favorites", 0),
        "unique_views": post_data.get("unique_views", 0),
        "answers": answers,
        "followups": followups,
        "is_resolved": post_data.get("no_answer", 0) == 0,
    }


def main():
    console.print("[bold cyan]Piazza Quick Scraper[/bold cyan]")
    console.print("=" * 50)
    
    with sync_playwright() as p:
        # Launch browser (visible so you can see what's happening)
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        
        # Navigate to Piazza
        console.print("[yellow]Navigating to Piazza...[/yellow]")
        page.goto(f"https://piazza.com/class/{NETWORK_ID}")
        
        # Wait for page to load
        console.print("[yellow]Waiting for page to load...[/yellow]")
        console.print("[cyan]If you're not logged in, please log in now.[/cyan]")
        console.print("[cyan]Press Enter when you see the Piazza dashboard...[/cyan]")
        
        input()
        
        # Now scrape using Piazza's internal JS
        console.print("[yellow]Fetching posts...[/yellow]")
        
        # Get feed using page evaluation
        feed_data = page.evaluate(f"""
            async () => {{
                // Make internal API call using page context
                const response = await fetch('https://piazza.com/logic/api', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                    }},
                    credentials: 'include',
                    body: JSON.stringify({{
                        method: 'network.get_my_feed',
                        params: {{nid: '{NETWORK_ID}', limit: 9999, offset: 0}}
                    }})
                }});
                return await response.json();
            }}
        """)
        
        if not feed_data.get('result'):
            console.print("[red]Failed to get feed. Trying alternative method...[/red]")
            
            # Try intercepting network requests instead
            # Get all post IDs from the visible feed
            post_links = page.query_selector_all('[data-pats*="feed_item"]')
            console.print(f"[yellow]Found {len(post_links)} visible posts in feed[/yellow]")
            
            # Alternative: scroll and collect post data from DOM
            posts_from_dom = []
            
            # Click "Show All" to load all posts
            try:
                show_all = page.query_selector('button:has-text("Show All")')
                if show_all:
                    show_all.click()
                    time.sleep(2)
            except:
                pass
            
            console.print("[cyan]Scraping visible posts from page...[/cyan]")
            
            # Get all feed items and extract basic info
            feed_items = page.evaluate("""
                () => {
                    const items = [];
                    document.querySelectorAll('[class*="feed-item"]').forEach(item => {
                        const link = item.querySelector('a[href*="cid="]');
                        if (link) {
                            const href = link.getAttribute('href');
                            const cidMatch = href.match(/cid=([^&]+)/);
                            if (cidMatch) {
                                items.push({
                                    cid: cidMatch[1],
                                    title: item.textContent.substring(0, 100)
                                });
                            }
                        }
                    });
                    return items;
                }
            """)
            
            console.print(f"[yellow]Found {len(feed_items)} feed items[/yellow]")
        else:
            feed_items = feed_data['result'].get('feed', [])
            console.print(f"[green]✓ Found {len(feed_items)} posts[/green]")
        
        # Now fetch each post individually
        posts = []
        
        limit = min(len(feed_items), 50)  # Limit to 50 for testing
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Fetching posts...", total=limit)
            
            for i, item in enumerate(feed_items[:limit]):
                cid = item.get('id') or item.get('cid')
                if not cid:
                    continue
                
                try:
                    post_data = page.evaluate(f"""
                        async () => {{
                            const response = await fetch('https://piazza.com/logic/api', {{
                                method: 'POST',
                                headers: {{
                                    'Content-Type': 'application/json',
                                }},
                                credentials: 'include',
                                body: JSON.stringify({{
                                    method: 'content.get',
                                    params: {{nid: '{NETWORK_ID}', cid: '{cid}'}}
                                }})
                            }});
                            return await response.json();
                        }}
                    """)
                    
                    if post_data.get('result'):
                        parsed = parse_post(post_data['result'])
                        posts.append(parsed)
                except Exception as e:
                    console.print(f"[red]Error fetching {cid}: {e}[/red]")
                
                progress.update(task, advance=1)
                time.sleep(0.1)  # Rate limiting
        
        browser.close()
    
    console.print(f"\n[green]✓ Fetched {len(posts)} posts[/green]")
    
    # Save posts
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = DATA_DIR / f"all_posts_{timestamp}.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(posts, f, indent=2, ensure_ascii=False, default=str)
    
    console.print(f"[green]✓ Saved to {output_file}[/green]")
    
    # Also save as latest
    latest_file = DATA_DIR / "all_posts_latest.json"
    with open(latest_file, 'w', encoding='utf-8') as f:
        json.dump(posts, f, indent=2, ensure_ascii=False, default=str)
    
    # Print summary by folder
    console.print("\n[bold]Posts by folder:[/bold]")
    folder_counts = {}
    for post in posts:
        for folder in post.get('folders', ['uncategorized']):
            folder_counts[folder] = folder_counts.get(folder, 0) + 1
    
    for folder, count in sorted(folder_counts.items()):
        console.print(f"  {folder}: {count}")


if __name__ == "__main__":
    main()

