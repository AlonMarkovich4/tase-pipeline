# UI Blueprint — שחזור ה-look-and-feel של `web/`

מסמך תיעוד לשחזור ה-UI של הדשבורד הקיים (`web/`, ה-Final, Next.js) בפרויקט חדש,
**ללא הלוגיקה הספציפית ל-TASE**. כל הערכים כאן נקראו בפועל מ-`web/src`.

> TL;DR: זה דשבורד **dark-first, RTL, עברית**, על **Next.js 16 App Router + React 19 + Tailwind v4 (CSS-first)**.
> אין ספריות UI/אנימציה/גרפים חיצוניות — **הכול hand-built**: אייקוני SVG inline, גרפים ב-SVG ידני, אנימציה ב-CSS keyframes.
> ה-design system כולו חי ב-`globals.css` כ-design tokens. זה החלק שאתה לוקח כמו שהוא.

---

## 1. הסטאק והתשתית

### 1.1 התלויות בפועל (`web/package.json`)

```json
{
  "engines": { "node": ">=20.9.0" },
  "dependencies": {
    "next": "16.2.9",
    "react": "19.2.4",
    "react-dom": "19.2.4"
  },
  "devDependencies": {
    "@tailwindcss/postcss": "^4",
    "@types/node": "^20",
    "@types/react": "^19",
    "@types/react-dom": "^19",
    "eslint": "^9",
    "eslint-config-next": "16.2.9",
    "tailwindcss": "^4",
    "typescript": "^5"
  }
}
```

**שים לב — מה שאין כאן חשוב כמו מה שיש:**

| מה שאולי ציפית | המצב בפועל |
|---|---|
| `framer-motion` | ❌ אין. אנימציות = CSS `@keyframes` + Tailwind `transition`. |
| `lenis` (smooth scroll) | ❌ אין. גלילה רגילה + scrollbar מעוצב ב-CSS. |
| `recharts` / `chart.js` / `d3` | ❌ אין. כל גרף הוא `<svg>` בנוי ידנית (ראה §5). |
| ספריית אייקונים (`lucide`, `heroicons`) | ❌ אין. אייקוני SVG inline ב-`components/icons.tsx`. |
| ספריית UI (`shadcn`, `radix`, `mui`) | ❌ אין. כל הרכיבים מקומיים, Tailwind בלבד. |
| `next-themes` | ❌ אין. החלפת theme ידנית עם `class` על `<html>` + `localStorage`. |

זה stack מינימלי בכוונה. **היתרון לפרויקט החדש:** אפס תלות חיצונית להעתיק, הכול קוד שאתה שולט בו.

### 1.2 רכיבי התשתית

- **Next.js 16.2.9, App Router** — תיקיית `src/app/`, כל `page.tsx` הוא **React Server Component** (async, fetch בצד שרת). רכיבים אינטראקטיביים מסומנים `"use client"`.
  - ⚠️ הערה מ-`web/AGENTS.md`: זו גרסת Next חדשה עם breaking changes מול ידע ישן. בפרויקט חדש פשוט הרץ `create-next-app` עדכני ותקבל את ה-conventions הנכונים — אל תניח API ישן.
- **React 19.2.4**.
- **TypeScript 5**, `strict: true`, alias `@/*` → `./src/*` (ראה `tsconfig.json`).
- **Tailwind v4** דרך PostCSS plugin בלבד. **אין `tailwind.config.js`**. כל הקונפיג ב-CSS (ראה §2).
  - `postcss.config.mjs`: `{ plugins: { "@tailwindcss/postcss": {} } }`
  - `globals.css` שורה ראשונה: `@import "tailwindcss";`
- **`next.config.ts`** — ריק (ברירות מחדל).
- פונט דרך `next/font/google` (Heebo) — ראה §3.

---

## 2. Design System (הלב — לוקחים כמו שהוא)

**מקור יחיד:** `web/src/app/globals.css`. Tailwind v4 הוא **CSS-first**: בלוק `@theme { ... }` מגדיר משתני CSS שהופכים אוטומטית ל-utility classes.
לדוגמה `--color-surface` → `bg-surface` / `text-surface` / `border-surface`; `--radius-card` → `rounded-card`.

