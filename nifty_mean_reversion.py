"""
NIFTY Linear-Regression Mean-Reversion Strategy — Daily Automation
-------------------------------------------------------------------
Runs the strategy, backtests it, saves a chart, builds a text summary,
and emails both to you. Designed to be run headlessly by cron / Task
Scheduler at 6pm on weekdays — no plt.show(), no interactive prompts.

SETUP (one-time):
1. pip install -r requirements.txt
2. Set these environment variables (see README.md for how, per platform):
     TELEGRAM_BOT_TOKEN  - token from @BotFather
     TELEGRAM_CHAT_ID    - your chat id (from @userinfobot)
3. Test manually: python nifty_mean_reversion.py
4. Deploy as a Render Cron Job (see README.md).

Logs every run to run_log.txt in this same folder so you can check
what happened on days you don't see a message (e.g. market holiday,
data fetch failure).
"""

import os
import sys
import logging
import traceback
from datetime import datetime

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # headless backend — required for cron/scheduled runs, no display needed
import matplotlib.pyplot as plt
import yfinance as yf
import requests
from sklearn.linear_model import LinearRegression
import warnings

warnings.simplefilter(action="ignore", category=pd.errors.PerformanceWarning)

# ---------------------------------------------------------------- config
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CHART_PATH = os.path.join(SCRIPT_DIR, "latest_chart.png")
LOG_PATH = os.path.join(SCRIPT_DIR, "run_log.txt")

TICKER = "^NSEI"          # NSE Nifty 50 Index
START_DATE = "2020-01-01"
WINDOW = 50
THRESHOLD = 2
INITIAL_CAPITAL = 10000
PLOT_LAST_N_DAYS = 90

logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


# ---------------------------------------------------------------- data
def fetch_stock_data(ticker, start_date, end_date):
    data = yf.download(ticker, start=start_date, end=end_date, progress=False)
    if data.empty:
        raise ValueError(f"No data returned for {ticker} — market may be closed or ticker invalid.")
    if isinstance(data.columns, pd.MultiIndex):
        return data["Close"][ticker]
    return data["Close"]


# ---------------------------------------------------------------- strategy
def linear_regression_mean_reversion_strategy(prices, window=50, threshold=2):
    signals = pd.DataFrame(index=prices.index)
    signals["price"] = prices
    signals["regression_line"] = np.nan
    signals["standard_error"] = np.nan
    signals["deviation"] = np.nan
    signals["upper_2se"] = np.nan
    signals["lower_2se"] = np.nan

    for i in range(window, len(prices)):
        y = prices.iloc[i - window:i].values.reshape(-1, 1)
        X = np.arange(window).reshape(-1, 1)
        model = LinearRegression().fit(X, y)

        regression_line = model.predict(np.array([[window - 1]]))[0][0]

        residuals = y - model.predict(X)
        residual_sum_of_squares = np.sum(residuals ** 2)
        standard_error = np.sqrt(residual_sum_of_squares / (window - 2))

        current_date = signals.index[i]
        signals.loc[current_date, "regression_line"] = regression_line
        signals.loc[current_date, "standard_error"] = standard_error
        signals.loc[current_date, "deviation"] = signals["price"].iloc[i] - regression_line
        signals.loc[current_date, "upper_2se"] = regression_line + 2 * standard_error
        signals.loc[current_date, "lower_2se"] = regression_line - 2 * standard_error

    signals["buy_signal"] = signals["deviation"] < -threshold * signals["standard_error"]
    signals["sell_signal"] = signals["deviation"] > threshold * signals["standard_error"]

    return signals.dropna()


# ---------------------------------------------------------------- backtest
def backtest_strategy(signals, initial_capital=10000):
    positions = pd.DataFrame(index=signals.index).fillna(0.0)
    portfolio = pd.DataFrame(index=signals.index).fillna(0.0)

    positions["stock"] = 0.0
    current_position = 0.0

    for i in range(1, len(signals)):
        if signals["buy_signal"].iloc[i]:
            current_position = initial_capital // signals["price"].iloc[i]
        elif signals["sell_signal"].iloc[i]:
            current_position = 0.0
        positions.loc[positions.index[i], "stock"] = current_position

    portfolio["positions"] = positions["stock"] * signals["price"]
    trade_flows = positions["stock"].diff().fillna(0.0) * signals["price"]
    portfolio["cash"] = initial_capital - trade_flows.cumsum()
    portfolio["total"] = portfolio["positions"] + portfolio["cash"]

    return portfolio


