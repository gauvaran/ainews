#!/usr/bin/env python3
"""
fetch_news.py - Fetch AI news, translate, summarize via Groq, return structured data
"""

import feedparser
import datetime
import re
import sys
import os
import socket
import urllib.request
import urllib.parse
import urllib.error
import json
import time
import hashlib
from html.parser import HTMLParser

NEWS_URL    = "https://news.google.com/rss/search?q=AI+tools+software+developers+programming+productivity&hl=en-US&gl=US&ceid=US:en"
GROQ_URL             = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL           = "llama-3.1-8b-instant"
GROQ_TRANSLATE_MODEL = "llama-3.3-70b-versatile"
GEMINI_URL  = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

# Specialized feeds — 1 article per feed, need 5, list has 9 as backup pool
SPECIALIZED_FEEDS = [
    ("https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "The Verge AI"),
    ("https://venturebeat.com/feed/",                                      "VentureBeat"),
    ("https://github.blog/feed/",                                          "GitHub Blog"),
    ("https://hnrss.org/newest?q=AI+LLM+developer&points=10",             "Hacker News"),
    ("https://feeds.arstechnica.com/arstechnica/technology-lab",           "Ars Technica"),
    ("https://dev.to/feed/tag/ai",                                         "Dev.to AI"),
    ("https://www.theregister.com/emergent_tech/ai/headlines.atom",        "The Register AI"),
    ("https://www.infoq.com/ai-ml-data-eng/articles.atom",                "InfoQ AI"),
    ("https://spectrum.ieee.org/rss/blog/tech-talk/fulltext",              "IEEE Spectrum"),
    ("https://techcrunch.com/category/artificial-intelligence/feed/",      "TechCrunch AI"),
]

try:
    import sys as _sys, os as _os
    _sys.path.insert(0, _os.path.dirname(__file__))
    from quotes import QUOTES as _CURATED_QUOTES
except Exception:
    _CURATED_QUOTES = []


def get_daily_quote():
    """Return today's quote from the curated 365-quote list, cycling by day-of-year."""
    if _CURATED_QUOTES:
        day_idx = (datetime.datetime.now().timetuple().tm_yday - 1) % len(_CURATED_QUOTES)
        q = _CURATED_QUOTES[day_idx]
        return {
            "foreign": q["text"],
            "vi":      q.get("vi"),
            "author":  q["author"],
            "explain": q.get("explain", ""),
        }
    # Emergency fallback
    return {"foreign": "Có chí thì nên.", "vi": None, "author": "Tục ngữ Việt Nam", "explain": "Ý chí và quyết tâm là chìa khóa thành công."}


class _ParagraphParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paras, self._buf, self._in = [], [], False

    def handle_starttag(self, tag, attrs):
        if tag == "p":
            self._in = True

    def handle_endtag(self, tag):
        if tag == "p" and self._in:
            text = "".join(self._buf).strip()
            if len(text) > 60:
                self.paras.append(text)
            self._in, self._buf = False, []

    def handle_data(self, data):
        if self._in:
            self._buf.append(data)


def _fetch_article_text(url, max_chars=4000):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"})
        with urllib.request.urlopen(req, timeout=10) as r:
            html = r.read().decode("utf-8", errors="ignore")
        p = _ParagraphParser()
        p.feed(html)
        return " ".join(p.paras)[:max_chars]
    except Exception:
        return ""


def _strip_html(text):
    """Strip HTML tags from RSS summary."""
    p = HTMLParser()
    class S(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts = []
        def handle_data(self, d):
            self.parts.append(d)
    s = S()
    s.feed(text)
    return " ".join(s.parts).strip()


def _groq_summarize(title, context_text, api_key, lang="vi"):
    """Summarize article using Groq. lang='vi' → Vietnamese, lang='en' → English (for Gemini to translate)."""
    if not api_key or not context_text:
        return ""
    if lang == "en":
        prompt = (
            "You are a tech news editor. Based ONLY on the content below, "
            "write an English summary in 150-200 words, clear and informative. "
            "Do NOT add information beyond what is provided.\n\n"
            f"Title: {title}\n\nContent:\n{context_text}"
        )
    else:
        prompt = (
            "Bạn là trợ lý biên tập tin tức công nghệ. "
            "Dựa HOÀN TOÀN vào nội dung được cung cấp bên dưới, "
            "hãy viết tóm tắt bằng tiếng Việt khoảng 150-200 từ, rõ ràng và dễ hiểu. "
            "TUYỆT ĐỐI không thêm thông tin ngoài bài, không suy diễn.\n\n"
            f"Tiêu đề: {title}\n\nNội dung:\n{context_text}"
        )
    payload = json.dumps({
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 500,
        "temperature": 0.3,
    }).encode()
    req = urllib.request.Request(
        GROQ_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode())
        return data["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        print(f"Groq HTTP {e.code}: {e.read().decode()[:200]}", file=sys.stderr)
        return ""
    except Exception as e:
        print(f"Groq error: {e}", file=sys.stderr)
        return ""


def _translate_vi(text, max_len=400):
    """Translate EN→VI via MyMemory (fallback only)."""
    try:
        params = urllib.parse.urlencode({"q": text[:max_len], "langpair": "en|vi"})
        with urllib.request.urlopen(f"https://api.mymemory.translated.net/get?{params}", timeout=10) as r:
            data = json.loads(r.read().decode())
        result = data.get("responseData", {}).get("translatedText", "")
        if result and not result.upper().startswith("MYMEMORY WARNING"):
            return result
    except Exception:
        pass
    return ""


def _gemini_translate_titles_batch(titles, api_key):
    """Translate all headlines in ONE Gemini 2.5 Flash call. Returns list aligned with input."""
    if not api_key or not titles:
        return [""] * len(titles)
    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))
    prompt = (
        "Dịch các tiêu đề tin tức sau sang tiếng Việt. "
        "Người đọc là developer Việt Nam giàu kinh nghiệm. "
        "Giữ nguyên các từ kỹ thuật thông dụng viết bằng tiếng Anh: "
        "AI, model, API, LLM, agent, token, fine-tune, developer, software, framework, v.v. "
        "Dịch tự nhiên như người Việt viết, không dịch cứng nhắc (ví dụ: giữ 'developer', không dịch thành 'nhà phát triển'). "
        "Chỉ trả về danh sách đánh số theo đúng thứ tự, không giải thích.\n\n"
        f"{numbered}"
    )
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2048},
    }).encode()
    req = urllib.request.Request(
        f"{GEMINI_URL}?key={api_key}",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.loads(r.read().decode())
            raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            lines = [re.sub(r'^\d+\.\s*', '', l).strip() for l in raw.splitlines() if l.strip()]
            while len(lines) < len(titles):
                lines.append("")
            return lines[:len(titles)]
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                print(f"Gemini 429 — retry {attempt+1}/3 in 10s...", file=sys.stderr)
                time.sleep(10)
            else:
                print(f"Gemini translate error: {e}", file=sys.stderr)
                return [""] * len(titles)
        except Exception as e:
            print(f"Gemini translate error: {e}", file=sys.stderr)
            return [""] * len(titles)
    return [""] * len(titles)


def _gemini_translate_all_batch(titles, summaries, api_key):
    """ONE Gemini call: translate all titles + summaries to Vietnamese.
    Returns (titles_vi, summaries_vi) lists aligned with input."""
    n = len(titles)
    if not api_key or not titles:
        return [""] * n, [""] * n
    titles_block   = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))
    summaries_block = "\n\n".join(f"{i+1}. {s}" for i, s in enumerate(summaries))
    prompt = (
        "Dịch sang tiếng Việt. Người đọc là developer Việt Nam giàu kinh nghiệm.\n"
        "Quy tắc: giữ nguyên thuật ngữ kỹ thuật tiếng Anh "
        "(AI, API, LLM, model, token, developer, framework, agent, fine-tune, v.v.). "
        "Dịch tự nhiên như người Việt viết, không dịch cứng nhắc.\n\n"
        "### TIÊU ĐỀ (dịch ngắn gọn):\n"
        f"{titles_block}\n\n"
        "### TÓM TẮT (dịch đầy đủ, giữ nguyên nghĩa gốc, ~150-200 từ mỗi bài):\n"
        f"{summaries_block}\n\n"
        "Trả về đúng format sau, không thêm gì khác:\n"
        "### TIÊU ĐỀ:\n1. ...\n\n### TÓM TẮT:\n1. ..."
    )
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 6000},
    }).encode()
    req = urllib.request.Request(
        f"{GEMINI_URL}?key={api_key}",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read().decode())
            raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()

            if "### TÓM TẮT:" not in raw:
                return [""] * n, [""] * n

            parts = raw.split("### TÓM TẮT:", 1)
            titles_raw   = parts[0].replace("### TIÊU ĐỀ:", "").strip()
            summaries_raw = parts[1].strip()

            def parse_short(text, expected):
                lines = [re.sub(r'^\d+\.\s*', '', l).strip()
                         for l in text.splitlines() if re.match(r'^\d+\.', l.strip())]
                while len(lines) < expected: lines.append("")
                return lines[:expected]

            def parse_long(text, expected):
                items = re.split(r'\n+(?=\d+\.)', text.strip())
                result = [re.sub(r'^\d+\.\s*', '', it).strip() for it in items if it.strip()]
                while len(result) < expected: result.append("")
                return result[:expected]

            return parse_short(titles_raw, n), parse_long(summaries_raw, n)

        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                wait = (attempt + 1) * 30  # 30s, 60s
                print(f"Gemini 429 — retry {attempt+1}/3 in {wait}s...", file=sys.stderr)
                time.sleep(wait)
            else:
                print(f"Gemini translate_all error: HTTP {e.code}", file=sys.stderr)
                return [""] * n, [""] * n
        except Exception as e:
            print(f"Gemini translate_all error: {e}", file=sys.stderr)
            return [""] * n, [""] * n
    return [""] * n, [""] * n


