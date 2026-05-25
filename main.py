import json
import os
import re
import time
from datetime import date, timedelta

import feedparser
#import google.generativeai as genai
from groq import Groq
import requests
from dotenv import load_dotenv

load_dotenv()

#GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
NEWS_API_KEY = os.environ.get("NEWS_API_KEY")
NEWSAPI_BASE = "https://newsapi.org/v2/everything"
#GEMINI_MODEL = "gemini-1.5-flash-8b"
GROQ_MODEL = "llama-3.3-70b-versatile"
TOPIC_SLEEP_SECONDS = 3


def load_config(path: str = "config.json") -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── News fetchers ─────────────────────────────────────────────────────────────

def fetch_newsapi(query: str, language: str, count: int, sources: str = "") -> list[dict]:
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    params = {
        "q": query,
        "from": yesterday,
        "sortBy": "popularity",
        "pageSize": count * 3,
        "apiKey": NEWS_API_KEY,
    }

    if sources:
        domains = {
            "reuters": "reuters.com",
            "bbc-news": "bbc.co.uk,bbc.com",
            "associated-press": "apnews.com",
            "bloomberg": "bloomberg.com",
            "the-verge": "theverge.com",
            "techcrunch": "techcrunch.com",
            "ars-technica": "arstechnica.com",
            "al-jazeera-english": "aljazeera.com",
            "the-guardian-uk": "theguardian.com",
        }
        source_list = [s.strip() for s in sources.split(",")]
        domain_list = []
        for s in source_list:
            if s in domains:
                domain_list.extend(domains[s].split(","))
        if domain_list:
            params["domains"] = ",".join(domain_list)
    else:
        params["language"] = language

    resp = requests.get(NEWSAPI_BASE, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    print(f"  NewsAPI 回應：status={data.get('status')}, totalResults={data.get('totalResults')}")
    articles = data.get("articles", [])
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

def fetch_rss_multi(rss_urls: list, count: int, keywords: list = None) -> list[dict]:
    all_entries = []
    for url in rss_urls:
        feed = feedparser.parse(url)
        print(f"  RSS 來源 {url}：{len(feed.entries)} 則")
        for entry in feed.entries:
            title = entry.get("title", "")
            url_link = entry.get("link", "")
            summary = entry.get("summary", "") or entry.get("description", "")
            summary = re.sub(r"<[^>]+>", "", summary)

            # 關鍵字過濾
            if keywords:
                combined = (title + " " + summary).lower()
                if not any(kw.lower() in combined for kw in keywords):
                    continue

            all_entries.append({
                "title": title,
                "url": url_link,
                "text": summary[:300],
                "published": entry.get("published_parsed"),
            })

    # 按發布時間排序，取最新的 count 則
    all_entries.sort(key=lambda x: x.get("published") or (0,), reverse=True)

    result = []
    for e in all_entries[:count]:
        result.append({
            "title": e["title"],
            "url": e["url"],
            "text": e["text"],
        })
    print(f"  關鍵字過濾後剩 {len(result)} 則")
    return result

def fetch_news(topic: dict, count: int) -> list[dict]:
    if topic["source"] == "newsapi":
        return fetch_newsapi(
            topic["query"],
            topic.get("language", "en"),
            count,
            topic.get("sources", "")
        )
    elif topic["source"] == "rss":
        return fetch_rss(topic["rss_url"], count)
    elif topic["source"] == "rss_multi":
        return fetch_rss_multi(
            topic["rss_urls"],
            count,
            topic.get("keywords")
        )

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
        client = Groq(api_key=GROQ_API_KEY)
        prompt = build_prompt(topic_name, articles)
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        raw = response.choices[0].message.content.strip()
        match = re.search(r"\[[\s\S]*\]", raw)
        if not match:
            raise ValueError("No JSON array found in Groq response")
        return json.loads(match.group())
    except Exception as exc:
        print(f"  [Groq ERROR] {topic_name}: {exc}")
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

    # 支援單一或多個 webhook
    webhook_envs = topic.get("webhook_envs") or [topic.get("webhook_env")]
    webhook_urls = [os.environ.get(env) for env in webhook_envs if os.environ.get(env)]

    if not webhook_urls:
        print(f"  [SKIP] 找不到任何 Webhook 環境變數，跳過此主題")
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
        print(f"  Groq 摘要完成（{len(summaries)} 則）")
    else:
        print("  Groq 失敗，改用原文前100字")

    # 3. Build embed
    payload = build_embed(topic, articles, summaries)

    # 4. 推送到所有 Webhook
    for webhook_url in webhook_urls:
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
