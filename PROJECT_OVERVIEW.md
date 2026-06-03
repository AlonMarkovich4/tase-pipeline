# PROJECT_OVERVIEW.md — TASE TA-35 Iron Condor Pipeline

> מסמך מיפוי פרויקט מקיף — נוצר אוטומטית ב-2026-06-03.
> **לא לעריכה ידנית** — עדכן ע"י הרצת מחדש של סקריפט המיפוי.

---

## 1. סקירה כללית

מערכת ייצור אוטומטית מלאה ל**מסחר בפקודות Iron Condor על מדד TA-35 בבורסה לניירות ערך בתל-אביב (TASE)**.

**מה המערכת עושה:**
1. אוספת נתוני אופציות (Put/Call) חיים מ-TASE כל 15 דקות בימי מסחר (א-ה, 09:30-17:30 שעון ישראל)
2. מחשבת אסטרטגיות Iron Condor בתחילת כל שבוע מסחר (שני 12:00) על 8 אינטרוולים × N תאריכי פקיעה
3. מסלק P&L אוטומטית בתאריכי פקיעה
4. שולחת התראות Telegram לכל אירוע קריטי (heartbeat שבועי, כניסת אסטרטגיה, סיכום יומי/שבועי, סילוק, קריסות)
5. מציגה דשבורד Streamlit לניתוח ביצועים ו-paper trading
6. גיבוי נתונים שבועי ל-Supabase Storage

**למי מיועד:** לניהול עצמי של תיק paper-trading (ובעתיד live) על אופציות TA-35.

---

## 2. סטאק טכנולוגי

| שכבה | טכנולוגיה | גרסה |
|------|-----------|-------|
| שפה | Python | 3.12 |
| WAF bypass | Playwright (Chromium) | ≥1.44.0 |
| DB + REST | Supabase (PostgreSQL + PostgREST) | — |
| אחסון קבצים | Supabase Storage | — |
| ולידציה | Pydantic | ≥2.0.0 |
| HTTP client | httpx | ≥0.27.0 |
| דשבורד | Streamlit | ≥1.35.0 |
| גרפים | Plotly | ≥5.20.0 |
| עיבוד נתונים | pandas, numpy | ≥2.0, ≥1.24 |
| פריסה | Docker → Render Background Worker | — |
| התראות | Telegram Bot API | — |
| מחיר fallback | Yahoo Finance API | — |

---

## 3. מבנה התיקיות

```
tase-pipeline/
├── main.py                    # לולאת תזמור ראשית (scheduler, cycle runner, session recovery)
├── config.py                  # קבועים משותפים (שעות מסחר, פרמטרים, TZ)
├── tase_api.py                # שכבת API של TASE (תאריכי פקיעה, pagination)
├── browser.py                 # מחזור חיים של Playwright + WAF evasion
├── strategy_engine.py         # חישוב Iron Condor + סילוק P&L
├── option_schema.py           # ולידציית Pydantic + בדיקות איכות נתונים
├── database.py                # REST client ל-Supabase (upsert, history, backup)
├── supabase_client.py         # שכבת HTTP משותפת (credentials, headers)
├── telegram_bot.py            # שליחת התראות (5 סוגי התראות)
├── health_server.py           # endpoint לבדיקת liveness ב-Render (port 10000)
├── dashboard.py               # דשבורד Streamlit (~1,800 שורות — RTL, dark theme)
├── test_strategy_engine.py    # בדיקות יחידה לחישוב condor
├── requirements.txt           # תלויות Python
├── Dockerfile                 # בנייה לפריסה ב-Render
├── supabase_setup.sql         # סכמת DB (6 טבלאות)
├── .env.example               # תבנית משתני סביבה
├── .streamlit/config.toml     # ערכת dark theme לדשבורד
└── setup_task.bat             # [ישן] Windows Task Scheduler (לא בשימוש ב-production)
```

---

## 4. ארכיטקטורה וזרימת מידע

