# logic.py – מערכת התאמת מוזמנים מתקדמת
"""שדרוג אלגוריתם התאמת השמות (גרסה מאוחדת 2025‑08‑03)
----------------------------------------------------------------
* אינטגרציה מלאה עם Google Sheets לניהול הרשאות
* מנגנון גיבוי אוטומטי לקובץ Excel מקומי
* חיזוק נורמליזציה (הסרת '|', '/', '()' ועוד)
* התעלמות ממילים סופיות לא רלוונטיות (״מילואים״, "נייד", "בית", "עבודה" …)
* fuzzy‑eq על־ידי Levenshtein ≥ 90 %
* בונוס 100 % כאשר core‑tokens זהים (שם‑פרטי + משפחה)
* length_penalty מוחל רק אם יש +2 טוקנים פער
* טיפול מתקדם בזיהוי עמודות שם פרטי+משפחה
* תמיכה ב-CSV ו-XLSX עם זיהוי אוטומטי
"""

from __future__ import annotations

import os, re, logging
from io import BytesIO
from typing import List, Set

import pandas as pd
import unidecode
from rapidfuzz import fuzz, distance

# Google Sheets via ADC (Cloud Run Service Account)
import google.auth
import gspread

# ───────── קבועים ─────────
NAME_COL          = "שם מלא"
PHONE_COL         = "מספר פלאפון"
COUNT_COL         = "כמות מוזמנים"
SIDE_COL          = "צד"
GROUP_COL         = "קבוצה"

AUTO_SCORE        = 100
AUTO_SELECT_TH    = 93
MIN_SCORE_DISPLAY = 70
MAX_DISPLAYED     = 6

# הרשאות/Scopes לקריאה בלבד
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

# ENV לגיליון המורשים
SPREADSHEET_ID_ENV  = "SPREADSHEET_ID"
WORKSHEET_TITLE_ENV = "WORKSHEET_TITLE"   # אופציונלי

# גיבוי מקומי
LOCAL_ALLOWED_FILE  = "allowed_users.xlsx"
LOCAL_PHONE_COLS    = ("טלפון", "phone", "מספר", "מספר פלאפון", "פלאפון")

# מילות יחס/קשר (ignored לגמרי)
GENERIC_TOKENS: Set[str] = {"של", "ה", "בן", "בת", "משפחת", "אחי", "אחות", "דוד", "דודה"}

# סיומות/כינויים שאינם חלק מהשם (נמחקות מהקצה)
SUFFIX_TOKENS: Set[str] = {
    "מילואים", "miluyim", "miloyim", "mil", "נייד", "סלולר", "סלולרי",
    "בית", "עבודה", "עסקי", "אישי", "משרד"
}

# ───────── עזרים ─────────
def only_digits(s: str) -> str:
    """מחזיר רק ספרות מהמחרוזת"""
    return re.sub(r"\D+", "", s or "")

# כל פיסוק + תווי ׀ / () [] יחלפו לרווח (נורמליזציה משופרת)
_punc_re   = re.compile(r"[\|\\/()\[\]\"'׳״.,\-]+")
_space_re  = re.compile(r"\s+")
_token_re  = re.compile(r"\s+")

def normalize(txt: str | None) -> str:
    """נירמול משופר: lowercase → הורדת סימני פיסוק → רווח יחיד → תעתיק לטיני."""
    if not txt:
        return ""
    t = str(txt).lower()
    t = _punc_re.sub(" ", t)
    t = _space_re.sub(" ", t).strip()
    return unidecode.unidecode(t)

def _clean_token(tok: str) -> str:
    """מסיר ו' חיבור וסיומת i, ומתעלם מ־SUFFIX_TOKENS"""
    if tok in SUFFIX_TOKENS:
        return ""
    if tok.startswith("v") and len(tok) > 2:
        tok = tok[1:]
    if len(tok) >= 4 and tok.endswith("i"):
        tok = tok[:-1]
    return tok

def _tokens(name: str) -> List[str]:
    """מחזיר רשימת טוקנים נקייה אחרי סינון מילים גנריות וסיומות"""
    tks = [_clean_token(t) for t in _token_re.split(name)]
    return [t for t in tks if t and t not in GENERIC_TOKENS]

def _fuzzy_eq(a: str, b: str) -> bool:
    """טוקנים זהים או דומים ≥ 90 % ב‑Levenshtein"""
    return a == b or distance.Levenshtein.normalized_similarity(a, b) >= 0.9

