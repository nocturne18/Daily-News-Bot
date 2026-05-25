# 每日新聞快訊 Discord Bot

每天台灣時間早上 08:00，自動抓取國際與台灣新聞，透過 Google Gemini API 翻譯摘要成繁體中文，推送至 Discord 對應頻道。

## 功能特色

- 5 個新聞主題，各自推送至獨立 Discord 頻道
- NewsAPI 抓取國際新聞（科技/AI、國際財經、國際政治）
- RSS 抓取台灣新聞（公視台灣時事、天下財經/產業）
- Google Gemini 自動翻譯並生成繁體中文摘要
- GitHub Actions 全自動排程，無需伺服器

---

## 檔案結構

```
news-bot/
├── main.py                          # 主程式
├── config.json                      # 主題與設定
├── requirements.txt                 # Python 相依套件
├── .env.example                     # 環境變數範本
├── .github/
│   └── workflows/
│       └── daily_news.yml           # GitHub Actions 排程
└── README.md
```

---

## 一、申請各 API Key

### 1. Google Gemini API Key

1. 前往 [Google AI Studio](https://aistudio.google.com/app/apikey)
2. 登入 Google 帳號
3. 點擊「Create API key」
4. 選擇「Create API key in new project」或選擇現有專案
5. 複製產生的 API Key（格式：`AIza...`）

> **注意**：Gemini 免費方案每分鐘有 15 次請求限制，本 Bot 每個主題間隔 3 秒，共 5 個主題，正常使用不會超限。

### 2. NewsAPI Key

1. 前往 [NewsAPI 註冊頁面](https://newsapi.org/register)
2. 填寫 Email、姓名、密碼完成註冊
3. 驗證 Email 後登入
4. 在 Dashboard 首頁即可看到你的 API Key（格式：`abc123...`）

> **注意**：免費方案（Developer）只能查詢最近 30 天內的新聞，且每天限制 100 次請求。本 Bot 每次執行共 3 個 NewsAPI 主題，完全在限額內。

---

## 二、在 Discord 建立 Webhook

每個新聞主題需要一個 Webhook URL。台灣時事與台灣財經/產業共用同一個（`WEBHOOK_TAIWAN`），所以總共需要建立 **4 個 Webhook**。

### 建立步驟（每個頻道重複一次）

1. 在 Discord 伺服器中，對目標頻道按右鍵 → **編輯頻道**
2. 左側選單點選「**整合**」（Integrations）
3. 點擊「**Webhooks**」→「**建立 Webhook**」
4. 設定 Webhook 名稱（例如：`每日科技新聞`）
5. 點擊「**複製 Webhook URL**」
6. 儲存設定

### 建議的頻道與 Webhook 對應

| 環境變數 | 建議頻道名稱 | 推送內容 |
|---|---|---|
| `WEBHOOK_TECH` | `#科技-AI新聞` | 科技/AI 主題 |
| `WEBHOOK_FINANCE` | `#國際財經` | 國際財經主題 |
| `WEBHOOK_POLITICS` | `#國際政治` | 國際政治主題 |
| `WEBHOOK_TAIWAN` | `#台灣新聞` | 台灣時事 + 台灣財經/產業（同頻道兩則） |

---

## 三、設定 GitHub Secrets

1. 在你的 GitHub Repository 頁面，點擊「**Settings**」
2. 左側選單點選「**Secrets and variables**」→「**Actions**」
3. 點擊「**New repository secret**」，依序加入以下 4 個 Secrets：

| Secret 名稱 | 值 |
|---|---|
| `GEMINI_API_KEY` | Google Gemini API Key |
| `NEWS_API_KEY` | NewsAPI Key |
| `WEBHOOK_TECH` | 科技頻道的 Webhook URL |
| `WEBHOOK_FINANCE` | 財經頻道的 Webhook URL |
| `WEBHOOK_POLITICS` | 政治頻道的 Webhook URL |
| `WEBHOOK_TAIWAN` | 台灣頻道的 Webhook URL |

---

## 四、Fork 並啟用 GitHub Actions

### 方式一：Fork 此 Repository（推薦）

1. 點擊本 Repository 右上角的「**Fork**」
2. 選擇你的帳號，完成 Fork
3. 在你 Fork 後的 Repository 中，依照第三步設定 GitHub Secrets
4. 點擊「**Actions**」頁籤
5. 若看到「I understand my workflows, go ahead and enable them」，點擊確認啟用
6. 左側選擇「**Daily News Bot**」→ 點擊「**Enable workflow**」

### 方式二：建立新 Repository

1. 建立新的 GitHub Repository
2. 將本專案所有檔案上傳（或使用 `git push`）
3. 依照第三步設定 GitHub Secrets
4. GitHub Actions 會自動偵測 `.github/workflows/daily_news.yml` 並啟用排程

### 手動測試執行

啟用後可立即手動測試：
1. 進入 Repository 的「**Actions**」頁籤
2. 左側點選「**Daily News Bot**」
3. 右側點擊「**Run workflow**」→「**Run workflow**」
4. 等待約 1-2 分鐘，查看執行結果與 Discord 頻道是否收到訊息

---

## 五、修改主題與頻道設定

### 修改主題數量或查詢關鍵字

編輯 `config.json`：

```json
{
  "news_per_topic": 5,  // 每個主題抓幾則新聞（建議 3-10）
  "topics": [
    {
      "name": "科技/AI",         // 顯示在 Discord 標題的名稱
      "emoji": "🤖",             // 標題前的 emoji
      "color": 5793266,          // Embed 左側色條（十進位色碼）
      "source": "newsapi",       // "newsapi" 或 "rss"
      "query": "artificial intelligence OR AI technology",  // NewsAPI 搜尋關鍵字
      "language": "en",          // 新聞語言（newsapi 專用）
      "webhook_env": "WEBHOOK_TECH"  // 對應的環境變數名稱
    }
  ]
}
```

### 新增 RSS 主題

```json
{
  "name": "新主題名稱",
  "emoji": "📰",
  "color": 16711680,
  "source": "rss",
  "rss_url": "https://example.com/rss.xml",
  "webhook_env": "WEBHOOK_NEW"
}
```

新增後記得在 GitHub Secrets 加入 `WEBHOOK_NEW`，並在 `.github/workflows/daily_news.yml` 的 `env` 區塊加上：

```yaml
WEBHOOK_NEW: ${{ secrets.WEBHOOK_NEW }}
```

### 修改 Embed 顏色

顏色值為十進位整數，可用以下方式換算：

```python
# 例：#58B9F2（淺藍色）→ 十進位
int("58B9F2", 16)  # = 5814770
```

或使用 [Discord Color Picker](https://www.spycolor.com/) 網站查詢。

---

## 本地測試

```bash
# 安裝相依套件
pip install -r requirements.txt

# 複製環境變數範本
cp .env.example .env

# 填入真實的 API Key 與 Webhook URL
# 編輯 .env 檔案...

# 執行
python main.py
```

---

## 錯誤排查

| 問題 | 可能原因 | 解決方式 |
|---|---|---|
| Discord 沒收到訊息 | Webhook URL 錯誤或已失效 | 重新建立 Webhook 並更新 Secret |
| Gemini 返回錯誤 | API Key 無效或超出配額 | 確認 Key 正確；等隔天配額重置 |
| NewsAPI 返回 401 | API Key 錯誤 | 確認 `NEWS_API_KEY` Secret 正確 |
| RSS 抓不到新聞 | RSS URL 失效 | 更新 `config.json` 中的 `rss_url` |
| Actions 沒有按時執行 | GitHub 免費帳號排程可能延遲 | 屬正常現象，最多延遲 30 分鐘 |

---

## 授權

MIT License