```
┌─────────────────────────────────────────────────────────────┐
│                        main.py (Render)                      │
│  לולאה כל 15 דק בשעות מסחר │ שינה בשעות שקט                │
└──────────┬──────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────┐    WAF bypass    ┌─────────────────────┐
│  browser.py      │◄────────────────►│  TASE API           │
│  Playwright +    │  page.evaluate() │  (Imperva protected) │
│  Chromium        │  JS fetch inline │                      │
└──────────┬───────┘                  └─────────────────────┘
           │ raw JSON rows
           ▼
┌──────────────────┐                  ┌─────────────────────┐
│  tase_api.py     │◄────────────────►│  option_schema.py   │
│  pagination +    │  validation gate │  Pydantic models +  │
│  expiry dates    │                  │  quality checks      │
└──────────┬───────┘                  └─────────────────────┘
           │ validated rows
           ▼
┌──────────────────┐                  ┌─────────────────────┐
│  database.py     │◄────────────────►│  Supabase           │
│  REST upsert     │  batch 50 rows   │  PostgreSQL +        │
│  state markers   │  key-value state │  PostgREST + Storage │
└──────────┬───────┘                  └─────────────────────┘
           │ Monday 12:00
           ▼
┌──────────────────┐                  ┌─────────────────────┐
│strategy_engine.py│◄────────────────►│  Yahoo Finance      │
│  Iron Condor     │  TA-35 fallback  │  (index price only)  │
│  calculation     │                  └─────────────────────┘
│  + settlement    │
└──────────┬───────┘
           │
           ▼
┌──────────────────┐                  ┌─────────────────────┐
│  telegram_bot.py │─────────────────►│  Telegram Bot API   │
│  5 alert types   │                  └─────────────────────┘
└──────────────────┘

┌──────────────────┐
│  dashboard.py    │◄── Supabase (reads)
│  Streamlit UI    │
│  + paper trading │
└──────────────────┘

┌──────────────────┐
│ health_server.py │◄── Render liveness probe (GET /)
│  port 10000      │
└──────────────────┘
```

---

## 5. פיצ'רים קיימים

| פיצ'ר | סטטוס | מיקום |
|--------|--------|-------|
| איסוף נתוני TASE כל 15 דק | **עובד** | main.py + tase_api.py |
| WAF bypass ע"י Playwright | **עובד** | browser.py |
| ולידציה + שער איכות נתונים | **עובד** | option_schema.py |
| upsert ל-Supabase (batch 50) | **עובד** | database.py |
| ניקוי snapshots ישנים | **עובד** | database.py |
| העתקה ל-history בסוף יום | **עובד** | database.py + main.py |
| גיבוי CSV שבועי ל-Storage | **עובד** | database.py + main.py |
| State markers restart-safe | **עובד** | database.py |
| זיהוי תאריך פקיעה מ-TASE | **עובד** | tase_api.py |
| fallback Yahoo לתאריכי פקיעה | **עובד** | tase_api.py |
| חישוב Iron Condor (8 intervals) | **עובד** | strategy_engine.py |
| 4-tier price matching | **עובד** | strategy_engine.py |
| Decimal arithmetic לדיוק ₪ | **עובד** | strategy_engine.py |
| Premium capping (>wing) | **עובד** | strategy_engine.py |
| Price sanity (>60 pts) | **עובד** | strategy_engine.py |
| Liquidity flags | **עובד** | strategy_engine.py |
| סינון לשבוע נוכחי בלבד | **עובד** | strategy_engine.py |
| סילוק P&L בתאריך פקיעה | **עובד** | strategy_engine.py |
| Weekly heartbeat Telegram | **עובד** | main.py + telegram_bot.py |
| Strategy launch alert | **עובד** | strategy_engine.py + telegram_bot.py |
| Settlement alert | **עובד** | strategy_engine.py + telegram_bot.py |
| Daily summary Telegram | **עובד** | main.py + telegram_bot.py |
| Weekly summary Telegram | **עובד** | main.py + telegram_bot.py |
| Crash alert + backoff | **עובד** | main.py + telegram_bot.py |
| Data quality anomaly alert | **עובד** | main.py + telegram_bot.py |
| Health check endpoint | **עובד** | health_server.py |
| Session recovery (reload → restart) | **עובד** | browser.py + main.py |
| Browser restart every 6 שעות | **עובד** | main.py |
| User-agent rotation | **עובד** | browser.py |
| Streamlit dashboard | **עובד** (חלקי — ראה §10) | dashboard.py |
| Paper trading arena | **עובד** | dashboard.py |
| Live unrealized P&L | **עובד** | dashboard.py |
| Strategy history table | **עובד** | dashboard.py |

