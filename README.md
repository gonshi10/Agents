# Earnings Agent 🤖📈

An intelligent AI-powered system that automatically monitors stock earnings, generates comprehensive summaries, and sends detailed email reports.

## 🚀 Features

- **Automated Earnings Monitoring**: Fetches earnings data for stocks in your watchlist
- **AI-Powered Analysis**: Uses OpenAI GPT-4 to generate key takeaways and insights
- **Smart API Batching**: Processes multiple tickers in a single AI call for efficiency
- **Intelligent Rate Limiting**: Built-in OpenAI API rate limiting with exponential backoff
- **Smart Email Reports**: Sends detailed, formatted emails for each earnings announcement
- **News Integration**: Fetches and filters relevant company news
- **Beat/Miss Analysis**: Automatically calculates EPS and revenue performance vs estimates

## 📋 Requirements

- Python 3.8+
- Finnhub API key (free tier available)
- OpenAI API key (GPT-4o-mini recommended)
- SMTP email access (Gmail, Outlook, etc.)

## 🛠️ Installation

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd earnings-agent
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   ```bash
   cp env.example .env
   # Edit .env with your actual API keys and settings
   ```

## ⚙️ Configuration

### Required Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `FINNHUB_API_KEY` | Your Finnhub API key | `abc123...` |
| `OPENAI_API_KEY` | Your OpenAI API key | `sk-abc123...` |
| `SMTP_USER` | Your email address | `user@gmail.com` |
| `SMTP_PASS` | Your email password/app password | `password123` |
| `EMAIL_TO` | Recipient email address | `recipient@example.com` |

### Watchlist Configuration

Create a CSV file with your stock symbols:

```csv
Symbol
AAPL
MSFT
GOOGL
NVDA
TSLA
```

## 🚀 Usage

### Basic Usage

```bash
python EarningsAgent.py
```

### Test Mode

```bash
python EarningsAgent.py --test
```

## 📧 Email Output

The system generates comprehensive email reports including:

- **Earnings Summary**: EPS and revenue vs estimates with beat/miss indicators
- **AI-Generated Key Takeaways**: 2-3 bullet points with insights per company
- **News Headlines**: Relevant same-day news and press releases
- **Data Tables**: Formatted financial metrics with visual indicators

## 🔄 Automation

### GitHub Actions (Recommended)

Create `.github/workflows/earnings-agent.yml`:

```yaml
name: Earnings Agent
on:
  schedule:
    - cron: '5 5 * * *'  # 5:05 AM UTC (12:05 AM ET)
  workflow_dispatch:  # Manual trigger

jobs:
  run-agent:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.9'
      - run: pip install -r requirements.txt
      - run: python EarningsAgent.py
        env:
          FINNHUB_API_KEY: ${{ secrets.FINNHUB_API_KEY }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          SMTP_USER: ${{ secrets.SMTP_USER }}
          SMTP_PASS: ${{ secrets.SMTP_PASS }}
          EMAIL_TO: ${{ secrets.EMAIL_TO }}
```

### Cron Job (Linux/Mac)

```bash
# Add to crontab -e
5 5 * * * cd /path/to/earnings-agent && /usr/bin/python3 EarningsAgent.py
```

## 🔍 How It Works

1. **Data Collection**: Fetches earnings calendar and company news from Finnhub
2. **Smart Batching**: Collects data for all tickers, then processes with AI in one call
3. **AI Analysis**: Generates insights for all companies using OpenAI GPT-4
4. **Email Generation**: Creates formatted HTML emails with all insights
5. **Delivery**: Sends individual emails for each earnings announcement

## 📊 API Usage

- **Finnhub**: ~2 calls per ticker (earnings + news)
- **OpenAI**: 1 call total for all tickers (smart batching)
- **Rate Limiting**: Built-in delays and exponential backoff

## 🚨 Troubleshooting

### Common Issues

1. **Missing API Keys**: Check your `.env` file
2. **SMTP Errors**: Verify email credentials and app passwords
3. **OpenAI Rate Limiting**: The system automatically handles this with smart batching
4. **No Earnings Found**: Check date logic and ticker symbols

### Debug Mode

```bash
python EarningsAgent.py --test
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## ⚠️ Disclaimer

This tool is for informational purposes only. Always verify data with official sources and consult financial professionals before making investment decisions.

---

**Happy Trading! 📈🚀**