def _groq_translate_summaries_batch(summaries, api_key):
    """Translate English summaries to Vietnamese using Groq 70B. One call per summary."""
    if not api_key:
        return summaries
    results = []
    for s in summaries:
        if not s:
            results.append(s)
            continue
        prompt = (
            "Translate the following tech news summary to natural Vietnamese. "
            "Keep English technical terms (AI, API, LLM, model, token, developer, framework, etc.). "
            "Return only the translation, no explanations.\n\n" + s
        )
        payload = json.dumps({
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 600,
            "temperature": 0.2,
        }).encode()
        req = urllib.request.Request(
            GROQ_URL, data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.loads(r.read().decode())
            results.append(d["choices"][0]["message"]["content"].strip())
            time.sleep(4)
        except Exception as e:
            print(f"Groq translate summary error: {e}", file=sys.stderr)
            results.append(s)
    return results


def _groq_translate_titles_batch(titles, api_key):
    """Translate all headlines in ONE Groq call. Returns list aligned with input."""
    if not api_key or not titles:
        return [_translate_vi(t) for t in titles]
    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))
    prompt = (
        "Dịch các tiêu đề tin tức sau sang tiếng Việt. "
        "Người đọc là developer giàu kinh nghiệm. "
        "Giữ nguyên thuật ngữ kỹ thuật EN (AI, model, API, LLM, agent, token, fine-tune, v.v.). "
        "Dịch sát nghĩa, tự nhiên. "
        "Chỉ trả về danh sách đánh số theo đúng thứ tự, không giải thích.\n\n"
        f"{numbered}"
    )
    payload = json.dumps({
        "model": GROQ_TRANSLATE_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 800,
        "temperature": 0.1,
    }).encode()
    req = urllib.request.Request(
        GROQ_URL, data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode())
        raw = data["choices"][0]["message"]["content"].strip()
        lines = [re.sub(r'^\d+\.\s*', '', l).strip() for l in raw.splitlines() if l.strip()]
        while len(lines) < len(titles):
            lines.append("")
        return lines[:len(titles)]
    except Exception:
        return [_translate_vi(t) for t in titles]


