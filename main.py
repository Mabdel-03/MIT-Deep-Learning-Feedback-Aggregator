#!/usr/bin/env python3
"""
MIT Deep Learning Feedback Aggregator

Main entry point for scraping Piazza posts and analyzing student feedback.
"""
import argparse
import sys
from datetime import datetime
from rich.console import Console
from rich.panel import Panel

import config
from scraper import PiazzaAuth, PostFetcher, DataProcessor
from scraper.browser_scraper import BrowserScraper
from analyzer import FeedbackAnalyzer

console = Console()


def print_banner():
    """Print the application banner."""
    banner = """
    ╔═══════════════════════════════════════════════════════════╗
    ║     MIT Deep Learning Feedback Aggregator                 ║
    ║     Piazza Scraper & LLM Analysis Tool                    ║
    ╚═══════════════════════════════════════════════════════════╝
    """
    console.print(banner, style="bold cyan")


def validate_config():
    """Validate that required configuration is present."""
    errors = []
    
    if not config.PIAZZA_EMAIL:
        errors.append("PIAZZA_EMAIL not set in .env")
    if not config.PIAZZA_PASSWORD:
        errors.append("PIAZZA_PASSWORD not set in .env")
    if not config.PIAZZA_NETWORK_ID:
        errors.append("PIAZZA_NETWORK_ID not set in .env")
    
    if errors:
        console.print("[red]Configuration errors:[/red]")
        for error in errors:
            console.print(f"  [red]✗ {error}[/red]")
        console.print("\n[yellow]Please copy env_template.txt to .env and fill in your credentials.[/yellow]")
        return False
    
    return True


def cmd_login(args):
    """Interactive login for SSO authentication."""
    console.print(Panel("Piazza Login", style="bold green"))
    
    scraper = BrowserScraper(headless=False)
    
    if scraper.is_logged_in():
        console.print("[green]✓ Already logged in with saved session[/green]")
        relogin = input("Do you want to re-login? (y/N): ").strip().lower()
        if relogin != 'y':
            return 0
    
    if scraper.login_interactive():
        return 0
    return 1


def cmd_scrape(args):
    """Run the scraper to fetch posts from Piazza."""
    console.print(Panel("Starting Piazza Scraper", style="bold green"))
    
    # Use browser-based scraper (works with SSO)
    scraper = BrowserScraper(headless=args.headless if hasattr(args, 'headless') else True)
    
    # Check if logged in
    if not scraper.is_logged_in():
        console.print("[yellow]No saved session found. Starting interactive login...[/yellow]")
        if not scraper.login_interactive():
            return 1
    
    # Fetch posts
    posts = scraper.fetch_all_posts(limit=args.limit)
    
    if not posts:
        console.print("[red]✗ No posts fetched. Try running 'python main.py login' first.[/red]")
        return 1
    
    # Process and categorize
    processor = DataProcessor()
    categorized = processor.categorize_posts(posts)
    
    # Get statistics
    stats = processor.get_statistics(categorized)
    console.print("\n[bold]Post Statistics:[/bold]")
    console.print(f"  Total posts: {stats['total_posts']}")
    console.print(f"  Total psets: {stats['total_psets']}")
    console.print(f"  Resolved: {stats['resolved_count']}")
    console.print(f"  Unresolved: {stats['unresolved_count']}")
    
    # Save data
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save all posts (flat)
    processor.save_to_json(posts, f"all_posts_{timestamp}.json")
    
    # Save categorized posts
    processor.save_to_json(categorized, f"categorized_posts_{timestamp}.json")
    
    # Save as latest for easy access
    processor.save_to_json(categorized, "categorized_posts_latest.json")
    
    console.print("\n[green]✓ Scraping complete![/green]")
    return 0


