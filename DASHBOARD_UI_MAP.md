# DASHBOARD_UI_MAP.md — מיפוי UI ונתונים של dashboard.py

> מסמך גילוי בלבד — נוצר ב-2026-06-03. לא שונה שום קוד.
> מבוסס על קריאה מלאה של dashboard.py (2,693 שורות).

---

## 1. מבנה הדשבורד

### מודל ניווט
**Sidebar radio** עם 4 עמודים — אין tabs, אין multi-page app, אין URL routing.
הניווט נעשה דרך `st.radio()` בסיידבר, ורינדור העמוד נשלט ע"י בלוק `if/elif` אחד בגוף הקובץ.

```
Sidebar
  ├── 🏠 Home           — מה לעשות עכשיו
  ├── 🕹️ Demo Trading   — זירת מסחר דמו
  ├── 🔵 Open Positions — N פוזיציות פתוחות
  └── 📜 History        — N אסטרטגיות שפקעו
```

**אלמנטים שתמיד מוצגים** (מחוץ לניווט):
- Header: `◆ TA-35 — Iron Condor Strategy Desk` + תאריך/שעה
- Freshness Banner: פס סטטוס נתונים + מדד TA-35 + מספר שורות/פקיעות
- Footer: שורה אחת עם copyright + auto-refresh + שעה

### מפת שורות לפי בלוק

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
| Load data + computed cols | 1562–1618 | Sidebar navigation |
| 🏠 Home | 1620–1812 | ~192 שורות |
| 🕹️ Demo Trading | 1815–2410 | ~595 שורות |
| 🔵 Open Positions | 2412–2550 | ~138 שורות (בתוך elif) |
| 📜 History | 2551–2678 | ~127 שורות (בתוך elif) |
| Footer | 2684–2693 | 10 שורות |

---

## 2. אינוונטר ויזואליזציות

### תמיד מוצג (כל עמוד)

| # | שם | סוג | ספרייה | מקור נתונים | שאלה שעונה |
|---|-----|-----|---------|-------------|-------------|
| 1 | Freshness Banner | Custom HTML div (pill-shaped) | st.markdown unsafe | `tase_putcall` (last fetch_date+fetch_time) + Yahoo | האם הנתונים עדכניים? מה מדד TA-35 עכשיו? |

---

### 🏠 Home

| # | שם | סוג | ספרייה | מקור נתונים | שאלה שעונה |
|---|-----|-----|---------|-------------|-------------|
| 2 | המלצה שבועית (Top 3) | Custom HTML cards (`rec-card`) | st.markdown unsafe | `iron_condor_strategies` — שבוע אחרון, unsettled, פקיעה קרובה | איזה מרווח כדאי לסחור השבוע? |
| 3 | "בסיכון עכשיו" | Custom HTML table (`table-scroll`) | st.markdown unsafe | `iron_condor_strategies` — unsettled + computed breakevens vs. live index | אילו פוזיציות פתוחות קרובות ל-breakeven? |
| 4 | דופק השבוע | Custom HTML metric-grid (4 כרטיסים) | st.markdown unsafe | `iron_condor_strategies` (settled, שבוע נוכחי) + `demo_balance` + `demo_trades` | P&L שבועי מסולק / מרווח מוביל / פוזיציות דמו פתוחות / יתרת דמו |
| 5 | מרווחים מועדפים | st.multiselect + st.button | Streamlit native | `pipeline_state` (key=preferred_intervals) | בחירה אילו מרווחים נכללים בסיכום |

---

### 🕹️ Demo Trading

