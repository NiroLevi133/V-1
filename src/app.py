# ───────────────────────────────────────────────────────────
# app.py  –  מיזוג טלפונים 💎
# ───────────────────────────────────────────────────────────
import time, secrets, re, logging, requests, os
from datetime import datetime
from typing import Optional
from pathlib import Path
import tempfile, gc
from io import BytesIO
import pandas as pd
import streamlit as st

from logic import (
    NAME_COL, PHONE_COL, COUNT_COL, SIDE_COL, GROUP_COL,
    AUTO_SELECT_TH, load_excel, to_buf,
    format_phone, normalize, compute_best_scores, full_score,
    is_user_authorized, MIN_SCORE_DISPLAY, MAX_DISPLAYED
)

# ───────── הגדרות בסיסיות ─────────
logging.basicConfig(level=logging.ERROR)
PAGE_TITLE        = " מיזוג טלפונים 💎"
CODE_TTL_SECONDS  = 300
MAX_AUTH_ATTEMPTS = 5
PHONE_PATTERN     = re.compile(r"^0\d{9}$")
ADMIN_WHATSAPP    = "972507676706"

st.set_page_config(page_title=PAGE_TITLE, layout="wide")

def get_required_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return v

GREEN_API_ID    = get_required_env("GREEN_API_ID")
GREEN_API_TOKEN = get_required_env("GREEN_API_TOKEN")   

#HELP
# תיקיה זמנית לכתיבה - עובדת גם לוקאלית וגם ב-Render
TMP_ROOT = Path(tempfile.gettempdir()) / "merge_app"
TMP_ROOT.mkdir(parents=True, exist_ok=True)

def _user_root() -> Path:
    """תיקיית עבודה פר-משתמש לפי מספר הטלפון (אחרי התחברות)."""
    phone = st.session_state.get("phone", "anon")
    p = TMP_ROOT / phone
    p.mkdir(parents=True, exist_ok=True)
    return p

def save_tmp(uploaded_file, subfolder: str, fname: str) -> Path:
    """שומר קובץ upload לתיקיית tmp/<phone>/<subfolder>/fname ומחזיר נתיב."""
    base = _user_root() / subfolder
    base.mkdir(parents=True, exist_ok=True)
    path = base / fname
    path.write_bytes(uploaded_file.getbuffer())
    return path

@st.cache_data(show_spinner=False)
def read_table(path_str: str) -> pd.DataFrame:
    """
    קריאת קובץ (xlsx/xls/csv) מהדיסק בפעם הראשונה; תוצאה נשמרת בקאש.
    משתמש ב-load_excel שלך כדי לשמור את כל הלוגיקה הקיימת.
    """
    p = Path(path_str)
    with open(p, "rb") as f:
        df = load_excel(f)
    # הקלה על הזיכרון: טיפוס מחרוזת קומפקטי אם זמין
    try:
        df[PHONE_COL] = df[PHONE_COL].astype("string[pyarrow]")
    except Exception:
        pass
    return df

def persist_guests(df: pd.DataFrame):
    """
    שומר את דאטה-פריים המוזמנים חזרה לקובץ (באותו path) ומנקה cache,
    כדי שהטעינה הבאה תראה את העדכון.
    """
    path = Path(st.session_state["guests_path"])
    buf: BytesIO = to_buf(df)        # to_buf שלך מחזיר BytesIO ל-Excel
    path.write_bytes(buf.getvalue())
    st.cache_data.clear()            # לנקות cache כדי שהקריאה הבאה תביא את הגרסה החדשה

def get_contacts_df() -> pd.DataFrame:
    return read_table(st.session_state["contacts_path"])

def get_guests_df() -> pd.DataFrame:
    return read_table(st.session_state["guests_path"])

def save_guests_df(df: pd.DataFrame) -> None:
    # משתמש ב-persist_guests שלך
    persist_guests(df)

    

# ───────── מנגנון איתור קבצים (styles / assets) ─────────
HERE = Path(__file__).resolve().parent           # .../src

def find_up(start: Path, subdir: str, fname: str) -> Path | None:
    """מחפש subdir/fname בתיקייה הנתונה וכל ה-parents שלה."""
    for base in (start, *start.parents):
        fp = base / subdir / fname
        if fp.is_file():
            return fp
    return None

