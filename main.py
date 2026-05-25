import json
import os
import re
import time
from datetime import date, timedelta

import feedparser
import google.generativeai as genai
import requests
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
NEWS_API_KEY = os.environ.get("NEWS_API_KEY")
NEWSAPI_BASE = "https://newsapi.org/v2/everything"
GEMINI_MODEL = "gemini-1.5-flash"
TOPIC_SLEEP_SECONDS = 3


def load_config(path: str = "config.json") -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── News fetchers ─────────────────────────────────────────────────────────────

def fetch_newsapi(query: str, language: str, count: int) -> list[dict]:
    today = date.today().isoformat()
    params = {
        "q": query,
        "language": language,
        "from": today,
        "sortBy": "publishedAt",
        "pageSize": count,
        "apiKey": NEWS_API_KEY,
    }
    resp = requests.get(NEWSAPI_BASE, params=params, timeout=15)
    resp.raise_for_status()
    articles = resp.json().get("articles", [])
    result = []
    for a in articles[:count]:
        content = a.get("content") or a.get("description") or ""
        result.append({
            "title": a.get("title", ""),
            "url": a.get("url", ""),
            "text": content[:300],
        })
    return result


def fetch_rss(rss_url: str, count: int) -> list[dict]:
    feed = feedparser.parse(rss_url)
    result = []
    for entry in feed.entries[:count]:
        title = entry.get("title", "")
        url = entry.get("link", "")
        summary = entry.get("summary", "") or entry.get("description", "")
        # Strip HTML tags
        summary = re.sub(r"<[^>]+>", "", summary)
        result.append({
            "title": title,
            "url": url,
            "text": summary[:300],
        })
    return result


def fetch_news(topic: dict, count: int) -> list[dict]:
    if topic["source"] == "newsapi":
        return fetch_newsapi(topic["query"], topic.get("language", "en"), count)
    elif topic["source"] == "rss":
        return fetch_rss(topic["rss_url"], count)
    raise ValueError(f"Unknown source: {topic['source']}")


# ── Gemini summarisation ──────────────────────────────────────────────────────

def build_prompt(topic_name: str, articles: list[dict]) -> str:
    news_lines = []
    for i, a in enumerate(articles, 1):
        news_lines.append(f"{i}. {a['title']}：{a['text']}")
    news_block = "\n".join(news_lines)

    return f"""你是一位專業的新聞編輯，請將以下新聞整理成繁體中文摘要。

新聞主題：{topic_name}
新聞列表：
{news_block}

請針對每則新聞，輸出：
1. 繁體中文標題（簡潔，20字以內）
2. 2-3句繁體中文摘要（說明事件重點、影響與背景）

輸出格式為 JSON array：
[
  {{"title": "中文標題", "summary": "摘要內容"}},
  ...
]
只輸出 JSON，不要其他說明文字。"""


def summarise_with_gemini(topic_name: str, articles: list[dict]) -> list[dict] | None:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)
        prompt = build_prompt(topic_name, articles)
        response = model.generate_content(prompt)
        raw = response.text.strip()

        # Extract JSON array even if wrapped in markdown code block
        match = re.search(r"\[[\s\S]*\]", raw)
        if not match:
            raise ValueError("No JSON array found in Gemini response")
        return json.loads(match.group())
    except Exception as exc:
        print(f"  [Gemini ERROR] {topic_name}: {exc}")
        return None


# ── Discord Webhook ───────────────────────────────────────────────────────────

def build_embed(topic: dict, articles: list[dict], summaries: list[dict] | None) -> dict:
    today_str = date.today().strftime("%Y/%m/%d")
    title = f"{topic['emoji']} {topic['name']} — {today_str}"
    source_label = "NewsAPI" if topic["source"] == "newsapi" else "RSS"

    lines = []
    for i, article in enumerate(articles):
        if summaries and i < len(summaries):
            zh_title = summaries[i].get("title", article["title"])
            zh_summary = summaries[i].get("summary", article["text"])
        else:
            # Fallback: use original title + first 100 chars of text
            zh_title = article["title"]
            zh_summary = article["text"][:100]

        lines.append(f"**{zh_title}**\n{zh_summary}\n→ {article['url']}")

    description = "\n\n".join(lines)

    return {
        "embeds": [
            {
                "title": title,
                "description": description,
                "color": topic["color"],
                "footer": {
                    "text": f"共 {len(articles)} 則・來源：{source_label}・由 Gemini 摘要"
                },
            }
        ]
    }


def send_to_discord(webhook_url: str, payload: dict) -> None:
    resp = requests.post(
        webhook_url,
        json=payload,
        timeout=15,
        headers={"Content-Type": "application/json"},
    )
    resp.raise_for_status()


# ── Main loop ─────────────────────────────────────────────────────────────────

def process_topic(topic: dict, count: int) -> None:
    name = topic["name"]
    print(f"\n[{name}] 開始處理...")

    webhook_url = os.environ.get(topic["webhook_env"])
    if not webhook_url:
        print(f"  [SKIP] 找不到環境變數 {topic['webhook_env']}，跳過此主題")
        return

    # 1. Fetch news
    try:
        articles = fetch_news(topic, count)
        print(f"  抓到 {len(articles)} 則新聞")
    except Exception as exc:
        print(f"  [ERROR] 抓新聞失敗：{exc}，跳過此主題")
        return

    if not articles:
        print("  沒有抓到任何新聞，跳過")
        return

    # 2. Summarise
    summaries = summarise_with_gemini(name, articles)
    if summaries:
        print(f"  Gemini 摘要完成（{len(summaries)} 則）")
    else:
        print("  Gemini 失敗，改用原文前100字")

    # 3. Build & send embed
    payload = build_embed(topic, articles, summaries)
    try:
        send_to_discord(webhook_url, payload)
        print(f"  [OK] 已推送到 Discord")
    except Exception as exc:
        print(f"  [ERROR] Discord 推送失敗：{exc}")


def main() -> None:
    print("=== 每日新聞快訊 Bot 啟動 ===")
    config = load_config()
    count = config.get("news_per_topic", 5)

    for topic in config["topics"]:
        process_topic(topic, count)
        time.sleep(TOPIC_SLEEP_SECONDS)

    print("\n=== 全部主題處理完畢 ===")


if __name__ == "__main__":
    main()