DEV_TOPICS = [
    "Dùng GitHub Copilot hiệu quả: tips & tricks cho dev hàng ngày",
    "Viết prompt tốt để sinh code chính xác hơn",
    "Tích hợp OpenAI API vào ứng dụng web trong 30 phút",
    "Dùng AI để viết unit test tự động",
    "Xây dựng chatbot hỏi-đáp tài liệu nội bộ với RAG",
    "Dùng AI review code: tích hợp vào quy trình PR",
    "Tự động sinh API documentation bằng LLM",
    "Dùng AI để debug lỗi nhanh hơn: kỹ thuật và thói quen",
    "Xây dựng CLI tool thông minh với LLM",
    "Streaming response trong chat app: UX tốt hơn với AI",
    "Dùng function calling để AI gọi API của bạn",
    "Xử lý structured output từ LLM: JSON, schema validation",
    "Tích hợp AI search vào ứng dụng với vector database",
    "Dùng AI để refactor legacy code an toàn",
    "Prompt engineering cho code generation: few-shot examples",
    "Xây dựng AI assistant cho Slack/Teams nội bộ",
    "Dùng AI để tự động hóa data pipeline và ETL",
    "Bảo mật khi dùng AI: tránh prompt injection trong app",
    "Giảm chi phí API: caching, batching, chọn đúng model",
    "Dùng AI để sinh test data và mock data tự động",
    "Tích hợp AI vào CI/CD: tự động check code quality",
    "Xây dựng SQL query builder thông minh với LLM",
    "Dùng AI để dịch và localize app nhanh hơn",
    "Monitoring và logging cho LLM app trong production",
    "Dùng AI để phân tích log và phát hiện lỗi sớm",
    "Tạo README và tài liệu kỹ thuật tự động với AI",
    "Xây dựng form tự động điền thông minh với LLM",
    "Dùng AI để tối ưu SQL query và database performance",
    "Tích hợp AI voice assistant vào ứng dụng",
    "Dùng AI để sinh code migration script tự động",
]


