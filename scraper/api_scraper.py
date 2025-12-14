"""
Direct API-based Piazza scraper.
Uses session established via browser for SSO authentication.
"""
import json
import time
import requests
from typing import Optional
from pathlib import Path
from bs4 import BeautifulSoup
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

import config

console = Console()


class APIScraper:
    """
    Direct API scraper for Piazza.
    Requires cookies from an authenticated session.
    """
    
    def __init__(self):
        """Initialize the API scraper."""
        self.session = requests.Session()
        self.base_url = "https://piazza.com/logic/api"
        self.network_id = config.PIAZZA_NETWORK_ID
        self.cookies_file = config.BASE_DIR / "session_cookies.json"
        
    def _clean_html(self, html_content: Optional[str]) -> str:
        """Remove HTML tags and clean up content."""
        if not html_content:
            return ""
        soup = BeautifulSoup(html_content, "html.parser")
        return soup.get_text(separator=" ", strip=True)
    
    def set_cookies(self, cookies: dict):
        """
        Set session cookies for authentication.
        
        Args:
            cookies: Dictionary of cookies
        """
        for name, value in cookies.items():
            self.session.cookies.set(name, value, domain='.piazza.com')
    
    def save_cookies(self, cookies: dict):
        """Save cookies to file for reuse."""
        with open(self.cookies_file, 'w') as f:
            json.dump(cookies, f, indent=2)
        console.print(f"[green]✓ Cookies saved to {self.cookies_file}[/green]")
    
    def load_cookies(self) -> bool:
        """
        Load cookies from file.
        
        Returns:
            True if cookies loaded successfully
        """
        if not self.cookies_file.exists():
            return False
        
        try:
            with open(self.cookies_file, 'r') as f:
                cookies = json.load(f)
            self.set_cookies(cookies)
            return True
        except:
            return False
    
    def _api_call(self, method: str, params: dict = None) -> dict:
        """
        Make an API call to Piazza.
        
        Args:
            method: API method name
            params: Parameters for the call
            
        Returns:
            Response JSON
        """
        data = {
            'method': method,
            'params': json.dumps(params or {})
        }
        
        response = self.session.post(self.base_url, data=data)
        return response.json()
    
    def verify_session(self) -> bool:
        """
        Verify that the session is authenticated.
        
        Returns:
            True if authenticated
        """
        try:
            result = self._api_call('user.status')
            if result.get('result'):
                email = result['result'].get('email', 'Unknown')
                console.print(f"[green]✓ Authenticated as: {email}[/green]")
                return True
            return False
        except Exception as e:
            console.print(f"[red]✗ Session verification failed: {e}[/red]")
            return False
    
    def get_feed(self, limit: int = 999999) -> list:
        """
        Get the post feed.
        
        Args:
            limit: Maximum number of posts
            
        Returns:
            List of feed items
        """
        result = self._api_call('network.get_my_feed', {
            'nid': self.network_id,
            'limit': limit,
            'offset': 0
        })
        
        if result.get('result'):
            return result['result'].get('feed', [])
        return []
    
    def get_post(self, cid: str) -> Optional[dict]:
        """
        Get a single post by CID.
        
        Args:
            cid: Post content ID
            
        Returns:
            Raw post data
        """
        result = self._api_call('content.get', {
            'nid': self.network_id,
            'cid': cid
        })
        return result.get('result')
    
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
        Fetch all posts from the network.
        
        Args:
            limit: Optional limit on number of posts
            
        Returns:
            List of parsed post dictionaries
        """
        posts = []
        
        console.print("[yellow]Fetching posts from Piazza...[/yellow]")
        
        # Get feed
        feed_items = self.get_feed(limit=limit or 999999)
        
        if limit:
            feed_items = feed_items[:limit]
        
        total_posts = len(feed_items)
        console.print(f"[cyan]Found {total_posts} posts to fetch[/cyan]")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Fetching posts...", total=total_posts)
            
            for item in feed_items:
                cid = item.get('id')
                if cid:
                    try:
                        raw_post = self.get_post(cid)
                        if raw_post:
                            parsed = self._parse_post(raw_post)
                            posts.append(parsed)
                    except Exception as e:
                        console.print(f"[red]Warning: Failed to fetch post {cid}: {e}[/red]")
                
                progress.update(task, advance=1)
                time.sleep(0.05)  # Rate limiting
        
        console.print(f"[green]✓ Fetched {len(posts)} posts[/green]")
        return posts