def find_css(fname: str) -> Path | None:
    """CSS מתוך styles – מנסה גם מה־cwd (לוקאל) וגם מ־HERE (שרת)."""
    return find_up(HERE, "styles", fname) or find_up(Path.cwd(), "styles", fname)

# ───────── טעינת style.css ─────────
css_path = find_css("style.css")
if css_path:
    st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)
else:
    st.error("⚠️ style.css לא נמצא – בדוק את מבנה התיקיות")

# ───────── כלי עזר ─────────
def normalize_phone_basic(p: str) -> Optional[str]:
    d = re.sub(r"\D", "", p or "")
    return d if PHONE_PATTERN.match(d) else None

def send_code(phone: str, code: str):
    chat = ("972" + phone[1:] if phone.startswith("0") else phone) + "@c.us"
    url  = f"https://api.green-api.com/waInstance{GREEN_ID}/sendMessage/{GREEN_TOKEN}"
    requests.post(url, json={"chatId": chat, "message": f"קוד האימות שלך: {code}"})

def force_rerun():
    st.rerun()
def load_login_css():
    login_css = """
    /* הסתרת header של streamlit */
    .stAppHeader, .stAppToolbar, header[data-testid="stHeader"], .stDeployButton {display:none!important;}
    
    /* רקע כחול - גם למסך קוד אימות */
    .stApp {
      background: linear-gradient(135deg,#E8EEFF 0%,#DBE6FF 100%)!important;
      min-height: 100vh!important;
    }
    
    /* מחיקת קווים אפורים והכנסה למסגרת */
    .main .block-container {
      padding: 2rem!important;
      max-width: 600px!important;
      margin: 0 auto!important;
      border: none!important;
      box-shadow: none!important;
      background: white!important;
      border-radius: 20px!important;
      box-shadow: 0 10px 30px rgba(0,0,0,0.1)!important;
      margin-top: 3rem!important;
    }
    
    /* אייקון עגול */
    .auth-icon {
      width: 70px!important;
      height: 70px!important;
      background: #E3F2FD!important;
      border-radius: 50%!important;
      display: flex!important;
      align-items: center!important;
      justify-content: center!important;
      margin: 0 auto 24px!important;
      font-size: 28px!important;
      color: #4A90E2!important;
    }
    
    /* כותרות */
    .auth-title {
      font-size: 28px!important;
      font-weight: 800!important;
      color: #2c3e50!important;
      margin-bottom: 10px!important;
      text-align: center!important;
    }
    
    .auth-subtitle {
      font-size: 15px!important;
      color: #7f8c8d!important;
      margin-bottom: 28px!important;
      text-align: center!important;
    }
    
    .phone-label {
      font-size: 14px!important;
      color: #555!important;
      margin-bottom: 8px!important;
      text-align: center!important;
    }
    
    /* שדה טקסט - גודל רגיל */
    .stTextInput > div > div > input {
      text-align: center!important;
      font-size: 16px!important;
      height: 42px!important;
      width: 100%!important;
      max-width: 350px!important;
      margin: 0 auto!important;
      border: 2px solid #e1e8ed!important;
      border-radius: 10px!important;
      direction: ltr!important;
      background: #fafafa!important;
      font-family: monospace!important;
    }
    
    .stTextInput > div {
      display: flex!important;
      justify-content: center!important;
      border: none!important;
      background: transparent!important;
      box-shadow: none!important;
    }
    
    .stTextInput > div > div {
      border: none!important;
      background: transparent!important;
      box-shadow: none!important;
      outline: none!important;
      max-width: 350px!important;
      width: 100%!important;
    }
    
    .stTextInput > div > div > input:focus {
      border-color: #4A90E2!important;
      box-shadow: 0 0 0 3px rgba(74,144,226,.12)!important;
      outline: none!important;
    }
    
    /* כפתור - גודל רגיל */
    .stButton > button {
      width: 100%!important;
      max-width: 350px!important;
      height: 42px!important;
      font-size: 16px!important;
      background: #7EA6F9!important;
      color: #fff!important;
      border: none!important;
      border-radius: 10px!important;
      margin: 10px auto!important;
      display: block!important;
      font-weight: 600!important;
      transition: .2s!important;
    }
    
    .stButton > button:hover {
      background: #5C83D8!important;
      transform: translateY(-1px)!important;
      box-shadow: 0 6px 18px rgba(94,131,216,.35)!important;
    }
    
    /* הודעות שגיאה מותאמות */
    .unauthorized-message {
      background: #ffe6e6!important;
      border: 2px solid #ff4444!important;
      border-radius: 12px!important;
      padding: 20px!important;
      text-align: center!important;
      margin: 20px auto!important;
      max-width: 350px!important;
    }
    
    .unauthorized-title {
      color: #cc0000!important;
      font-size: 18px!important;
      font-weight: bold!important;
      margin-bottom: 10px!important;
    }
    
    .unauthorized-text {
      color: #666!important;
      font-size: 14px!important;
      margin-bottom: 15px!important;
    }
    
    .whatsapp-button {
      background: #25D366!important;
      color: white!important;
      padding: 12px 20px!important;
      border-radius: 10px!important;
      text-decoration: none!important;
      display: inline-flex!important;
      align-items: center!important;
      gap: 8px!important;
      font-weight: 600!important;
      transition: all 0.2s!important;
      border: none!important;
      font-size: 14px!important;
    }
    
    .whatsapp-button:hover {
      background: #1da851!important;
      transform: translateY(-1px)!important;
      text-decoration: none!important;
      color: white!important;
    }
    """
    st.markdown(f"<style>{login_css}</style>", unsafe_allow_html=True)