---

## 6. Backend ו-API

המערכת **אינה** שרת API עצמאי — היא background worker. נקודות הגישה:

### Health Check (HTTP)
```
GET http://localhost:10000/
→ 200 {"status": "running"|"sleeping", "last_cycle": "...", "consecutive_failures": N, "cycles_today": N}
→ 503 אם consecutive_failures ≥ 5 וסטטוס לא sleeping
```

### Supabase REST (פנימי)
כל הגישה ל-DB דרך PostgREST עם service role key.

| פעולה | endpoint |
|-------|----------|
| upsert options | POST /tase_putcall |
| upsert strategies | POST /iron_condor_strategies |
| state markers | POST /pipeline_state |
| history copy | GET + POST /tase_putcall_history |
| backup | Storage API |

**אין אימות/הרשאות משתמש** — המערכת רצה כ-single-tenant.

### Streamlit Dashboard
גישה ישירה ל-Supabase כ-read (+ כתיבה ל-demo_balance/demo_trades).
אין login — גישה פתוחה לכל מי שיודע את ה-URL.

---

## 7. מסד נתונים

**סוג:** PostgreSQL דרך Supabase (managed)

### טבלאות עיקריות

#### `tase_putcall` (snapshot חי)
- **מטרה:** הסנאפשוט האחרון בלבד של נתוני אופציות
- **עמודות מרכזיות:** `fetch_date`, `fetch_time`, `expiry_date`, `trade_date`, `rowtype`, `drvtype`, `expirationprice_call/put`, `lastrate_call/put`, `delta_call/put`, `underlingasset_call/put`, `dealsno_call/put` + ~45 עמודות נוספות
- **upsert constraint:** (fetch_date, fetch_time, expiry_date, derivativeid_call, derivativeid_put)
- **ניקוי:** נמחקת ומתחלפת בכל cycle מוצלח

#### `tase_putcall_history` (ארכיב)
- **מטרה:** שמירה היסטורית — snapshot יומי בסוף יום מסחר
- **סכמה:** זהה ל-tase_putcall
- **גידול:** אחד לשבוע בגיבוי CSV

#### `iron_condor_strategies` (אסטרטגיות)
- **עמודות:** `trigger_date`, `trigger_time`, `base_index_value`, `expiry_date`, `interval_pct`
- **רגליים:** `short_call_strike`, `long_call_strike`, `short_put_strike`, `long_put_strike` (+ IDs, prices, deltas)
- **P&L:** `total_net_premium`, `max_profit_ils`, `max_risk_ils`, `risk_reward_ratio`, `breakeven_upper/lower`
- **סילוק:** `actual_index_close`, `actual_pnl_points`, `actual_pnl_ils`, `result_status`
- **דגלים:** `premium_flag` ("price_capped", "low_liquidity"), `actual_wing_put/call`
- **upsert constraint:** (trigger_date, expiry_date, interval_pct)

#### `pipeline_state` (מצב pipeline)
- **מטרה:** key-value store למניעת שליחה כפולה לאחר restart
- **מפתחות:** `daily_summary_sent:YYYY-MM-DD`, `weekly_summary_sent:YYYY-Www`, `strategy_triggered:YYYY-Www`, `settlement_done:YYYY-MM-DD`, `weekly_heartbeat:YYYY-Www`

#### `demo_balance` (paper trading)
- **מטרה:** ספר חשבון paper-trading
- **עמודות:** balance, reason, timestamp