### 2.1 צבעים — ערכי dark (ברירת מחדל)

```css
@theme {
  --color-bg:        #070b14;   /* רקע האפליקציה (כמעט-שחור כחלחל) */
  --color-surface:   #0e1525;   /* רקע כרטיס */
  --color-surface2:  #141d31;   /* שכבה שנייה: אייקונים, chips, hover */
  --color-border:    rgba(255, 255, 255, 0.07);  /* גבול עדין */
  --color-border2:   rgba(255, 255, 255, 0.12);  /* גבול בולט יותר */

  --color-text1:     #e6eaf2;   /* טקסט ראשי */
  --color-text2:     #9aa6bd;   /* טקסט משני (labels) */
  --color-text3:     #5d6a82;   /* טקסט עמום (hints, צירים) */

  --color-accent:    #22d3ee;   /* ציאן — צבע המותג, פעולות, active */
  --color-accent2:   #38bdf8;   /* תכלת — accent משני */
  --color-pos:       #34d399;   /* ירוק — רווח/חיובי */
  --color-neg:       #f87171;   /* אדום — הפסד/שלילי */
  --color-warn:      #fbbf24;   /* ענבר — אזהרה/חלקי */
  --color-purple:    #a78bfa;   /* סגול — קטגוריה נוספת */

  --color-grid:        rgba(255, 255, 255, 0.06);  /* קווי גריד בגרפים */
  --color-grid-strong: rgba(255, 255, 255, 0.22);  /* ציר אפס בגרפים */

  --radius-card: 16px;

  --font-sans: var(--font-heebo), ui-sans-serif, system-ui, sans-serif;
}
```

### 2.2 צבעים — ערכי light (override על `html.light`)

ה-theme השני עובד על ידי דריסת אותם משתנים תחת `html.light`. **אותם שמות tokens** — לכן אף רכיב לא צריך לדעת על light/dark, הוא משתמש ב-`bg-surface` והצבע מתחלף לבד.

```css
html.light {
  --color-bg:        #f1f4f9;
  --color-surface:   #ffffff;
  --color-surface2:  #eaeef5;
  --color-border:    rgba(15, 23, 42, 0.10);
  --color-border2:   rgba(15, 23, 42, 0.16);
  --color-text1:     #0f172a;
  --color-text2:     #475569;
  --color-text3:     #7c8aa0;
  --color-accent:    #0891b2;
  --color-accent2:   #0284c7;
  --color-pos:       #059669;
  --color-neg:       #dc2626;
  --color-warn:      #b45309;
  --color-purple:    #7c3aed;
  --color-grid:        rgba(15, 23, 42, 0.08);
  --color-grid-strong: rgba(15, 23, 42, 0.20);
  color-scheme: light;
}
```

### 2.3 טיפוגרפיה

- פונט יחיד: **Heebo** (תומך עברית+לטינית), משקלים `400/500/600/700`.
- סולם בפועל (מתוך השימוש בקוד, Tailwind classes):
  - כותרת עמוד: `text-2xl font-bold` (24px/700)
  - כותרת מקטע/כרטיס: `text-lg font-bold` (18px/700)
  - ערך KPI גדול: `text-2xl font-bold tabular-nums` (24px) או `text-3xl` למספר הירו
  - label של KPI: `text-xs text-text2` (12px)
  - sub/hint: `text-[11px]` / `text-xs text-text3`
  - מיקרו-טקסט: `text-[10px]`
- **`tabular-nums`** על כל מספר (מחירים, אחוזים, תאריכים) — יישור ספרות עקבי. דפוס מחייב.
- כותרות נוטות ל-`tracking-tight`.

### 2.4 Spacing, radius, shadow, effects