| # | שם | סוג | ספרייה | מקור נתונים | שאלה שעונה |
|---|-----|-----|---------|-------------|-------------|
| 6 | Sandbox metrics | Custom HTML metric-grid (4 כרטיסים) | st.markdown unsafe | `session_state.sandbox_legs` (computed) | Net Premium / Max Profit / Max Loss / Breakevens של האסטרטגיה שנבנית |
| 7 | Payoff Chart — Sandbox | Plotly Scatter עם fill areas (ירוק/אדום) | plotly.graph_objects | `session_state.sandbox_legs` (computed) | עקומת P&L של האסטרטגיה על פני טווח מחירי מדד. מציג גם את strike lines ונקודות breakeven |
| 8 | Legs Table — Sandbox | Custom HTML table | st.markdown unsafe | `session_state.sandbox_legs` | פירוט כל רגל: סוג / פעולה / strike / premium / qty / cost/credit |
| 9 | Strategy Builder | st.expander + st.selectbox + st.number_input × N | Streamlit native | session_state + SANDBOX_TEMPLATES dict | עריכת רגליים ידנית / טעינת תבנית |
| 10 | Option Chain | Custom HTML table (`chain-wrap`) — 9 עמודות | st.markdown unsafe | `tase_putcall` (latest snapshot עבור expiry נבחר): strike, lastrate_call/put, delta, OI, volume | מחירי אופציות live לפי strike. ATM מסומן בצבע שונה. ITM מודגש. |
| 11 | Portfolio metrics | Custom HTML metric-grid (4 כרטיסים) | st.markdown unsafe | `demo_balance` + `demo_trades` (open+closed) | יתרת חשבון / P&L לא ממומש כולל / מספר פוזיציות פתוחות / סגורות |
| 12 | Open Positions List | Custom HTML cards + per-leg tables | st.markdown unsafe | `demo_trades` (status=open) + computed P&L | פירוט כל פוזיציה פתוחה עם P&L לא ממומש לפי רגל |
| 13 | Closed Trades Table | Custom HTML table | st.markdown unsafe | `demo_trades` (status=closed) | היסטוריית עסקאות: כניסה / סטלמנט / P&L / סיבת סגירה |
| 14 | Auto-Settlement Dialog | @st.dialog modal | Streamlit native | `iron_condor_strategies` (actual_index_close) + `demo_trades` | הודעה אוטומטית כשפוזיציות פגו — P&L מסולק ויתרה מעודכנת |

---

### 🔵 Open Positions

| # | שם | סוג | ספרייה | מקור נתונים | שאלה שעונה |
|---|-----|-----|---------|-------------|-------------|
| 15 | Week header metrics | Custom HTML metric-grid (5 כרטיסים) | st.markdown unsafe | `iron_condor_strategies` (שבוע נבחר) | Run Date / Run Time / Entry Index / Strategies count / Status badge |
| 16 | Interval summary metrics | Custom HTML metric-grid (עד 8 כרטיסים) | st.markdown unsafe | `iron_condor_strategies` (unsettled) + computed unrealized P&L | P&L לא ממומש לפי מרווח עבור כל השבוע |
| 17 | Live Index metrics | Custom HTML metric-grid (3 כרטיסים) | st.markdown unsafe | live_index (Yahoo/Supabase) + `iron_condor_strategies` | Live Index / שינוי מכניסה / Unrealized P&L (LIVE או PROXY) |
| 18 | Legs Table | Custom HTML table (`table-scroll`) | render_legs_table() | `iron_condor_strategies` (מרווח נבחר) | 4 רגלי ה-Iron Condor: Leg / Action / Strike / Premium |
| 19 | Expiry Metrics | Custom HTML metric-grid (7 כרטיסים) | render_expiry_metrics() | `iron_condor_strategies` (מרווח נבחר) | Net Premium / Max Profit / Max Risk / R:R / Lower BE / Upper BE / DTE |
| 20 | Payoff Chart — Open | Plotly Scatter עם fill areas + live index vline | render_payoff_chart() | `iron_condor_strategies` + live_index | עקומת P&L עם קו מדד חי — האם אנחנו ב-safe zone? |

---

### 📜 History

