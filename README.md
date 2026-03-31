# 🤖 AI Code Review Bot

Automated code review powered by **Claude AI**. Receives GitHub pull request webhooks, analyzes diffs for bugs, security vulnerabilities, and code quality issues, and posts structured review comments directly on the PR.

## Architecture

```
GitHub PR Webhook
       │
       ▼
┌─────────────────┐     ┌──────────────────┐     ┌───────────────┐
│  API Gateway /   │────▶│  FastAPI App      │────▶│  Anthropic    │
│  Lambda          │     │  (Webhook Handler)│     │  Claude API   │
└─────────────────┘     └──────────────────┘     └───────────────┘
                               │       │
                               ▼       ▼
                        ┌──────────┐  ┌──────────────┐
                        │ DynamoDB │  │ GitHub API   │
                        │ (Reviews)│  │ (PR Comments)│
                        └──────────┘  └──────────────┘
```

## Features

- **Webhook-driven**: Automatically reviews PRs on open, sync, or reopen events
- **Structured analysis**: Categorizes findings by severity (critical/warning/suggestion/nitpick) and type (bug/security/performance/quality)
- **Inline comments**: Posts formatted Markdown reviews directly on GitHub PRs
- **Review persistence**: Stores all reviews in DynamoDB for analytics and audit trails
- **Manual trigger**: REST endpoint to trigger reviews on-demand for any PR
- **Repository stats**: Aggregated review metrics per repository
- **Infrastructure as Code**: Full AWS CDK stack for one-command deployment

## Tech Stack

| Layer            | Technology                          |
|------------------|-------------------------------------|
| Runtime          | Python 3.12, FastAPI, Uvicorn       |
| AI               | Anthropic Claude API                |
| Storage          | AWS DynamoDB                        |
| Infrastructure   | AWS CDK, Lambda, API Gateway        |
| Containerization | Docker, Docker Compose              |
| HTTP Client      | httpx (async)                       |
| Testing          | pytest                              |

## Quick Start

### Prerequisites
- Python 3.12+
- Docker & Docker Compose
- An [Anthropic API key](https://console.anthropic.com/)
- A [GitHub Personal Access Token](https://github.com/settings/tokens) with `repo` scope

### Local Development

```bash
# Clone the repo
git clone https://github.com/your-username/ai-code-review-bot.git
cd ai-code-review-bot

# Set up environment
cp .env.example .env
# Edit .env with your API keys

# Run with Docker Compose (includes DynamoDB Local)
docker compose up --build

# Or run directly
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Run Tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

### Set Up GitHub Webhook

1. Go to your repo → **Settings** → **Webhooks** → **Add webhook**
2. Payload URL: `https://your-domain.com/webhook/github`
3. Content type: `application/json`
4. Secret: (same as `GITHUB_WEBHOOK_SECRET` in `.env`)
5. Events: Select **Pull requests**

## API Endpoints

| Method | Path                    | Description                              |
|--------|-------------------------|------------------------------------------|
| GET    | `/health`               | Health check                             |
| POST   | `/webhook/github`       | GitHub webhook receiver                  |
| POST   | `/review`               | Manual review trigger                    |
| GET    | `/stats/{owner}/{repo}` | Review statistics for a repository       |

### Manual Review

```bash
curl -X POST http://localhost:8000/review \
  -H "Content-Type: application/json" \
  -d '{"repo": "owner/repo", "pr_number": 42}'
```

## Deploy to AWS

The project includes a CDK stack that deploys Lambda + API Gateway + DynamoDB.

```bash
cd infra
pip install aws-cdk-lib constructs
cdk bootstrap   # First time only
cdk deploy
```

Set Lambda environment variables for `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, and `GITHUB_WEBHOOK_SECRET` via AWS Console or CDK context.

## Project Structure

```
ai-code-review-bot/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app & webhook endpoints
│   ├── config.py            # Environment-based configuration
│   ├── reviewer.py          # Claude AI review engine
│   ├── github_client.py     # GitHub API integration
│   └── db.py                # DynamoDB data access layer
├── infra/
│   └── stack.py             # AWS CDK infrastructure
├── tests/
│   └── test_bot.py          # Unit & integration tests
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── README.md
```

## How It Works

1. A developer opens or updates a pull request
2. GitHub sends a webhook event to the bot
3. The bot fetches the PR diff via GitHub API
4. Code diffs are sent to Claude with a structured review prompt
5. Claude returns findings categorized by severity and type
6. The bot formats findings as Markdown and posts them as a PR comment
7. Review metadata is persisted to DynamoDB for analytics

## License

MIT