def _fuzzy_jaccard(gs: List[str], cs: List[str]) -> float:
    """חישוב Jaccard עם התחשבות ב-fuzzy equality"""
    matched, used = 0, set()
    for g in gs:
        for c in cs:
            if c in used:
                continue
            if _fuzzy_eq(g, c):
                matched += 1
                used.add(c)
                break
    union = len(set(gs)) + len(set(cs)) - matched
    return matched / union if union else 1.0

def format_phone(ph: str) -> str:
    """עיצוב טלפון: 972 -> 0, פורמט XXX-XXXXXXX"""
    d = "".join(filter(str.isdigit, str(ph)))
    if d.startswith("972"):
        d = "0" + d[3:]
    return f"{d[:3]}-{d[3:]}" if len(d) == 10 else d

# ───────── מערכת הרשאות: Google Sheets + קובץ גיבוי ─────────
def _pick_worksheet(sh):
    """מאתר לשונית לפי שם (לא רגיש לרישיות/רווחים). אם אין/לא נמצא – הראשונה."""
    wanted = os.getenv(WORKSHEET_TITLE_ENV)
    if wanted:
        w = wanted.strip().lower()
        for ws in sh.worksheets():
            if (ws.title or "").strip().lower() == w:
                return ws
    return sh.get_worksheet(0)

def _find_phone_col(header: list[str]) -> int:
    """אינדקס עמודת הטלפון לפי כותרת (case-insensitive). אם לא נמצא – B (1)."""
    header_lower = [str(h).strip().lower() for h in header]
    lookup = tuple(x.lower() for x in ("טלפון", "מספר פלאפון", "פלאפון", "phone", "מספר"))
    for i, h in enumerate(header_lower):
        if h in lookup:
            return i
    return 1

def _load_allowed_from_sheets() -> set[str] | None:
    """טוען סט טלפונים מורשים מ-Sheets דרך ADC. מחזיר None אם אין/שגיאה (כדי לאפשר גיבוי)."""
    sheet_id = os.getenv(SPREADSHEET_ID_ENV)
    if not sheet_id:
        return None
    try:
        creds, _ = google.auth.default(scopes=SCOPES)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(sheet_id)
        ws = _pick_worksheet(sh)

        rows = ws.get_all_values() or []
        if len(rows) < 2:
            logging.info("Allowed sheet is empty or header-only.")
            return set()

        header = [str(c).strip() for c in rows[0]]
        phone_idx = _find_phone_col(header)

        allowed = {
            only_digits(r[phone_idx])
            for r in rows[1:]
            if len(r) > phone_idx and only_digits(r[phone_idx])
        }

        if allowed:
            logging.info("Loaded %d allowed phones from Sheets.", len(allowed))
        else:
            logging.info("No allowed phones found in Sheets after normalization.")
        return allowed
    except Exception:
        logging.exception("Failed to load allowed phones from Sheets")
        return None

def _load_allowed_from_excel() -> set[str]:
    """גיבוי: טוען טלפונים מורשים מ-allowed_users.xlsx (אם קיים)."""
    if not os.path.exists(LOCAL_ALLOWED_FILE):
        return set()
    try:
        df = pd.read_excel(LOCAL_ALLOWED_FILE, dtype=str)
    except Exception:
        logging.exception("Failed to read local allowed Excel")
        return set()

    cols = [c for c in df.columns if any(k in str(c).lower() for k in LOCAL_PHONE_COLS)]
    if not cols:
        return set()

    phone_col = cols[0]
    allowed = {only_digits(str(v)) for v in df[phone_col] if only_digits(str(v))}
    logging.info("Loaded %d allowed phones from local Excel.", len(allowed))
    return allowed

def is_user_authorized(phone: str) -> bool:
    """True אם המספר (אחרי נורמליזציה) מופיע ברשימת המורשים (Sheets או Excel מקומי)."""
    clean = only_digits(phone)
    allowed = _load_allowed_from_sheets()
    if allowed is None:
        allowed = _load_allowed_from_excel()
    return clean in allowed