| # | שם | סוג | ספרייה | מקור נתונים | שאלה שעונה |
|---|-----|-----|---------|-------------|-------------|
| 21 | Week header metrics | Custom HTML metric-grid (5 כרטיסים) | st.markdown unsafe | `iron_condor_strategies` (שבוע נבחר) | אותם 5 כרטיסים כמו Open Positions |
| 22 | Interval Comparison Table | Custom HTML table | st.markdown unsafe | `iron_condor_strategies` (settled, שבוע נבחר) | השוואת מרווחים: Expiries / Wins / Win Rate / Max Possible / Actual P&L / Utilization |
| 23 | Progress Bars — Max vs. Actual | Custom HTML `cmp-row` divs (HTML progress bars) | st.markdown unsafe | `iron_condor_strategies` (settled, שבוע נבחר) | ויזואליזציה של: כמה מהרווח הפוטנציאלי מומש בפועל, לפי מרווח |
| 24 | Settlement metrics | Custom HTML metric-grid (4 כרטיסים) | st.markdown unsafe | `iron_condor_strategies` (settled row, מרווח נבחר) | Settlement Index / Zone badge (SAFE/PUT BREACH/etc.) / Actual P&L / Max Possible |
| 25 | Legs Table | Custom HTML table | render_legs_table() | `iron_condor_strategies` (settled row) | 4 רגלי ה-Iron Condor בכניסה |
| 26 | Strike Distance Table | Custom HTML table | st.markdown unsafe | `iron_condor_strategies` (settled row) | מרחק כל strike מסטלמנט — מה היה הסיכוי לפרוץ? |
| 27 | Expiry Metrics | Custom HTML metric-grid (7 כרטיסים) | render_expiry_metrics() | `iron_condor_strategies` (settled row) | אותם 7 כרטיסים כמו Open Positions |
| 28 | Payoff Chart — History | Plotly Scatter עם fill areas + settlement vline | render_payoff_chart() | `iron_condor_strategies` + actual_index_close | עקומת P&L עם קו סטלמנט — איפה בדיוק נפלנו? |
| 29 | P&L Hero | Custom HTML `pnl-hero` div | st.markdown unsafe | `iron_condor_strategies` (actual_pnl_ils) | הצגה גדולה ומרכזית של תוצאת P&L הסופית |

---

## 3. נתונים

### טבלאות Supabase שמשמשות את הדשבורד

| טבלה | TTL cache | שאילתה | שימוש |
|------|-----------|---------|-------|
| `iron_condor_strategies` | 120 שניות | `select=*`, 90 יום אחורה, batch 1000 | כל עמודות הניתוח: Home / Open / History |
| `tase_putcall` | 60 שניות | latest fetch_date+fetch_time, 1000 שורות | freshness banner, live index, option chain |
| `tase_putcall` (chain) | 90 שניות | expiry_date + latest snapshot, 500/batch | Option Chain ב-Demo Trading |
| `pipeline_state` | 30 שניות | key=preferred_intervals | מרווחים מועדפים |
| `demo_balance` | ללא cache | latest row | יתרת חשבון demo |
| `demo_trades` | ללא cache | status=open/closed | פוזיציות paper trading |

### שדות זמינים ב-DB שאינם מוצגים בדשבורד

אלה שדות שנטענים (בשאילתת `select=*`) אך אינם מוצגים בשום רכיב ויזואלי:

**מ-`iron_condor_strategies`:**
| שדה | תיאור | הזדמנות ויזואליזציה |
|-----|--------|---------------------|
| `result_status` | טקסט: max_profit / partial / max_loss / zero | Breakdown chart לפי תוצאה |
| `actual_pnl_points` | P&L בנקודות מדד (לא ₪) | השוואת תוצאות על ציר מדד |
| `short_put_delta` / `long_put_delta` | דלתא של כל רגל בכניסה | טבלת רגליים עם דלתא |
| `short_call_delta` / `long_call_delta` | — | — |
| `premium_flag` | "price_capped", "low_liquidity", "partial_liquidity" | תג/filter לאיכות נתוני כניסה |
| `trigger_time` | שעת הרצה | — |
| `days_to_expiry` | DTE בכניסה | גרף scatter: DTE vs. P&L |
| `risk_reward_ratio` | R:R המחושב (לפני תיקון premium) | — |

**מ-`tase_putcall` (בשרשרת האופציות):**
| שדה | תיאור | הזדמנות ויזואליזציה |
|-----|--------|---------------------|
| `baserate_call/put` | מחיר תיאורטי TASE | השוואה ל-lastrate בשרשרת |
| `theorprice_call/put` | מחיר תיאורטי (שדה נפרד) | — |
| `trade_date` | תאריך מסחר אחרון | freshness per-strike |

**נתונים שלא קיימים בכלל ב-DB (אין בכלל):**
- שיעור ריבית / IV / Vega / Theta — לא נאספים מ-TASE
- היסטוריית מחירי אופציות לאורך יום (רק snapshot אחרון)
- נתוני P&L מצטבר שבוע-אחרי-שבוע (לא שדה יחיד — צריך aggregation)

