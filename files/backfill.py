#!/usr/bin/env python3
"""
backfill.py - Generate backdated newsletters with real news from NewsAPI.
Usage: NEWSAPI_KEY=xxx python3 files/backfill.py
"""
import os, sys, datetime, time, json, urllib.request, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load .env
_env = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env):
    with open(_env) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

from fetch_news import (
    _groq_translate_titles_batch, _gemini_translate_all_batch,
    _groq_summarize, _groq_lesson, _groq_tips,
    _fetch_article_text, _CURATED_QUOTES,
)
from ai_news_bot import save_web_pages, _all_dated_files

GUARDIAN_KEY = os.environ.get("GUARDIAN_KEY", "")
GROQ_KEY     = os.environ.get("GROQ_API_KEY", "")
GEMINI_KEY   = os.environ.get("GEMINI_API_KEY", "")


def _fetch_guardian(date_str, page_size=10):
    params = urllib.parse.urlencode({
        "q":           "AI tools developer software programming LLM productivity",
        "from-date":   date_str,
        "to-date":     date_str,
        "lang":        "en",
        "order-by":    "relevance",
        "page-size":   page_size,
        "show-fields": "trailText,byline",
        "api-key":     GUARDIAN_KEY,
    })
    req = urllib.request.Request(
        f"https://content.guardianapis.com/search?{params}",
        headers={"User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode())
        return data.get("response", {}).get("results", [])
    except Exception as e:
        print(f"  Guardian API error: {e}")
        return []


def process_date(date_str):
    d      = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    label  = d.strftime("%d/%m/%Y")
    print(f"\n{'─'*52}\n  {date_str}  ({label})")

    raw = _fetch_guardian(date_str)
    if len(raw) < 3:
        print(f"  Only {len(raw)} articles — skipping")
        return False

    raw = raw[:8]
    parsed = []
    for a in raw:
        title   = a.get("webTitle", "").strip()
        link    = a.get("webUrl", "")
        context = (a.get("fields") or {}).get("trailText", "")
        if not context:
            context = _fetch_article_text(link) if link else ""
        parsed.append({
            "title_en":  title,
            "publisher": "The Guardian",
            "link":      link,
            "context":   context[:4000],
        })

    print(f"  {len(parsed)} articles — summarizing (EN)...")
    sum_lang = "en" if GEMINI_KEY else "vi"
    title_inputs  = [p["title_en"] for p in parsed]
    summaries_raw = []
    for i, p in enumerate(parsed):
        print(f"  summarize {i+1}/{len(parsed)}...", end=" ", flush=True)
        s = _groq_summarize(p["title_en"], p["context"], GROQ_KEY, lang=sum_lang)
        time.sleep(8)
        print("ok")
        summaries_raw.append(s)

    print("  translating titles + summaries via Gemini..." if GEMINI_KEY else "  translating titles via Groq...")
    if GEMINI_KEY:
        titles_vi, summaries_vi = _gemini_translate_all_batch(title_inputs, summaries_raw, GEMINI_KEY)
        if not any(titles_vi):
            titles_vi    = _groq_translate_titles_batch(title_inputs, GROQ_KEY)
            summaries_vi = summaries_raw
    else:
        titles_vi    = _groq_translate_titles_batch(title_inputs, GROQ_KEY)
        summaries_vi = summaries_raw
    time.sleep(8)

    articles = []
    for i, p in enumerate(parsed):
        articles.append({
            "title_en":  p["title_en"],
            "title_vi":  (titles_vi[i] if i < len(titles_vi) else "") or p["title_en"],
            "publisher": p["publisher"],
            "link":      p["link"],
            "summary":   summaries_vi[i] if i < len(summaries_vi) else summaries_raw[i],
        })

    print("  lesson...", end=" ", flush=True)
    lesson = _groq_lesson(GROQ_KEY);  time.sleep(6);  print("ok")
    print("  tips...",   end=" ", flush=True)
    tips   = _groq_tips(GROQ_KEY);   time.sleep(6);  print("ok")

    # Quote by day-of-year
    quote = {"foreign": "Có chí thì nên.", "vi": None,
             "author": "Tục ngữ Việt Nam", "explain": "Ý chí và quyết tâm là chìa khóa thành công."}
    if _CURATED_QUOTES:
        q = _CURATED_QUOTES[(d.timetuple().tm_yday - 1) % len(_CURATED_QUOTES)]
        quote = {"foreign": q["text"], "vi": q.get("vi"),
                 "author": q["author"], "explain": q.get("explain", "")}

    os.environ["WEB_DATE_OVERRIDE"] = date_str
    save_web_pages({
        "quote": quote, "articles": articles,
        "lesson": lesson, "tips": tips,
        "date": label, "groq": bool(GROQ_KEY),
    })
    print(f"  ✓ saved docs/{date_str}.html")
    return True


if __name__ == "__main__":
    if not GUARDIAN_KEY:
        print("ERROR: GUARDIAN_KEY not set"); sys.exit(1)

    force = "--force" in sys.argv
    existing      = set() if force else set(_all_dated_files())
    today         = datetime.date.today()
    to_process    = [
        (today - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range(1, 31)
        if (today - datetime.timedelta(days=i)).strftime("%Y-%m-%d") not in existing
    ][::-1]   # oldest first

    if not to_process:
        print("Nothing to backfill — all dates already exist."); sys.exit(0)

    print(f"Backfilling {len(to_process)} dates: {to_process[0]} → {to_process[-1]}")
    print(f"Estimated time: ~{len(to_process) * 110 // 60} min\n")

    ok = 0
    for i, date_str in enumerate(to_process, 1):
        print(f"[{i}/{len(to_process)}]", end="")
        if process_date(date_str):
            ok += 1
        if i < len(to_process):
            print("  sleeping 15s before next day...")
            time.sleep(15)

    print(f"\n{'='*52}")
    print(f"Done: {ok}/{len(to_process)} generated.")
    print("Next: git add docs/ && git push")
