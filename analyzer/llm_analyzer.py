"""
LLM-based feedback analyzer using Anthropic Claude.
"""
import json
from typing import Optional
from pathlib import Path
from anthropic import Anthropic
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

import config

console = Console()

ANALYSIS_PROMPT = """You are an expert educational analyst helping TAs and instructors improve their course problem sets based on student feedback from Piazza.

Analyze the following student posts about {pset} - {problem}. These posts include questions, discussions, and feedback from students.

For each post, I've included:
- Title and content
- Any answers and followups
- Whether the question was resolved

Based on this data, provide a comprehensive analysis with the following structure:

1. **Sentiment Analysis** (1-5 scale where 1=very negative, 5=very positive)
   - Overall score
   - Brief justification

2. **Common Issues** (list the top 3-5 confusion points or difficulties students faced)
   - Be specific about what students struggled with
   - Include approximate frequency if multiple students mentioned the same issue

3. **Actionable Suggestions** (provide 3-5 concrete recommendations)
   - How to improve the problem statement
   - Additional resources or hints that could help
   - Changes to make for future iterations

4. **Summary Statistics**
   - Total posts analyzed
   - Resolution rate
   - Key themes

Return your analysis as a valid JSON object with the following structure:
{{
    "sentiment": {{
        "score": <float 1-5>,
        "summary": "<brief justification>"
    }},
    "common_issues": [
        {{
            "issue": "<description>",
            "frequency": "<how many students mentioned this>",
            "severity": "<low/medium/high>"
        }}
    ],
    "suggestions": [
        {{
            "suggestion": "<actionable recommendation>",
            "priority": "<low/medium/high>",
            "effort": "<low/medium/high>"
        }}
    ],
    "statistics": {{
        "total_posts": <int>,
        "resolved_count": <int>,
        "key_themes": ["<theme1>", "<theme2>"]
    }}
}}

STUDENT POSTS:
{posts_content}

Return ONLY the JSON object, no additional text or markdown formatting."""


class FeedbackAnalyzer:
    """Analyzes Piazza feedback using Claude LLM."""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the feedback analyzer.
        
        Args:
            api_key: Anthropic API key (uses env var if not provided)
        """
        self.api_key = api_key or config.ANTHROPIC_API_KEY
        if not self.api_key:
            raise ValueError(
                "Anthropic API key required. Set ANTHROPIC_API_KEY in .env or pass directly."
            )
        
        self.client = Anthropic(api_key=self.api_key)
        self.model = config.LLM_MODEL
    
    def _format_posts_for_analysis(self, posts: list) -> str:
        """
        Format posts into a string for LLM analysis.
        
        Args:
            posts: List of post dictionaries
            
        Returns:
            Formatted string representation of posts
        """
        formatted = []
        
        for i, post in enumerate(posts[:config.MAX_POSTS_PER_ANALYSIS], 1):
            post_text = f"""