def load_file_uploader_css():
    file_css = """
    /* 1) איפוס מעטפת ה-uploader */
    [data-testid="stFileUploader"] > div {
      padding: 0 !important;
      background: transparent !important;
      box-shadow: none !important;
      border: none !important;
    }

    /* 2) עיצוב הדרופזון עצמו - עם הגרדיאנט שלך */
    [data-testid="stFileUploadDropzone"]{
      position: relative;
      border: 2px dashed rgba(255,255,255,0.3) !important;
      border-radius: 16px !important;
      padding: 26px 18px !important;
      background: linear-gradient(45deg, #667eea 0%, #764ba2 100%) !important;
      transition: all 0.3s ease;
      box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3) !important;
    }

    /* הובר/פוקוס */
    [data-testid="stFileUploadDropzone"]:hover{
      transform: translateY(-2px) !important;
      box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4) !important;
      border-color: rgba(255,255,255,0.6) !important;
    }

    /* 3) מסתירים את הטקסט/כפתור המובנים */
    [data-testid="stFileDropzoneInstructions"]{
      visibility: hidden;
      height: 72px;
    }

    [data-testid="stFileUploadDropzone"] button{
      display: none !important;
    }

    /* 4) שכבת-על עברית יפה */
    [data-testid="stFileUploadDropzone"]::after{
      content: "📄 גרור קובץ או לחץ לבחירה\\A Excel/CSV • עד 200MB";
      white-space: pre-line;
      position: absolute;
      inset: 0;
      display: grid;
      place-items: center;
      text-align: center;
      font-weight: 600;
      font-size: 0.95rem;
      color: white;
      pointer-events: none;
      direction: rtl;
      text-shadow: 0 1px 2px rgba(0,0,0,0.1);
    }

    /* 5) כאשר יש קובץ - מסתירים את השכבה */
    [data-testid="stFileUploader"]:has([data-testid="stUploadedFile"]) [data-testid="stFileUploadDropzone"]::after{
      content: "";
    }

    /* 6) טקסטים שונים לכל תיבה */
    [data-testid="stFileUploader"]:nth-of-type(1) [data-testid="stFileUploadDropzone"]::after{
      content: "📇 בחר קובץ אנשי קשר\\A Excel/CSV • עד 200MB";
    }

    [data-testid="stFileUploader"]:nth-of-type(2) [data-testid="stFileUploadDropzone"]::after{
      content: "🎉 בחר קובץ מוזמנים\\A Excel/CSV • עד 200MB";
    }

    /* 7) כשנבחר קובץ - שינוי צבע לירוק */
    [data-testid="stFileUploader"]:has([data-testid="stUploadedFile"]) [data-testid="stFileUploadDropzone"]{
      background: linear-gradient(45deg, #11998e 0%, #38ef7d 100%) !important;
      box-shadow: 0 4px 15px rgba(17, 153, 142, 0.3) !important;
    }

    /* 8) עיצוב שם הקובץ שנבחר */
    [data-testid="stUploadedFile"] {
      background: rgba(255,255,255,0.9) !important;
      border-radius: 8px !important;
      padding: 8px 12px !important;
      margin-top: 8px !important;
      border: none !important;
    }

    /* 9) מובייל */
    @media (max-width: 420px){
      [data-testid="stFileUploadDropzone"]{
        padding: 22px 14px !important;
      }
      [data-testid="stFileUploadDropzone"]::after{
        font-size: 0.9rem;
      }
    }
    """
    st.markdown(f"<style>{file_css}</style>", unsafe_allow_html=True)