#### `demo_trades` (עסקאות paper)
- **מטרה:** פוזיציות פתוחות וסגורות
- **עמודות:** `trade_id`, `strategy_name`, `expiry_date`, `entry_index`, `legs` (JSON), `max_profit_ils`, `max_risk_ils`, `net_premium_pts`, `status`, `settlement_index`, `pnl_ils`, `close_reason`

---

## 8. קונפיגורציה וסביבה

### משתני סביבה נדרשים (מ-.env.example)

```
SUPABASE_URL          # URL של פרויקט Supabase
SUPABASE_KEY          # service role key של Supabase
SUPABASE_TABLE        # שם טבלת live (ברירת מחדל: tase_putcall)
SUPABASE_HISTORY_TABLE # שם טבלת history (ברירת מחדל: tase_putcall_history)
FETCH_INTERVAL_MINUTES # אינטרוול איסוף (ברירת מחדל: 15)
HEADLESS              # true/false לדפדפן (ברירת מחדל: true)
TELEGRAM_BOT_TOKEN    # token של Telegram bot
TELEGRAM_CHAT_ID      # chat ID לשליחת הודעות
PORT                  # פורט health check (ברירת מחדל: 10000)
```

### קבועים ב-config.py
```python
TZ_ISRAEL             = ZoneInfo("Asia/Jerusalem")
TRADING_DAYS          = {0,1,2,3,4}  # א-ה
MARKET_OPEN           = 09:30
MARKET_CLOSE          = 17:30
STRATEGY_WINDOW_OPEN  = 12:00
STRATEGY_WINDOW_CLOSE = 13:00
TASE_MULTIPLIER       = 50  # ₪ לנקודה לחוזה
WING_WIDTH            = 20  # נקודות
INTERVALS             = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]  # %
PRICE_SANITY_MAX_PTS  = 60  # דחיית מחירים > 60 נקודות
BROWSER_RESTART_SECONDS = 21600  # 6 שעות
FETCH_INTERVAL_MINUTES  = 15
BATCH_SIZE              = 50
PAGE_TIMEOUT_MS         = 45000
```

### הרצה לוקאלית
```bash
# 1. התקן תלויות
pip install -r requirements.txt
playwright install chromium

# 2. הגדר .env (העתק מ-.env.example)
cp .env.example .env
# ערוך .env עם הפרטים האמיתיים

# 3. הרץ pipeline
python main.py

# 4. הרץ דשבורד (בטרמינל נפרד)
streamlit run dashboard.py

# 5. הרץ בדיקות
python test_strategy_engine.py
```

---

## 9. דיפלוי

### פלטפורמה
**Render** — Background Worker (לא Web Service) עם Docker.

### Dockerfile
1. `python:3.12-slim` כבסיס
2. התקנת system deps לChromium (libx11, libnss3, libdrm2, ...)
3. `pip install -r requirements.txt`
4. `playwright install chromium`
5. העתקת קבצי המקור
6. `CMD ["python", "main.py"]`

### CI/CD
**לא קיים** — פריסה ידנית (git push → Render auto-deploy מ-main branch).

### Health Check ב-Render
Render מצביע ל-`GET /` על פורט 10000.
- 200 = בריא (רץ או ישן)
- 503 = לא בריא (קריסות חוזרות)

### Dashboard
**לא ברור / צריך אימות** — לא ברור אם dashboard.py פרוס בנפרד (כ-Render Web Service) או רק לוקאלי. ה-Dockerfile מריץ רק `main.py`.

---

## 10. חוסרים וחלקים לא גמורים

### ידועים מהקוד
1. **Dashboard deployment** — לא ברור / צריך אימות: אין Dockerfile נפרד ל-dashboard.py. ייתכן שהוא רץ לוקאלי בלבד, או שיש service נוסף ב-Render שלא מופיע בריפו.

2. **אין login ל-dashboard** — כל מי שיודע את ה-URL יכול לראות נתונים ולבצע paper trades. אם ה-URL ציבורי — זו בעיה.

3. **setup_task.bat** — קובץ ישן מתקופת deployment לוקאלי ב-Windows. לא בשימוש ב-production הנוכחי. מועמד למחיקה.

