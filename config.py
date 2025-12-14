"""
Configuration settings for the Piazza Feedback Analyzer.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Base paths
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
ANALYSIS_DIR = DATA_DIR / "analysis"

# Create directories if they don't exist
RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)

# Piazza credentials
PIAZZA_EMAIL = os.getenv("PIAZZA_EMAIL")
PIAZZA_PASSWORD = os.getenv("PIAZZA_PASSWORD")
PIAZZA_NETWORK_ID = os.getenv("PIAZZA_NETWORK_ID")

# Anthropic API
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Pset/Problem detection patterns
# These patterns are used to identify which pset/problem a post relates to
# Modify these based on your course's naming conventions
PSET_PATTERNS = [
    r"pset\s*(\d+)",           # pset1, pset 1, Pset1
    r"problem\s*set\s*(\d+)",  # problem set 1
    r"hw\s*(\d+)",             # hw1, hw 1
    r"homework\s*(\d+)",       # homework 1
    r"assignment\s*(\d+)",     # assignment 1
]

PROBLEM_PATTERNS = [
    r"(?:problem|q|question|part)\s*(\d+(?:\.\d+)?(?:[a-z])?)",  # problem 1, q1, question 1.2, part 1a
    r"(?:prob|p)\.?\s*(\d+(?:\.\d+)?(?:[a-z])?)",                # prob 1, p1, p.1
    r"\((\d+(?:\.\d+)?(?:[a-z])?)\)",                            # (1), (1a), (1.2)
]

# LLM Analysis settings
LLM_MODEL = "claude-sonnet-4-20250514"
MAX_POSTS_PER_ANALYSIS = 50  # Maximum posts to include in a single LLM call

