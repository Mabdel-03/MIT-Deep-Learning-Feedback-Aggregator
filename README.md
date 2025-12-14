# MIT Deep Learning Feedback Aggregator

A Python tool for scraping Piazza posts and analyzing student feedback using LLM (Claude) to identify common issues, sentiment, and actionable suggestions for improving problem sets.

## Features

- **Piazza Scraper**: Fetches all posts from a Piazza course using your TA credentials
- **Smart Categorization**: Automatically categorizes posts by pset and problem number
- **LLM Analysis**: Uses Claude to analyze student feedback and generate insights
- **Comprehensive Reports**: Generates markdown reports with sentiment analysis, common issues, and suggestions

## Installation

1. Clone the repository:
```bash
git clone https://github.com/Mabdel-03/MIT-Deep-Learning-Feedback-Aggregator.git
cd MIT-Deep-Learning-Feedback-Aggregator
```

2. Create a virtual environment and install dependencies:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. Set up your credentials:
```bash
cp env_template.txt .env
# Edit .env with your credentials
```

## Configuration

Edit the `.env` file with your credentials:

```
PIAZZA_EMAIL=your_email@mit.edu
PIAZZA_PASSWORD=your_password
PIAZZA_NETWORK_ID=your_network_id
ANTHROPIC_API_KEY=your_anthropic_api_key
```

### Finding Your Network ID

Run the following command to list all your Piazza classes and their network IDs:

```bash
python main.py list-classes
```

## Usage

### List Your Piazza Classes

```bash
python main.py list-classes
```

### Scrape Posts from Piazza

```bash
# Scrape all posts
python main.py scrape

# Scrape with a limit (useful for testing)
python main.py scrape --limit 50
```

### Analyze Scraped Posts

```bash
# Analyze the latest scraped data
python main.py analyze

# Analyze only student posts
python main.py analyze --students-only

# Analyze a specific file
python main.py analyze --input categorized_posts_20241214_120000.json
```

### Run Full Pipeline

```bash
# Scrape and analyze in one command
python main.py full

# With a post limit
python main.py full --limit 100
```

## Output

### Scraped Data

Data is saved to the `data/raw/` directory:
- `all_posts_<timestamp>.json`: All posts in flat format
- `categorized_posts_<timestamp>.json`: Posts organized by pset/problem
- `categorized_posts_latest.json`: Latest categorized data (for easy access)

### Analysis Results

Analysis is saved to the `data/analysis/` directory:
- `analysis_<timestamp>.json`: Full analysis results in JSON format
- `analysis_latest.json`: Latest analysis (for easy access)
- `report_<timestamp>.md`: Human-readable markdown report

## Data Structure

### Categorized Posts

```json
{
  "pset1": {
    "problem1": [
      {
        "id": "...",
        "title": "Question about gradient",
        "content": "...",
        "answers": [...],
        "followups": [...],
        "is_resolved": true
      }
    ],
    "problem2": [...],
    "general": [...]
  },
  "pset2": {...}
}
```

### Analysis Results

```json
{
  "pset1": {
    "problem1": {
      "sentiment": {
        "score": 3.2,
        "summary": "Mixed - students found concept interesting but struggled with..."
      },
      "common_issues": [
        {
          "issue": "Confusion about gradient computation",
          "frequency": "5 students",
          "severity": "high"
        }
      ],
      "suggestions": [
        {
          "suggestion": "Add worked example for gradient computation",
          "priority": "high",
          "effort": "medium"
        }
      ],
      "statistics": {
        "total_posts": 15,
        "resolved_count": 12,
        "key_themes": ["gradients", "backpropagation"]
      }
    }
  }
}
```

## Customization

### Pset/Problem Detection Patterns

Edit `config.py` to customize how posts are categorized:

```python
PSET_PATTERNS = [
    r"pset\s*(\d+)",           # pset1, pset 1
    r"hw\s*(\d+)",             # hw1, hw 1
    # Add your own patterns
]

PROBLEM_PATTERNS = [
    r"(?:problem|q|question)\s*(\d+)",
    # Add your own patterns
]
```

## Privacy & Security

- Your credentials are stored locally in `.env` (gitignored)
- Student names are not stored - only role (student/TA/instructor)
- All data is stored locally - nothing is sent externally except to the LLM API

## License

MIT License

