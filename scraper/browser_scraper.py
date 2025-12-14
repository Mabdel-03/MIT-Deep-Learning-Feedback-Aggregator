"""
Browser-based Piazza scraper using Playwright.
Useful when SSO authentication is required.
"""
import json
import time
from pathlib import Path
from typing import Optional
from playwright.sync_api import sync_playwright, Page
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from bs4 import BeautifulSoup

import config

console = Console()


class BrowserScraper:
    """
    Browser-based scraper for Piazza using Playwright.
    This approach works with SSO authentication by using a persistent browser session.
    """
    
    def __init__(self, headless: bool = False):
        """
        Initialize the browser scraper.
        
        Args:
            headless: Run browser in headless mode (default: False for SSO login visibility)
        """
        self.headless = headless
        self.user_data_dir = config.BASE_DIR / ".browser_data"
        self.user_data_dir.mkdir(exist_ok=True)
        
    def _clean_html(self, html_content: Optional[str]) -> str:
        """Remove HTML tags and clean up content."""
        if not html_content:
            return ""
        soup = BeautifulSoup(html_content, "html.parser")
        return soup.get_text(separator=" ", strip=True)
    
    def login_interactive(self) -> bool:
        """
        Open browser for interactive login (useful for SSO).
        The session will be saved for future use.
        
        Returns:
            True if login was successful
        """
        console.print("[yellow]Opening browser for login...[/yellow]")
        console.print("[yellow]Please log in manually. The session will be saved.[/yellow]")
        
        with sync_playwright() as p:
            browser = p.chromium.launch_persistent_context(
                user_data_dir=str(self.user_data_dir),
                headless=False,  # Always show browser for interactive login
                viewport={"width": 1280, "height": 800}
            )
            
            page = browser.pages[0] if browser.pages else browser.new_page()
            page.goto(f"https://piazza.com/class/{config.PIAZZA_NETWORK_ID}")
            
            console.print("[cyan]Waiting for you to log in...[/cyan]")
            console.print("[cyan]Press Enter in this terminal when you're logged in and see the Piazza dashboard.[/cyan]")
            
            input()  # Wait for user to confirm login
            
            # Verify login by checking for user element
            try:
                page.wait_for_selector('[class*="settings"]', timeout=5000)
                console.print("[green]✓ Login successful! Session saved.[/green]")
                browser.close()
                return True
            except:
                console.print("[red]✗ Could not verify login. Please try again.[/red]")
                browser.close()
                return False
    
    def _extract_post_data(self, page: Page, post_id: str) -> Optional[dict]:
        """
        Extract data from a single post using the Piazza API.
        
        Args:
            page: Playwright page object
            post_id: The post CID
            
        Returns:
            Parsed post dictionary
        """
        try:
            # Use Piazza's internal API
            response = page.evaluate(f"""
                async () => {{
                    const response = await fetch('https://piazza.com/logic/api', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/x-www-form-urlencoded',
                        }},
                        body: 'method=content.get&params={{"cid":"{post_id}","nid":"{config.PIAZZA_NETWORK_ID}"}}'
                    }});
                    return await response.json();
                }}
            """)
            
            if response and response.get('result'):
                return self._parse_post(response['result'])
            return None
            
        except Exception as e:
            console.print(f"[red]Error fetching post {post_id}: {e}[/red]")
            return None
    
    def _parse_post(self, post_data: dict) -> dict:
        """Parse raw post data into structured format."""
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
                    "content": self._clean_html(content),
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
                            "content": self._clean_html(reply.get("subject", "")),
                            "created_at": reply.get("created", ""),
                        })
                followups.append({
                    "content": self._clean_html(child.get("subject", "")),
                    "created_at": child.get("created", ""),
                    "replies": replies,
                })
        
        return {
            "id": post_data.get("id", ""),
            "nr": post_data.get("nr", 0),
            "title": latest.get("subject", ""),
            "content": self._clean_html(latest.get("content", "")),
            "type": post_data.get("type", ""),
            "folders": post_data.get("folders", []),
            "tags": post_data.get("tags", []),
            "created_at": post_data.get("created", ""),
            "updated_at": post_data.get("updated", ""),
            "num_favorites": post_data.get("num_favorites", 0),
            "unique_views": post_data.get("unique_views", 0),
            "answers": answers,
            "followups": followups,
            "is_resolved": post_data.get("no_answer", 0) == 0,
        }
    
    def fetch_all_posts(self, limit: Optional[int] = None) -> list:
        """
        Fetch all posts using the browser session.
        
        Args:
            limit: Optional limit on number of posts
            
        Returns:
            List of parsed post dictionaries
        """
        posts = []
        
        console.print("[yellow]Starting browser-based scraping...[/yellow]")
        
        with sync_playwright() as p:
            browser = p.chromium.launch_persistent_context(
                user_data_dir=str(self.user_data_dir),
                headless=self.headless,
                viewport={"width": 1280, "height": 800}
            )
            
            page = browser.pages[0] if browser.pages else browser.new_page()
            
            # Navigate to the class
            page.goto(f"https://piazza.com/class/{config.PIAZZA_NETWORK_ID}")
            
            # Wait for page to load
            try:
                page.wait_for_selector('[class*="feed"]', timeout=10000)
            except:
                console.print("[red]✗ Could not load Piazza. You may need to login first.[/red]")
                console.print("[yellow]Run: python main.py login[/yellow]")
                browser.close()
                return []
            
            # Get feed using API
            console.print("[cyan]Fetching post list...[/cyan]")
            feed_response = page.evaluate(f"""
                async () => {{
                    const response = await fetch('https://piazza.com/logic/api', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/x-www-form-urlencoded',
                        }},
                        body: 'method=network.get_my_feed&params={{"nid":"{config.PIAZZA_NETWORK_ID}","limit":999999,"offset":0}}'
                    }});
                    return await response.json();
                }}
            """)
            
            if not feed_response or not feed_response.get('result'):
                console.print("[red]✗ Failed to fetch feed[/red]")
                browser.close()
                return []
            
            feed_items = feed_response['result'].get('feed', [])
            total_posts = len(feed_items)
            
            if limit:
                feed_items = feed_items[:limit]
                total_posts = len(feed_items)
            
            console.print(f"[green]Found {total_posts} posts to fetch[/green]")
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("[cyan]Fetching posts...", total=total_posts)
                
                for item in feed_items:
                    post_id = item.get('id')
                    if post_id:
                        post = self._extract_post_data(page, post_id)
                        if post:
                            posts.append(post)
                    
                    progress.update(task, advance=1)
                    time.sleep(0.05)  # Small delay to avoid rate limiting
            
            browser.close()
        
        console.print(f"[green]✓ Fetched {len(posts)} posts[/green]")
        return posts
    
    def is_logged_in(self) -> bool:
        """Check if there's a valid saved session."""
        if not (self.user_data_dir / "Default").exists():
            return False
        
        with sync_playwright() as p:
            browser = p.chromium.launch_persistent_context(
                user_data_dir=str(self.user_data_dir),
                headless=True,
                viewport={"width": 1280, "height": 800}
            )
            
            page = browser.pages[0] if browser.pages else browser.new_page()
            page.goto("https://piazza.com/class")
            
            try:
                # Check if redirected to login
                page.wait_for_url("**/class/**", timeout=5000)
                browser.close()
                return True
            except:
                browser.close()
                return False

