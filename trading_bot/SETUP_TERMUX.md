# Crypto Trading Bot — Termux (Android) Setup

**Two things you can run on Termux:**

| What | Command | Needs API keys? |
|------|---------|----------------|
| Backtest | `python backtest_cli.py` | No |
| Live bot | `python -m live.run` | Yes (`.env` file) |

The PyQt6 desktop GUI (`main.py`) does **not** work on Android — use the CLI
backtester and Telegram-controlled live bot instead.

---

## 1. Install Termux

**IMPORTANT:** Install from **F-Droid** (https://f-droid.org/packages/com.termux/),
not from Google Play. The Play Store version is outdated and broken.

- Install F-Droid, search for "Termux", install it.
- Also install **Termux:API** from F-Droid (needed for background running).

## 2. Update packages

```bash
pkg update && pkg upgrade -y
```

## 3. Install essential tools

```bash
pkg install python git openssl-tool binutils -y
```

`binutils` is needed to compile some Python native extensions on ARM.

## 4. Upgrade pip

```bash
pip install --upgrade pip
```

## 5. Get the code

```bash
cd ~
git clone https://github.com/YOUR_USER/YOUR_REPO.git
cd Crypto/trading_bot
```

## 6. Set up your API keys

Copy the example env file, then edit it with your actual keys:

```bash
cp .env.example .env
nano .env
```

Fill in your Bybit and Telegram credentials:
```
BYBIT_API_KEY=your_bybit_api_key
BYBIT_API_SECRET=your_bybit_api_secret
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
```

To exit `nano`: `Ctrl+X`, then `Y`, then `Enter`.

## 7. Install Python dependencies

```bash
pip install -r requirements.txt
```

This installs: `ccxt`, `pandas`, `numpy`, `pytz`, `python-telegram-bot`,
`pyarrow`, `feedparser`, `streamlit`, `plotly`.

---

---

## 8. Run a backtest (three ways)

### A) CLI (fast, no GUI)
```bash
python backtest_cli.py
```

### B) Streamlit web UI (recommended — interactive charts)
```bash
streamlit run streamlit_app.py
```
Opens at `http://localhost:8501` in your phone's browser.

### C) Live bot control page
With the Streamlit server running, click **Live Bot** in the sidebar to
start/stop the bot, view positions, and tail logs — all from the browser.

---

### Examples

```bash
cd ~/Crypto/trading_bot
python backtest_cli.py
```

This runs **ATR Trend-Breakout** on BTC/USDT, 4H data, 90-day lookback,
$10,000 capital — all default settings. You'll see metrics and a trade log.

### Examples

```bash
# Different symbol
python backtest_cli.py --symbol ETH/USDT

# Different strategy (5M Trend Pullback)
python backtest_cli.py --strategy trend-pullback --lookback 60

# NY Range Re-Entry with custom params
python backtest_cli.py --strategy ny-range --rr 3 --risk-percent 2

# IBR (Institutional Breakout Retest)
python backtest_cli.py --strategy ibr --symbol SOL/USDT --lookback 120

# SLC with custom params
python backtest_cli.py --strategy slc --swing-window 8 --impulse-mult 2.0

# Custom ATR params
python backtest_cli.py --strategy atr-breakout --ema-fast 20 --ema-slow 100 \
  --atr-sl-mult 3 --rr 4 --trail-activation 1.5

# Longest possible: all at once
python backtest_cli.py \
  --exchange bybit \
  --symbol BTC/USDT \
  --strategy atr-breakout \
  --lookback 180 \
  --capital 50000 \
  --rr 5 \
  --risk-percent 3 \
  --fee-rate 0.0006 \
  --ema-fast 50 --ema-slow 200 \
  --donchian-period 20 \
  --atr-period 14 \
  --atr-sl-mult 2 \
  --trail-activation 2 \
  --trail-offset 1
```

See all options:
```bash
python backtest_cli.py --help
```

### Available strategies & their timeframes

| Strategy | Timeframe | CLI name |
|----------|-----------|----------|
| ATR Trend-Breakout | 4H | `atr-breakout` |
| 5M Trend Pullback | 5M | `trend-pullback` |
| 4H NY Range Re-Entry | 5M + 4H | `ny-range` |
| IBR | 15M | `ibr` |
| SLC | 15M | `slc` |

---

## 9. First run (paper mode — safe)

```bash
python -m live.run
```

On the very first run, `config.json` is auto-created with 20 symbols and
paper mode. The bot will start printing heartbeats every 2 minutes.

Press `Ctrl+C` to stop.

> **Verify:** check `live/logs/bot.log` for details.

## 10. Switching to live mode

Once you are comfortable with paper mode:

1. Open `config.json` with nano:
   ```bash
   nano config.json
   ```
2. Change `"mode": "paper"` to `"mode": "live"`
3. Set `"capital": 100` (or your deposit amount)
4. Save and restart the bot

## 11. Running persistently (so the bot survives phone sleep)

### Option A: tmux (recommended)

```bash
pkg install tmux -y
tmux new -s bot
python -m live.run
```

Detach: `Ctrl+B` then `D`
Re-attach: `tmux attach -t bot`

### Option B: termux-wake-lock (prevents CPU sleep)

```bash
pkg install termux-api -y
termux-wake-lock crypto-bot
python -m live.run
```

Run `termux-wake-unlock crypto-bot` when you want to release it.

### Best: tmux + termux-wake-lock

```bash
termux-wake-lock crypto-bot
tmux new -s bot
python -m live.run
```

Detach with `Ctrl+B D`. The bot keeps running in the background.

## 12. Auto-start on phone boot (optional)

Create `~/.termux/boot/crypto-bot.sh`:

```bash
mkdir -p ~/.termux/boot
cat > ~/.termux/boot/crypto-bot.sh << 'EOF'
#!/data/data/com.termux/files/usr/bin/sh
termux-wake-lock crypto-bot
cd ~/Crypto/trading_bot
python -m live.run
EOF
chmod +x ~/.termux/boot/crypto-bot.sh
```

Requires the **Termux:Boot** app from F-Droid.

## 13. Logs & monitoring

- **View live logs:** `tail -f live/logs/bot.log`
- **Telegram:** Bot sends heartbeat, entry, exit, and safety alerts
- **Commands** via Telegram: `/status`, `/pause`, `/resume`, `/stop`, `/positions`

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `SSL: CERTIFICATE_VERIFY_FAILED` | `pkg install ca-certificates && update-ca-certificates` |
| `pip install` fails on ARM build | `pkg install binutils` — retry |
| Bot stops when phone sleeps | Use `termux-wake-lock` (see section 10) |
| `python-telegram-bot` ImportError | `pip install "starlette>=0.46"` |
| Config issues | Delete `config.json` and restart — it will regenerate |

## Quick start (already set up)

```bash
cd ~/Crypto/trading_bot

# Option 1: CLI backtest (no GUI)
python backtest_cli.py --symbol ETH/USDT --strategy atr-breakout

# Option 2: Streamlit web UI (backtest + live bot control)
streamlit run streamlit_app.py

# Option 3: Headless live bot (requires .env keys)
python -m live.run
```
