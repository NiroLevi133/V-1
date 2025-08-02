# logic.py – התאמות טלפונים וטעינת קבצים
"""שדרוג אלגוריתם התאמת השמות (גרסה 2025‑07‑22)
-------------------------------------------------
* חיזוק נורמליזציה (הסרת '|', '/', '()' ועוד)
* התעלמות ממילים סופיות לא רלוונטיות (״מילואים״, "נייד", "בית", "עבודה" …)
* fuzzy‑eq על־ידי Levenshtein ≥ 90 %
* בונוס 100 % כאשר core‑tokens זהים (שם‑פרטי + משפחה)
* length_penalty מוחל רק אם יש +2 טוקנים פער
"""

from __future__ import annotations
import re
import os
from io import BytesIO
from typing import List, Set

import pandas as pd
import unidecode
from rapidfuzz import fuzz, distance
import gspread
from google.oauth2 import service_account

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

# הגדרות Google Sheets
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SPREADSHEET_ID = "1kMilBqKmldMBuvHtOdJsEGfo6Kb-J0W5rEXAhmG57b0"

# מילות יחס/קשר (ignored לגמרי)
GENERIC_TOKENS: Set[str] = {
    "של", "ה", "בן", "בת", "משפחת", "אחי", "אחות", "דוד", "דודה"
}
# סיומות/כינויים שאינם חלק מהשם (נמחקות מהקצה)
SUFFIX_TOKENS: Set[str] = {
    "מילואים", "miluyim", "miloyim", "mil", "נייד", "סלולר", "סלולרי",
    "בית", "עבודה", "עסקי", "אישי", "משרד"
}

# ───────── GOOGLE SHEETS CONNECTION ─────────
def _get_sheet():
    """צריבת התחברות לגוגל שיטס"""
    possible_paths = [
        "/etc/secrets/gcp_credentials.json",
        "gcp_credentials.json",
        "./gcp_credentials.json"
    ]
    creds = None
    for path in possible_paths:
        if os.path.exists(path):
            creds = service_account.Credentials.from_service_account_file(path, scopes=SCOPES)
            break
    if not creds:
        return None
    gc = gspread.authorize(creds)
    return gc.open_by_key(SPREADSHEET_ID).worksheet("גיליון1")

def is_user_authorized(phone: str) -> bool:
    """בדיקה האם משתמש מורשה - גוגל שיטס + קובץ מקומי"""
    clean_phone = re.sub(r"\D", "", phone or "")
    sheet = _get_sheet()
    if sheet:
        for row in sheet.get_all_records():
            if clean_phone == re.sub(r"\D", "", str(row.get("טלפון", ""))):
                return True
    # קובץ מקומי
    local = "allowed_users.xlsx"
    if os.path.exists(local):
        df = pd.read_excel(local)
        for col in df.columns:
            if any(k in str(col).lower() for k in ["טלפון","phone","מספר"]):
                for val in df[col].astype(str):
                    if clean_phone == re.sub(r"\D","", val):
                        return True
                break
    return False

# ───────── HELPERS ─────────
_punc_re   = re.compile(r"[\|\\/()\[\]\"'׳'״.,\-]+")
_space_re  = re.compile(r"\s+")
_token_re  = re.compile(r"\s+")

def _best_text_col(candidates: List[str], df: pd.DataFrame) -> str:
    """בחירת עמודת טקסט איכותית מתוך מועמדים."""
    def score(col):
        s = df[col].astype(str).fillna("")
        return ((s.str.strip() != "").sum(), s.str.contains(r"[A-Za-zא-ת]").mean(), s.str.len().mean())
    return max(candidates, key=score)