4. **אין TODO/FIXME בקוד** — הקוד נקי ממרקרים, אך זה לא ערובה לגמירות מלאה.

5. **בדיקות חלקיות** — `test_strategy_engine.py` מכסה רק `_calculate_condor()`. אין בדיקות ל:
   - `tase_api.py` (קשה לבדיקה ללא browser)
   - `database.py` (קשה ללא Supabase)
   - `telegram_bot.py` (קשה ללא bot token)
   - `main.py` (לוגיקת תזמון)

6. **Yahoo Finance fallback** — אינו רשמי; ה-API עלול להישבר ללא התראה. ה-fallback הוא לא-מתועד ולא מוגן.

7. **Singular strategy trigger window** — אם ה-pipeline יקרוס בין 12:00-13:00 ביום שני ויחזור לאחר 13:00, האסטרטגיה לא תחושב עד לשבוע הבא.

8. **User-agent pool קטן** — רק 3 Chrome versions. לא ברור אם מספיק לעקוף fingerprinting לאורך זמן.

---

## לוח זמנים מלא (שבוע מסחר טיפוסי)

| זמן (ישראל) | אירוע |
|-------------|-------|
| א 09:30 | pipeline מתעורר, מתחיל cycles |
| א ~10:00 | Weekly heartbeat Telegram (אם ראשון השבוע) |
| א 12:00-13:00 | Iron Condor strategy calculation + Telegram alert |
| א-ה כל 15 דק | fetch cycle → validate → upsert → quality check |
| ה 17:30 | Daily summary Telegram + copy to history |
| ה ~18:30 | Weekly summary Telegram |
| ה ~18:00 | Weekly CSV backup to Supabase Storage |
| יום פקיעה ~10:00+ | Settlement P&L calculation + Telegram alert |
| מחוץ לשעות מסחר | pipeline ישן, health check מחזיר 200 |

---

## 11. מיפוי UI ודשבורד (dashboard.py)

> מבוסס על קריאה מלאה של dashboard.py (2,693 שורות).

### מבנה הדשבורד

**מודל ניווט:** Sidebar radio עם 4 עמודים — אין tabs, אין multi-page app, אין URL routing.
הניווט נעשה דרך `st.radio()` בסיידבר, ורינדור העמוד נשלט ע"י בלוק `if/elif` אחד בגוף הקובץ.

```
Sidebar
  ├── 🏠 Home           — מה לעשות עכשיו
  ├── 🕹️ Demo Trading   — זירת מסחר דמו
  ├── 🔵 Open Positions — N פוזיציות פתוחות
  └── 📜 History        — N אסטרטגיות שפקעו
```

**אלמנטים שתמיד מוצגים:** Header + Freshness Banner (מדד TA-35, שורות, פקיעות, זמן עדכון) + Footer.

**מפת שורות:**

| בלוק | שורות | תיאור |
|------|--------|-------|
| Imports + config | 1–68 | ייבוא, palette, קבועים |
| Global CSS | 69–545 | בלוק סגנון אחד (476 שורות) |
| Data layer — strategies | 549–790 | load_strategies, get_last_update, get_live_index, preferred_intervals |
| Data layer — demo trading | 792–978 | load_option_chain, demo CRUD functions |
| Helpers + computations | 981–1213 | fmt_*, compute_unrealized_pnl, build_payoff_curve, sandbox helpers |
| Render components | 1215–1340 | render_payoff_chart, render_legs_table, render_expiry_metrics, render_breadcrumb |
| Sandbox templates | 1343–1449 | 10 תבניות אסטרטגיה עם הגדרות רגליים |
| Session state + dialog | 1452–1481 | אתחול session_state, @st.dialog לסטלמנט |
| Header + freshness banner | 1483–1559 | Always-visible header |
| 🏠 Home | 1620–1812 | ~192 שורות |
| 🕹️ Demo Trading | 1815–2410 | ~595 שורות |
| 🔵 Open Positions | 2412–2550 | ~138 שורות (בתוך elif) |
| 📜 History | 2551–2678 | ~127 שורות (בתוך elif) |

---

