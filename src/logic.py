# logic.py – הרשאות + לוגיקת התאמות, גרסה נקייה לעבודה ב-Cloud Run

from __future__ import annotations
import os, re, logging
from io import BytesIO
from typing import List, Set

import pandas as pd
import unidecode
from rapidfuzz import fuzz, distance

# --- Google Sheets (ADC via Cloud Run Service Account) ---
import google.auth
import gspread

# ───────── CONSTANTS ─────────
NAME_COL          = "שם מלא"
PHONE_COL         = "מספר פלאפון"
COUNT_COL         = "כמות מוזמנים"
SIDE_COL          = "צד"
GROUP_COL         = "קבוצה"

AUTO_SCORE        = 100
AUTO_SELECT_TH    = 93
MIN_SCORE_DISPLAY = 70
MAX_DISPLAYED     = 6

# הרשאות Google APIs (קריאה בלבד)
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

# Env vars לקריאת גיליון המורשים
SPREADSHEET_ID_ENV  = "SPREADSHEET_ID"     # ה-ID שב-URL של הגיליון
WORKSHEET_TITLE_ENV = "WORKSHEET_TITLE"    # שם הלשונית (אופציונלי)

LOCAL_ALLOWED_FILE  = "allowed_users.xlsx"  # גיבוי מקומי
LOCAL_PHONE_COLS    = ("טלפון", "phone", "מספר", "מספר פלאפון", "פלאפון")

# מילות יחס/קשר (ignored לגמרי)
GENERIC_TOKENS: Set[str] = {"של", "ה", "בן", "בת", "משפחת", "אחי", "אחות", "דוד", "דודה"}
# סיומות/כינויים שאינם חלק מהשם (נמחקות מהקצה)
SUFFIX_TOKENS: Set[str] = {
    "מילואים", "miluyim", "miloyim", "mil", "נייד", "סלולר", "סלולרי", "בית", "עבודה", "עסקי", "אישי", "משרד"
}

# ───────── הרשאות משתמשים (Sheets + קובץ גיבוי) ─────────
def only_digits(s: str) -> str:
    return re.sub(r"\D+", "", s or "")

def _load_allowed_from_sheets() -> set[str] | None:
    """טוען סט של טלפונים מורשים מ-Google Sheets דרך ה-Service Account של Cloud Run.
    מחזיר None אם אין ID בסביבה או אם הייתה שגיאה בזמן הקריאה.
    """
    sheet_id = os.getenv(SPREADSHEET_ID_ENV)
    if not sheet_id:
        return None

    try:
        creds, _ = google.auth.default(scopes=SCOPES)
        gc = gspread.authorize(creds)

        sh = gc.open_by_key(sheet_id)
        title = os.getenv(WORKSHEET_TITLE_ENV)
        ws = sh.worksheet(title) if title else sh.sheet1

        rows = ws.get_all_values() or []
        if len(rows) < 2:
            return set()

        # זיהוי עמודת הטלפון (Case-insensitive)
        header = [str(c).strip() for c in rows[0]]
        header_lower = [h.lower() for h in header]
        lookup = tuple(x.lower() for x in LOCAL_PHONE_COLS)
        try:
            phone_idx = next(i for i, h in enumerate(header_lower) if h in lookup)
        except StopIteration:
            phone_idx = 1  # ברירת מחדל: עמודה B

        return {
            only_digits(r[phone_idx])
            for r in rows[1:]
            if len(r) > phone_idx and only_digits(r[phone_idx])
        }

    except Exception:
        logging.exception("Failed to load allowed phones from Sheets")
        return None

def _load_allowed_from_excel() -> set[str]:
    """גיבוי: טוען טלפונים מורשים מ-allowed_users.xlsx (אם קיים לצד האפליקציה)."""
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
    return {only_digits(str(v)) for v in df[phone_col] if only_digits(str(v))}

def is_user_authorized(phone: str) -> bool:
    """True אם המספר (אחרי נירמול) מופיע ברשימת המורשים (Sheets או Excel מקומי)."""
    clean = only_digits(phone)
    allowed = _load_allowed_from_sheets()
    if allowed is None:
        allowed = _load_allowed_from_excel()
    return clean in allowed

# ───────── נירמול שמות / ניקוד / ציונים (הקוד שלך, בתיקונים קלים) ─────────
_punc_re   = re.compile(r"[\|\\/()\[\]\"'׳\".,\-]+")
_space_re  = re.compile(r"\s+")
_token_re  = re.compile(r"\s+")

def _best_text_col(candidates: List[str], df: pd.DataFrame) -> str:
    def score(col):
        s = df[col].astype(str).fillna("")
        return ((s.str.strip() != "").sum(), s.str.contains(r"[A-Za-zא-ת]").mean(), s.str.len().mean())
    return max(candidates, key=score)

def _resolve_full_name_series(df: pd.DataFrame) -> pd.Series:
    cols = list(df.columns)
    low = {c: c.strip().lower() for c in cols}
    direct = {"שם מלא","full name","fullname","guest name","שם המוזמן"}
    for c in cols:
        if low[c] in direct:
            return df[c].fillna("").astype(str).str.strip()
    first = [c for c in cols if "פרטי" in low[c] or low[c] in {"שם","first","firstname"}]
    last  = [c for c in cols if "משפחה" in low[c] or low[c] in {"last","lastname","surname"}]
    if first and last:
        f, l = _best_text_col(first, df), _best_text_col(last, df)
        return (df[f].fillna("").astype(str).str.strip() + " " +
                df[l].fillna("").astype(str).str.strip()).str.replace(r"\s+"," ",regex=True).str.strip()
    name_like = [c for c in cols if any(k in low[c] for k in ["שם","name","guest","מוזמן"])]
    if name_like:
        c = _best_text_col(name_like, df)
        return df[c].fillna("").astype(str).str.strip()
    return pd.Series([""]*len(df))

