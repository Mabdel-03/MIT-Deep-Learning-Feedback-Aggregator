"""
Post fetcher module for retrieving Piazza posts.
"""
import time
from typing import Generator, Optional
from datetime import datetime
from bs4 import BeautifulSoup
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

console = Console()


class PostFetcher:
    """Fetches and extracts posts from a Piazza network."""
    
    def __init__(self, network):
        """
        Initialize the post fetcher.
        
        Args:
            network: Authenticated Piazza network object
        """
        self.network = network
    
    def _clean_html(self, html_content: Optional[str]) -> str:
        """
        Remove HTML tags and clean up content.
        
        Args:
            html_content: HTML string to clean
            
        Returns:
            Plain text content
        """
        if not html_content:
            return ""
        soup = BeautifulSoup(html_content, "html.parser")
        return soup.get_text(separator=" ", strip=True)
    
    def _extract_author_role(self, post_data: dict) -> str:
        """
        Extract the author's role from post data.
        
        Args:
            post_data: Raw post data from Piazza API
            
        Returns:
            Role string: 'student', 'instructor', or 'ta'
        """
        history = post_data.get("history", [])
        if history:
            # Get the original author's info
            author_info = history[0]
            if author_info.get("anon") == "full":
                return "anonymous"
            # Check if author is instructor
            uid = author_info.get("uid")
            if uid:
                # Try to determine role from post metadata
                if post_data.get("bucket_name") == "Instructors":
                    return "instructor"
        
        # Default to student if we can't determine
        return "student"
    
    def _extract_answers(self, post_data: dict) -> list:
        """
        Extract all answers (instructor and student) from a post.
        
        Args:
            post_data: Raw post data from Piazza API
            
        Returns:
            List of answer dictionaries
        """
        answers = []
        children = post_data.get("children", [])
        
        for child in children:
            if child.get("type") in ["i_answer", "s_answer"]:
                answer_type = "instructor" if child.get("type") == "i_answer" else "student"
                history = child.get("history", [{}])
                content = history[0].get("content", "") if history else ""
                
                answers.append({
                    "type": answer_type,
                    "content": self._clean_html(content),
                    "created_at": child.get("created", ""),
                    "endorsements": len(child.get("tag_endorse", [])),
                })
        
        return answers
    
    def _extract_followups(self, post_data: dict) -> list:
        """
        Extract all followup discussions from a post.
        
        Args:
            post_data: Raw post data from Piazza API
            
        Returns:
            List of followup dictionaries
        """
        followups = []
        children = post_data.get("children", [])
        
        for child in children:
            if child.get("type") == "followup":
                subject = child.get("subject", "")
                
                # Get replies to this followup
                replies = []
                for reply in child.get("children", []):
                    if reply.get("type") == "feedback":
                        replies.append({
                            "content": self._clean_html(reply.get("subject", "")),
                            "created_at": reply.get("created", ""),
                        })
                
                followups.append({
                    "content": self._clean_html(subject),
                    "created_at": child.get("created", ""),
                    "replies": replies,
                })
        
        return followups
    
    def _parse_post(self, post_data: dict) -> dict:
        """
        Parse a single post into a structured format.
        
        Args:
            post_data: Raw post data from Piazza API
            
        Returns:
            Structured post dictionary
        """
        history = post_data.get("history", [{}])
        latest = history[0] if history else {}
        
        # Get folders/tags
        folders = post_data.get("folders", [])
        tags = post_data.get("tags", [])
        
        return {
            "id": post_data.get("id", ""),
            "nr": post_data.get("nr", 0),  # Post number
            "title": latest.get("subject", ""),
            "content": self._clean_html(latest.get("content", "")),
            "type": post_data.get("type", ""),  # 'question', 'note', etc.
            "folders": folders,
            "tags": tags,
            "author_role": self._extract_author_role(post_data),
            "created_at": post_data.get("created", ""),
            "updated_at": post_data.get("updated", ""),
            "num_favorites": post_data.get("num_favorites", 0),
            "unique_views": post_data.get("unique_views", 0),
            "answers": self._extract_answers(post_data),
            "followups": self._extract_followups(post_data),
            "is_resolved": post_data.get("no_answer", 0) == 0,
        }
    
    def fetch_all_posts(self, limit: Optional[int] = None) -> list:
        """
        Fetch all posts from the network.
        
        Args:
            limit: Optional limit on number of posts to fetch
            
        Returns:
            List of parsed post dictionaries
        """
        posts = []
        
        console.print("[yellow]Fetching posts from Piazza...[/yellow]")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            # First, get the feed to know total count
            feed = self.network.get_feed(limit=999999)
            total_posts = len(feed.get("feed", []))
            
            if limit:
                total_posts = min(total_posts, limit)
            
            task = progress.add_task("[cyan]Fetching posts...", total=total_posts)
            
            # Iterate through posts
            post_iter = self.network.iter_all_posts(limit=limit)
            
            for post_data in post_iter:
                try:
                    parsed = self._parse_post(post_data)
                    posts.append(parsed)
                    progress.update(task, advance=1)
                except Exception as e:
                    console.print(f"[red]Warning: Failed to parse post: {e}[/red]")
                    continue
                
                # Small delay to avoid rate limiting
                time.sleep(0.1)
        
        console.print(f"[green]✓ Fetched {len(posts)} posts[/green]")
        return posts
    
    def fetch_post_by_id(self, post_id: str) -> Optional[dict]:
        """
        Fetch a single post by its ID.
        
        Args:
            post_id: The post ID (cid)
            
        Returns:
            Parsed post dictionary or None if not found
        """
        try:
            post_data = self.network.get_post(post_id)
            return self._parse_post(post_data)
        except Exception as e:
            console.print(f"[red]Failed to fetch post {post_id}: {e}[/red]")
            return None

