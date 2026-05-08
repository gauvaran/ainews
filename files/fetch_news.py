#!/usr/bin/env python3
"""
fetch_news.py - Fetch AI news, translate, summarize via Groq, return structured data
"""

import feedparser
import datetime
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

NEWS_URL   = "https://news.google.com/rss/search?q=AI+tools+software+developers+programming+productivity&hl=en-US&gl=US&ceid=US:en"
GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.1-8b-instant"

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


def _groq_summarize(title, context_text, api_key):
    """Summarize article in Vietnamese using Groq. Context = article text or RSS description."""
    if not api_key or not context_text:
        return ""
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


def _groq_translate_title(title, api_key):
    """Translate a news headline EN→VI using Groq, keeping technical terms in English."""
    if not api_key:
        return _translate_vi(title)
    prompt = (
        "Dịch tiêu đề tin tức sau sang tiếng Việt. "
        "Người đọc là developer giàu kinh nghiệm. "
        "Giữ nguyên thuật ngữ kỹ thuật tiếng Anh (AI, model, API, LLM, agent, token, fine-tune, v.v.). "
        "Dịch sát nghĩa, tự nhiên, không giải thích. Chỉ trả về bản dịch, không có gì khác.\n\n"
        f"{title}"
    )
    payload = json.dumps({
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 120,
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
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode())
        return data["choices"][0]["message"]["content"].strip()
    except Exception:
        return _translate_vi(title)


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
        "model": GROQ_MODEL,
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
        "model": GROQ_MODEL,
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


def _process_entry(entry, groq_key, fallback_publisher=""):
    """Translate, fetch context, summarize one RSS entry. Returns article dict."""
    title_en = entry.get("title", "").strip()
    publisher = fallback_publisher
    if " - " in title_en:
        parts = title_en.rsplit(" - ", 1)
        title_en, publisher = parts[0].strip(), parts[1].strip()
    elif not publisher:
        publisher = entry.get("source", {}).get("title", "")

    title_vi = _groq_translate_title(title_en, groq_key)
    time.sleep(2)

    link = entry.get("link", "")
    context = _fetch_article_text(link)
    if not context:
        context = _strip_html(entry.get("summary", entry.get("description", "")))

    summary = _groq_summarize(title_en, context, groq_key)
    time.sleep(4)

    return {
        "title_en":  title_en,
        "title_vi":  title_vi,
        "publisher": publisher,
        "link":      link,
        "summary":   summary,
    }


def fetch_ai_news(google_items=3, specialized_items=5):
    """Return structured dict: quote + 3 Google News + 5 specialized feed articles."""
    groq_key = os.environ.get("GROQ_API_KEY", "")
    articles = []

    socket.setdefaulttimeout(12)

    _headers = {"User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"}

    # ── 3 articles from Google News ──────────────────────────────────────────
    try:
        feed = feedparser.parse(NEWS_URL, request_headers=_headers)
        for entry in feed.entries[:google_items]:
            articles.append(_process_entry(entry, groq_key))
    except Exception as e:
        print(f"Google News feed error: {e}", file=sys.stderr)

    # ── 5 articles from specialized feeds, 10-feed pool as backup ────────────
    collected = 0
    for feed_url, feed_name in SPECIALIZED_FEEDS:
        if collected >= specialized_items:
            break
        try:
            feed = feedparser.parse(feed_url, request_headers=_headers)
            if feed.entries:
                articles.append(_process_entry(feed.entries[0], groq_key, fallback_publisher=feed_name))
                collected += 1
                print(f"OK: {feed_name}", file=sys.stderr)
            else:
                print(f"Empty feed: {feed_name}", file=sys.stderr)
        except Exception as e:
            print(f"Specialized feed error ({feed_name}): {e}", file=sys.stderr)

    if not articles:
        return None

    lesson_content = _groq_lesson(groq_key)
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