def _groq_lesson(api_key):
    """Generate a daily AI lesson for developers using Groq. Topic is chosen by Groq based on date seed."""
    if not api_key:
        return ""
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    categories = ", ".join([
        "tích hợp AI API vào ứng dụng", "GitHub Copilot & AI coding tools",
        "prompt engineering cho dev", "RAG & semantic search",
        "AI trong CI/CD & DevOps", "tự động hóa với LLM",
        "bảo mật AI app", "tối ưu chi phí & hiệu năng LLM",
        "AI cho testing & QA", "AI trong database & data pipeline",
    ])
    prompt = (
        f"Hôm nay là {today}. Bạn là AI engineer senior dạy dev ứng dụng AI vào công việc lập trình hàng ngày.\n\n"
        f"Dựa vào ngày hôm nay, hãy chọn MỘT chủ đề cụ thể, thực tiễn (không lặp lại chủ đề quá gần đây) "
        f"trong các lĩnh vực: {categories}.\n\n"
        f"Viết bài học theo cấu trúc:\n"
        f"1. **Tên chủ đề** (1 dòng, súc tích)\n"
        f"2. Giải thích ngắn gọn — tại sao dev cần biết (2-3 câu)\n"
        f"3. Ví dụ thực tế hoặc code snippet minh họa\n"
        f"4. 💡 Tip hoặc bước tiếp theo\n\n"
        f"Yêu cầu: 120-160 từ, tiếng Việt, giữ thuật ngữ kỹ thuật tiếng Anh."
    )
    payload = json.dumps({
        "model": GROQ_TRANSLATE_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 600,
        "temperature": 0.7,
    }).encode()
    req = urllib.request.Request(
        GROQ_URL, data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode())
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"Groq lesson error: {e}", file=sys.stderr)
        return ""


