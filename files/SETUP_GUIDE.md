# 🤖 Viber AI News Bot — Complete Setup Guide

**Free daily AI news → Viber group, every 7:30 AM GMT+7**
Uses: Oracle Cloud Free VM + Viber Linux + UI Automation

---

## What You'll Need

- Oracle Cloud free account (forever free tier)
- Your phone (to log into Viber once)
- ~1 hour of setup time

---

## STEP 1 — Create Oracle Cloud Free VM

1. Go to **cloud.oracle.com** → Sign up (free, no credit card charged)
2. Go to **Compute → Instances → Create Instance**
3. Settings:
   - **Image:** Ubuntu 22.04
   - **Shape:** VM.Standard.E2.1.Micro *(Always Free)*
   - **Storage:** 50GB *(Always Free)*
4. Download your **SSH private key** when prompted
5. Click **Create** and wait ~2 minutes

---

## STEP 2 — Connect to Your VM

```bash
# From your PC terminal:
ssh -i your-private-key.key ubuntu@YOUR_VM_IP
```

*(Replace YOUR_VM_IP with the public IP shown in Oracle Cloud)*

---

## STEP 3 — Upload and Run Setup Script

```bash
# On your VM, create the bot folder
mkdir ~/viber-news-bot && cd ~/viber-news-bot

# Upload all files (run this from your PC):
scp -i your-key.key install.sh fetch_news.py ai_news_bot.py send_viber.sh ubuntu@YOUR_VM_IP:~/viber-news-bot/

# Back on VM — run installer:
cd ~/viber-news-bot
bash install.sh
```

---

## STEP 4 — Login to Viber (One-Time)

You need to log in to Viber visually once. We use **x11vnc** to see the screen remotely.

### On VM:
```bash
# Start virtual display
Xvfb :99 -screen 0 1280x800x24 &

# Start VNC server so you can see the screen
x11vnc -display :99 -nopw -listen localhost -xkb &

# Start Viber
DISPLAY=:99 /opt/viber/Viber &
```

### On Your PC:
```bash
# Create SSH tunnel to VNC
ssh -L 5900:localhost:5900 -i your-key.key ubuntu@YOUR_VM_IP
```

Then open a **VNC viewer** (like RealVNC or TigerVNC) and connect to `localhost:5900`

You'll see Viber — **log in with your phone number** and complete verification. This is done only once!

---

## STEP 5 — Configure Your Group Name

```bash
nano ~/viber-news-bot/ai_news_bot.py
```

Find this line and change it to your **exact** Viber group name:
```python
VIBER_GROUP_NAME = "YOUR_GROUP_NAME_HERE"
```

Save with `Ctrl+O` then `Enter`, exit with `Ctrl+X`

---

## STEP 6 — Test the Bot

```bash
cd ~/viber-news-bot
python3 ai_news_bot.py
```

Check your Viber group — you should see the AI news message arrive! ✅

---

## STEP 7 — Verify Cron Schedule

The installer already added the cron job. Verify it:

```bash
crontab -l
```

You should see:
```
30 0 * * * cd /home/ubuntu/viber-news-bot && python3 ai_news_bot.py >> bot.log 2>&1
```

This runs at **00:30 UTC = 7:30 AM GMT+7** every day. ✅

---

## Monitoring

```bash
# Watch live logs
tail -f ~/viber-news-bot/bot.log

# Check last 20 lines
tail -20 ~/viber-news-bot/bot.log
```

---

## Troubleshooting

| Problem | Solution |
|---|---|
| Viber can't find group | Make sure group name matches exactly (case sensitive) |
| Viber not starting | Check `ps aux \| grep Viber`, restart with `DISPLAY=:99 /opt/viber/Viber &` |
| Message not sent | Run manually and check `bot.log` for errors |
| VM stops working | Oracle free tier is always on — check Oracle Cloud console |

---

## Sample Message Output

```
🤖 AI NEWS DIGEST
📅 30 Apr 2026 | 7:30 AM
──────────────────────────────

🔹 OpenAI Releases New Model With Improved Reasoning
   📰 The Verge
   🔗 https://...

🔹 Google DeepMind Announces Breakthrough in Protein Folding
   📰 BBC Technology
   🔗 https://...

🔹 Meta AI Launches Open Source Language Model
   📰 TechCrunch
   🔗 https://...

──────────────────────────────
💡 Stay ahead in AI!
```

---

## Files Overview

| File | Purpose |
|---|---|
| `install.sh` | One-time setup script |
| `fetch_news.py` | Fetches AI news from Google News RSS |
| `send_viber.sh` | Automates Viber desktop UI to send message |
| `ai_news_bot.py` | Main runner — combines fetch + send |
| `bot.log` | Auto-generated daily logs |

---

*Built for Oracle Cloud Always Free Tier — costs $0 forever.*