- **Radius:** `rounded-2xl` (16px) לכרטיסים, `rounded-xl` (12px) לאריחים/אייקונים, `rounded-lg` (8px) לכפתורים/chips, `rounded-full` ל-pills ולנקודות סטטוס.
- **Spacing:** מרווח אנכי בין מקטעים `space-y-5`; padding כרטיס `p-5`/`p-6`; grid gap `gap-4`/`gap-3`.
- **Shadow:** כמעט ואין צללים כבדים. עומק נוצר מ-`border` + `bg-surface/70` + `backdrop-blur`. הדגשה נקודתית: `shadow-lg` (tooltip), `ring-1 ring-accent/30` (אלמנט פעיל).
- **Backdrop blur:** כרטיסים הם `bg-surface/70 backdrop-blur` (חצי-שקוף עם טשטוש) — נותן את תחושת ה"זכוכית".
- **Brand glow:** שתי הילות רדיאליות מאחורי כל האפליקציה דרך `body::before` (ציאן מימין-למעלה, תכלת משמאל-למטה), `pointer-events:none`, `z-index:0`. גם לה גרסת light.
- **Scrollbar מעוצב:** `scrollbar-width: thin` + thumb בצבע `rgba(255,255,255,.12)`, רוחב 8px, פינות מעוגלות. גם לה גרסת light.

### 2.5 הכרטיס הקנוני (חוזר בכל דף)

קבוע מקומי שחוזר בראש כמעט כל קובץ:

```ts
const card = "rounded-2xl border border-border bg-surface/70 backdrop-blur";
```

זה ה-DNA הוויזואלי. כל כרטיס/מקטע משתמש בו, לרוב עם `p-5` או `p-6`.

---

## 3. RTL ועברית

הכול מוגדר במקום אחד — `web/src/app/layout.tsx`:

```tsx
<html lang="he" dir="rtl" className={`${heebo.variable} h-full`}>
```

- **`dir="rtl"` על `<html>`** — כל ה-document RTL. Tailwind logical properties עובדות אוטומטית: `pr-14` הוא הצד שמתפנה לרייל, `border-l` הוא הגבול הפנימי וכו'.
- **`lang="he"`**.
- **פונט עברי** דרך `next/font/google`:

```tsx
import { Heebo } from "next/font/google";
const heebo = Heebo({
  subsets: ["hebrew", "latin"],
  variable: "--font-heebo",
  weight: ["400", "500", "600", "700"],
});
```

ה-`variable` (`--font-heebo`) מוזרק ל-`<html className>`, ו-`globals.css` מצביע אליו: `--font-sans: var(--font-heebo), ...`.

- **יישור:** טקסט מיושר לימין (`text-right`), שורות עם אייקון משתמשות ב-`justify-end` / `justify-between`. האייקון בדרך כלל **אחרי** הטקסט (מימין) ב-flow ה-RTL.
- **גרפים נשארים LTR בעיניים:** מספרים מעוצבים עם `toLocaleString("en-US")` כדי לקבל ספרות מערביות ופסיקי-אלפים, גם בתוך טקסט עברי. תאריכים מוצגים `dd/mm/yyyy`.
- **המרת חיווי דרך לוקאל:** שמות ימים/חודשים בעברית הם מילונים מקומיים (`DAYS_HE`, `MONTHS_HE`) — לא הסתמכות על `Intl` עם locale עברי.

> להעברה לפרויקט חדש לא-עברי: שנה `lang`/`dir`, החלף את הפונט, והוצא את מילוני `DAYS_HE`/`MONTHS_HE`. כל השאר (logical spacing) עובד בשני הכיוונים.

---

## 4. מבנה הדפים והרכיבים

### 4.1 מבנה תיקיות

