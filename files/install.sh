#!/bin/bash
# install.sh - Setup script for Oracle Cloud Ubuntu VM
# Run once with: bash install.sh

set -e
echo "======================================"
echo "  AI News Bot (Gmail) - Setup Script"
echo "======================================"

# ─── 1. Update system ─────────────────────────────────────────────────────────
echo ""
echo "[1/6] Updating system..."
sudo apt-get update -y
sudo apt-get upgrade -y

# ─── 2. Install dependencies ──────────────────────────────────────────────────
echo ""
echo "[2/6] Installing dependencies..."
sudo apt-get install -y \
    python3 \
    python3-pip \
    curl

# ─── 3. Install Python packages ───────────────────────────────────────────────
echo ""
echo "[3/6] Installing Python packages..."
pip3 install feedparser --break-system-packages 2>/dev/null || pip3 install feedparser

# ─── 4. Set Gmail App Password ────────────────────────────────────────────────
echo ""
echo "[4/6] Gmail App Password setup..."
echo "      Go to: myaccount.google.com → Security → 2-Step Verification → App passwords"
echo "      Then set: export EMAIL_PASSWORD='xxxx xxxx xxxx xxxx'"

# ─── 5. Make scripts executable ───────────────────────────────────────────────
echo ""
echo "[5/6] Setting permissions..."
chmod +x ai_news_bot.py

# ─── 6. Setup cron job (7:30 AM GMT+7 = 00:30 UTC) ───────────────────────────
echo ""
echo "[6/6] Setting up cron job..."
SCRIPT_DIR=$(pwd)
CRON_JOB="30 0 * * * EMAIL_PASSWORD='YOUR_APP_PASSWORD' cd $SCRIPT_DIR && python3 ai_news_bot.py >> bot.log 2>&1"

# Add to crontab if not already there
(crontab -l 2>/dev/null | grep -v "ai_news_bot"; echo "$CRON_JOB") | crontab -

echo ""
echo "======================================"
echo "  ✅ Installation complete!"
echo "======================================"
echo ""
echo "NEXT STEPS:"
echo ""
echo "  1. Generate a Gmail App Password:"
echo "     myaccount.google.com → Security → 2-Step Verification → App passwords"
echo ""
echo "  2. Set env var (add to ~/.bashrc or cron environment):"
echo "     export EMAIL_PASSWORD='xxxx xxxx xxxx xxxx'"
echo ""
echo "  3. Test the bot:"
echo "     EMAIL_PASSWORD='your-app-password' python3 ai_news_bot.py"
echo ""
echo "  4. Bot will auto-run daily at 7:30 AM GMT+7 (00:30 UTC)"
echo "     Check logs: tail -f bot.log"
echo ""