def _groq_tips(api_key):
    """Generate 2 trending AI tips & tricks for developers."""
    if not api_key:
        return ""
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    prompt = (
        f"Hôm nay là {today}. Bạn là senior dev chia sẻ tips thực chiến về AI tools.\n\n"
        "Viết ĐÚNG 2 tip & trick ngắn gọn, trending về dùng AI trong công việc dev hàng ngày "
        "(GitHub Copilot, ChatGPT, Claude, Cursor, Gemini, Windsurf, Codeium, v.v.). "
        "Chọn tips đang hot hoặc ít người biết, cụ thể và áp dụng được ngay.\n\n"
        "Format mỗi tip:\n"
        "### ⚡ [Tên tip]\n"
        "[2-3 câu: giải thích + ví dụ prompt mẫu hoặc lệnh cụ thể]\n\n"
        "Yêu cầu: tiếng Việt, giữ thuật ngữ EN, mỗi tip ≤ 60 từ. Viết 2 tip liền nhau."
    )
    payload = json.dumps({
        "model": GROQ_TRANSLATE_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 450,
        "temperature": 0.85,
    }).encode()
    req = urllib.request.Request(
        GROQ_URL, data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode())
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"Groq tips error: {e}", file=sys.stderr)
        return ""


def _load_prev_seen():
    """Return (known_titles_lower, known_urls) from the most recent docs/YYYY-MM-DD.html
    that is NOT today's date (avoids deduplicating against the file being regenerated)."""
    docs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
    if not os.path.isdir(docs_dir):
        return set(), set()
    today_slug = (os.environ.get("WEB_DATE_OVERRIDE")
                  or datetime.datetime.now().strftime("%Y-%m-%d"))
    files = sorted(
        f for f in os.listdir(docs_dir)
        if re.match(r'\d{4}-\d{2}-\d{2}\.html$', f) and f != f"{today_slug}.html"
    )
    if not files:
        return set(), set()
    prev_path = os.path.join(docs_dir, files[-1])
    try:
        with open(prev_path, encoding='utf-8') as f:
            html = f.read()
        titles = set()
        for m in re.finditer(r'&#127468;&#127463;&nbsp;(.+?)(?=<)', html):
            t = m.group(1).strip()
            # Strip all " - Publisher" suffixes (Google News may have multiple)
            t = t.split(' - ')[0].strip()
            titles.add(t.lower())
        urls = {m.group(1).split('?')[0]
                for m in re.finditer(r'href="(https://(?!news\.google)[^"]+)"', html)}
        return titles, urls
    except Exception:
        return set(), set()


