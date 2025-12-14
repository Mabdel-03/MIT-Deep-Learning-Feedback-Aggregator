#!/usr/bin/env python3
"""
Scrape all posts from Piazza by navigating to each post URL.
Uses the existing browser session (must be logged in).
"""
import json
import time
import re
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

console = Console()

# Configuration
NETWORK_ID = "mexb078f4z54ia"
MAX_POST_NR = 630  # Highest post number
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data" / "raw"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def clean_html(html_content):
    """Remove HTML tags from content."""
    if not html_content:
        return ""
    soup = BeautifulSoup(html_content, "html.parser")
    return soup.get_text(separator=" ", strip=True)


def extract_post_from_page(page) -> dict:
    """Extract post data from the current page."""
    try:
        # Wait for content to load
        page.wait_for_selector('main, article, [class*="post"]', timeout=5000)
        
        # Extract using JavaScript
        data = page.evaluate("""
            () => {
                const result = {
                    title: '',
                    content: '',
                    type: '',
                    folders: [],
                    answers: [],
                    followups: [],
                    date: '',
                    isResolved: false
                };
                
                // Get title - look for heading in main content area
                const titleEl = document.querySelector('h1, h2, [class*="subject"]');
                if (titleEl) {
                    result.title = titleEl.textContent?.trim() || '';
                }
                
                // Get main content - look for post body
                const contentEls = document.querySelectorAll('[class*="content"], [class*="body"], article p');
                let content = '';
                contentEls.forEach(el => {
                    const text = el.textContent?.trim() || '';
                    if (text.length > 30 && !text.includes('Skip navigation')) {
                        content += text + '\\n';
                    }
                });
                result.content = content.substring(0, 5000);
                
                // Check for folders/tags in breadcrumbs or tags area
                document.querySelectorAll('[class*="folder"], [class*="tag"], [class*="badge"]').forEach(el => {
                    const text = el.textContent?.trim();
                    if (text && text.length < 50 && !result.folders.includes(text)) {
                        result.folders.push(text);
                    }
                });
                
                // Look for date
                const datePattern = /\\d{1,2}\\/\\d{1,2}\\/\\d{2}/;
                const pageText = document.body.textContent || '';
                const dateMatch = pageText.match(datePattern);
                if (dateMatch) {
                    result.date = dateMatch[0];
                }
                
                // Check if resolved
                result.isResolved = pageText.includes('Resolved') || 
                                   pageText.includes('good answer') ||
                                   pageText.includes('endorsed');
                
                // Get post type
                if (pageText.includes('This is a note')) {
                    result.type = 'note';
                } else if (pageText.includes('question')) {
                    result.type = 'question';
                }
                
                // Look for answers
                document.querySelectorAll('[class*="answer"]').forEach(el => {
                    const text = el.textContent?.trim();
                    if (text && text.length > 50) {
                        const isInstructor = el.textContent?.includes('instructor') || 
                                            el.closest('[class*="instructor"]') !== null;
                        result.answers.push({
                            type: isInstructor ? 'instructor' : 'student',
                            content: text.substring(0, 2000)
                        });
                    }
                });
                
                return result;
            }
        """)
        
        return data
    except Exception as e:
        return {"error": str(e)}


def main():
    console.print("[bold cyan]Piazza Full Scraper[/bold cyan]")
    console.print("=" * 50)
    console.print(f"[yellow]Will attempt to scrape posts 1-{MAX_POST_NR}[/yellow]")
    
    all_posts = []
    failed_posts = []
    
    with sync_playwright() as p:
        # Launch browser with saved session
        user_data_dir = BASE_DIR / ".browser_data"
        
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=True,  # Run headless for speed
            viewport={"width": 1280, "height": 800}
        )
        
        page = browser.pages[0] if browser.pages else browser.new_page()
        
        # First check if we're logged in
        console.print("[yellow]Checking login status...[/yellow]")
        page.goto(f"https://piazza.com/class/{NETWORK_ID}")
        time.sleep(2)
        
        if "login" in page.url.lower() or "sso" in page.url.lower():
            console.print("[red]Not logged in! Please run 'python main.py login' first.[/red]")
            browser.close()
            return
        
        console.print("[green]✓ Logged in[/green]")
        
        # Scrape each post
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Scraping posts...", total=MAX_POST_NR)
            
            for nr in range(1, MAX_POST_NR + 1):
                try:
                    url = f"https://piazza.com/class/{NETWORK_ID}/post/{nr}"
                    page.goto(url, wait_until="domcontentloaded")
                    time.sleep(0.3)  # Brief wait for content
                    
                    # Check if post exists (not 404 or error)
                    if "error" in page.url.lower() or "not found" in page.content().lower():
                        failed_posts.append(nr)
                        progress.update(task, advance=1)
                        continue
                    
                    # Extract post data
                    post_data = extract_post_from_page(page)
                    
                    if post_data and not post_data.get("error"):
                        post_data["nr"] = nr
                        post_data["url"] = url
                        all_posts.append(post_data)
                    else:
                        failed_posts.append(nr)
                    
                except Exception as e:
                    failed_posts.append(nr)
                
                progress.update(task, advance=1)
                
                # Save progress every 50 posts
                if nr % 50 == 0:
                    progress.update(task, description=f"[cyan]Scraping posts... ({len(all_posts)} saved)")
                    
                    # Save intermediate results
                    temp_file = DATA_DIR / "posts_scraping_progress.json"
                    with open(temp_file, 'w') as f:
                        json.dump(all_posts, f, indent=2)
        
        browser.close()
    
    console.print(f"\n[green]✓ Scraped {len(all_posts)} posts successfully[/green]")
    console.print(f"[yellow]Failed to scrape {len(failed_posts)} posts[/yellow]")
    
    # Save final results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = DATA_DIR / f"all_posts_full_{timestamp}.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "scraped_at": timestamp,
            "total_attempted": MAX_POST_NR,
            "total_scraped": len(all_posts),
            "failed_count": len(failed_posts),
            "posts": all_posts
        }, f, indent=2, ensure_ascii=False)
    
    console.print(f"[green]✓ Saved to {output_file}[/green]")
    
    # Also save as latest
    latest_file = DATA_DIR / "all_posts_complete.json"
    with open(latest_file, 'w', encoding='utf-8') as f:
        json.dump({
            "scraped_at": timestamp,
            "total_attempted": MAX_POST_NR,
            "total_scraped": len(all_posts),
            "posts": all_posts
        }, f, indent=2, ensure_ascii=False)
    
    console.print(f"[green]✓ Also saved to {latest_file}[/green]")
    
    # Print summary by folder
    console.print("\n[bold]Posts by folder:[/bold]")
    folder_counts = {}
    for post in all_posts:
        for folder in post.get('folders', ['uncategorized']):
            folder_counts[folder] = folder_counts.get(folder, 0) + 1
    
    for folder, count in sorted(folder_counts.items(), key=lambda x: -x[1])[:10]:
        console.print(f"  {folder}: {count}")


if __name__ == "__main__":
    main()