### אינוונטר ויזואליזציות (29 רכיבים)

**תמיד מוצג:**

| # | שם | סוג | ספרייה | מקור נתונים | שאלה שעונה |
|---|-----|-----|---------|-------------|-------------|
| 1 | Freshness Banner | Custom HTML div (pill) | st.markdown unsafe | `tase_putcall` (last fetch) + Yahoo | האם הנתונים עדכניים? מה מדד TA-35 עכשיו? |

**🏠 Home:**

| # | שם | סוג | ספרייה | מקור נתונים | שאלה שעונה |
|---|-----|-----|---------|-------------|-------------|
| 2 | המלצה שבועית (Top 3) | Custom HTML cards | st.markdown unsafe | `iron_condor_strategies` — שבוע אחרון, unsettled | איזה מרווח כדאי לסחור השבוע? |
| 3 | "בסיכון עכשיו" | Custom HTML table | st.markdown unsafe | `iron_condor_strategies` — breakevens vs. live index | אילו פוזיציות קרובות ל-breakeven? |
| 4 | דופק השבוע | metric-grid (4 כרטיסים) | st.markdown unsafe | `iron_condor_strategies` + `demo_balance` + `demo_trades` | P&L שבועי / מרווח מוביל / דמו פתוח / יתרה |
| 5 | מרווחים מועדפים | st.multiselect + st.button | Streamlit native | `pipeline_state` | בחירה אילו מרווחים נכללים בסיכום |

**🕹️ Demo Trading:**

| # | שם | סוג | ספרייה | מקור נתונים | שאלה שעונה |
|---|-----|-----|---------|-------------|-------------|
| 6 | Sandbox metrics | metric-grid (4 כרטיסים) | st.markdown unsafe | session_state.sandbox_legs (computed) | Net Premium / Max Profit / Max Loss / Breakevens |
| 7 | Payoff Chart — Sandbox | Plotly Scatter + fill areas | plotly.graph_objects | session_state.sandbox_legs (computed) | עקומת P&L של האסטרטגיה שנבנית |
| 8 | Legs Table — Sandbox | Custom HTML table | st.markdown unsafe | session_state.sandbox_legs | פירוט רגליים: סוג / פעולה / strike / premium / qty / cost |
| 9 | Strategy Builder | st.expander + selectbox + number_input | Streamlit native | session_state + SANDBOX_TEMPLATES | עריכת רגליים ידנית / טעינת תבנית |
| 10 | Option Chain | Custom HTML table (9 עמודות) | st.markdown unsafe | `tase_putcall` (latest snapshot, expiry נבחר) | מחירי אופציות live לפי strike; ATM מסומן, ITM מודגש |
| 11 | Portfolio metrics | metric-grid (4 כרטיסים) | st.markdown unsafe | `demo_balance` + `demo_trades` | יתרה / P&L לא ממומש / פתוחות / סגורות |
| 12 | Open Positions List | Custom HTML cards + per-leg tables | st.markdown unsafe | `demo_trades` (open) + computed P&L | P&L לא ממומש לפי רגל לכל פוזיציה |
| 13 | Closed Trades Table | Custom HTML table | st.markdown unsafe | `demo_trades` (closed) | היסטוריה: כניסה / סטלמנט / P&L / סיבה |
| 14 | Auto-Settlement Dialog | @st.dialog modal | Streamlit native | `iron_condor_strategies` (actual_index_close) | הודעה כשפוזיציות פגו — P&L ויתרה מעודכנת |

**🔵 Open Positions:**