---

## 4. עיצוב ו-layout

### Theme
**`.streamlit/config.toml`:**
```toml
[theme]
base = "dark"
primaryColor = "#00B0FF"
backgroundColor = "#0B0D10"
secondaryBackgroundColor = "#151921"
textColor = "#E8EAED"
font = "sans serif"
```

Palette מוגדרת גם בקוד Python (קבועים `C_BG`, `C_CARD`, `C_GREEN` וכו') — משמשת ל-f-string CSS.

### CSS
**476 שורות CSS אחד** ב-`st.markdown(..., unsafe_allow_html=True)` בתחילת הקובץ (שורות 70–545). הכל מרוכז שם — אין CSS חיצוני.

**מה מוגדר ב-CSS:**
- פונט Inter מ-Google Fonts (import URL)
- הסתרת MainMenu, footer, header, deploy button
- RTL לכל `stMarkdown`, sidebar — LTR לטבלאות וגרפים
- Sidebar נעול פתוח (`collapsedControl: display:none`)
- Custom classes: `metric-card`, `metric-grid`, `table-scroll`, `fresh-banner`, `pnl-hero`, `rec-card`, `cmp-row`, `chain-wrap`, `badge`, `empty-state`, `section-hdr`, `step-breadcrumb`, `strike-zone`
- Streamlit overrides: `div[data-baseweb="select"]`

### Layout בפועל

**כל עמוד:**
- Header: markdown div מרכזי
- Freshness Banner: pill div מרכזי, max-width 760px
- גוף: `max-width: 1440px`, `padding: 1rem 2rem`

**Sidebar:** 280px min-width, נעול פתוח.

**עמודות:** `st.columns()` משמשת למיקום שורות בקרה (selectbox + button), לא לפריסת מדורים ראשיים. כל הכרטיסים וטבלאות בגוף העמוד הם scroll אנכי יחיד.

**Expanders:** רק אחד — "📐 בחר אסטרטגיה והגדר רגליים" ב-Demo Trading.

**אין containers, אין tabs, אין columns ראשיות** — הדשבורד כולו הוא עמודה אחת עם scroll.

---

## 5. אינטראקטיביות ו-UX

### Widgets ו-inputs

| Widget | מיקום | מה הוא עושה |
|--------|--------|-------------|
| `st.radio` | Sidebar | ניווט בין 4 עמודים |
| `st.selectbox` (שבוע) | Open/History | בחירת שבוע מסחר |
| `st.selectbox` (פקיעה) | Open/History | בחירת תאריך פקיעה |
| `st.selectbox` (מרווח) | Open/History | בחירת אחד מ-8 intervals |
| `st.selectbox` (תבנית) | Demo Trading | בחירת אסטרטגיה מ-10 תבניות |
| `st.selectbox` (chain expiry) | Demo Trading | בחירת פקיעה לשרשרת |
| `st.selectbox` (strike/type/action) | Demo Trading | הוספת רגל לגרף מהשרשרת |
| `st.toggle` | Demo Trading | הצג את כל ה-strikes / רק ATM±8 |
| `st.multiselect` | Home | בחירת מרווחים מועדפים |
| `st.number_input` × 5 | Demo Trading | עריכת כל רגל: strike/premium/qty |
| `st.button` — "טען תבנית" | Demo Trading | טעינת תבנית לסנדבוקס |
| `st.button` — "נקה" | Demo Trading | מחיקת כל הרגליים |
| `st.button` — "הוסף רגל" | Demo Trading | הוספת רגל ריקה |
| `st.button` — "🗑️" × N | Demo Trading | מחיקת רגל ספציפית |
| `st.button` — "שגר לדמו" | Home + Open Positions | שמירת אסטרטגיה ל-demo_trades |
| `st.button` — "שגר אסטרטגיה" | Demo Trading | ביצוע עסקה מהסנדבוקס |
| `st.button` — "סגור" | Demo Trading | סגירה ידנית של פוזיציה |
| `st.button` — "שמור מרווחים" | Home | שמירת preferred_intervals |
| `st.download_button` | Demo Trading | ייצוא היסטוריה ל-CSV |

### ניהול session_state

```python
st.session_state.sandbox_legs     # list[dict] — רגלי האסטרטגיה בסנדבוקס
st.session_state.sandbox_template # str|None — מפתח תבנית אחרונה שנטענה
st.session_state.settled_ids      # set — מזהי עסקאות שסולקו בסשן זה (למנוע dialog כפול)
```

### זרימת עדכון תצוגה
כמעט כל פעולה קוראת `st.cache_data.clear()` + `st.rerun()` — כל המטמונים נמחקים גלובלית ואז הדף נטען מחדש. אין עדכון חלקי.

---

## 6. ביצועים

### שימוש ב-cache

| פונקציה | decorator | TTL |
|---------|-----------|-----|
| `load_strategies()` | `@st.cache_data` | 120 שניות |
| `get_last_update()` | `@st.cache_data` | 60 שניות |
| `get_live_index()` | `@st.cache_data` | 60 שניות |
| `_fetch_option_prices_for_expiry()` | `@st.cache_data` | 60 שניות |
| `load_option_chain()` | `@st.cache_data` | 90 שניות |
| `get_available_expiries()` | `@st.cache_data` | 120 שניות |
| `get_preferred_intervals()` | `@st.cache_data` | 30 שניות |

**אין** `@st.cache_resource` בשום מקום.

### פונקציות ללא cache (קריאת DB בכל render)

| פונקציה | קריאות DB | בעיה |
|---------|-----------|-------|
| `get_demo_balance()` | 1 per render | נקראת בכל עמוד Demo Trading |
| `load_demo_trades("open")` | 1 per render | נקראת 2-3 פעמים בעמוד Demo Trading |
| `load_demo_trades("closed")` | 1 per render | — |
| `demo_open_has()` | קוראת `load_demo_trades("open")` בתוכה | בלולאה על Top-3 ב-Home |

### נקודות איטיות פוטנציאליות

1. **`st.cache_data.clear()` גלובלי** — כל כפתור (שגר לדמו, סגור, הוסף רגל) מנקה את כל המטמונים. לאחר כל פעולה: `load_strategies()` טוען מחדש עד 1,000 שורות × batch (HTTP).

2. **`compute_unrealized_pnl()` בלולאה** — ב-Open Positions, נקראת פעם אחת לכל interval בלולאה כדי לחשב summary metrics, ואז שוב לכרטיס הפרטים. כל קריאה פותחת HTTP request (עם cache).

3. **`load_demo_trades("open")` ב-Home** — נקראת לבדיקת `_open_demo_keys` בלולאת Top-3 (שורה 1662), ועוד פעם נפרדת ל-Week Pulse (שורה 1778). שתי קריאות HTTP ללא cache.

4. **אין auto-refresh מנגנון אמיתי** — ה-footer כותב "Auto-refresh 2 min" אך אין `st.rerun()` מתוזמן, אין `streamlit-autorefresh` ב-requirements, ואין שום מנגנון שגורם לרענון תקופתי. הנתונים מתעדכנים רק כשהמשתמש מקיים אינטראקציה ידנית.

---

## 7. נקודות חולשה בהצגה

### A. Auto-refresh שקרי
**הבעיה:** Footer + sidebar מציגים "Auto-refresh 2 min" — אך אין מנגנון כזה בקוד. הנתונים נשארים קפואים עד שהמשתמש לוחץ משהו.
**השפעה:** אם המשתמש צופה בדשבורד בשעות מסחר מבלי לגעת בדף, הוא רואה נתונים ישנים בלי לדעת.

### B. אין גרף P&L מצטבר לאורך זמן
**הבעיה:** כל הניתוח ב-History הוא within שבוע אחד בלבד. אין תצוגה של P&L מצטבר לאורך שבועות, אין equity curve, אין ביצועים כוללים.
**מה קיים:** dropdown לבחירת שבוע → אין ציר זמן רציף.
**השפעה:** לא ניתן להבין trend ארוך-טווח בלי לעבור שבוע-שבוע ידנית.

### C. כל הטבלאות HTML — לא ניתן למיין, לסנן או לייצא
**הבעיה:** כל 9+ הטבלאות בדשבורד בנויות כ-string HTML ב-`st.markdown()`. אין sorting, אין filtering, אין st.dataframe, אין צירוף CSV (חוץ מ-demo trades).
**הזדמנות שהוחמצה:** `st.dataframe()` עם `use_container_width=True` + column_config מציעה sort/filter/download מובנה.

### D. Demo Trading — עמוד ארוך מדי ועמוס מדי
**הבעיה:** עמוד אחד משלב 3 פונקציות שונות לגמרי:
  1. Sandbox builder (בנה אסטרטגיה + גרף)
  2. Option Chain (שרשרת מחירים חיה)
  3. Demo Portfolio (פוזיציות + היסטוריה)

כל אחת מהן יכולה להיות עמוד עצמאי. בפועל: scroll ארוך מאוד, הגרף נעלם כשיורדים לשרשרת.
**השפעה:** UX מבלבל — לא ברור מה המטרה של העמוד.

### E. Option Chain — לא ניתן ללחוץ ישירות על strike
**הבעיה:** השרשרת מציגה את המחירים בטבלת HTML, אבל כדי להוסיף רגל צריך:
  1. לזהות ויזואלית את ה-strike
  2. לגלול למטה
  3. לבחור מ-dropdown נפרד
  
אין click-to-add ישיר על שורה בשרשרת.

### F. אין breakdown לפי `result_status`
**הבעיה:** כל עסקה מסולקת מקבלת `result_status` (max_profit / partial / max_loss), אך שדה זה לא מוצג בשום ויזואליזציה. המשתמש רואה רק P&L כסכום — לא "כמה פעמים הגענו למקסימום רווח".

### G. דלתא של כל רגל לא מוצגת
**הבעיה:** `short_call_delta`, `short_put_delta` (ועוד) נטענים ב-`load_strategies()` אך לא מוצגים בטבלת הרגליים. המשתמש לא יכול לראות את הפרופיל ההסתברותי של הכניסה.
**יוצא דופן:** ב-Home, הדלתא משמשת לחישוב ה-score הפנימי (לא מוצגת גולמית).

### H. אין הסבר לציון ההמלצה ב-Home
**הבעיה:** כרטיסי ההמלצה מציגים "ציון 87" בלי שום הסבר גרפי — רק caption קטן בתחתית שאומר "60% סיכוי + 40% תשואה". הנוסחה לא ברורה ללא קריאת הקוד.

### I. comparison data מוגבל לשבוע אחד
**הבעיה:** טבלת "מה יכולת להרוויח?" ב-History מחשבת win rate ו-utilization רק לשבוע הנבחר. אם שבוע מכיל רק פקיעה אחת — הנתון חסר משמעות סטטיסטית.

### J. בעמוד Open Positions: unrealized P&L מחושב בשתי שיטות שונות ללא הסבר מספיק
**הבעיה:** הפונקציה `compute_unrealized_pnl()` מחזירה `("live", value)` או `("expiry_proxy", value)`. הדשבורד מציג "LIVE" / "PROXY" — אך לא מסביר שהמשמעות שונה מהותית: PROXY הוא הערכה גסה לפי מחיר מדד בלבד, לא ממחיר אופציות בשוק.

### K. אין תצוגת volatility / implied volatility
**הבעיה:** נתוני `baserate` ו-`theorprice` זמינים ב-DB (מחיר תיאורטי TASE). ההפרש בין מחיר תיאורטי למחיר שוק הוא פרוקסי ל-IV. לא מוצג בשום מקום.

### L. freshness banner לא מציין באיזה expiry יש בעיה
**הבעיה:** ה-banner מציג את זמן הסנאפשוט האחרון, אבל אם רק חלק מהפקיעות נטענו — הוא לא מציין אילו חסרות. משתמש לא יכול לדעת אם ה-70 שורות הן 2 פקיעות מלאות או 5 חלקיות.

### M. `st.cache_data.clear()` גלובלי — עלות נסויה
**הבעיה:** כל לחיצה על כפתור כלשהו מנקה את כל המטמונים (`st.cache_data.clear()`) ומריצה `st.rerun()`. משמעות: כל `load_strategies()` (עד 1,000 שורות × batches) נטען מחדש גם כשלחצו רק "הוסף רגל לסנדבוקס".
