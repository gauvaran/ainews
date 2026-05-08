#!/usr/bin/env python3
"""
ai_news_bot.py - Fetch AI news and send as HTML email via Gmail SMTP
"""

import smtplib
import sys
import os
import re
import time
import logging
import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr
from html import escape as h
import re as _re

# Load .env before importing fetch_news so env vars are available at module level
_env_file = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env_file):
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

from fetch_news import fetch_ai_news

# ─── CONFIG ───────────────────────────────────────────────────────────────────
EMAIL_FROM     = os.environ.get("EMAIL_FROM", "")
EMAIL_TO       = os.environ.get("EMAIL_TO",   "")
EMAIL_BCC      = os.environ.get("EMAIL_BCC",  "")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "")
SMTP_HOST      = "smtp.gmail.com"
SMTP_PORT      = 587
MAX_RETRIES    = 3
RETRY_DELAY    = 15
LOG_FILE       = os.path.join(os.path.dirname(__file__), "bot.log")
# ──────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)]
)


def md_to_html(text):
    """Convert Groq Markdown output to safe inline HTML for email."""
    # 1. Escape HTML special chars first
    text = h(text)
    # 2. Code blocks (```...```) → <pre><code>
    text = _re.sub(
        r'```(?:\w+)?\n?(.*?)```',
        lambda m: f'<pre style="background:#F3F4F6;color:#1F2937;padding:10px 14px;border:1px solid #D1D5DB;border-radius:4px;font-size:12px;overflow-x:auto;margin:8px 0;font-family:Consolas,Courier New,monospace;">{m.group(1).strip()}</pre>',
        text, flags=_re.DOTALL
    )
    # 3. Inline code → <code>
    text = _re.sub(r'`([^`]+)`', r'<code style="background:#F3F4F6;color:#1F2937;border:1px solid #D1D5DB;padding:1px 5px;border-radius:3px;font-size:12px;font-family:Consolas,Courier New,monospace;">\1</code>', text)
    # 4. **bold**
    text = _re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    # 5. *italic*
    text = _re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    # 6. ### / ## / # headings → bold line
    text = _re.sub(r'^#{1,3}\s+(.+)$', r'<strong style="font-size:14px;">\1</strong>', text, flags=_re.MULTILINE)
    # 7. Bullet points: - item or * item
    text = _re.sub(r'^[\-\*]\s+(.+)$', r'&nbsp;&nbsp;&#8226;&nbsp;\1', text, flags=_re.MULTILINE)
    # 8. Blank lines → paragraph break
    text = _re.sub(r'\n{2,}', '</p><p style="margin:8px 0;font-size:13px;color:#333;line-height:1.8;">', text)
    # 9. Single newlines → <br>
    text = text.replace('\n', '<br>')
    # 10. Wrap in paragraph
    text = f'<p style="margin:0;font-size:13px;color:#333;line-height:1.8;">{text}</p>'
    return text