# ---------------------------------------------------------------- chart
def save_chart(signals, portfolio, path, last_n_days=90):
    view_signals = signals.iloc[-last_n_days:]
    view_portfolio = portfolio.iloc[-last_n_days:]

    fig, (ax1, ax2) = plt.subplots(2, figsize=(12, 8))

    ax1.plot(view_signals.index, view_signals["price"], label="Price")
    ax1.plot(view_signals.index, view_signals["regression_line"], label="Regression Line", color="orange")
    ax1.fill_between(
        view_signals.index,
        view_signals["lower_2se"],
        view_signals["upper_2se"],
        color="lightgrey", label="2 SE Band",
    )

    buy_dates = view_signals[view_signals["buy_signal"]].index
    ax1.scatter(buy_dates, view_signals.loc[buy_dates, "price"],
                label="Buy Signal", marker="^", color="green", s=100, zorder=5)

    sell_dates = view_signals[view_signals["sell_signal"]].index
    ax1.scatter(sell_dates, view_signals.loc[sell_dates, "price"],
                label="Sell Signal", marker="v", color="red", s=100, zorder=5)

    ax1.legend()
    ax1.set_title(f"{TICKER} Linear Regression Mean Reversion (Last {last_n_days} Days)")
    ax1.grid(True, alpha=0.3)

    ax2.plot(view_portfolio.index, view_portfolio["total"], label="Portfolio Value", color="purple")
    ax2.set_title(f"Portfolio Value (Last {last_n_days} Days)")
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------- summary
def build_text_summary(signals, portfolio):
    latest = signals.iloc[-1]
    latest_date = signals.index[-1].strftime("%Y-%m-%d")
    portfolio_value = portfolio["total"].iloc[-1]
    portfolio_start = portfolio["total"].iloc[0]
    pnl_pct = (portfolio_value / portfolio_start - 1) * 100

    if latest["buy_signal"]:
        signal_text = "BUY signal (price below regression band)"
    elif latest["sell_signal"]:
        signal_text = "SELL signal (price above regression band)"
    else:
        signal_text = "No signal (price within band)"

    lines = [
        f"NIFTY Mean Reversion Strategy — {latest_date}",
        "=" * 50,
        f"Current Price:      {latest['price']:.2f}",
        f"Regression Price:   {latest['regression_line']:.2f}",
        f"Standard Error:     {latest['standard_error']:.2f}",
        f"Upper 2SE Band:     {latest['upper_2se']:.2f}",
        f"Lower 2SE Band:     {latest['lower_2se']:.2f}",
        f"Today's Signal:     {signal_text}",
        "",
        f"Backtest Portfolio Value: {portfolio_value:,.2f} (started at {portfolio_start:,.2f})",
        f"Cumulative P&L: {pnl_pct:+.2f}%",
        "",
        "Recent signals (last 10 trading days):",
    ]

    recent = signals.iloc[-10:][["price", "regression_line", "buy_signal", "sell_signal"]]
    for idx, row in recent.iterrows():
        tag = "BUY" if row["buy_signal"] else ("SELL" if row["sell_signal"] else "-")
        lines.append(f"  {idx.strftime('%Y-%m-%d')}  price={row['price']:.2f}  reg={row['regression_line']:.2f}  [{tag}]")

    return "\n".join(lines)


# ---------------------------------------------------------------- telegram
def _telegram_creds():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise EnvironmentError(
            "Missing TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID environment variables. "
            "See README.md for setup."
        )
    return token, chat_id


def send_telegram_message(text):
    token, chat_id = _telegram_creds()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    # Telegram messages cap at 4096 chars; truncate defensively
    resp = requests.post(url, data={"chat_id": chat_id, "text": text[:4000]}, timeout=30)
    resp.raise_for_status()


def send_telegram_photo(photo_path, caption=""):
    token, chat_id = _telegram_creds()
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    # Telegram photo captions cap at 1024 chars; truncate defensively
    with open(photo_path, "rb") as f:
        resp = requests.post(
            url,
            data={"chat_id": chat_id, "caption": caption[:1000]},
            files={"photo": f},
            timeout=60,
        )
    resp.raise_for_status()


# ---------------------------------------------------------------- main
def main():
    logging.info("Run started.")
    try:
        end_date = datetime.today().strftime("%Y-%m-%d")
        prices = fetch_stock_data(TICKER, START_DATE, end_date)
        signals = linear_regression_mean_reversion_strategy(prices, WINDOW, THRESHOLD)
        portfolio = backtest_strategy(signals, INITIAL_CAPITAL)

        save_chart(signals, portfolio, CHART_PATH, PLOT_LAST_N_DAYS)
        summary = build_text_summary(signals, portfolio)

        send_telegram_message(summary)
        send_telegram_photo(CHART_PATH, caption=f"{TICKER} chart — {datetime.today().strftime('%Y-%m-%d')}")

        logging.info("Run completed successfully. Telegram message + chart sent.")
        print(summary)
        print(f"\nChart saved to {CHART_PATH}. Telegram message sent.")

    except Exception as e:
        logging.error(f"Run failed: {e}\n{traceback.format_exc()}")
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