| # | שם | סוג | ספרייה | מקור נתונים | שאלה שעונה |
|---|-----|-----|---------|-------------|-------------|
| 15 | Week header metrics | metric-grid (5 כרטיסים) | st.markdown unsafe | `iron_condor_strategies` (שבוע נבחר) | Run Date / Run Time / Entry Index / Count / Status |
| 16 | Interval summary metrics | metric-grid (עד 8 כרטיסים) | st.markdown unsafe | `iron_condor_strategies` (unsettled) + computed | P&L לא ממומש לפי מרווח |
| 17 | Live Index metrics | metric-grid (3 כרטיסים) | st.markdown unsafe | live_index + `iron_condor_strategies` | Index / שינוי מכניסה / Unrealized P&L (LIVE/PROXY) |
| 18 | Legs Table | Custom HTML table | render_legs_table() | `iron_condor_strategies` (מרווח נבחר) | 4 רגלי ה-Iron Condor |
| 19 | Expiry Metrics | metric-grid (7 כרטיסים) | render_expiry_metrics() | `iron_condor_strategies` | Premium / Max Profit / Max Risk / R:R / BEs / DTE |
| 20 | Payoff Chart — Open | Plotly Scatter + fill + live vline | render_payoff_chart() | `iron_condor_strategies` + live_index | עקומת P&L עם קו מדד חי |

**📜 History:**

| # | שם | סוג | ספרייה | מקור נתונים | שאלה שעונה |
|---|-----|-----|---------|-------------|-------------|
| 21 | Week header metrics | metric-grid (5 כרטיסים) | st.markdown unsafe | `iron_condor_strategies` (שבוע נבחר) | אותם 5 כרטיסים כמו Open Positions |
| 22 | Interval Comparison Table | Custom HTML table | st.markdown unsafe | `iron_condor_strategies` (settled) | Wins / Win Rate / Max Possible / Actual P&L / Utilization |
| 23 | Progress Bars — Max vs. Actual | Custom HTML cmp-row divs | st.markdown unsafe | `iron_condor_strategies` (settled) | כמה מהרווח הפוטנציאלי מומש, לפי מרווח |
| 24 | Settlement metrics | metric-grid (4 כרטיסים) | st.markdown unsafe | `iron_condor_strategies` (settled row) | Settlement Index / Zone badge / Actual P&L / Max Possible |
| 25 | Legs Table | Custom HTML table | render_legs_table() | `iron_condor_strategies` (settled row) | 4 רגלי הכניסה |
| 26 | Strike Distance Table | Custom HTML table | st.markdown unsafe | `iron_condor_strategies` (settled row) | מרחק כל strike מסטלמנט |
| 27 | Expiry Metrics | metric-grid (7 כרטיסים) | render_expiry_metrics() | `iron_condor_strategies` | אותם 7 כרטיסים כמו Open Positions |
| 28 | Payoff Chart — History | Plotly Scatter + fill + settlement vline | render_payoff_chart() | `iron_condor_strategies` + actual_index_close | עקומת P&L עם קו סטלמנט |
| 29 | P&L Hero | Custom HTML pnl-hero div | st.markdown unsafe | `iron_condor_strategies` (actual_pnl_ils) | הצגה גדולה של תוצאת P&L הסופית |

---

### נתונים — טבלאות ושדות

**טבלאות שמשמשות את הדשבורד:**

| טבלה | TTL cache | שימוש |
|------|-----------|-------|
| `iron_condor_strategies` | 120 שניות | כל עמודות הניתוח |
| `tase_putcall` | 60 שניות | freshness banner, live index, option chain |
| `pipeline_state` | 30 שניות | מרווחים מועדפים |
| `demo_balance` | ללא cache | יתרת חשבון demo |
| `demo_trades` | ללא cache | פוזיציות paper trading |

**שדות זמינים ב-DB שאינם מוצגים בדשבורד:**

| שדה | תיאור |
|-----|--------|
| `result_status` | max_profit / partial / max_loss / zero — לא מוצג בשום גרף |
| `actual_pnl_points` | P&L בנקודות (לא ₪) |
| `short/long_call/put_delta` | דלתא לכל רגל בכניסה — לא מוצגת בטבלת הרגליים |
| `premium_flag` | price_capped / low_liquidity — לא מוצג כ-filter |
| `days_to_expiry` | DTE בכניסה — מוצג רק בכרטיס אחד |
| `baserate_call/put` | מחיר תיאורטי TASE — לא מוצג בשרשרת |

---

### עיצוב ו-layout