def build_html(data):
    quote    = data["quote"]
    articles = data["articles"]
    date_str = data["date"]
    source   = "Google News · Groq AI" if data.get("groq") else "Google News"

    # ── Quote block ──────────────────────────────────────────────────────────
    vi_line = ""
    if quote.get("vi") and quote["vi"] != quote["foreign"]:
        vi_line = f'<p style="margin:6px 0 0;font-size:13px;color:#444444;line-height:1.5;">&nbsp;&nbsp;&nbsp;&#8618;&nbsp;{h(quote["vi"])}</p>'
    explain_line = ""
    if quote.get("explain"):
        explain_line = f'<p style="margin:8px 0 0;font-size:12px;color:#5A6A7A;font-style:italic;line-height:1.5;font-family:Arial,sans-serif;">&#128161;&nbsp;{h(quote["explain"])}</p>'

    # ── Tips block ───────────────────────────────────────────────────────────
    tips_html = ""
    if data.get("tips"):
        tips_html = f"""
  <tr>
    <td bgcolor="#FFFBEB" style="background-color:#FFFBEB;padding:20px 30px;border-top:3px solid #D97706;">
      <p style="margin:0 0 12px;font-size:11px;color:#D97706;letter-spacing:1px;font-family:Arial,sans-serif;text-transform:uppercase;font-weight:bold;">
        &#9889;&nbsp;Tips &amp; Tricks cho Dev
      </p>
      {md_to_html(data["tips"])}
    </td>
  </tr>"""

    # ── Lesson block ─────────────────────────────────────────────────────────
    lesson_html = ""
    if data.get("lesson"):
        lesson_html = f"""
  <tr>
    <td bgcolor="#F0FFF4" style="background-color:#F0FFF4;padding:20px 30px;border-top:3px solid #2E7D32;">
      <p style="margin:0 0 12px;font-size:11px;color:#2E7D32;letter-spacing:1px;font-family:Arial,sans-serif;text-transform:uppercase;font-weight:bold;">
        &#128218;&nbsp;B&#224;i h&#7885;c AI h&#244;m nay cho Dev
      </p>
      {md_to_html(data["lesson"])}
    </td>
  </tr>"""

    # ── Article rows ─────────────────────────────────────────────────────────
    articles_html = ""
    for i, art in enumerate(articles, 1):
        title_display = h(art["title_vi"] or art["title_en"])
        summary_block = ""
        if art.get("summary"):
            summary_block = f"""
            <tr>
              <td colspan="2" style="padding:10px 0 0 44px;">
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                  <tr>
                    <td bgcolor="#F0F7FF" style="background-color:#F0F7FF;padding:12px 14px;border-left:3px solid #0066CC;">
                      <p style="margin:0;font-size:13px;color:#333333;line-height:1.7;">{h(art["summary"])}</p>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>"""

        publisher_html = f'<span style="color:#555555;">&#128240;&nbsp;{h(art["publisher"])}</span>&nbsp;&nbsp;&nbsp;' if art["publisher"] else ""
        link_html = f'<a href="{h(art["link"], quote=True)}" style="color:#0066CC;text-decoration:none;font-size:12px;">&#128279;&nbsp;Đọc bài viết &#8594;</a>' if art["link"] else ""

        articles_html += f"""
          <tr>
            <td bgcolor="#FFFFFF" style="background-color:#FFFFFF;padding:20px 30px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td width="32" valign="top" style="padding-right:12px;padding-top:2px;">
                    <table role="presentation" cellpadding="0" cellspacing="0">
                      <tr>
                        <td bgcolor="#003087" width="28" height="28" align="center" valign="middle"
                            style="background-color:#003087;width:28px;height:28px;border-radius:14px;text-align:center;vertical-align:middle;">
                          <span style="color:#FFFFFF;font-size:13px;font-weight:bold;font-family:Arial,sans-serif;">{i}</span>
                        </td>
                      </tr>
                    </table>
                  </td>
                  <td valign="top">
                    <p style="margin:0 0 4px;font-size:16px;font-weight:bold;color:#003087;line-height:1.35;font-family:Arial,sans-serif;">{title_display}</p>
                    <p style="margin:0 0 8px;font-size:12px;color:#999999;font-style:italic;font-family:Arial,sans-serif;">&#127468;&#127463;&nbsp;{h(art["title_en"])}</p>
                    <p style="margin:0;font-size:12px;font-family:Arial,sans-serif;">{publisher_html}{link_html}</p>
                  </td>
                </tr>
                {summary_block}
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding:0 30px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr><td height="1" bgcolor="#E8ECF0" style="background-color:#E8ECF0;font-size:0;line-height:0;">&nbsp;</td></tr>
              </table>
            </td>
          </tr>"""

    return f"""<!DOCTYPE html>
<html lang="vi" xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:v="urn:schemas-microsoft-com:vml">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<!--[if mso]>
<noscript><xml><o:OfficeDocumentSettings><o:AllowPNG/><o:PixelsPerInch>96</o:PixelsPerInch>
</o:OfficeDocumentSettings></xml></noscript>
<![endif]-->
</head>
<body style="margin:0;padding:0;background-color:#EEF2F7;-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%;">

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="#EEF2F7" style="background-color:#EEF2F7;">
<tr><td align="center" style="padding:24px 12px;">

<!--[if mso]><table role="presentation" width="600" cellpadding="0" cellspacing="0"><tr><td><![endif]-->
<table role="presentation" width="600" cellpadding="0" cellspacing="0"
       style="max-width:600px;width:100%;background-color:#FFFFFF;border-radius:10px;" bgcolor="#FFFFFF">

  <!-- HEADER -->
  <tr>
    <td bgcolor="#003087" style="background-color:#003087;padding:28px 30px 22px 30px;text-align:center;border-radius:10px 10px 0 0;">
      <p style="margin:0 0 6px;font-size:11px;color:#7EB1E8;letter-spacing:2px;font-family:Arial,sans-serif;text-transform:uppercase;">
        BIS &#8209; MT &nbsp;&#183;&nbsp; {date_str}
      </p>
      <h1 style="margin:0;font-size:26px;font-weight:bold;color:#FFFFFF;font-family:Arial,sans-serif;line-height:1.2;">
        &#129302; B&#7843;n Tin AI H&#7857;ng Ng&#224;y
      </h1>
      <p style="margin:8px 0 0;font-size:13px;color:#90C4F0;font-family:Arial,sans-serif;">
        C&#7853;p nh&#7853;t c&#244;ng ngh&#7879; AI m&#7899;i nh&#7845;t
      </p>
    </td>
  </tr>

  <!-- QUOTE -->
  <tr>
    <td bgcolor="#EBF4FF" style="background-color:#EBF4FF;padding:16px 30px;border-top:3px solid #0066CC;">
      <p style="margin:0;font-size:14px;color:#1A3A5C;font-style:italic;line-height:1.6;font-family:Georgia,serif;">
        &#10024;&nbsp;&ldquo;{h(quote["foreign"])}&rdquo;
      </p>
      {vi_line}
      <p style="margin:8px 0 0;font-size:12px;color:#888888;font-family:Arial,sans-serif;">&mdash;&nbsp;{h(quote["author"])}</p>
      {explain_line}
    </td>
  </tr>

  <!-- SECTION LABEL -->
  <tr>
    <td bgcolor="#F5F7FA" style="background-color:#F5F7FA;padding:12px 30px;">
      <p style="margin:0;font-size:11px;color:#999999;letter-spacing:1px;font-family:Arial,sans-serif;text-transform:uppercase;font-weight:bold;">
        &#128240;&nbsp;Tin t&#7913;c n&#7893;i b&#7853;t
      </p>
    </td>
  </tr>

  <!-- ARTICLES -->
  {articles_html}

  <!-- TIPS SECTION -->
  {tips_html}

  <!-- LESSON SECTION -->
  {lesson_html}

  <!-- FOOTER -->
  <tr>
    <td bgcolor="#003087" style="background-color:#003087;padding:20px 30px;text-align:center;border-radius:0 0 10px 10px;">
      <p style="margin:0 0 4px;font-size:13px;color:#90C4F0;font-family:Arial,sans-serif;">
        &#128161;&nbsp;Lu&#244;n &#273;i &#273;&#7847;u trong th&#7871; gi&#7899;i AI!&nbsp;&#183;&nbsp;Stay ahead in AI!
      </p>
      <p style="margin:6px 0 0;font-size:11px;color:#4A7AAB;font-family:Arial,sans-serif;">
        Ngu&#7891;n: {source}
      </p>
    </td>
  </tr>

</table>
<!--[if mso]></td></tr></table><![endif]-->

</td></tr>
</table>
</body>
</html>"""


