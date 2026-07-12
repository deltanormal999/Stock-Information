# NIFTY Mean Reversion — Free Deployment on GitHub Actions

Runs `nifty_mean_reversion.py` on a schedule using GitHub Actions (free).
It fetches ^NSEI data, runs the linear-regression mean-reversion strategy,
backtests it, then sends a text summary and the chart image to you via
Telegram — no server, no email/SMTP, no ongoing cost.

## Why GitHub Actions instead of Render

Render's Cron Jobs have a $1/month minimum. GitHub Actions is free for
public repos with no minute cap, and on private repos gives 2,000 free
minutes/month on the Free plan — this job runs a couple of minutes once a
day on weekdays (roughly 40-60 minutes/month), well inside that.

## 1. Create a Telegram bot (2 minutes)

1. Open Telegram, search for **@BotFather**, start a chat.
2. Send `/newbot`, give it a name and a username (must end in `bot`).
3. BotFather replies with a token like `123456789:AAF...` — save it, you'll
   need it in step 4.

## 2. Get your chat ID

1. Search for **@userinfobot** on Telegram, start a chat with it.
2. It immediately replies with your numeric ID — save it too.
3. Go back to **your own bot's** chat (the one you just created) and send
   it any message (e.g. "hi") — bots can't message you first.

## 3. Push this project to GitHub

Files needed in the repo root:
- `nifty_mean_reversion.py`
- `requirements.txt`
- `.github/workflows/daily-run.yml`

```
git init
git add nifty_mean_reversion.py requirements.txt .github
git commit -m "NIFTY mean reversion daily automation"
git branch -M main
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```

A **public** repo gets unlimited free Actions minutes. If you'd rather
keep it private (reasonable, since it touches your trading logic), that's
fine too — you're nowhere near the 2,000 free minute/month cap either way.

## 4. Add your Telegram credentials as repo secrets

1. On GitHub, open the repo → **Settings** → **Secrets and variables** →
   **Actions**.
2. Click **New repository secret** twice, adding:
   - `TELEGRAM_BOT_TOKEN` → the token from step 1
   - `TELEGRAM_CHAT_ID` → the ID from step 2

Secrets are encrypted and never shown in logs, so this is safe even in a
public repo.

## 5. Test it before trusting the schedule

1. On GitHub, go to the **Actions** tab → **NIFTY Mean Reversion Daily
   Run** (in the left sidebar) → **Run workflow** (this uses the
   `workflow_dispatch` trigger already included in the YAML) → **Run
   workflow** button.
2. Watch it run (takes ~1-2 minutes). Click into the run to see logs for
   each step.
3. Check your Telegram chat for the summary message + chart.

If something fails, the failing step is highlighted directly in the GitHub
Actions log — most likely causes are a typo in a secret name or a market
holiday (empty data from Yahoo Finance).

## 6. The schedule

`.github/workflows/daily-run.yml` already includes:
```yaml
schedule:
  - cron: "30 12 * * 1-5"
```
GitHub Actions cron always runs in **UTC**. 12:30 UTC = 6:00 PM IST (IST
has no DST, so this stays fixed year-round). `1-5` = Monday-Friday.

One thing to know: GitHub explicitly documents that scheduled workflows
can be delayed by a few minutes during periods of high platform load —
it's a "run at or after" schedule, not a hard real-time guarantee. Fine
for a daily report; not something to rely on to the second.

## Notes

- No server to maintain, no persistent disk needed — the chart is emailed
  via Telegram each run and also uploaded as a 14-day workflow artifact
  (visible under the run's **Summary** tab) as a backup, in case you want
  to look back at a specific day's chart.
- The script uses matplotlib's `Agg` backend (headless), required in any
  runner environment without a display.
- ^NSEI doesn't trade weekends/Indian holidays — a run on those days just
  reflects the last available close, not an error.
- Treat the signals as decision-support output from a backtest, not
  investment advice.