def _resolve_full_name_series(df: pd.DataFrame) -> pd.Series:
    """
    מאחד עמודות שם פרטי ומשפחה / מזהה ישירות עמודת 'שם מלא' / דמוית שם.
    """
    cols = list(df.columns)
    low = {c: c.strip().lower() for c in cols}
    # ישירות
    direct = {"שם מלא","full name","fullname","guest name","שם המוזמן"}
    for c in cols:
        if low[c] in direct:
            return df[c].fillna("").astype(str).str.strip()
    # פרטי + משפחה
    first = [c for c in cols if "פרטי" in low[c] or low[c] in {"שם","first","firstname"}]
    last  = [c for c in cols if "משפחה" in low[c] or low[c] in {"last","lastname","surname"}]
    if first and last:
        f, l = _best_text_col(first, df), _best_text_col(last, df)
        return (df[f].fillna("").astype(str).str.strip() + " " +
                df[l].fillna("").astype(str).str.strip()).str.replace(r"\s+"," ",regex=True).str.strip()
    # דמוית שם
    name_like = [c for c in cols if any(k in low[c] for k in ["שם","name","guest","מוזמן"])]
    if name_like:
        c = _best_text_col(name_like, df)
        return df[c].fillna("").astype(str).str.strip()
    return pd.Series([""]*len(df))

def normalize(txt: str | None) -> str:
    """Normalization: lowercase, strip punctuation, single-space, latin."""
    if not txt:
        return ""
    t = str(txt).lower()
    t = _punc_re.sub(" ", t)
    t = _space_re.sub(" ", t).strip()
    return unidecode.unidecode(t)

def _clean_token(tok: str) -> str:
    if tok in SUFFIX_TOKENS:
        return ""
    if tok.startswith("v") and len(tok)>2:
        tok = tok[1:]
    if len(tok)>=4 and tok.endswith("i"):
        tok = tok[:-1]
    return tok

def _tokens(name: str) -> List[str]:
    return [t for t in (_clean_token(x) for x in _token_re.split(name)) if t and t not in GENERIC_TOKENS]

def _fuzzy_eq(a: str, b: str) -> bool:
    return a==b or distance.Levenshtein.normalized_similarity(a,b)>=0.9

def _fuzzy_jaccard(gs: List[str], cs: List[str]) -> float:
    matched, used = 0, set()
    for g in gs:
        for c in cs:
            if c in used: continue
            if _fuzzy_eq(g,c):
                matched+=1; used.add(c); break
    union = len(set(gs))+len(set(cs))-matched
    return matched/union if union else 1.0

def format_phone(ph: str) -> str:
    d = "".join(filter(str.isdigit, str(ph)))
    if d.startswith("972"): d = "0"+d[3:]
    return f"{d[:3]}-{d[3:]}" if len(d)==10 else d

# ───────── CORE SCORING ─────────
def full_score(g_norm: str, c_norm: str) -> int:
    if not g_norm or not c_norm:
        return 0
    if g_norm.strip()==c_norm.strip():
        return AUTO_SCORE
    g_t, c_t = _tokens(g_norm), _tokens(c_norm)
    if g_t==c_t:
        return AUTO_SCORE
    if not g_t or not c_t:
        return fuzz.partial_ratio(g_norm, c_norm)
    tr = fuzz.token_set_ratio(" ".join(g_t)," ".join(c_t))/100
    fr = fuzz.ratio(g_t[0],c_t[0])/100
    jr = _fuzzy_jaccard(g_t,c_t)
    gap = abs(len(g_t)-len(c_t))
    penalty = (min(len(g_t),len(c_t))/max(len(g_t),len(c_t))) if gap>=2 else 1
    return int(round((0.6*tr+0.2*fr+0.2*jr)*penalty*100))

def reason_for(g_norm: str, c_norm: str, score: int) -> str:
    overlap = [t for t in _tokens(g_norm) if t in set(_tokens(c_norm))]
    if overlap:
        return f"חפיפה: {', '.join(overlap[:2])}"
    if score>=AUTO_SELECT_TH:
        return "התאמה גבוהה"
    return ""

