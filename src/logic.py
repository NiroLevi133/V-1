# logic.py – בדיקת משתמש מורשה (Sheets + קובץ מקומי)
import os
import re
import logging
import pandas as pd

# gspread + Google Auth
import google.auth
import gspread

# ───────── CONSTANTS ─────────
# אם תרצה, תגדיר את אלה כמשתני סביבה ב־Cloud Run:
SPREADSHEET_ID_ENV   = "SPREADSHEET_ID"    # מזהה הגיליון מתוך ה-URL: https://.../d/<ID>/...
WORKSHEET_TITLE_ENV  = "WORKSHEET_TITLE"   # שם הלשונית (לדוג׳ 'גיליון1'), אפשר None

LOCAL_ALLOWED_FILE   = "allowed_users.xlsx"  # קובץ גיבוי במידה ואין Sheets
LOCAL_PHONE_COLS     = ("טלפון", "phone", "מספר")  # מילות מפתח לכותרת עמודת טלפון

# Scopes ל־Sheets + Drive (לקריאה בלבד)
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

# ───────── Helpers ─────────
def only_digits(s: str) -> str:
    """מוריד כל תו שאינו ספרה."""
    return re.sub(r"\D+", "", s or "")

def _load_allowed_from_sheets() -> set[str] | None:
    """מנסה לטעון את רשימת המורשים מגוגל שיטס. מחזיר None אם נכשל."""
    sheet_id = os.getenv(SPREADSHEET_ID_ENV)
    if not sheet_id:
        logging.info("Env var %s not set, skipping Sheets.", SPREADSHEET_ID_ENV)
        return None

    # לוקח שם לשונית אם קיים
    sheet_title = os.getenv(WORKSHEET_TITLE_ENV)

    try:
        # ADC: משתמש בקרדנשלס של השירות (Cloud Run SA)
        creds, _ = google.auth.default(scopes=SCOPES)
        client = gspread.authorize(creds)

        sh = client.open_by_key(sheet_id)
        ws = sh.worksheet(sheet_title) if sheet_title else sh.sheet1

        rows = ws.get_all_values()
        if not rows or len(rows) < 2:
            logging.warning("Allowed sheet is empty or has no data.")
            return set()

        # כותרת בעמודה הראשונה מזהה עמודת טלפון
        header = [c.strip() for c in rows[0]]
        try:
            phone_idx = next(i for i,h in enumerate(header) if h in LOCAL_PHONE_COLS)
        except StopIteration:
            phone_idx = 1  # עמודה B כברירת מחדל

        allowed = {
            only_digits(row[phone_idx])
            for row in rows[1:]
            if len(row) > phone_idx and only_digits(row[phone_idx])
        }
        logging.info("Loaded %d allowed phones from Sheets.", len(allowed))
        return allowed

    except Exception as e:
        logging.exception("Failed to load allowed phones from Sheets")
        return None

def _load_allowed_from_excel() -> set[str]:
    """טוען את רשימת המורשים מקובץ Excel מקומי."""
    if not os.path.exists(LOCAL_ALLOWED_FILE):
        logging.info("Local allowed file %s not found.", LOCAL_ALLOWED_FILE)
        return set()

    try:
        df = pd.read_excel(LOCAL_ALLOWED_FILE, dtype=str)
    except Exception as e:
        logging.exception("Failed to read local allowed Excel file")
        return set()

    # מוצא עמודת טלפון לפי כותרת
    cols = [c for c in df.columns if any(k in str(c).lower() for k in LOCAL_PHONE_COLS)]
    if not cols:
        logging.warning("No phone column found in local Excel.")
        return set()

    phone_col = cols[0]
    allowed = {
        only_digits(str(val))
        for val in df[phone_col]
        if only_digits(str(val))
    }
    logging.info("Loaded %d allowed phones from local Excel.", len(allowed))
    return allowed

# ───────── Public API ─────────
def is_user_authorized(phone: str) -> bool:
    """
    מחזיר True אם המספר מופיע ברשימת המורשים (Sheets או Excel מקומי).
    """
    clean_phone = only_digits(phone)

    # מנסה קודם גוגל שיטס
    allowed = _load_allowed_from_sheets()
    if allowed is not None:
        return clean_phone in allowed

    # אחרת גיבוי מקומי
    allowed_local = _load_allowed_from_excel()
    return clean_phone in allowed_local


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