```
web/src/
├── app/
│   ├── layout.tsx          # root: <html dir=rtl>, פונט, theme bootstrap, <AppShell>
│   ├── globals.css         # ★ כל ה-design system (tokens, theme, effects)
│   ├── page.tsx            # "/"          — דף בית / סקירה
│   ├── strategies/page.tsx # "/strategies"
│   ├── demo/page.tsx       # "/demo"
│   ├── calendar/page.tsx   # "/calendar"
│   ├── alerts/page.tsx     # "/alerts"
│   ├── settings/page.tsx   # "/settings"
│   └── simulator/
│       ├── page.tsx        # "/simulator"
│       └── actions.ts      # server action (TASE-specific)
├── components/
│   ├── AppShell.tsx        # ★ גנרי — layout: rail + brand bar + main
│   ├── Sidebar.tsx         # ★ גנרי — rail אנכי + ניווט + theme toggle
│   ├── icons.tsx           # ★ גנרי — אוסף אייקוני SVG inline
│   ├── IndexChart.tsx      # ~גנרי — גרף קו SVG עם hover
│   ├── BestCondorPager.tsx # ~גנרי — תבנית pager (תוכן TASE)
│   ├── StrategiesTable.tsx # ~גנרי — אקורדיון+טבלה+פילטרים (תוכן TASE)
│   ├── CalendarView.tsx    # ~גנרי — רשת כרטיסי תאריך + פילטרים
│   ├── DemoWeeks.tsx       # ~גנרי — אקורדיון כרטיסים + פילטרים
│   ├── OptionChain.tsx     # TASE — שרשרת אופציות
│   ├── Simulator.tsx       # TASE — בונה אסטרטגיות
│   ├── MarketEvents.tsx    # placeholder
│   └── ...
└── lib/
    ├── data.ts             # TASE — שכבת נתונים (Supabase/PostgREST)
    └── strategies.ts       # TASE — שמות אסטרטגיות
```

### 4.2 הדפים — מבנה ויזואלי (לא נתונים)

כל הדפים הם async Server Components, עוטפים `<div className="space-y-5">`, ופותחים בדרך כלל בשורת **KPIs** ואז מקטעי-תוכן.

| נתיב | מבנה ויזואלי |
|---|---|
| **`/`** (בית) | (1) pill "עודכן לאחרונה" מיושר לימין · (2) רשת KPI `grid sm:grid-cols-2 lg:grid-cols-4` (3 KPI + כרטיס מדד) · (3) כרטיס "הירו": כותרת+שינוי% + `<IndexChart>` · (4) `<OptionChain>`. |
| **`/strategies`** | (1) רשת 4 KPI · (2) `<BestCondorPager>` · (3) כרטיס "התפלגות תוצאות" עם **בר מקטעים אופקי** + legend · (4) כרטיס גרף עמודות (חיובי/שלילי סביב ציר אפס) · (5) `<StrategiesTable>`. |
| **`/demo`** | (1) רשת 4 KPI · (2) או **empty-state** ממורכז או `<DemoWeeks>` (אקורדיון לפי שבוע, כרטיסי עסקה ברשת). |
| **`/calendar`** | (1) רשת 3 KPI · (2) `<CalendarView>` — כרטיס פילטרים, ואז מקטעי "קרובות"/"עברו" עם רשת כרטיסי-יום. |
| **`/alerts`** | (1) כרטיס freshness/health (`justify-between`) · (2) רשת `lg:grid-cols-2`: "פעילות מערכת" (רשימת שורות) + "אירועי שוק" (empty placeholder). |
| **`/settings`** | (1) כותרת+תת-כותרת · (2) רשת `lg:grid-cols-2` של כרטיסי `Section`, כל אחד רשימת `Row` (label/value/desc) עם מפריד תחתון. read-only. |
| **`/simulator`** | מעביר נתונים ל-`<Simulator>` (אינטראקטיבי, TASE-specific). |

### 4.3 רכיבי UI לשימוש חוזר

**`AppShell`** — ה-layout הראשי (גנרי לחלוטין).
- מבנה: `<Sidebar />` (rail קבוע מימין) + `<div className="pr-14">` (מתפנה מהרייל) המכיל **brand bar** (לוגו "GMM" + אייקון בקופסה) ואז `<main className="mx-auto max-w-[1400px] px-6 pb-16">`.
- props: `{ children }`.

**`Sidebar`** — rail ניווט אנכי דק (גנרי; רק רשימת ה-`NAV` ספציפית לדומיין).
- `"use client"`. `fixed right-0 top-0 bottom-0 w-14`, חצי-שקוף עם `backdrop-blur`, `border-l`.
- מערך `NAV` של `{ icon, href }`; פריט פעיל לפי `usePathname()`.
- כפתורי תחתית: **theme toggle** (sun/moon) + logout. ה-toggle מוסיף/מסיר `class="light"` על `<html>` ושומר ב-`localStorage`.
- פריט פעיל: `bg-accent/15 text-accent ring-1 ring-accent/30`; לא-פעיל: `text-text3 hover:bg-surface2 hover:text-text1`.