def build_plain_text(data):
    lines = []
    q = data["quote"]
    lines.append(f'"{q["foreign"]}"')
    if q.get("vi") and q["vi"] != q["foreign"]:
        lines.append(f'  → {q["vi"]}')
    lines.append(f'  — {q["author"]}')
    if q.get("explain"):
        lines.append(f'  💡 {q["explain"]}')
    lines.append("\n" + "=" * 50)
    lines.append(f'BẢN TIN AI HẰNG NGÀY | BIS-MT | {data["date"]}')
    lines.append("=" * 50)
    for i, art in enumerate(data["articles"], 1):
        title = art["title_vi"] or art["title_en"]
        lines.append(f"\n{i}. {title}")
        lines.append(f"   🇬🇧 {art['title_en']}")
        if art["publisher"]:
            lines.append(f"   {art['publisher']}")
        if art["link"]:
            lines.append(f"   {art['link']}")
        if art.get("summary"):
            lines.append(f"\n   {art['summary']}")
    if data.get("tips"):
        lines.append("\n" + "─" * 50)
        lines.append("⚡ TIPS & TRICKS")
        lines.append(data["tips"])
    lines.append("\n" + "=" * 50)
    lines.append("Luôn đi đầu trong thế giới AI!")
    return "\n".join(lines)


