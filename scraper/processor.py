"""
Data processor module for structuring and categorizing posts.
"""
import re
import json
from pathlib import Path
from typing import Optional
from collections import defaultdict
from rich.console import Console

import config

console = Console()


class DataProcessor:
    """Processes and structures Piazza posts by pset/problem."""
    
    def __init__(self):
        """Initialize the data processor with pattern matchers."""
        self.pset_patterns = [re.compile(p, re.IGNORECASE) for p in config.PSET_PATTERNS]
        self.problem_patterns = [re.compile(p, re.IGNORECASE) for p in config.PROBLEM_PATTERNS]
    
    def _extract_pset(self, post: dict) -> Optional[str]:
        """
        Extract pset number from a post.
        
        Args:
            post: Parsed post dictionary
            
        Returns:
            Pset identifier (e.g., 'pset1') or None
        """
        # Check folders first (most reliable)
        for folder in post.get("folders", []):
            for pattern in self.pset_patterns:
                match = pattern.search(folder)
                if match:
                    return f"pset{match.group(1)}"
        
        # Check tags
        for tag in post.get("tags", []):
            for pattern in self.pset_patterns:
                match = pattern.search(tag)
                if match:
                    return f"pset{match.group(1)}"
        
        # Check title
        title = post.get("title", "")
        for pattern in self.pset_patterns:
            match = pattern.search(title)
            if match:
                return f"pset{match.group(1)}"
        
        # Check content (first 500 chars to avoid false positives)
        content = post.get("content", "")[:500]
        for pattern in self.pset_patterns:
            match = pattern.search(content)
            if match:
                return f"pset{match.group(1)}"
        
        return None
    
    def _extract_problem(self, post: dict) -> Optional[str]:
        """
        Extract problem number from a post.
        
        Args:
            post: Parsed post dictionary
            
        Returns:
            Problem identifier (e.g., 'problem1', 'problem2a') or None
        """
        # Check title first (most reliable for problem identification)
        title = post.get("title", "")
        for pattern in self.problem_patterns:
            match = pattern.search(title)
            if match:
                return f"problem{match.group(1).lower()}"
        
        # Check folders
        for folder in post.get("folders", []):
            for pattern in self.problem_patterns:
                match = pattern.search(folder)
                if match:
                    return f"problem{match.group(1).lower()}"
        
        # Check content (first 300 chars)
        content = post.get("content", "")[:300]
        for pattern in self.problem_patterns:
            match = pattern.search(content)
            if match:
                return f"problem{match.group(1).lower()}"
        
        return None
    
    def categorize_posts(self, posts: list) -> dict:
        """
        Categorize posts by pset and problem.
        
        Args:
            posts: List of parsed post dictionaries
            
        Returns:
            Hierarchical dictionary: {pset: {problem: [posts]}}
        """
        console.print("[yellow]Categorizing posts by pset/problem...[/yellow]")
        
        # Use nested defaultdict for easy access
        categorized = defaultdict(lambda: defaultdict(list))
        uncategorized = []
        
        for post in posts:
            pset = self._extract_pset(post)
            problem = self._extract_problem(post)
            
            if pset:
                if problem:
                    categorized[pset][problem].append(post)
                else:
                    categorized[pset]["general"].append(post)
            else:
                uncategorized.append(post)
        
        # Add uncategorized posts
        if uncategorized:
            categorized["uncategorized"]["all"] = uncategorized
        
        # Convert defaultdict to regular dict for JSON serialization
        result = {
            pset: dict(problems) 
            for pset, problems in categorized.items()
        }
        
        # Print summary
        self._print_summary(result)
        
        return result
    
    def _print_summary(self, categorized: dict):
        """Print a summary of categorized posts."""
        console.print("\n[bold]Categorization Summary:[/bold]")
        
        total = 0
        for pset, problems in sorted(categorized.items()):
            pset_total = sum(len(posts) for posts in problems.values())
            total += pset_total
            console.print(f"  [cyan]{pset}[/cyan]: {pset_total} posts")
            for problem, posts in sorted(problems.items()):
                console.print(f"    - {problem}: {len(posts)} posts")
        
        console.print(f"\n[green]Total categorized: {total} posts[/green]")
    
    def filter_student_posts(self, categorized: dict) -> dict:
        """
        Filter to only include posts authored by students.
        
        Args:
            categorized: Hierarchical post dictionary
            
        Returns:
            Filtered dictionary with only student posts
        """
        filtered = {}
        
        for pset, problems in categorized.items():
            filtered[pset] = {}
            for problem, posts in problems.items():
                student_posts = [
                    p for p in posts 
                    if p.get("author_role") in ["student", "anonymous"]
                ]
                if student_posts:
                    filtered[pset][problem] = student_posts
        
        return filtered
    
    def save_to_json(self, data: dict, filename: str) -> Path:
        """
        Save data to a JSON file.
        
        Args:
            data: Dictionary to save
            filename: Name of the output file
            
        Returns:
            Path to the saved file
        """
        output_path = config.RAW_DATA_DIR / filename
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        
        console.print(f"[green]✓ Saved data to {output_path}[/green]")
        return output_path
    
    def load_from_json(self, filename: str) -> dict:
        """
        Load data from a JSON file.
        
        Args:
            filename: Name of the file to load
            
        Returns:
            Loaded dictionary
        """
        input_path = config.RAW_DATA_DIR / filename
        
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        console.print(f"[green]✓ Loaded data from {input_path}[/green]")
        return data
    
    def get_statistics(self, categorized: dict) -> dict:
        """
        Generate statistics about the categorized posts.
        
        Args:
            categorized: Hierarchical post dictionary
            
        Returns:
            Statistics dictionary
        """
        stats = {
            "total_posts": 0,
            "total_psets": 0,
            "posts_by_pset": {},
            "posts_by_type": defaultdict(int),
            "resolved_count": 0,
            "unresolved_count": 0,
            "total_answers": 0,
            "total_followups": 0,
        }
        
        for pset, problems in categorized.items():
            if pset != "uncategorized":
                stats["total_psets"] += 1
            
            pset_count = 0
            for problem, posts in problems.items():
                pset_count += len(posts)
                stats["total_posts"] += len(posts)
                
                for post in posts:
                    stats["posts_by_type"][post.get("type", "unknown")] += 1
                    
                    if post.get("is_resolved"):
                        stats["resolved_count"] += 1
                    else:
                        stats["unresolved_count"] += 1
                    
                    stats["total_answers"] += len(post.get("answers", []))
                    stats["total_followups"] += len(post.get("followups", []))
            
            stats["posts_by_pset"][pset] = pset_count
        
        stats["posts_by_type"] = dict(stats["posts_by_type"])
        return stats