**KPI card** — לא רכיב משותף אחד; **דפוס מועתק** (פונקציה `Kpi` מקומית בכל דף). הצורה הקנונית:
```tsx
<div className="rounded-2xl border border-border bg-surface/70 backdrop-blur flex items-center justify-between p-5">
  <div className="text-right">
    <div className="mb-1 text-xs text-text2">{label}</div>
    <div className="text-2xl font-bold tabular-nums">{value}</div>
    {sub && <div className="mt-0.5 text-[11px] text-text3">{sub}</div>}
  </div>
  <span className="grid h-11 w-11 place-items-center rounded-xl bg-surface2 text-xl text-accent">{icon}</span>
</div>
```
props נפוצים: `{ icon, label, value, tone, sub, subTone }`. `tone` = class צבע (`text-pos`/`text-neg`/`text-accent`/`text-warn`/`text-text1`).

**Pager** (`BestCondorPager`, וגם בתוך `OptionChain`) — דפוס דפדוף בין פריטים.
- `useState(idx)`, שני כפתורי ניווט (chevron מסובב `-rotate-90`/`rotate-90`), תווית "‎{idx+1}/{total}".
- כפתור: `grid h-7 w-7 place-items-center rounded-lg border border-border bg-surface2 ... disabled:opacity-30`.
- גוף: רשת `Stat` (label קטן + ערך `text-2xl tabular-nums`).

**Accordion-by-group** (`StrategiesTable`, `DemoWeeks`) — דפוס קבוצות מתקפלות.
- `useState<Set<string>>` של מפתחות פתוחים; פריטים "פעילים" נפתחים אוטומטית.
- כותרת קבוצה היא `<button aria-expanded>` עם chevron שמסתובב (`-rotate-90` כשסגור).
- `StrategiesTable` מציג טבלה פנימית; `DemoWeeks` מציג רשת כרטיסים.

**FilterRow** — שורת כפתורי פילטר (פונקציה מקומית כמעט זהה ב-3 רכיבים).
```tsx
<button className={`rounded-lg border px-3 py-1.5 text-xs transition ${
  active ? "border-accent/40 bg-accent/15 text-accent"
         : "border-border bg-surface2 text-text2 hover:text-text1"}`}>
```
props: `{ label, options: {v,l}[], value, onPick }`. **מועמד מצוין לחילוץ לרכיב משותף בפרויקט החדש** (כרגע משוכפל).

**Charts** (כולם SVG ידני, ראה §5): `IndexChart` (קו עם hover), בר-עמודות חיובי/שלילי ב-`strategies`, בר-מקטעים אופקי (התפלגות).

**Status dot / pill / chip / badge** — דפוסי חיווי קטנים:
- נקודת סטטוס: `h-2 w-2 rounded-full bg-pos|warn|neg`.
- pill מידע: `inline-flex items-center gap-2 rounded-full border border-border bg-surface/70 px-3 py-1.5 text-xs`.
- chip: `rounded-md px-1.5 py-0.5 bg-surface2 text-text2` (או tone accent).
- badge תוצאה: `rounded px-1.5 py-0.5 text-[10px] font-bold bg-pos/15 text-pos` (וריאציות לכל tone).

**`icons.tsx`** — אוסף אייקוני SVG inline, אפס תלות. factory:
```tsx
const base = (d, vb = "0 0 24 24") => (p) => (
  <svg viewBox={vb} fill="none" stroke="currentColor" strokeWidth={1.7}
       strokeLinecap="round" strokeLinejoin="round" className={p.className}
       width="1em" height="1em" aria-hidden>{d}</svg>
);
export const Home = base(<><path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/></>);
// Home, BarChart, Message, Calendar, Trending, File, Settings, Sun, Moon,
// Logout, Refresh, ArrowLeft, ChevronDown, Wallet, Star, Shield, Target, Boost
```
`stroke="currentColor"` + `width/height="1em"` → האייקון יורש צבע וגודל מהטקסט הסובב (`text-accent text-xl`). זה דפוס מעולה לקחת כמו שהוא.

