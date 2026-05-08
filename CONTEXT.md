# 🤖 Viber AI News Bot — Project Context for Claude CLI

Use this file to continue building the project in Claude Code CLI.
Start with: `claude` then say **"read CONTEXT.md and continue the project"**

---

## 📌 Project Goal

Automatically post **daily AI news** to a **Viber group** at **7:30 AM GMT+7**, completely **free**.

---

## 🏗️ Architecture

```
Oracle Cloud Free VM (Ubuntu 22.04)
  └── Xvfb (virtual display :99)
      └── Viber Linux Desktop (logged in manually once)
          └── xdotool (UI automation)
              └── Python script sends message
                  └── cron job at 00:30 UTC = 7:30 AM GMT+7
```

**News source:** Google News RSS feed (free, no API key)
**Scheduler:** Linux cron
**Cloud:** Oracle Cloud Always Free Tier ($0/month forever)

---

## 📁 Files Already Created

| File | Purpose | Status |
|---|---|---|
| `install.sh` | One-time setup on VM | ✅ Done |
| `fetch_news.py` | Fetches AI news from Google News RSS | ✅ Done |
| `send_viber.sh` | Automates Viber desktop UI via xdotool | ✅ Done |
| `ai_news_bot.py` | Main runner: fetch + send | ✅ Done |
| `SETUP_GUIDE.md` | Full setup instructions | ✅ Done |

---

## ⚙️ Key Config (needs user input)

In `ai_news_bot.py`:
```python
VIBER_GROUP_NAME = "YOUR_GROUP_NAME_HERE"   # ← User must change this
```

---

## 🔧 How It Works

### fetch_news.py
- Calls Google News RSS: `https://news.google.com/rss/search?q=artificial+intelligence+AI`
- Uses `feedparser` library (pip install feedparser)
- Returns formatted message with 5 top AI headlines
- Message includes title, source, and link for each article

### send_viber.sh
- Starts Xvfb virtual display on `:99` if not running
- Starts Viber if not running
- Uses `xdotool` to:
  1. Activate Viber window
  2. Press `Ctrl+F` to search
  3. Type group name
  4. Press Enter to open group
  5. Click message input area
  6. Type the news message
  7. Press Enter to send

### ai_news_bot.py
- Calls `fetch_news.py` to get news
- Calls `send_viber.sh` with group name + message
- Logs everything to `bot.log`

### Cron Job
```
30 0 * * * cd ~/viber-news-bot && python3 ai_news_bot.py >> bot.log 2>&1
```

---

## 🚧 Known Issues / What Needs Work

1. **Viber search UX** — xdotool search may not reliably find the group if Viber UI changes. May need screenshot-based detection or coordinate calibration.

2. **Message input click coordinates** — Uses window geometry from xdotool; may need adjustment if Viber toolbar height differs on VM.

3. ~~**Viber startup time** — `sleep 10` after starting Viber may be too short/long~~ — **Fixed:** now polls for the window (up to 30s) instead of fixed sleep.

4. ~~**Special characters in news titles** — xdotool `type` breaks on Unicode~~ — **Fixed:** message is now copied to clipboard with `xclip` and pasted via Ctrl+V; falls back to xdotool type only if xclip/xsel unavailable.

5. **Group search reliability** — After Ctrl+F, uses Down arrow to select first result rather than pressing Enter immediately; may still fail if Viber opens a different search UI.

---

## 📋 Pending Tasks

- [ ] Test `send_viber.sh` on actual Oracle Cloud VM
- [ ] Calibrate click coordinates for Viber message input box
- ~~[ ] Add retry logic if message fails to send~~ — **Done:** 3 retries with 15s backoff in `ai_news_bot.py`
- ~~[ ] Add screenshot capture for debugging~~ — **Done:** screenshots saved to `/tmp/viber_debug/` at each automation step
- [ ] Handle Viber session expiry / re-login
- [ ] Add option to customize number of news items (currently 5)
- [ ] Add Vietnamese language option for news digest header
- [ ] Test with actual Viber group name containing spaces/special chars

---

## 🛠️ Tech Stack

- **Python 3** — main scripting language
- **feedparser** — RSS feed parsing
- **xdotool** — X11 UI automation
- **Xvfb** — virtual framebuffer (headless display)
- **wmctrl** — window management
- **bash** — shell scripting
- **cron** — task scheduling

---

## 🖥️ VM Details

- **Provider:** Oracle Cloud Always Free
- **OS:** Ubuntu 22.04 LTS
- **Shape:** VM.Standard.E2.1.Micro (1 OCPU, 1GB RAM)
- **Viber path:** `/opt/viber/Viber`
- **Display:** `:99`
- **Bot directory:** `~/viber-news-bot/`

---

## 💬 Sample Output Message

```
🤖 AI NEWS DIGEST
📅 30 Apr 2026 | 7:30 AM
──────────────────────────────

🔹 OpenAI Releases GPT-5 With Multimodal Reasoning
   📰 The Verge
   🔗 https://news.google.com/...

🔹 Google DeepMind Breakthrough in Robotics AI
   📰 BBC Technology
   🔗 https://news.google.com/...

🔹 Meta Open Sources New LLaMA Model
   📰 TechCrunch
   🔗 https://news.google.com/...

──────────────────────────────
💡 Stay ahead in AI!
```

---

## 🔗 References

- Oracle Cloud Free Tier: https://www.oracle.com/cloud/free/
- Viber Linux Download: https://download.cdn.viber.com/desktop/Linux/viber.deb
- xdotool docs: https://www.semicomplete.com/projects/xdotool/
- Google News RSS: https://news.google.com/rss/search?q=artificial+intelligence

---

*Continue from where we left off. Next: test on Oracle Cloud VM, calibrate click coordinates, and handle Viber session expiry.*