# ───────── LOAD & EXPORT ─────────
def load_excel(file) -> pd.DataFrame:
    """טוען CSV או Excel, מנרמל ושומר עמודות: שם מלא, פלאפון, כמות, צד, קבוצה."""
    # 1) קריאה דינמית של CSV או Excel
    if hasattr(file, "name") and str(file.name).lower().endswith(".csv"):
        df = pd.read_csv(file).rename(columns=lambda c: str(c).strip())
    else:
        df = pd.read_excel(file).rename(columns=lambda c: str(c).strip())

    # 2) זיהוי וטיפול בעמודת טלפון
    if PHONE_COL not in df.columns:
        hints = ["טלפון", "פלא", "נייד", "cell", "mobile", "phone", "מספר"]
        alt = [c for c in df.columns if any(h in str(c).lower() for h in hints)]
        if alt:
            df.rename(columns={alt[0]: PHONE_COL}, inplace=True)
        else:
            df[PHONE_COL] = ""
    df[PHONE_COL] = (
        df[PHONE_COL]
        .fillna("")                  # רק על Series
        .astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.strip()
    )

    # 3) טיפול חכם בעמודת "שם מלא"
    if NAME_COL in df.columns:
        df[NAME_COL] = df[NAME_COL].fillna("").astype(str).str.strip()
    else:
        df[NAME_COL] = _resolve_full_name_series(df)

    # 4) טיפול חכם בעמודת "כמות מוזמנים"
    count_hints = [
        "כמות", "מספר מוזמנים", "מס' מוזמנים", "מוזמנים",
        "מספר אורחים", "אורחים",
        "guest count", "guests", "guest", "count", "qty", "quantity", "amount"
    ]
    if COUNT_COL not in df.columns:
        alt_count = [c for c in df.columns if any(h in str(c).lower() for h in count_hints)]
        if alt_count:
            df.rename(columns={alt_count[0]: COUNT_COL}, inplace=True)
        else:
            df[COUNT_COL] = 1

    # המרת כל תא למספר הראשון שמופיע בו, ברירת־מחדל 1
    counts_raw = df[COUNT_COL].astype(str)
    counts_num = pd.to_numeric(counts_raw.str.extract(r"(\d+)")[0], errors="coerce")
    df[COUNT_COL] = counts_num.fillna(1).astype(int)

    # 5) עמודות צד וקבוצה
    for col in (SIDE_COL, GROUP_COL):
        if col not in df.columns:
            df[col] = ""
        else:
            df[col] = df[col].fillna("").astype(str).str.strip()

    # 6) סדרת השמות המנורמלת להתאמה
    df["norm_name"] = df[NAME_COL].map(normalize)
    return df


def to_buf(df: pd.DataFrame) -> BytesIO:
    # מסירים גם את עמודת השם המלא מהייצוא
    export = df.drop(columns=["norm_name","score","best_score", NAME_COL], errors="ignore").copy()
    original = [c for c in export.columns if c!=PHONE_COL]
    final = original+[PHONE_COL]
    export = export.reindex(columns=final, fill_value="")
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        export.to_excel(w, index=False, sheet_name="RSVP")
    buf.seek(0)
    return buf

def top_matches(guest_norm: str, contacts_df: pd.DataFrame) -> pd.DataFrame:
    if not guest_norm:
        return pd.DataFrame(columns=list(contacts_df.columns)+["score","reason"])
    scores = contacts_df["norm_name"].apply(lambda c: full_score(guest_norm,c))
    df = (
        contacts_df.assign(score=scores)
        .query("score>=@MIN_SCORE_DISPLAY")
        .sort_values(["score",NAME_COL],ascending=[False,True])
        .head(MAX_DISPLAYED)
        .copy()
    )
    df["reason"] = df.apply(lambda r: reason_for(guest_norm, r["norm_name"], int(r["score"])),axis=1)
    return df

def compute_best_scores(guests_df: pd.DataFrame, contacts_df: pd.DataFrame) -> pd.Series:
    return guests_df["norm_name"].apply(lambda n: int(contacts_df["norm_name"].apply(lambda c: full_score(n,c)).max()) if n else 0)