# ───────── תמונת המדריך ─────────
JONI_IMG = find_up(HERE, "assets", "Joni.png") or find_up(Path.cwd(), "assets", "Joni.png")

# ───────── משתנה מדריך ─────────
if "show_contacts_guide" not in st.session_state:
    st.session_state.show_contacts_guide = False


def render_contacts_guide():
    col_text, col_img = st.columns([1, 2])

    with col_text:
        st.header("📝 מדריך הורדת קובץ אנשי קשר")
        st.markdown("""
**שלבי הורדה:**
1. התחברו מהמחשב (לא מהטלפון).  
2. התקינו את התוסף **Joni**: <https://joni.pyrogss.com>  
3. פתחו **WhatsApp Web**.  
4. לחצו על סמל J → **אנשי קשר** → **שמירה לקובץ אקסל**.  
5. הקובץ יורד למחשב.
""", unsafe_allow_html=True)
        if st.button("✖️ סגור מדריך"):
            st.session_state.show_contacts_guide = False
            st.rerun()

    with col_img:
        if JONI_IMG:
            st.image(str(JONI_IMG), width=550, use_container_width=False)
        else:
            st.warning("⚠️ Joni.png לא נמצא – שים אותו ב-assets/")

# ───────── תהליך התחברות ─────────
def auth_flow() -> bool:
    if st.session_state.get("auth_ok"):
        return True

    load_login_css()
    state = st.session_state.setdefault("auth_state", "phone")
    icon      = "💬" if state == "phone" else "🔐"
    subtitle  = "התחבר באמצעות מספר טלפון" if state == "phone" else "הכנס את הקוד שנשלח"
    label_txt = "מספר טלפון" if state == "phone" else "קוד אימות"

    st.markdown(f'<div class="auth-icon">{icon}</div>', unsafe_allow_html=True)
    st.markdown('<div class="auth-title">מערכת שילוב רשימות</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="auth-subtitle">{subtitle}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="phone-label">{label_txt}</div>', unsafe_allow_html=True)

    if state == "phone":
        phone = st.text_input("מספר טלפון", placeholder="05X-XXXXXXX",
                              max_chars=10, key="phone_input", label_visibility="hidden")
        if st.button("שלח קוד אימות 💬"):
            p = normalize_phone_basic(phone)
            if not p:
                st.error("מספר לא תקין.")
            else:
                try:
                    if not is_user_authorized(p):
                        wa = f"https://wa.me/{ADMIN_WHATSAPP}?text=אני רוצה להצטרף למערכת"
                        st.markdown(f"""
<div class="unauthorized-message">
   <div class="unauthorized-title">🚫 מספר לא מורשה</div>
   <div class="unauthorized-text">פנה למנהל המערכת להוספתך</div>
   <a href="{wa}" target="_blank" class="whatsapp-button">💬 צור קשר בוואטסאפ</a>
</div>
""", unsafe_allow_html=True)
                    else:
                        code = "".join(secrets.choice("0123456789") for _ in range(4))
                        st.session_state.update(
                            {"auth_code": code, "phone": p,
                             "code_ts": time.time(), "auth_state": "code"}
                        )
                        send_code(p, code)
                        st.success("הקוד נשלח.")
                        force_rerun()
                except Exception as e:
                    st.error(f"שגיאה בבדיקת הרשאה: {e}")

    else:  # state == code
        entry   = st.text_input("קוד אימות", placeholder="4 ספרות", max_chars=4, label_visibility="hidden")
        expired = (time.time() - st.session_state.code_ts) > CODE_TTL_SECONDS
        if expired:
            st.warning("הקוד פג תוקף")
        if st.button("אמת 🔓"):
            if expired:
                st.error("הקוד פג תוקף")
            elif entry == st.session_state.auth_code:
                st.session_state.auth_ok = True
                st.success("✅ התחברת בהצלחה!")
                time.sleep(1); force_rerun()
            else:
                att = st.session_state.get("auth_attempts", 0) + 1
                st.session_state.auth_attempts = att
                if att >= MAX_AUTH_ATTEMPTS:
                    st.error("נחרגת ממספר הניסיונות – נסה שוב מאוחר יותר")
                    st.session_state.auth_state = "phone"; force_rerun()
                else:
                    st.error(f"קוד שגוי • נשארו {MAX_AUTH_ATTEMPTS - att} ניסיונות")
    return False