--- Post {i} ---
Title: {post.get('title', 'No title')}
Content: {post.get('content', 'No content')}
Type: {post.get('type', 'unknown')}
Resolved: {'Yes' if post.get('is_resolved') else 'No'}
Views: {post.get('unique_views', 0)}
"""
            
            # Add answers
            answers = post.get('answers', [])
            if answers:
                post_text += "\nAnswers:\n"
                for ans in answers:
                    post_text += f"  [{ans.get('type', 'unknown')}]: {ans.get('content', '')[:500]}\n"
            
            # Add followups (limit to first 3)
            followups = post.get('followups', [])[:3]
            if followups:
                post_text += "\nFollowups:\n"
                for fu in followups:
                    post_text += f"  - {fu.get('content', '')[:200]}\n"
            
            formatted.append(post_text)
        
        return "\n".join(formatted)
    
    def analyze_problem(self, posts: list, pset: str, problem: str) -> dict:
        """
        Analyze posts for a specific problem.
        
        Args:
            posts: List of posts for this problem
            pset: Pset identifier
            problem: Problem identifier
            
        Returns:
            Analysis dictionary
        """
        if not posts:
            return {
                "sentiment": {"score": None, "summary": "No posts to analyze"},
                "common_issues": [],
                "suggestions": [],
                "statistics": {"total_posts": 0, "resolved_count": 0, "key_themes": []}
            }
        
        posts_content = self._format_posts_for_analysis(posts)
        
        prompt = ANALYSIS_PROMPT.format(
            pset=pset,
            problem=problem,
            posts_content=posts_content
        )
        
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Extract the response content
            response_text = response.content[0].text.strip()
            
            # Parse JSON response
            # Handle potential markdown code blocks
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            
            analysis = json.loads(response_text)
            return analysis
            
        except json.JSONDecodeError as e:
            console.print(f"[red]Failed to parse LLM response as JSON: {e}[/red]")
            return {
                "error": "Failed to parse response",
                "raw_response": response_text if 'response_text' in locals() else None
            }
        except Exception as e:
            console.print(f"[red]LLM analysis failed: {e}[/red]")
            return {"error": str(e)}
    
    def analyze_all(self, categorized_posts: dict) -> dict:
        """
        Analyze all categorized posts.
        
        Args:
            categorized_posts: Hierarchical dictionary of posts
            
        Returns:
            Complete analysis dictionary
        """
        console.print("[yellow]Starting LLM analysis of all posts...[/yellow]")
        
        analysis_results = {}
        
        # Count total problems to analyze
        total_problems = sum(
            len(problems) 
            for pset, problems in categorized_posts.items() 
            if pset != "uncategorized"
        )
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Analyzing...", total=total_problems)
            
            for pset, problems in categorized_posts.items():
                if pset == "uncategorized":
                    continue
                
                analysis_results[pset] = {}
                
                for problem, posts in problems.items():
                    progress.update(
                        task, 
                        description=f"[cyan]Analyzing {pset}/{problem}..."
                    )
                    
                    analysis = self.analyze_problem(posts, pset, problem)
                    analysis_results[pset][problem] = analysis
                    
                    progress.update(task, advance=1)
        
        console.print("[green]✓ Analysis complete[/green]")
        return analysis_results
    
    def save_analysis(self, analysis: dict, filename: str = "analysis_results.json") -> Path:
        """
        Save analysis results to a JSON file.
        
        Args:
            analysis: Analysis results dictionary
            filename: Output filename
            
        Returns:
            Path to saved file
        """
        output_path = config.ANALYSIS_DIR / filename
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(analysis, f, indent=2, ensure_ascii=False)
        
        console.print(f"[green]✓ Analysis saved to {output_path}[/green]")
        return output_path
    
    def generate_report(self, analysis: dict) -> str:
        """
        Generate a human-readable report from analysis results.
        
        Args:
            analysis: Analysis results dictionary
            
        Returns:
            Markdown formatted report
        """
        report = ["# Piazza Feedback Analysis Report\n"]
        
        for pset, problems in sorted(analysis.items()):
            report.append(f"\n## {pset.upper()}\n")
            
            for problem, data in sorted(problems.items()):
                report.append(f"\n### {problem.title()}\n")
                
                if "error" in data:
                    report.append(f"*Analysis error: {data['error']}*\n")
                    continue
                
                # Sentiment
                sentiment = data.get("sentiment", {})
                score = sentiment.get("score", "N/A")
                summary = sentiment.get("summary", "")
                report.append(f"**Sentiment Score:** {score}/5\n")
                report.append(f"> {summary}\n")
                
                # Common Issues
                issues = data.get("common_issues", [])
                if issues:
                    report.append("\n**Common Issues:**\n")
                    for issue in issues:
                        severity = issue.get("severity", "medium")
                        report.append(f"- [{severity.upper()}] {issue.get('issue', '')}\n")
                
                # Suggestions
                suggestions = data.get("suggestions", [])
                if suggestions:
                    report.append("\n**Suggestions:**\n")
                    for sug in suggestions:
                        priority = sug.get("priority", "medium")
                        report.append(f"- [{priority.upper()}] {sug.get('suggestion', '')}\n")
                
                # Statistics
                stats = data.get("statistics", {})
                if stats:
                    report.append(f"\n*Posts analyzed: {stats.get('total_posts', 0)}, ")
                    report.append(f"Resolved: {stats.get('resolved_count', 0)}*\n")
        
        return "".join(report)