def cmd_analyze(args):
    """Run LLM analysis on scraped posts."""
    console.print(Panel("Starting LLM Analysis", style="bold green"))
    
    if not config.ANTHROPIC_API_KEY:
        console.print("[red]✗ ANTHROPIC_API_KEY not set in .env[/red]")
        console.print("[yellow]Please add your Anthropic API key to use the analyzer.[/yellow]")
        return 1
    
    # Load categorized posts
    processor = DataProcessor()
    
    try:
        if args.input:
            categorized = processor.load_from_json(args.input)
        else:
            categorized = processor.load_from_json("categorized_posts_latest.json")
    except FileNotFoundError:
        console.print("[red]✗ No scraped data found. Run 'scrape' first.[/red]")
        return 1
    
    # Filter to student posts only for analysis
    if args.students_only:
        categorized = processor.filter_student_posts(categorized)
        console.print("[yellow]Filtering to student posts only[/yellow]")
    
    # Run analysis
    analyzer = FeedbackAnalyzer()
    analysis = analyzer.analyze_all(categorized)
    
    # Save analysis results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    analyzer.save_analysis(analysis, f"analysis_{timestamp}.json")
    analyzer.save_analysis(analysis, "analysis_latest.json")
    
    # Generate and save report
    report = analyzer.generate_report(analysis)
    report_path = config.ANALYSIS_DIR / f"report_{timestamp}.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    console.print(f"[green]✓ Report saved to {report_path}[/green]")
    
    # Print report to console
    console.print("\n")
    console.print(Panel(report, title="Analysis Report", expand=False))
    
    return 0


def cmd_list_classes(args):
    """List all Piazza classes the user has access to."""
    console.print(Panel("Listing Piazza Classes", style="bold green"))
    
    auth = PiazzaAuth(config.PIAZZA_EMAIL, config.PIAZZA_PASSWORD)
    if not auth.login():
        return 1
    
    classes = auth.list_user_classes()
    
    console.print("\n[bold]Your Piazza Classes:[/bold]")
    for cls in classes:
        nid = cls.get("nid", "unknown")
        name = cls.get("name", "Unknown Course")
        term = cls.get("term", "")
        console.print(f"  [cyan]{nid}[/cyan]: {name} ({term})")
    
    console.print(f"\n[yellow]Use the network ID (nid) as PIAZZA_NETWORK_ID in your .env file[/yellow]")
    return 0


def cmd_full(args):
    """Run full pipeline: scrape and analyze."""
    console.print(Panel("Running Full Pipeline", style="bold green"))
    
    # Run scraper
    result = cmd_scrape(args)
    if result != 0:
        return result
    
    console.print("\n")
    
    # Run analyzer
    args.input = None  # Use latest scraped data
    args.students_only = True  # Focus on student feedback
    result = cmd_analyze(args)
    
    return result


def main():
    """Main entry point."""
    print_banner()
    
    parser = argparse.ArgumentParser(
        description="MIT Deep Learning Feedback Aggregator - Piazza Scraper & LLM Analyzer"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Login command
    subparsers.add_parser("login", help="Interactive login (for SSO authentication)")
    
    # Scrape command
    scrape_parser = subparsers.add_parser("scrape", help="Scrape posts from Piazza")
    scrape_parser.add_argument(
        "--limit", "-l", type=int, default=None,
        help="Limit number of posts to fetch (default: all)"
    )
    scrape_parser.add_argument(
        "--headless", action="store_true",
        help="Run browser in headless mode"
    )
    
    # Analyze command
    analyze_parser = subparsers.add_parser("analyze", help="Analyze scraped posts with LLM")
    analyze_parser.add_argument(
        "--input", "-i", type=str, default=None,
        help="Input JSON file (default: categorized_posts_latest.json)"
    )
    analyze_parser.add_argument(
        "--students-only", "-s", action="store_true",
        help="Only analyze student-authored posts"
    )
    
    # List classes command
    subparsers.add_parser("list-classes", help="List your Piazza classes and their IDs")
    
    # Full pipeline command
    full_parser = subparsers.add_parser("full", help="Run full pipeline (scrape + analyze)")
    full_parser.add_argument(
        "--limit", "-l", type=int, default=None,
        help="Limit number of posts to fetch (default: all)"
    )
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 0
    
    # Validate config based on command
    if args.command in ["scrape", "full"]:
        if not config.PIAZZA_NETWORK_ID:
            console.print("[red]✗ PIAZZA_NETWORK_ID must be set in .env[/red]")
            return 1
    elif args.command == "list-classes":
        if not config.PIAZZA_EMAIL or not config.PIAZZA_PASSWORD:
            console.print("[red]✗ PIAZZA_EMAIL and PIAZZA_PASSWORD must be set in .env[/red]")
            return 1
    elif args.command == "analyze":
        pass  # Will check for data files inside the command
    # login command doesn't need validation
    
    # Run command
    commands = {
        "login": cmd_login,
        "scrape": cmd_scrape,
        "analyze": cmd_analyze,
        "list-classes": cmd_list_classes,
        "full": cmd_full,
    }
    
    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())