# ======= MAIN APPLICATION =======
if not auth_flow():
    st.stop()

# אם ביקשו מדריך – מציגים במסך הראשי ועוצרים
if st.session_state.get("show_contacts_guide"):
    st.title(PAGE_TITLE)
    render_contacts_guide()
    st.stop()

# ממשיכים לאפליקציה הרגילה
load_file_uploader_css()
st.title(PAGE_TITLE)
# --- ביטול מרכזת ה‑TextInput מהלוגין + עיצוב קומפקטי לשדות הקטנים ---
st.markdown("""
<style>
/* בעמוד הראשי: לא למרכז את כל ה‑TextInput של סטרימליט */
[data-testid="stAppViewBlockContainer"] .stTextInput > div{
  display:block !important;
  justify-content:flex-start !important;
}
[data-testid="stAppViewBlockContainer"] .stTextInput > div > div{
  max-width:none !important;
  margin:0 !important;
}

/* עטיפה קומפקטית לימין לשדות הקטנים */
.compact-right{ display:flex; justify-content:flex-end; }
.compact-right .stTextInput input{
  width:180px !important;
  height:30px !important;
  font-size:13px !important;
  text-align:right !important;
  padding:0 8px !important;
  border:1px solid #cfd6dd !important;
  border-radius:6px !important;
}
</style>
""", unsafe_allow_html=True)


if "upload_confirmed" not in st.session_state:
    st.session_state.upload_confirmed = False

if not st.session_state.upload_confirmed:
    with st.sidebar:
        st.markdown("## 📂 העלאת קבצים")
        st.markdown("---")

        # כותרת + כפתור מדריך באותה שורה
        title_col, btn_col = st.columns([0.6, 0.4])
        with title_col:
            st.markdown("### 👥 קובץ אנשי קשר")
        with btn_col:
            if st.button("📖מדריך להורדת הקובץ", key="contacts_guide_btn", use_container_width=True):
                st.session_state.show_contacts_guide = True
                st.rerun()

        # תיבת העלאת קובץ אנשי קשר
        contacts_file = st.file_uploader(
            "קובץ אנשי קשר",
            type=["xlsx", "xls", "csv"],
            key="contacts_uploader",
            label_visibility="collapsed",
        )

        # תיבת העלאת קובץ מוזמנים
        st.markdown("### 🎉 קובץ מוזמנים")
        guests_file = st.file_uploader(
            "קובץ מוזמנים",
            type=["xlsx", "xls", "csv"],
            key="guests_uploader",
            label_visibility="collapsed",
        )

        # סטטוס טעינת הקבצים (כאן אין more python‑expressions – רק if/else)
        col1, col2 = st.columns(2)
with col1:
    if contacts_file:
        st.success("✅ אנשי קשר נטען")
    else:
        st.info("⏳ ממתין לקובץ אנשי קשר")

with col2:
    if guests_file:
        st.success("✅ מוזמנים נטען")
    else:
        st.info("⏳ ממתין לקובץ מוזמנים")