- **Theme:** `.streamlit/config.toml` — dark, primaryColor `#00B0FF`, bg `#0B0D10`
- **CSS:** בלוק אחד של 476 שורות ב-`st.markdown(unsafe_allow_html=True)`, כולל Inter font מ-Google Fonts
- **RTL/LTR:** sidebar + markdown = RTL; טבלאות + גרפים = LTR (מוגדר ב-CSS)
- **Sidebar:** נעול פתוח, 280px min-width
- **Layout:** עמודה אחת רציפה עם scroll — אין columns ראשיות, אין tabs, רק `st.columns()` לשורות בקרה
- **Expanders:** רק אחד — Strategy Builder ב-Demo Trading

---

### אינטראקטיביות ו-UX

**Session state (3 מפתחות):**
```python
st.session_state.sandbox_legs     # list[dict] — רגלי הסנדבוקס
st.session_state.sandbox_template # str|None — תבנית אחרונה
st.session_state.settled_ids      # set — עסקאות שסולקו בסשן (למנוע dialog כפול)
```

**זרימת עדכון:** כמעט כל פעולה קוראת `st.cache_data.clear()` + `st.rerun()` — ניקוי גלובלי של כל המטמונים ורענון מלא.

---

### ביצועים

**פונקציות מ-cached:**

| פונקציה | TTL |
|---------|-----|
| `load_strategies()` | 120 שניות |
| `get_last_update()` | 60 שניות |
| `get_live_index()` | 60 שניות |
| `_fetch_option_prices_for_expiry()` | 60 שניות |
| `load_option_chain()` | 90 שניות |
| `get_available_expiries()` | 120 שניות |
| `get_preferred_intervals()` | 30 שניות |

**פונקציות ללא cache (קריאת DB בכל render):** `get_demo_balance()`, `load_demo_trades("open")` (נקראת 2–3 פעמים בעמוד), `demo_open_has()`.

---

### נקודות חולשה בהצגה

| # | חולשה | פירוט |
|---|--------|-------|
| A | Auto-refresh שקרי | Footer + sidebar כותבים "Auto-refresh 2 min" — אין מנגנון כזה בקוד. הנתונים קפואים עד אינטראקציה ידנית |
| B | אין equity curve | כל ניתוח History מוגבל לשבוע אחד — אין P&L מצטבר לאורך שבועות, אין trend |
| C | טבלאות HTML — לא ניתן למיין/לסנן | כל 9+ הטבלאות הן string HTML — אין sorting, filtering, או export מובנה |
| D | Demo Trading עמוס מדי | עמוד אחד משלב: sandbox builder + option chain + portfolio — scroll ארוך, הגרף נעלם בגלילה |
| E | Option Chain — אין click-to-add | להוסיף רגל מהשרשרת: לזהות strike → לגלול למטה → לבחור מ-dropdown נפרד |
| F | result_status לא מוצג | כל עסקה מקבלת max_profit/partial/max_loss, אך לא מוצג בשום ויזואליזציה |
| G | דלתא לא מוצגת | short/long delta נטענים אך לא מוצגים בטבלת הרגליים |
| H | ציון המלצה לא מוסבר | "ציון 87" בלי הסבר גרפי — רק caption קטן בתחתית |
| I | Comparison data — שבוע אחד בלבד | win rate ו-utilization מחושבים לשבוע הנבחר; אם שבוע = פקיעה אחת, חסר משמעות סטטיסטית |
| J | LIVE vs. PROXY לא מוסבר | "PROXY" = הערכה גסה לפי מחיר מדד בלבד, לא ממחיר אופציות — המשמעות השונה לא מוסברת |
| K | אין תצוגת IV | baserate ו-theorprice זמינים ב-DB — ההפרש ממחיר שוק הוא פרוקסי ל-IV, לא מוצג |
| L | Freshness banner לא מפרט איזה expiry חסר | מספר שורות כולל — לא ניתן לדעת אם 70 שורות = 2 פקיעות מלאות או 5 חלקיות |
| M | `st.cache_data.clear()` גלובלי | כל לחיצה (כולל "הוסף רגל") מנקה את כל המטמונים — load_strategies() טוען מחדש 1,000 שורות |
