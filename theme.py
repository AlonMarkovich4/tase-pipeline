"""
theme.py — Single source of truth for the Strategy Desk design tokens.

Colour, radius, and font tokens live here ONCE. Three consumers read them:

  1. dashboard.py Python code — imports the palette constants (aliased to
     the existing T_* / C_* names so no call-site changes).
  2. The injected CSS — ``base_style()`` generates the ``:root`` block from
     the same values, so the CSS custom properties can never drift from the
     Python constants again.
  3. .streamlit/config.toml — the Streamlit-native theme. Streamlit reads it
     *before* Python runs, so its four colours are mirrored by hand; each
     line there is commented with the token it must equal (BG / SURFACE /
     TEXT1 / ACCENT).

Changing a brand colour is now a one-line edit here (plus the matching line
in config.toml for the native-widget colours).
"""

# ── Core palette ─────────────────────────────────────────────────
BG      = "#0B0D10"               # page background        -> config backgroundColor
SURFACE = "#111418"               # card / panel surface   -> config secondaryBackgroundColor
SURF2   = "#161B22"               # raised surface (table headers, chips)
BORDER  = "rgba(255,255,255,0.07)"  # subtle border
BORDER2 = "rgba(255,255,255,0.12)"  # stronger border

TEXT1   = "#E8EAED"               # primary text           -> config textColor
TEXT2   = "#9AA0A6"               # secondary / label text
TEXT3   = "#5F6368"               # tertiary / disabled

ACCENT  = "#00B0FF"               # single accent          -> config primaryColor
POS     = "#34A853"               # positive / profit
NEG     = "#E53935"               # negative / loss
WARN    = "#F9A825"               # warning / amber
REF     = "#00BCD4"               # reference lines (live index, settlement)

# ── Radius scale ─────────────────────────────────────────────────
R_SM = "8px"
R_MD = "12px"

# ── Spacing scale (4-point grid) ─────────────────────────────────
# The dominant padding/margin/gap values across the dashboard already sit on
# this grid; these tokens name them so the rhythm is intentional and editable
# in one place. Off-grid one-offs (6/10/14/20px fine-tuning) stay literal.
SP_1 = "4px"
SP_2 = "8px"
SP_3 = "12px"
SP_4 = "16px"
SP_5 = "24px"
SP_6 = "32px"

# Self-hosted Inter — NO web-font CDN dependency. The woff2 files live in
# static/fonts/ and are served by Streamlit's own static file server (needs
# `enableStaticServing = true` in config.toml) under the app/static/ path.
# Inter leads the stack; the system fonts after it are the fallback when
# static serving is unavailable (older/unknown deploy) AND for glyphs Inter
# lacks — notably Hebrew, which Inter has no glyphs for, so RTL text renders
# in the system font via the browser's per-glyph fallback (the same way it
# behaved under the old Google-Fonts CDN setup). All these system fonts ship
# tabular numerals, so the aligned-figures look survives either path.
FONT_STACK = ("'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', "
              "Roboto, Helvetica, Arial, sans-serif")

# Self-hosted Inter faces. Served from static/fonts/ at the app/static/ path.
_FONT_DIR = "app/static/fonts"
_INTER_WEIGHTS = (400, 500, 600)   # the weights the design system actually uses
_INTER_SUBSETS = {
    "latin": (
        "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,"
        "U+0304,U+0308,U+0329,U+2000-206F,U+2074,U+20AC,U+2122,U+2191,"
        "U+2193,U+2212,U+2215,U+FEFF,U+FFFD"
    ),
    # latin-ext carries the ₪ shekel sign (U+20AA), used across the P&L UI.
    "latin-ext": (
        "U+0100-02AF,U+0304,U+0308,U+0329,U+1E00-1E9F,U+1EF2-1EFF,U+2020,"
        "U+20A0-20AB,U+20AD-20CF,U+2113,U+2C60-2C7F,U+A720-A7FF"
    ),
}


def _font_faces() -> str:
    """Generate @font-face rules for the self-hosted Inter woff2 files.

    Uses font-display: swap (system font shows, then swaps to Inter on load —
    never invisible text) and per-subset unicode-range so the browser only
    fetches the weights/subsets a given screen needs.
    """
    faces = []
    for subset, urange in _INTER_SUBSETS.items():
        for w in _INTER_WEIGHTS:
            faces.append(
                "@font-face {\n"
                "  font-family: 'Inter';\n"
                "  font-style: normal;\n"
                f"  font-weight: {w};\n"
                "  font-display: swap;\n"
                f"  src: url('{_FONT_DIR}/inter-{subset}-{w}-normal.woff2') "
                "format('woff2');\n"
                f"  unicode-range: {urange};\n"
                "}"
            )
    return "\n".join(faces)


def build_css_root() -> str:
    """Emit the CSS ``:root`` custom-property block from the tokens above.

    Generated rather than hand-written so the CSS variables are guaranteed
    to equal the Python constants.
    """
    return f""":root {{
  --bg:       {BG};
  --surface:  {SURFACE};
  --surf2:    {SURF2};
  --border:   {BORDER};
  --border2:  {BORDER2};
  --text1:    {TEXT1};
  --text2:    {TEXT2};
  --text3:    {TEXT3};
  --accent:   {ACCENT};
  --pos:      {POS};
  --neg:      {NEG};
  --warn:     {WARN};
  --ref:      {REF};
  --r-sm:     {R_SM};
  --r-md:     {R_MD};
  --sp-1:     {SP_1};
  --sp-2:     {SP_2};
  --sp-3:     {SP_3};
  --sp-4:     {SP_4};
  --sp-5:     {SP_5};
  --sp-6:     {SP_6};
}}"""


def base_style() -> str:
    """Content for the first injected ``<style>`` tag: the generated design
    tokens plus the base font rule.

    Injected before the static stylesheet so its variables and font cascade
    into everything that follows.
    """
    return f"""{_font_faces()}
{build_css_root()}
html, body, [class*="css"] {{
  font-family: {FONT_STACK} !important;
}}"""