# כפתור האישור
confirm = st.button("✅ אשר קבצים", disabled=not (contacts_file and guests_file), use_container_width=True)

if confirm:
    with st.spinner("טוען קבצים…"):
        # שומר קבצים לדיסק (tmp/<phone>/contacts|guests/...)
        st.session_state["contacts_path"] = str(
            save_tmp(contacts_file, "contacts", contacts_file.name)
        )
        st.session_state["guests_path"] = str(
            save_tmp(guests_file, "guests", guests_file.name)
        )

        # טוען DataFrames פעם אחת (מהדיסק) ומחשב best_score – בלי לשמור אותם ב-session_state
        contacts_df = read_table(st.session_state["contacts_path"])
        guests_df   = read_table(st.session_state["guests_path"])

        # בדיקת תקינות טלפון (כמו שהיה)
        invalid_phones = []
        for idx, row in guests_df.iterrows():
            phone = str(row[PHONE_COL]).strip()
            if phone and not normalize_phone_basic(phone):
                invalid_phones.append(f"שורה {idx+1}: {row[NAME_COL]} - {phone}")
        if invalid_phones:
            for invalid in invalid_phones[:5]:
                st.error(invalid)
            if len(invalid_phones) > 5:
                st.error(f"ועוד {len(invalid_phones)-5} שגיאות...")

        # חישוב ציונים והטמעה בדאטה-פריים
        guests_df["best_score"] = compute_best_scores(guests_df, contacts_df)

        # לשמור את המצב המעודכן חזרה לקובץ ולהוציא מה־RAM
        persist_guests(guests_df)

        del contacts_df, guests_df, contacts_file, guests_file
        gc.collect()

    st.success("✅ הקבצים נטענו והמידע עודכן בהצלחה!")
    st.session_state.upload_confirmed = True
    st.rerun()



if not st.session_state.upload_confirmed:
    st.stop()

with st.sidebar:
    st.checkbox("רק חסרי מספר", key="filter_no", on_change=lambda: st.session_state.update(idx=0))

df = get_guests_df()
filtered_df = df.copy()

if st.session_state.get("filter_no"):
    filtered_df = filtered_df[filtered_df[PHONE_COL].str.strip() == ""]

all_sides  = df[SIDE_COL].dropna().unique().tolist()
all_groups = df[GROUP_COL].dropna().unique().tolist()

with st.sidebar:
    st.multiselect("סנן לפי צד", options=all_sides,  key="filter_sides")
    st.multiselect("סנן לפי קבוצה", options=all_groups, key="filter_groups")

if st.session_state.get("filter_sides"):
    filtered_df = filtered_df[filtered_df[SIDE_COL].isin(st.session_state.filter_sides)]
if st.session_state.get("filter_groups"):
    filtered_df = filtered_df[filtered_df[GROUP_COL].isin(st.session_state.filter_groups)]

filtered_total = len(filtered_df)
complete_idx   = min(st.session_state.get("idx", 0), filtered_total)

with st.sidebar:
    st.markdown(f"**{complete_idx}/{filtered_total} הושלמו**")
    st.progress(complete_idx / filtered_total if filtered_total else 0)
    st.download_button(
        "💾 הורד Excel מלא",
        data=to_buf(get_guests_df()),
        file_name="רשימת_מוזמנים_מלאה.xlsx",
        use_container_width=True,
    )

df = filtered_df.sort_values(["best_score", NAME_COL], ascending=[False, True])
if "idx" not in st.session_state:
    st.session_state.idx = 0

if st.session_state.idx >= len(df):
    st.success("🎉 סיימנו!")
    st.download_button("⬇️ הורד קובץ סופי", data=to_buf(get_guests_df()), file_name="רשימת_מוזמנים_סופית.xlsx", use_container_width=True)
    st.stop()

cur = df.iloc[st.session_state.idx]

st.markdown(
    f"""
    ## {cur[NAME_COL]}
    <div style='font-size:16px'>
    🧭 <b>צד:</b> {cur[SIDE_COL]}
    🧩 <b>קבוצה:</b> {cur[GROUP_COL]}
    👥 <b>כמות:</b> {int(cur[COUNT_COL])}<br><br><br>
    </div>
    """,
    unsafe_allow_html=True,
)

