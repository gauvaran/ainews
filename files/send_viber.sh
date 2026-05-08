#!/bin/bash
# send_viber.sh - Automates Viber Desktop to send a message to a group
# Requires: xvfb, xdotool, wmctrl, xclip, scrot, viber (Linux client)

GROUP_NAME="$1"
MESSAGE="$2"

if [ -z "$GROUP_NAME" ] || [ -z "$MESSAGE" ]; then
    echo "Usage: $0 'Group Name' 'Message to send'"
    exit 1
fi

DISPLAY_NUM=":99"
export DISPLAY=$DISPLAY_NUM
SCREENSHOT_DIR="/tmp/viber_debug"
mkdir -p "$SCREENSHOT_DIR"

take_screenshot() {
    local label="$1"
    scrot "$SCREENSHOT_DIR/viber_$(date +%H%M%S)_${label}.png" 2>/dev/null || true
}

# ─── 1. Start Virtual Display if not running ──────────────────────────────────
if ! pgrep -x "Xvfb" > /dev/null; then
    echo "[INFO] Starting virtual display..."
    Xvfb $DISPLAY_NUM -screen 0 1280x800x24 &
    sleep 2
fi

# ─── 2. Start Viber if not running ────────────────────────────────────────────
if ! pgrep -x "Viber" > /dev/null; then
    echo "[INFO] Starting Viber..."
    /opt/viber/Viber &

    # Poll for window instead of fixed sleep
    echo "[INFO] Waiting for Viber window (up to 30s)..."
    for i in $(seq 1 30); do
        if xdotool search --class "viber" 2>/dev/null | grep -q . || \
           xdotool search --name "Viber" 2>/dev/null | grep -q .; then
            echo "[INFO] Viber window appeared after ${i}s"
            break
        fi
        sleep 1
    done
    sleep 3  # Extra wait for UI to fully render
fi

# ─── 3. Get Viber window ID ───────────────────────────────────────────────────
WINDOW_ID=$(xdotool search --class "viber" 2>/dev/null | tail -1)
if [ -z "$WINDOW_ID" ]; then
    WINDOW_ID=$(xdotool search --name "Viber" 2>/dev/null | head -1)
fi

if [ -z "$WINDOW_ID" ]; then
    echo "[ERROR] Could not find Viber window"
    take_screenshot "ERROR_no_window"
    exit 1
fi

echo "[INFO] Found Viber window ID: $WINDOW_ID"
xdotool windowactivate --sync "$WINDOW_ID"
xdotool windowraise "$WINDOW_ID"
sleep 1
take_screenshot "01_viber_open"

# ─── 4. Search for the group ──────────────────────────────────────────────────
echo "[INFO] Searching for group: $GROUP_NAME"
xdotool key --window "$WINDOW_ID" ctrl+f
sleep 1
take_screenshot "02_search_open"

# Clear existing text and type group name
xdotool key --window "$WINDOW_ID" ctrl+a
sleep 0.2
xdotool type --clearmodifiers --delay 50 "$GROUP_NAME"
sleep 2
take_screenshot "03_search_typed"

# Use Down arrow to select first result, then Enter to open it
xdotool key --window "$WINDOW_ID" Down
sleep 0.5
xdotool key --window "$WINDOW_ID" Return
sleep 2
take_screenshot "04_group_opened"

# ─── 5. Focus the message input area ─────────────────────────────────────────
echo "[INFO] Focusing message input..."
xdotool key --window "$WINDOW_ID" Escape
sleep 0.3

# Get window geometry
GEOM=$(xdotool getwindowgeometry "$WINDOW_ID" 2>/dev/null)
WIDTH=$(echo "$GEOM" | grep "Geometry" | sed 's/.*Geometry: \([0-9]*\)x.*/\1/')
HEIGHT=$(echo "$GEOM" | grep "Geometry" | sed 's/.*Geometry: [0-9]*x\([0-9]*\).*/\1/')

if [ -n "$WIDTH" ] && [ -n "$HEIGHT" ]; then
    INPUT_X=$((WIDTH / 2))
    INPUT_Y=$((HEIGHT - 60))
    echo "[INFO] Clicking input at ${INPUT_X},${INPUT_Y} (window: ${WIDTH}x${HEIGHT})"
    xdotool mousemove --window "$WINDOW_ID" "$INPUT_X" "$INPUT_Y"
    xdotool click --window "$WINDOW_ID" 1
    sleep 0.5
else
    echo "[WARN] Could not get window geometry, clicking center-bottom fallback"
    xdotool click --window "$WINDOW_ID" 1
fi
take_screenshot "05_input_focused"

# ─── 6. Paste message via clipboard (handles Unicode and emojis) ──────────────
echo "[INFO] Copying message to clipboard..."
if echo -n "$MESSAGE" | xclip -selection clipboard 2>/dev/null; then
    echo "[INFO] Using xclip"
elif echo -n "$MESSAGE" | xsel --clipboard --input 2>/dev/null; then
    echo "[INFO] Using xsel"
else
    echo "[WARN] Clipboard tools unavailable — falling back to xdotool type"
    xdotool type --clearmodifiers --delay 20 "$MESSAGE"
    sleep 1
    take_screenshot "06_message_typed"
    echo "[INFO] Sending message..."
    xdotool key --window "$WINDOW_ID" Return
    sleep 1
    take_screenshot "07_message_sent"
    echo "[SUCCESS] Message sent to group: $GROUP_NAME"
    exit 0
fi

sleep 0.3
xdotool key --window "$WINDOW_ID" ctrl+v
sleep 1
take_screenshot "06_message_pasted"

# ─── 7. Send the message ──────────────────────────────────────────────────────
echo "[INFO] Sending message..."
xdotool key --window "$WINDOW_ID" Return
sleep 1
take_screenshot "07_message_sent"

echo "[SUCCESS] Message sent to group: $GROUP_NAME"
echo "[INFO] Debug screenshots saved to: $SCREENSHOT_DIR"