---

## 5. דפוסי UI מרכזיים + דוגמאות קוד גנריות

### 5.1 Layout
שתי שכבות: `body::before` (glow ברקע, `z-0`) ו-`<div className="relative z-10">` (התוכן). `AppShell` שם rail קבוע `w-14` מימין ו-`pr-14` על שאר הדף; `main` ממורכז עד `max-w-[1400px]`.

### 5.2 גרף קו ב-SVG (הדפוס שמחליף recharts)
מתוך `IndexChart.tsx`. עקרון: ממפים ערכים ל-`viewBox` קבוע, בונים path עם החלקת Catmull-Rom→bézier, מוסיפים שכבת gradient fill, וקו hover אינטראקטיבי עם tooltip ב-HTML overlay (לא טקסט SVG — נמנע מעיוות).
```tsx
const W = 1000, H = 280, padX = 40;
const x = (i) => padX + (i * (W - 2*padX)) / Math.max(series.length - 1, 1);
const y = (v) => padTop + (1 - (v - min) / span) * (H - padTop - padBot);
// ...smoothPath(pts) -> "M .. C .. C .."
<svg viewBox={`0 0 ${W} ${H}`} className="h-64 w-full" preserveAspectRatio="none">
  <defs><linearGradient id="idxFill" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%"  stopColor="var(--color-accent)" stopOpacity="0.28"/>
    <stop offset="100%" stopColor="var(--color-accent)" stopOpacity="0"/>
  </linearGradient></defs>
  <path d={area} fill="url(#idxFill)"/>
  <path d={line} fill="none" stroke="var(--color-accent)" strokeWidth="2.5"/>
</svg>
```
שים לב: גרפים מושכים צבע דרך `var(--color-accent)` ישירות (לא class) — כך הם מתחלפים אוטומטית עם ה-theme.

### 5.3 גרף עמודות חיובי/שלילי
מתוך `strategies/page.tsx` (`ExpiryPnlChart`): ציר אפס באמצע (`stroke="var(--color-grid-strong)"`), עמודה כלפי מעלה אם חיובי (`var(--color-pos)`) או מטה אם שלילי (`var(--color-neg)`), עם תווית ערך מעל/מתחת.

### 5.4 בר מקטעים אופקי + legend (התפלגות)
flex של divs ברוחב יחסי בתוך מיכל `rounded-full overflow-hidden`, כל מקטע בצבע token, ו-legend נקודות מתחת. דפוס "stacked bar" קל-משקל בלי ספרייה.

### 5.5 מצבי Loading / Empty
- **Loading:** אין spinners. Server Components מחכים ל-`await Promise.all([...])` ומגישים HTML מוכן. (אם תרצה streaming — הוסף `loading.tsx`/`<Suspense>`, לא קיים כרגע.)
- **Empty state** — דפוס קבוע:
```tsx
<div className="rounded-2xl border border-border bg-surface/70 p-12 text-center">
  <div className="text-text2">אין עדיין נתונים</div>
  <div className="mt-1 text-sm text-text3">הסבר קצר מה לעשות</div>
</div>
```
- **Empty בתוך מקטע** (פילטר ללא תוצאות): `py-8 text-center text-sm text-text3`.
- **Null-safety:** מספרים מפורמטים דרך helper `ils()` / `num()` שמחזירים `"—"` כשהערך `null`.

### 5.6 אנימציות (CSS בלבד)
- **Transitions:** `transition` + שינוי צבע ב-hover (כל הכפתורים/קישורים); `transition-transform` + `-rotate-90` לחצי אקורדיון.
- **Keyframe יחיד** ב-`globals.css` — ticker רץ (לסרגל נע), עם pause ב-hover:
```css
@keyframes ticker { from { transform: translateX(0); } to { transform: translateX(-50%); } }
.animate-ticker { animation: ticker 38s linear infinite; }
.animate-ticker:hover { animation-play-state: paused; }
```