def normalize(txt: str | None) -> str:
    if not txt:
        return ""
    t = str(txt).lower()
    t = _punc_re.sub(" ", t)
    t = _space_re.sub(" ", t).strip()
    return unidecode.unidecode(t)

def _clean_token(tok: str) -> str:
    if tok in SUFFIX_TOKENS:
        return ""
    if tok.startswith("v") and len(tok) > 2:
        tok = tok[1:]
    if len(tok) >= 4 and tok.endswith("i"):
        tok = tok[:-1]
    return tok

def _tokens(name: str) -> List[str]:
    return [t for t in (_clean_token(x) for x in _token_re.split(name)) if t and t not in GENERIC_TOKENS]

def _fuzzy_eq(a: str, b: str) -> bool:
    return a == b or distance.Levenshtein.normalized_similarity(a, b) >= 0.9

def _fuzzy_jaccard(gs: List[str], cs: List[str]) -> float:
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
    d = "".join(filter(str.isdigit, str(ph)))
    if d.startswith("972"):
        d = "0" + d[3:]
    return f"{d[:3]}-{d[3:]}" if len(d) == 10 else d

def full_score(g_norm: str, c_norm: str) -> int:
    if not g_norm or not c_norm:
        return 0
    if g_norm.strip() == c_norm.strip():
        return AUTO_SCORE
    g_t, c_t = _tokens(g_norm), _tokens(c_norm)
    if g_t == c_t:
        return AUTO_SCORE
    if not g_t or not c_t:
        return fuzz.partial_ratio(g_norm, c_norm)
    tr = fuzz.token_set_ratio(" ".join(g_t), " ".join(c_t)) / 100
    fr = fuzz.ratio(g_t[0], c_t[0]) / 100
    jr = _fuzzy_jaccard(g_t, c_t)
    gap = abs(len(g_t) - len(c_t))
    penalty = (min(len(g_t), len(c_t)) / max(len(g_t), len(c_t))) if gap >= 2 else 1
    return int(round((0.6 * tr + 0.2 * fr + 0.2 * jr) * penalty * 100))

def reason_for(g_norm: str, c_norm: str, score: int) -> str:
    overlap = [t for t in _tokens(g_norm) if t in set(_tokens(c_norm))]
    if overlap:
        return f"חפיפה: {', '.join(overlap[:2])}"
    if score >= AUTO_SELECT_TH:
        return "התאמה גבוהה"
    return ""

def load_excel(file) -> pd.DataFrame:
    # 1) קריאה דינמית של CSV או Excel
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
        df[PHONE_COL].fillna("").astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.strip()
    )

    # 3) עמודת "שם מלא"
    if NAME_COL in df.columns:
        df[NAME_COL] = df[NAME_COL].fillna("").astype(str).str.strip()
    else:
        df[NAME_COL] = _resolve_full_name_series(df)

    # 4) "כמות מוזמנים"
    count_hints = ["כמות", "מספר מוזמנים", "מס' מוזמנים", "מוזמנים",
                   "מספר אורחים", "אורחים", "guest count", "guests", "guest", "count", "qty", "quantity", "amount"]
    if COUNT_COL not in df.columns:
        alt_count = [c for c in df.columns if any(h in str(c).lower() for h in count_hints)]
        if alt_count:
            df.rename(columns={alt_count[0]: COUNT_COL}, inplace=True)
        else:
            df[COUNT_COL] = 1
    counts_raw = df[COUNT_COL].astype(str)
    counts_num = pd.to_numeric(counts_raw.str.extract(r"(\d+)")[0], errors="coerce")
    df[COUNT_COL] = counts_num.fillna(1).astype(int)

    # 5) צד/קבוצה
    for col in (SIDE_COL, GROUP_COL):
        if col not in df.columns:
            df[col] = ""
        else:
            df[col] = df[col].fillna("").astype(str).str.strip()

    # 6) שם מנורמל
    df["norm_name"] = df[NAME_COL].map(normalize)
    return df

def to_buf(df: pd.DataFrame) -> BytesIO:
    export = df.drop(columns=["norm_name", "score", "best_score", NAME_COL], errors="ignore").copy()
    original = [c for c in export.columns if c != PHONE_COL]
    final = original + [PHONE_COL]
    export = export.reindex(columns=final, fill_value="")
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        export.to_excel(w, index=False, sheet_name="RSVP")
    buf.seek(0)
    return buf

def top_matches(guest_norm: str, contacts_df: pd.DataFrame) -> pd.DataFrame:
    if not guest_norm:
        return pd.DataFrame(columns=list(contacts_df.columns) + ["score", "reason"])
    scores = contacts_df["norm_name"].apply(lambda c: full_score(guest_norm, c))
    df = (
        contacts_df.assign(score=scores)
        .query("score>=@MIN_SCORE_DISPLAY")
        .sort_values(["score", NAME_COL], ascending=[False, True])
        .head(MAX_DISPLAYED)
        .copy()
    )
    df["reason"] = df.apply(lambda r: reason_for(guest_norm, r["norm_name"], int(r["score"])), axis=1)
    return df

def compute_best_scores(guests_df: pd.DataFrame, contacts_df: pd.DataFrame) -> pd.Series:
    return guests_df["norm_name"].apply(
        lambda n: int(contacts_df["norm_name"].apply(lambda c: full_score(n, c)).max()) if n else 0
    )