# ─── חישוב התאמות ───
matches     = get_contacts_df().copy()
matches["score"] = matches["norm_name"].map(lambda c: full_score(cur.norm_name, c))

# ─── בחירת מועמדים ───
if matches["score"].max() == 100:
    # אם יש התאמה מושלמת (100%), הצג עד 3 תוצאות עם score >= 90
    candidates = (
        matches[matches["score"] >= 90]
        .sort_values(["score", NAME_COL], ascending=[False, True])
        .head(3)
    )
else:
    # אחרת – הצג את שלושת הגבוהים מעל סף 70%, ואם אין כאלה – את ששת הגבוהים
    candidates = (
        matches[matches["score"] >= MIN_SCORE_DISPLAY]
        .sort_values(["score", NAME_COL], ascending=[False, True])
        .head(3)
    )
    if candidates.empty:
        candidates = (
            matches[ matches["score"] >= MIN_SCORE_DISPLAY ]
            .sort_values(["score", NAME_COL], ascending=[False, True])
            .head(MAX_DISPLAYED)
        )

# ─── בניית אפשרויות לציון המשתמש ───
options = ["❌ ללא התאמה"] + [
    f"{int(r.score)}% | {r[NAME_COL]} | {format_phone(r[PHONE_COL])}"
    for _, r in candidates.iterrows()
] + ["➕ הוסף ידני", "🔍 חפש אנשי קשר"]

choice = st.radio(
    "בחר התאמה:", options,
    index=1 if not candidates.empty and candidates.iloc[0].score >= AUTO_SELECT_TH else 0,
    label_visibility="collapsed"
)

manual_phone = ""
search_phone = ""

if choice == "➕ הוסף ידני":
    # שדה קטן, מיושר לימין, בלי תווית
    st.markdown('<div class="compact-right">', unsafe_allow_html=True)
    manual_phone = st.text_input(
        "", placeholder="05XXXXXXXX", key="manual_phone", label_visibility="hidden"
    )
    st.markdown('</div>', unsafe_allow_html=True)

elif choice == "🔍 חפש אנשי קשר":
    st.markdown('<div class="compact-right">', unsafe_allow_html=True)
    query = st.text_input(
        "", placeholder="שם/מספר", key="search_query", label_visibility="hidden"
    )
    st.markdown('</div>', unsafe_allow_html=True)

    if len(query) >= 2:
        result = get_contacts_df()[
            get_contacts_df().norm_name.str.contains(normalize(query))
            | get_contacts_df()[PHONE_COL].str.contains(query)
        ].head(6)

        if not result.empty:
            # ה-Selectbox נשאר ברוחב רגיל, אפשר לצמצם עם st.columns אם תרצה
            sel = st.selectbox(
                "בחר איש קשר",
                [f"{r[NAME_COL]} | {format_phone(r[PHONE_COL])}" for _, r in result.iterrows()],
                key="search_select",
            )
            if sel:
                search_phone = sel.split("|")[-1].strip()


# כפתורים מוחלפים - אישור גדול משמאל, חזרה קטן מימין
col1, col2 = st.columns([2, 1])
with col1:
    if st.button("✅ אישור", use_container_width=True, key="approve_btn"):
        val = None
        if manual_phone:
            val = normalize_phone_basic(manual_phone)
        elif search_phone:
            val = search_phone
        elif choice.startswith("❌"):
            val = ""
        else:
            val = choice.split("|")[-1].strip()

        if val is not None:
            guests_df = get_guests_df()
            guests_df.at[cur.name, PHONE_COL] = format_phone(val) if val else ""
            save_guests_df(guests_df)  # שמור לדיסק ונקה cache
            st.session_state.idx += 1
            force_rerun()
        else:
            st.warning("אין ערך תקין.")

with col2:
    if st.button(
        "⬅️ חזרה",
        disabled=(st.session_state.idx == 0),
        use_container_width=True,
        key="back_btn"
    ):
        st.session_state.idx = max(0, st.session_state.idx - 1)
        force_rerun()