### 5.7 החלפת Theme (גנרי — קח כמו שהוא)
שני חלקים. (א) סקריפט anti-flash ב-`layout.tsx` שרץ לפני ה-render:
```tsx
<script dangerouslySetInnerHTML={{ __html:
  `try{if(localStorage.getItem('theme')==='light')document.documentElement.classList.add('light')}catch(e){}` }} />
```
(ב) ה-toggle ב-`Sidebar` שמסנכרן class + localStorage. כל ה-tokens מתחלפים כי שניהם מוגדרים על אותם שמות (§2.2).

---

## 6. הפרדה קריטית — מה גנרי מול מה TASE-specific

### ✅ גנרי — קח כמו שהוא (עיצוב/layout/רכיבים)
- **`globals.css` במלואו** — design tokens, theme dark+light, glow, scrollbar, keyframes. **זה הנכס המרכזי.**
- **`layout.tsx`** — מבנה ה-`<html dir>`, פונט, theme bootstrap. (שנה רק `lang`/`dir`/`metadata`/הפונט אם לא עברית.)
- **`AppShell.tsx`** — מבנה rail+brand+main. (החלף "GMM"/אייקון Boost.)
- **`Sidebar.tsx`** — מנגנון הניווט + theme toggle. (החלף את מערך `NAV`.)
- **`icons.tsx`** — אוסף האייקונים והפקטורי. הוסף/הסר אייקונים לפי הצורך.
- **דפוסי UI:** KPI card, FilterRow, Pager, Accordion-by-group, Empty-state, status dot/pill/chip/badge, גרפי ה-SVG (`IndexChart`, bar, segmented). **המבנים** גנריים — רק התוויות והנתונים TASE.
- **כל מערכת ה-Tailwind classes** והקונבנציות (tabular-nums, text-right, card const).

### ⚠️ ספציפי ל-TASE — החלף את התוכן, שמור את המעטפת
- **`lib/data.ts`** — שכבת נתונים: חיבור **Supabase/PostgREST** (`SUPABASE_URL`/`SUPABASE_KEY`), טבלאות `iron_condor_strategies` / `tase_putcall`, ערך מדד TLV35, VTA35, fallback series. **כל הלוגיקה דומיינית.** שמור את ה-*תבנית* (server-only fetch, `no-store`, helper `sb<T>()`, מחזיר `[]` בכשל) — החלף את ה-queries.
- **`lib/strategies.ts`** — שמות אסטרטגיות אופציות (איירון קונדור, פרפר...).
- **`components/OptionChain.tsx`** — שרשרת אופציות; מושגי strike/call/put/ATM.
- **`components/Simulator.tsx`** + **`simulator/actions.ts`** — בונה אסטרטגיות אופציות; קבועים `MULT = 50` (₪ לנקודת מדד), `COMMISSION = 2.5`, payoff glyphs, legs.
- **תוכן הדפים** — KPIs כמו "אחוז הצלחה / R/R / יחס סיכון", "Iron Condor", "פקיעות", "VTA35", "פוטנציאל פר פקיעה". **המבנה הוויזואלי גנרי; הסמנטיקה TASE.**
- **מילוני עברית** `DAYS_HE`/`MONTHS_HE`/`RESULT`/`REASON_HE` — דומייני+שפה.
- **`metadata`** ("GMM — TLV35"), המותג "GMM", אייקון `Boost`.

### גבול אפור
`IndexChart`, `BestCondorPager`, `StrategiesTable`, `CalendarView`, `DemoWeeks` — **מנועי ה-UI גנריים** (גרף, pager, אקורדיון, רשת כרטיסים, פילטרים), אבל ה-`type` של ה-props (`Strategy`, `DemoTrade`, `ExpiryEntry`...) ושמות השדות דומייניים. בפרויקט החדש: שמור את ה-JSX/הסטייט, החלף את ה-types ואת התוויות העבריות.

---

## 7. איך לאתחל פרויקט חדש עם אותו בסיס