def send_email(subject, html, plain_text):
    if not EMAIL_PASSWORD:
        logging.error("EMAIL_PASSWORD not set")
        return False

    match = re.match(r'^(.+?)\s*<(.+?)>$', EMAIL_FROM)
    if match:
        display_name, from_addr = match.group(1).strip(), match.group(2).strip()
        from_header = formataddr((str(Header(display_name, "utf-8")), from_addr))
    else:
        from_addr = EMAIL_FROM
        from_header = EMAIL_FROM

    # All recipients go to BCC — TO is hidden
    bcc_raw  = f"{EMAIL_TO},{EMAIL_BCC}" if EMAIL_TO else EMAIL_BCC
    bcc_list = [b.strip() for b in bcc_raw.split(",") if b.strip()]
    all_recipients = bcc_list

    msg = MIMEMultipart("alternative")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"]    = from_header
    msg["To"]      = "undisclosed-recipients:;"
    msg["Bcc"]     = ", ".join(bcc_list)

    msg.attach(MIMEText(plain_text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    for attempt in range(1, MAX_RETRIES + 1):
        logging.info(f"Send attempt {attempt}/{MAX_RETRIES}...")
        try:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
                server.starttls()
                server.login(from_addr, EMAIL_PASSWORD)
                server.sendmail(from_addr, all_recipients, msg.as_bytes())
            logging.info("Email sent successfully!")
            return True
        except Exception as e:
            logging.warning(f"Attempt {attempt} failed: {e}")
        if attempt < MAX_RETRIES:
            logging.info(f"Retrying in {RETRY_DELAY}s...")
            time.sleep(RETRY_DELAY)

    return False


DOCS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")


def _date_slug():
    return os.environ.get("WEB_DATE_OVERRIDE") or datetime.datetime.now().strftime("%Y-%m-%d")


def _all_dated_files():
    """Return sorted list of date strings (YYYY-MM-DD) for existing web pages."""
    if not os.path.isdir(DOCS_DIR):
        return []
    return sorted(
        f[:-5] for f in os.listdir(DOCS_DIR)
        if re.match(r'\d{4}-\d{2}-\d{2}\.html$', f)
    )


def build_web_html(data, prev_date=None, next_date=None):
    """Wrap the email HTML with a sticky nav bar for web viewing."""
    prev_btn = (
        f'<a href="{prev_date}.html" style="color:#90C4F0;text-decoration:none;">&#8592; {prev_date}</a>'
        if prev_date else '<span style="color:#4A6A8A;">&#8592;</span>'
    )
    next_btn = (
        f'<a href="{next_date}.html" style="color:#90C4F0;text-decoration:none;">{next_date} &#8594;</a>'
        if next_date else '<span style="color:#4A6A8A;">&#8594;</span>'
    )
    nav = f"""<div style="background:#001a4d;padding:10px 20px;text-align:center;font-family:Arial,sans-serif;font-size:13px;position:sticky;top:0;z-index:999;border-bottom:2px solid #0066CC;">
  <span style="margin-right:24px;">{prev_btn}</span>
  <a href="index.html" style="color:#FFD700;text-decoration:none;font-weight:bold;">&#128240; T&#7845;t c&#7843; b&#7843;n tin</a>
  <span style="color:#FFFFFF;margin:0 24px;">{h(data['date'])}</span>
  <span>{next_btn}</span>
</div>
"""
    email_html = build_html(data)
    return _re.sub(r'(<body[^>]*>)', r'\1\n' + nav, email_html, count=1)


def update_web_index(all_dates):
    """Regenerate docs/index.html — archive list + auto-redirect to today."""
    os.makedirs(DOCS_DIR, exist_ok=True)

    rows = ""
    for d in reversed(all_dates):
        dt = datetime.datetime.strptime(d, "%Y-%m-%d")
        label = dt.strftime("%d/%m/%Y")
        weekday = ["Thứ Hai","Thứ Ba","Thứ Tư","Thứ Năm","Thứ Sáu","Thứ Bảy","Chủ Nhật"][dt.weekday()]
        rows += f'<tr><td style="padding:10px 16px;border-bottom:1px solid #E8ECF0;"><a href="{d}.html" style="color:#003087;text-decoration:none;font-size:15px;font-weight:bold;">{label}</a><span style="color:#999;font-size:13px;margin-left:10px;">{weekday}</span></td></tr>\n'

    latest = all_dates[-1] if all_dates else ""
    latest_dt = datetime.datetime.strptime(latest, "%Y-%m-%d") if latest else None
    latest_label = latest_dt.strftime("%d/%m/%Y") if latest_dt else ""

    index_html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>B&#7843;n Tin AI - BIS-MT</title>
</head>
<body style="margin:0;padding:0;background:#EEF2F7;font-family:Arial,sans-serif;">
<div style="max-width:600px;margin:40px auto;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.1);">
  <div style="background:#003087;padding:28px 30px;text-align:center;">
    <h1 style="margin:0;color:#fff;font-size:24px;">&#129302; B&#7843;n Tin AI H&#7857;ng Ng&#224;y</h1>
    <p style="margin:8px 0 0;color:#90C4F0;font-size:13px;">BIS &#8209; MT &nbsp;&#183;&nbsp; L&#432;u tr&#7919; b&#7843;n tin</p>
  </div>
  {f'<div style="padding:16px 30px;text-align:center;background:#EBF4FF;border-bottom:1px solid #C8DCF0;"><a href="{latest}.html" style="display:inline-block;background:#003087;color:#fff;padding:10px 24px;border-radius:6px;text-decoration:none;font-size:14px;font-weight:bold;">&#128240; Xem b&#7843;n tin m&#7899;i nh&#7845;t &mdash; {latest_label}</a></div>' if latest else ''}
  <div style="padding:12px 30px 4px;background:#F5F7FA;">
    <p style="margin:0;font-size:11px;color:#999;letter-spacing:1px;text-transform:uppercase;font-weight:bold;">T&#7845;t c&#7843; b&#7843;n tin</p>
  </div>
  <table width="100%" cellpadding="0" cellspacing="0">
    {rows}
  </table>
  <div style="padding:16px 30px;text-align:center;background:#F5F7FA;">
    <p style="margin:0;font-size:12px;color:#999;">C&#7853;p nh&#7853;t m&#7895;i ng&#224;y l&#250;c 07:30 GMT+7</p>
  </div>
</div>
</body>
</html>"""

    with open(os.path.join(DOCS_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)


def save_web_pages(data):
    """Save today's web page and refresh the index."""
    os.makedirs(DOCS_DIR, exist_ok=True)

    today = _date_slug()
    existing = _all_dated_files()
    all_dates = sorted(set(existing + [today]))
    idx = all_dates.index(today)
    prev_date = all_dates[idx - 1] if idx > 0 else None
    next_date = all_dates[idx + 1] if idx < len(all_dates) - 1 else None

    web_html = build_web_html(data, prev_date, next_date)
    with open(os.path.join(DOCS_DIR, f"{today}.html"), "w", encoding="utf-8") as f:
        f.write(web_html)

    # Create .nojekyll so GitHub Pages doesn't skip files
    nojekyll = os.path.join(DOCS_DIR, ".nojekyll")
    if not os.path.exists(nojekyll):
        open(nojekyll, "w").close()

    update_web_index(all_dates)
    logging.info(f"Web pages saved: docs/{today}.html + docs/index.html")


def main():
    logging.info("=== AI News Bot started ===")

    logging.info("Fetching AI news...")
    data = fetch_ai_news()
    if not data:
        logging.error("Failed to fetch news. Aborting.")
        sys.exit(1)
    logging.info(f"Fetched {len(data['articles'])} articles")

    html       = build_html(data)
    plain_text = build_plain_text(data)
    subject    = f"Bản tin AI - BIS-MT - {data['date']}"

    bcc_info = f" | BCC: {EMAIL_BCC}" if EMAIL_BCC else ""
    logging.info(f"Sending to {EMAIL_TO}{bcc_info}...")

    if os.environ.get("NO_EMAIL"):
        logging.info("NO_EMAIL set — skipping email send")
    elif send_email(subject, html, plain_text):
        logging.info("Email sent successfully")
    else:
        logging.error(f"Failed after {MAX_RETRIES} attempts.")
        sys.exit(1)

    save_web_pages(data)
    logging.info("=== Bot finished successfully ===")


if __name__ == "__main__":
    main()