# ───────── אלגוריתם התאמה מתקדם ─────────
def full_score(g_norm: str, c_norm: str) -> int:
    """ציון התאמה 0–100 בין שני שמות מנורמלים עם אלגוריתם משופר."""
    if not g_norm or not c_norm:
        return 0
    if g_norm.strip() == c_norm.strip():
        return AUTO_SCORE
        
    g_t, c_t = _tokens(g_norm), _tokens(c_norm)
    
    # התאמה מלאה לאחר ניקוי (core‑tokens זהים)
    if g_t == c_t:
        return AUTO_SCORE
    
    if not g_t or not c_t:
        return fuzz.partial_ratio(g_norm, c_norm)
    
    # חישוב רכיבי הציון
    tr = fuzz.token_set_ratio(" ".join(g_t), " ".join(c_t)) / 100
    fr = fuzz.ratio(g_t[0], c_t[0]) / 100
    jr = _fuzzy_jaccard(g_t, c_t)
    
    # ענישה קלה על פער טוקנים >= 2
    gap = abs(len(g_t) - len(c_t))
    penalty = (min(len(g_t), len(c_t)) / max(len(g_t), len(c_t))) if gap >= 2 else 1
    
    score = (0.6 * tr + 0.2 * fr + 0.2 * jr) * penalty * 100
    return int(round(score))

def reason_for(g_norm: str, c_norm: str, score: int) -> str:
    """מחזיר הסבר קצר למה ניתן הציון הזה"""
    overlap = [t for t in _tokens(g_norm) if t in set(_tokens(c_norm))]
    if overlap:
        return f"חפיפה: {', '.join(overlap[:2])}"
    if score >= AUTO_SELECT_TH:
        return "התאמה גבוהה"
    return ""

# ───────── זיהוי עמודות שם/טלפון בקובצי קלט ─────────
def _best_text_col(candidates: List[str], df: pd.DataFrame) -> str:
    """בחירת עמודת טקסט איכותית מתוך מועמדים."""
    def score(col):
        s = df[col].astype(str).fillna("")
        return ((s.str.strip() != "").sum(), s.str.contains(r"[A-Za-zא-ת]").mean(), s.str.len().mean())
    return max(candidates, key=score)

def _resolve_full_name_series(df: pd.DataFrame) -> pd.Series:
    """
    מאחד שם פרטי+משפחה / מזהה 'שם מלא' / דמויות שם – ומחזיר Series.
    אלגוריתם מתקדם לזיהוי וחיבור עמודות שם.
    """
    cols = list(df.columns)
    low = {c: str(c).strip().lower() for c in cols}
    
    # זיהוי ישיר של עמודת שם מלא
    direct = {"שם מלא", "full name", "fullname", "guest name", "שם המוזמן"}
    for c in cols:
        if low[c] in direct:
            return df[c].fillna("").astype(str).str.strip()
    
    # חיבור שם פרטי + משפחה
    first = [c for c in cols if "פרטי" in low[c] or low[c] in {"שם", "first", "firstname"}]
    last  = [c for c in cols if "משפחה" in low[c] or low[c] in {"last", "lastname", "surname"}]
    if first and last:
        f, l = _best_text_col(first, df), _best_text_col(last, df)
        return (df[f].fillna("").astype(str).str.strip() + " " +
                df[l].fillna("").astype(str).str.strip()).str.replace(r"\s+", " ", regex=True).str.strip()
    
    # חיפוש עמודות דמויות שם
    name_like = [c for c in cols if any(k in low[c] for k in ["שם", "name", "guest", "מוזמן"])]
    if name_like:
        c = _best_text_col(name_like, df)
        return df[c].fillna("").astype(str).str.strip()
    
    return pd.Series([""] * len(df))