### צעד 1 — scaffold
```bash
npx create-next-app@latest my-dashboard \
  --typescript --tailwind --app --src-dir --import-alias "@/*" --eslint
cd my-dashboard
```
זה נותן: App Router, `src/`, TypeScript strict, Tailwind v4 (PostCSS), alias `@/*` — בדיוק כמו `web/`. **אל תניח Next ישן — סמוך על ה-scaffold העדכני.**

### צעד 2 — פונט (אם עברית/RTL)
ב-`src/app/layout.tsx`:
```tsx
import { Heebo } from "next/font/google";
const heebo = Heebo({ subsets: ["hebrew","latin"], variable: "--font-heebo",
                      weight: ["400","500","600","700"] });
// <html lang="he" dir="rtl" className={`${heebo.variable} h-full`}>
```
לפרויקט לטיני: החלף ל-`Inter`/אחר, `lang="en"`, הסר `dir="rtl"`.

### צעד 3 — העתק את ה-design system
החלף את `src/app/globals.css` כולו בגרסה מ-§2 (בלוק `@theme`, ה-body/glow, scrollbar, `html.light`, keyframes). **זה הצעד שקובע את ה-look.**

### צעד 4 — העתק את שלד ה-UI הגנרי
מ-`web/src/components/`: `icons.tsx`, `AppShell.tsx`, `Sidebar.tsx` (ערוך `NAV`). הוסף את ה-`const card` והדפוסים (KPI card, FilterRow, Empty-state, גרפי SVG) לפי הצורך.

### צעד 5 — שכבת נתונים משלך
צור `src/lib/data.ts` בתבנית של TASE אבל עם המקור שלך:
```ts
import "server-only";
async function api<T>(path: string): Promise<T[]> {
  try { const r = await fetch(`${BASE}/${path}`, { cache: "no-store", headers: {...} });
        return r.ok ? await r.json() as T[] : []; }
  catch { return []; }
}
```
שמור על: `server-only`, `cache: "no-store"`, fail-soft (`[]`/`null`), כל ה-fetch ב-page עם `await Promise.all([...])`.

### צעד 6 — בנה דפים
כל דף: `export default async function Page()`, עוטף `<div className="space-y-5">`, פותח ב-grid KPI, ואז מקטעי `card`. העתק את שלד `/` או `/settings` כנקודת מוצא.

### קבצי קונפיג להעתיק (כמעט as-is)
- `postcss.config.mjs` — `{ plugins: { "@tailwindcss/postcss": {} } }`
- `tsconfig.json` — strict + `"@/*": ["./src/*"]`
- `next.config.ts` — ריק
- `package.json engines` — `node >=20.9.0`

### checklist
- [ ] `@import "tailwindcss"` בראש `globals.css`
- [ ] בלוק `@theme` עם כל ה-tokens
- [ ] `html.light` override (אם רוצים light mode)
- [ ] `dir`/`lang`/פונט ב-`layout.tsx` + script ה-anti-flash
- [ ] `AppShell` + `Sidebar` עם `NAV` שלך
- [ ] `icons.tsx`
- [ ] `lib/data.ts` בתבנית server-only fail-soft
- [ ] `const card` ודפוסי KPI/Filter/Empty משוכפלים או מחולצים לרכיבים

---

## נספח — מפת קבצים מהירה

| צריך... | פתח את |
|---|---|
| צבעים/פונט/theme/glow | `web/src/app/globals.css` |
| RTL/פונט/theme bootstrap | `web/src/app/layout.tsx` |
| layout ראשי | `web/src/components/AppShell.tsx` |
| ניווט + theme toggle | `web/src/components/Sidebar.tsx` |
| אייקונים | `web/src/components/icons.tsx` |
| גרף קו (תבנית) | `web/src/components/IndexChart.tsx` |
| KPI / bar / segmented | `web/src/app/strategies/page.tsx` |
| pager | `web/src/components/BestCondorPager.tsx` |
| accordion + table + filters | `web/src/components/StrategiesTable.tsx` |
| רשת כרטיסי-תאריך | `web/src/components/CalendarView.tsx` |
| empty-state / list rows | `web/src/app/demo/page.tsx`, `web/src/app/alerts/page.tsx` |
| תבנית שכבת נתונים | `web/src/lib/data.ts` |