def fetch_ai_news(google_items=3, specialized_items=5):
    """Return structured dict: quote + 3 Google News + 5 specialized feed articles."""
    groq_key   = os.environ.get("GROQ_API_KEY", "")
    gemini_key = os.environ.get("GEMINI_API_KEY", "")

    socket.setdefaulttimeout(12)
    _headers = {"User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"}

    prev_titles, prev_urls = _load_prev_seen()

    # ── Phase 1: collect raw entries (no Groq yet) ────────────────────────────
    raw = []  # list of (entry, publisher_hint)

    try:
        feed = feedparser.parse(NEWS_URL, request_headers=_headers)
        added = 0
        for entry in feed.entries[:google_items * 5]:
            if added >= google_items:
                break
            t = entry.get("title", "").strip()
            # Strip all " - Publisher" suffixes
            t_key = t.split(' - ')[0].strip().lower()
            rss_summary = _strip_html(entry.get("summary", entry.get("description", "")))
            if t_key in prev_titles or len(rss_summary) < 80:
                continue
            raw.append((entry, ""))
            prev_titles.add(t_key)
            added += 1
    except Exception as e:
        print(f"Google News feed error: {e}", file=sys.stderr)

    collected = 0
    for feed_url, feed_name in SPECIALIZED_FEEDS:
        if collected >= specialized_items:
            break
        try:
            feed = feedparser.parse(feed_url, request_headers=_headers)
            picked = False
            for entry in feed.entries[:5]:
                url = entry.get("link", "").split("?")[0]
                t   = entry.get("title", "").strip().lower()
                if url and url not in prev_urls and t not in prev_titles:
                    raw.append((entry, feed_name))
                    prev_urls.add(url)
                    prev_titles.add(t)
                    collected += 1
                    picked = True
                    print(f"OK: {feed_name}", file=sys.stderr)
                    break
            if not picked:
                # All entries seen before — take the first one anyway
                if feed.entries:
                    raw.append((feed.entries[0], feed_name))
                    collected += 1
                    print(f"OK (repeated): {feed_name}", file=sys.stderr)
                else:
                    print(f"Empty: {feed_name}", file=sys.stderr)
        except Exception as e:
            print(f"Feed error ({feed_name}): {e}", file=sys.stderr)

    if not raw:
        return None

    # ── Phase 2: parse titles / publishers ────────────────────────────────────
    parsed = []
    for entry, pub_hint in raw:
        title_en = entry.get("title", "").strip()
        publisher = pub_hint
        if " - " in title_en:
            parts = title_en.rsplit(" - ", 1)
            title_en, publisher = parts[0].strip(), parts[1].strip()
        elif not publisher:
            publisher = entry.get("source", {}).get("title", "")
        link = entry.get("link", "")
        context = _fetch_article_text(link)
        if not context:
            context = _strip_html(entry.get("summary", entry.get("description", "")))
        parsed.append({"title_en": title_en, "publisher": publisher, "link": link, "context": context})

    # ── Phase 3: Groq summarizes (EN when Gemini available, VI otherwise) ──────
    sum_lang = "en" if gemini_key else "vi"
    summaries_raw = []
    for i, p in enumerate(parsed):
        print(f"  summarize {i+1}/{len(parsed)}...", end=" ", flush=True, file=sys.stderr)
        s = _groq_summarize(p["title_en"], p["context"], groq_key, lang=sum_lang)
        time.sleep(6)
        print("ok", file=sys.stderr)
        summaries_raw.append(s)

    # ── Phase 4: ONE Gemini call → translate titles + summaries ──────────────
    title_inputs = [p["title_en"] for p in parsed]
    if gemini_key:
        print("Translating titles + summaries via Gemini...", file=sys.stderr)
        titles_vi, summaries_vi = _gemini_translate_all_batch(title_inputs, summaries_raw, gemini_key)
        if not any(titles_vi):
            print("Gemini failed, falling back to Groq for titles+summaries...", file=sys.stderr)
            titles_vi    = _groq_translate_titles_batch(title_inputs, groq_key)
            summaries_vi = _groq_translate_summaries_batch(summaries_raw, groq_key)
        else:
            _vi_chars = set('àáảạãăắặẳẵằâấầẩẫậèéẻẹẽêếềểệễìíỉịĩòóỏọõôốồổỗộơớờởỡợùúủụũưứừửữựỳýỷỵỹđ')
            untranslated = [i for i, s in enumerate(summaries_vi)
                            if not s or not any(c in _vi_chars for c in s)]
            if len(untranslated) > len(summaries_vi) // 2:
                print(f"Gemini only translated {n - len(untranslated)}/{n} summaries, falling back to Groq...", file=sys.stderr)
                summaries_vi = _groq_translate_summaries_batch(summaries_raw, groq_key)
            elif untranslated:
                print(f"Gemini missed summaries {untranslated}, retranslating with Groq...", file=sys.stderr)
                groq_partial = _groq_translate_summaries_batch(
                    [summaries_raw[i] for i in untranslated], groq_key)
                for idx, i in enumerate(untranslated):
                    summaries_vi[i] = groq_partial[idx]
    else:
        titles_vi    = _groq_translate_titles_batch(title_inputs, groq_key)
        summaries_vi = summaries_raw  # already Vietnamese from Groq
    time.sleep(5)

    articles = []
    for i, p in enumerate(parsed):
        articles.append({
            "title_en":  p["title_en"],
            "title_vi":  titles_vi[i] or p["title_en"],
            "publisher": p["publisher"],
            "link":      p["link"],
            "summary":   summaries_vi[i] or summaries_raw[i],
        })

    # ── Phase 5: lesson + tips ────────────────────────────────────────────────
    lesson_content = _groq_lesson(groq_key)
    time.sleep(4)
    tips_content   = _groq_tips(groq_key)

    return {
        "quote":    get_daily_quote(),
        "articles": articles,
        "lesson":   lesson_content,
        "tips":     tips_content,
        "date":     datetime.datetime.now().strftime("%d/%m/%Y"),
        "groq":     bool(groq_key),
    }


if __name__ == "__main__":
    import pprint
    pprint.pprint(fetch_ai_news())