# ───────── טעינת קלט וייצוא ─────────
def load_excel(file) -> pd.DataFrame:
    """טוען CSV/XLSX עם זיהוי אוטומטי, מנרמל ומוודא עמודות חובה."""
    # 1) קריאה עם זיהוי פורמט אוטומטי
    if hasattr(file, "name") and str(file.name).lower().endswith(".csv"):
        df = pd.read_csv(file).rename(columns=lambda c: str(c).strip())
    else:
        df = pd.read_excel(file).rename(columns=lambda c: str(c).strip())

    # 2) עמודת טלפון
    if PHONE_COL not in df.columns:
        hints = ["טלפון", "פלא", "נייד", "cell", "mobile", "phone", "מספר"]
        alt = [c for c in df.columns if any(h in str(c).lower() for h in hints)]
        if alt:
            df.rename(columns={alt[0]: PHONE_COL}, inplace=True)
        else:
            df[PHONE_COL] = ""
    df[PHONE_COL] = (
        df[PHONE_COL]
        .fillna("")
        .astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.strip()
    )

    # 3) עמודת שם מלא (עם אלגוריתם מתקדם)
    if NAME_COL in df.columns:
        df[NAME_COL] = df[NAME_COL].fillna("").astype(str).str.strip()
    else:
        df[NAME_COL] = _resolve_full_name_series(df)

    # 4) עמודת כמות מוזמנים
    count_hints = [
        "כמות", "מספר מוזמנים", "מס' מוזמנים", "מוזמנים", "מספר אורחים", "אורחים",
        "guest count", "guests", "guest", "count", "qty", "quantity", "amount",
    ]
    if COUNT_COL not in df.columns:
        alt_count = [c for c in df.columns if any(h in str(c).lower() for h in count_hints)]
        if alt_count:
            df.rename(columns={alt_count[0]: COUNT_COL}, inplace=True)
        else:
            df[COUNT_COL] = 1
    counts_raw = df[COUNT_COL].astype(str)
    counts_num = pd.to_numeric(counts_raw.str.extract(r"(\d+)")[0], errors="coerce")
    df[COUNT_COL] = counts_num.fillna(1).astype(int)

    # 5) עמודות צד וקבוצה
    for col in (SIDE_COL, GROUP_COL):
        if col not in df.columns:
            df[col] = ""
        else:
            df[col] = df[col].fillna("").astype(str).str.strip()

    # 6) שם מנורמל להתאמות
    df["norm_name"] = df[NAME_COL].map(normalize)
    return df

def to_buf(df: pd.DataFrame) -> BytesIO:
    """ייצוא ל-Excel: מסיר עמודות פנימיות ומשאיר טלפון בסוף."""
    export = df.drop(columns=["norm_name", "score", "best_score", NAME_COL], errors="ignore").copy()
    original = [c for c in export.columns if c != PHONE_COL]
    final = original + [PHONE_COL]
    export = export.reindex(columns=final, fill_value="")
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        export.to_excel(w, index=False, sheet_name="RSVP")
    buf.seek(0)
    return buf

# ───────── מערכת התאמות מתקדמת ─────────
def top_matches(guest_norm: str, contacts_df: pd.DataFrame) -> pd.DataFrame:
    """
    בוחר למוזמן עם השם המנורמל guest_norm את המועמדים הטובים ביותר מה־contacts_df לפי:
    1. אם יש התאמה מושלמת (100%) – עד 3 תוצאות עם score >= 90.
    2. אחרת – עד 3 תוצאות עם score >= MIN_SCORE_DISPLAY (70).
    3. אם אין כאלה – עד 3 תוצאות עם score >= 55 (threshold fallback).
    
    לוגיקה מתקדמת המבטיחה תוצאות איכותיות.
    """
    if not guest_norm:
        return pd.DataFrame(columns=list(contacts_df.columns) + ["score", "reason"])

    # 1) מחשיבים את כל הציונים
    scores = contacts_df["norm_name"].apply(lambda c: full_score(guest_norm, c))
    df     = contacts_df.assign(score=scores)

    # 2) בודקים האם יש Perfect Match (100%)
    max_score = int(df["score"].max())
    if max_score == AUTO_SCORE:
        candidates = (
            df[df["score"] >= 90]
            .sort_values(["score", NAME_COL], ascending=[False, True])
            .head(3)
            .copy()
        )
    else:
        # 3) מציגים לפחות MIN_SCORE_DISPLAY
        candidates = (
            df[df["score"] >= MIN_SCORE_DISPLAY]
            .sort_values(["score", NAME_COL], ascending=[False, True])
            .head(3)
            .copy()
        )
        # 4) fallback – אם אין כלל מועמדים ≥MIN_SCORE_DISPLAY, נציג לפחות מעל 50
        if candidates.empty:
            candidates = (
                df[df["score"] >= 50]
                .sort_values(["score", NAME_COL], ascending=[False, True])
                .head(3)
                .copy()
            )

    # 5) מוסיפים עמודת 'reason' להסבר התאמה
    candidates["reason"] = candidates.apply(
        lambda r: reason_for(guest_norm, r["norm_name"], int(r["score"])), axis=1
    )
    return candidates

def compute_best_scores(guests_df: pd.DataFrame, contacts_df: pd.DataFrame) -> pd.Series:
    """מחשב את הציון הטוב ביותר לכל מוזמן מול כל אנשי הקשר"""
    return guests_df["norm_name"].apply(
        lambda n: int(contacts_df["norm_name"].apply(lambda c: full_score(n, c)).max()) if n else 0
    )