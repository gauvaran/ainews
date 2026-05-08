#!/usr/bin/env python3
"""
fetch_news.py - Fetch AI news, translate, summarize via Groq, return structured data
"""

import feedparser
import datetime
import sys
import os
import urllib.request
import urllib.parse
import urllib.error
import json
import time
import hashlib
from html.parser import HTMLParser

NEWS_URL   = "https://news.google.com/rss/search?q=artificial+intelligence+AI&hl=en-US&gl=US&ceid=US:en"
GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.1-8b-instant"

QUOTES = [
    {"foreign": "The only way to do great work is to love what you do.",                    "author": "Steve Jobs",              "vi": "Cách duy nhất để làm việc vĩ đại là yêu thích điều bạn đang làm."},
    {"foreign": "In the middle of every difficulty lies opportunity.",                       "author": "Albert Einstein",         "vi": "Giữa mọi khó khăn đều ẩn chứa một cơ hội."},
    {"foreign": "The future belongs to those who believe in the beauty of their dreams.",    "author": "Eleanor Roosevelt",       "vi": "Tương lai thuộc về những người tin vào vẻ đẹp của ước mơ mình."},
    {"foreign": "It does not matter how slowly you go as long as you do not stop.",          "author": "Khổng Tử",                "vi": "Không quan trọng bạn đi chậm đến đâu, miễn là bạn không dừng lại."},
    {"foreign": "Người không học như ngọc không mài.",                                       "author": "Tục ngữ Việt Nam",        "vi": "Người không chịu học thì không thể tỏa sáng, như ngọc không mài giũa."},
    {"foreign": "La vita è ciò che ti accade mentre fai altri progetti.",                     "author": "John Lennon (Ý)",         "vi": "Cuộc sống là những gì xảy ra khi bạn đang bận lên kế hoạch cho điều khác."},
    {"foreign": "Einfachheit ist die höchste Stufe der Vollkommenheit.",                      "author": "Leonardo da Vinci (Đức)", "vi": "Sự đơn giản là đỉnh cao của sự hoàn hảo."},
    {"foreign": "Chaque jour est une nouvelle chance de changer ta vie.",                     "author": "Tục ngữ Pháp",            "vi": "Mỗi ngày là một cơ hội mới để thay đổi cuộc đời bạn."},
    {"foreign": "The best time to plant a tree was 20 years ago. The second best time is now.", "author": "Tục ngữ Trung Quốc",  "vi": "Thời điểm tốt nhất để trồng cây là 20 năm trước. Thời điểm tốt thứ hai là ngay bây giờ."},
    {"foreign": "Có chí thì nên.",                                                            "author": "Tục ngữ Việt Nam",        "vi": "Nếu có ý chí và quyết tâm, ắt sẽ thành công."},
    {"foreign": "知識は力なり。",                                                              "author": "Francis Bacon (Nhật)",    "vi": "Tri thức là sức mạnh."},
    {"foreign": "The secret of getting ahead is getting started.",                            "author": "Mark Twain",              "vi": "Bí quyết để tiến về phía trước là bắt đầu."},
    {"foreign": "Fall seven times, stand up eight.",                                          "author": "Tục ngữ Nhật Bản",        "vi": "Ngã bảy lần, đứng dậy tám lần."},
    {"foreign": "Học, học nữa, học mãi.",                                                     "author": "Vladimir Lenin",          "vi": "Hãy không ngừng học tập — tri thức không có điểm dừng."},
    {"foreign": "Innovation distinguishes between a leader and a follower.",                  "author": "Steve Jobs",              "vi": "Sáng tạo phân biệt người dẫn đầu với kẻ đi theo."},
]


def get_daily_quote():
    idx = int(hashlib.md5(datetime.datetime.now().strftime("%Y%m%d").encode()).hexdigest(), 16) % len(QUOTES)
    return QUOTES[idx]


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
    """Translate EN→VI via MyMemory (fallback)."""
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


def fetch_ai_news(max_items=5):
    """Return structured dict: quote + list of articles."""
    groq_key = os.environ.get("GROQ_API_KEY", "")

    try:
        feed = feedparser.parse(NEWS_URL)
        if not feed.entries:
            return None
    except Exception as e:
        print(f"Feed error: {e}", file=sys.stderr)
        return None

    articles = []
    for entry in feed.entries[:max_items]:
        title_en = entry.get("title", "").strip()
        publisher = ""
        if " - " in title_en:
            parts = title_en.rsplit(" - ", 1)
            title_en, publisher = parts[0].strip(), parts[1].strip()

        # Translate title
        title_vi = _translate_vi(title_en)
        time.sleep(0.4)

        # Get context for summary: try article page first, fall back to RSS description
        link = entry.get("link", "")
        context = _fetch_article_text(link)
        if not context:
            context = _strip_html(entry.get("summary", entry.get("description", "")))

        # Summarize
        summary = _groq_summarize(title_en, context, groq_key)
        if summary:
            time.sleep(0.3)

        articles.append({
            "title_en":  title_en,
            "title_vi":  title_vi,
            "publisher": publisher or entry.get("source", {}).get("title", ""),
            "link":      link,
            "summary":   summary,
        })

    lesson_content = _groq_lesson(groq_key)

    return {
        "quote":    get_daily_quote(),
        "articles": articles,
        "lesson":   lesson_content,
        "date":     datetime.datetime.now().strftime("%d/%m/%Y"),
        "groq":     bool(groq_key),
    }


if __name__ == "__main__":
    import pprint
    pprint.pprint(fetch_ai_news(max_items=2))
