# ───────────────────────────────────────────────
# app.py – מיזוג טלפונים 💎   (2025-08-03)
# ───────────────────────────────────────────────
from __future__ import annotations

# 1) IMPORTS & CONFIG
import os, re, time, logging, tempfile, secrets, requests, gc
from io import BytesIO
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from logic import (
    NAME_COL, PHONE_COL, COUNT_COL, SIDE_COL, GROUP_COL,
    MIN_SCORE_DISPLAY, MAX_DISPLAYED, AUTO_SELECT_TH,
    load_excel, to_buf, format_phone, normalize,
    compute_best_scores, full_score, is_user_authorized,
)

# Load environment variables (.env) from project root or src/
ENV_PATH = (Path(__file__).resolve().parent.parent / ".env")
if not ENV_PATH.exists():
    ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(ENV_PATH, override=False)

PAGE_TITLE = "מיזוג טלפונים 💎"
CODE_TTL_SECONDS = 300
MAX_AUTH_ATTEMPTS = 5  # הוספה מהקובץ השני
DEV_MODE   = os.getenv("DEV_MODE", "0") == "1"
GREEN_ID   = os.getenv("GREEN_API_ID") or os.getenv("GREEN_ID")
GREEN_TOK  = os.getenv("GREEN_API_TOKEN") or os.getenv("GREEN_TOKEN")
PHONE_RE   = re.compile(r"^0\d{9}$")
PHONE_PATTERN = PHONE_RE  # alias מהקובץ השני

logging.basicConfig(level=logging.INFO)
logging.info("GREEN creds present? ID=%s TOKEN=%s", bool(GREEN_ID), bool(GREEN_TOK))

st.set_page_config(page_title=PAGE_TITLE, layout="wide")

# 2) HELPERS & IO
TMP_ROOT = Path(tempfile.gettempdir()) / "merge_app"
TMP_ROOT.mkdir(exist_ok=True)

def _user_root() -> Path:
    """Temporary folder per-user by phone."""
    root = TMP_ROOT / st.session_state.get("phone", "anon")
    root.mkdir(exist_ok=True)
    return root

def save_tmp(uploaded, sub: str, fname: str) -> Path:
    """Save uploaded file to tmp and return path."""
    path = _user_root() / sub / fname
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(uploaded.getbuffer())
    return path

@st.cache_data(show_spinner=False)
def read_table(path: str) -> pd.DataFrame:
    """Read Excel/CSV and normalize via logic.load_excel."""
    with open(path, "rb") as f:
        df = load_excel(f)
    try:
        df[PHONE_COL] = df[PHONE_COL].astype("string[pyarrow]")
    except Exception:
        pass
    return df

# Utility to find assets (e.g., Joni.png)
def find_up(start: Path, subdir: str, fname: str) -> Optional[Path]:
    """Search for subdir/fname from start upwards."""
    for base in (start, *start.parents):
        fp = base / subdir / fname
        if fp.is_file():
            return fp
    return None

# Session-state wrappers
def get_contacts_df() -> pd.DataFrame:
    """Load contacts DataFrame or stop if not uploaded."""
    p = st.session_state.get("contacts_path")
    if not p:
        st.error("לא הועלה קובץ אנשי קשר."); st.stop()
    return read_table(p)

def get_guests_df() -> pd.DataFrame:
    """Load guests DataFrame or stop if not uploaded."""
    p = st.session_state.get("guests_path")
    if not p:
        st.error("לא הועלה קובץ מוזמנים."); st.stop()
    return read_table(p)

def persist_guests(df: pd.DataFrame) -> None:
    """Save guests DataFrame back to file and clear cache."""
    buf = to_buf(df)
    Path(st.session_state["guests_path"]).write_bytes(buf.getvalue())
    st.cache_data.clear()

# Utility functions
def normalize_phone_basic(p: str) -> Optional[str]:
    d = re.sub(r"\D", "", p or "")
    return d if PHONE_RE.match(d) else None

def send_code(phone: str, code: str):
    """Send OTP via GREEN-API or log in DEV mode."""
    chat = ("972" + phone[1:] if phone.startswith("0") else phone) + "@c.us"
    if DEV_MODE and not (GREEN_ID and GREEN_TOK):
        logging.info("[DEV] OTP %s → %s", code, chat)
        return
    if not (GREEN_ID and GREEN_TOK):
        raise RuntimeError("GREEN API creds missing")
    url = f"https://api.green-api.com/waInstance{GREEN_ID}/sendMessage/{GREEN_TOK}"
    requests.post(url, json={"chatId": chat, "message": f"קוד האימות שלך: {code}"}, timeout=10)

def force_rerun():
    """Utility function for forcing rerun - מהקובץ השני"""
    st.rerun()

# 3) CSS INJECTION & LOGIN CSS

def inject_css() -> None:
    """Inject external CSS from styles/ directory."""
    base = Path(__file__).resolve().parent.parent / "styles"
    for fname in ("style.css",):
        css_path = base / fname
        if css_path.is_file():
            st.markdown(f"<style>{css_path.read_text('utf-8')}</style>", unsafe_allow_html=True)

def load_login_css() -> None:
    """Inject login page CSS - שילוב משני הקבצים עם השיפורים מהקובץ השני"""
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
    
    /* הסתרת מספר תווים ושורת עזרה */
    .stTextInput > label > div[data-testid="InputInstructions"] {
      display: none!important;
    }
    .stTextInput > div > div > div[data-testid="InputInstructions"] {
      display: none!important;
    }
    div[data-testid="InputInstructions"] {
      display: none!important;
    }
    
    /* רכוז הכל */
    .stMarkdown, .stTextInput, .stButton {
      text-align: center!important;
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
    
    /* מקלדת מספרים למובייל */
    input[data-testid*="phone"], input[data-testid*="code"] {
      inputmode: numeric !important;
      pattern: [0-9]* !important;
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
    
    .stTextInput {
      border: none!important;
      background: transparent!important;
      box-shadow: none!important;
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
    
    /* הסתרת קוביות לבנות וקווים */
    .element-container[data-testid] {
      background: transparent!important;
      border: none!important;
      box-shadow: none!important;
    }
    
    /* הודעות הצלחה וכשלון - CSS חזק יותר */
    .stAlert, .stSuccess, .stError, .stWarning, 
    div[data-testid="stAlert"], div[data-testid="stSuccess"], 
    div[data-testid="stError"], div[data-testid="stWarning"] {
      max-width: 350px!important;
      margin: 10px auto!important;
      text-align: center!important;
      display: flex!important;
      justify-content: center!important;
      width: 350px!important;
    }
    
    .stAlert > div, .stSuccess > div, .stError > div, .stWarning > div,
    div[data-testid="stAlert"] > div, div[data-testid="stSuccess"] > div,
    div[data-testid="stError"] > div, div[data-testid="stWarning"] > div {
      font-size: 14px!important;
      padding: 8px 16px!important;
      border-radius: 8px!important;
      text-align: center!important;
      max-width: 350px!important;
      width: 100%!important;
      margin: 0 auto!important;
    }
    
    /* CSS ספציפי מאוד להודעת הצלחה */
    .main .block-container .stSuccess {
      max-width: 350px!important;
      width: 350px!important;
      margin: 10px auto!important;
    }
    
    .main .block-container .stSuccess > div {
      max-width: 350px!important;
      width: 100%!important;
      text-align: center!important;
    }
    """
    
    st.markdown(f"<style>{login_css}</style>", unsafe_allow_html=True)

def load_file_uploader_css():
    """CSS מותאם לתיבות העלאת קבצים - נקיות ומסודרות - מהקובץ השני"""
    file_css = """
    /* ========================================
       עיצוב תיבות העלאת קבצים - גרסה נקייה
       ======================================== */
    
    /* איפוס כללי */
    div[data-testid="stFileUploader"] {
        margin: 15px 0 !important;
        padding: 0 !important;
    }
    
    /* הסתרת הlabel הראשי */
    div[data-testid="stFileUploader"] > label {
        display: none !important;
    }
    
    /* איפוס האזור החיצוני */
    div[data-testid="stFileUploader"] > div {
        margin: 0 !important;
        padding: 0 !important;
        border: none !important;
        background: transparent !important;
    }
    
    /* עיצוב אזור הdrop zone */
    section[data-testid="stFileUploadDropzone"] {
        border: 2px dashed #dee2e6 !important;
        border-radius: 12px !important;
        background: white !important;
        padding: 20px 15px !important;
        text-align: center !important;
        transition: all 0.3s ease !important;
        margin: 0 !important;
        height: auto !important;
        min-height: 80px !important;
    }
    
    /* הוברר על אזור הdrop */
    section[data-testid="stFileUploadDropzone"]:hover {
        border-color: #4A90E2 !important;
        background: #f8f9fa !important;
        box-shadow: 0 2px 8px rgba(74,144,226,0.15) !important;
    }
    
    /* מיכל ההוראות */
    div[data-testid="stFileDropzoneInstructions"] {
        margin: 0 !important;
        padding: 0 !important;
        display: flex !important;
        flex-direction: column !important;
        align-items: center !important;
        gap: 8px !important;
    }
    
    div[data-testid="stFileDropzoneInstructions"] > div {
        margin: 0 !important;
        padding: 0 !important;
        display: flex !important;
        flex-direction: column !important;
        align-items: center !important;
        gap: 4px !important;
    }
    
    /* הטקסט המרכזי - החלפה */
    div[data-testid="stFileDropzoneInstructions"] > div > span {
        visibility: hidden !important;
        position: absolute !important;
    }
    
    div[data-testid="stFileDropzoneInstructions"] > div > span::before {
        content: "📄 לחץ כאן או גרור קובץ Excel" !important;
        visibility: visible !important;
        position: relative !important;
        color: #6c757d !important;
        font-size: 13px !important;
    }
    
    /* הטקסט התחתון - החלפה */
    div[data-testid="stFileDropzoneInstructions"] > div > small {
        visibility: hidden !important;
        position: absolute !important;
    }
    
    div[data-testid="stFileDropzoneInstructions"] > div > small::before {
        content: "xlsx, xls, csv" !important;
        visibility: visible !important;
        position: relative !important;
        color: #adb5bd !important;
        font-size: 11px !important;
    }
    
    /* הכפתור Browse files */
    section[data-testid="stFileUploadDropzone"] button[data-testid="baseButton-secondary"] {
        background: #f8f9fa !important;
        border: 1px solid #ced4da !important;
        border-radius: 6px !important;
        padding: 6px 12px !important;
        font-size: 11px !important;
        color: transparent !important;
        cursor: pointer !important;
        transition: all 0.2s ease !important;
        margin-top: 8px !important;
        position: relative !important;
        height: 28px !important;
        min-height: 28px !important;
    }
    
    /* הוברר על הכפתור */
    section[data-testid="stFileUploadDropzone"] button[data-testid="baseButton-secondary"]:hover {
        background: #e9ecef !important;
        transform: translateY(-1px) !important;
        border-color: #4A90E2 !important;
    }
    
    /* הטקסט בכפתור */
    section[data-testid="stFileUploadDropzone"] button[data-testid="baseButton-secondary"]::after {
        content: "🗂️ עיון בקבצים" !important;
        color: #495057 !important;
        position: absolute !important;
        top: 50% !important;
        left: 50% !important;
        transform: translate(-50%, -50%) !important;
        font-size: 11px !important;
        white-space: nowrap !important;
    }
    
    /* תצוגת הקובץ שנבחר */
    div[data-testid="stFileUploader"] span[title] {
        background: #d1ecf1 !important;
        border: 1px solid #bee5eb !important;
        border-radius: 6px !important;
        padding: 4px 8px !important;
        font-size: 11px !important;
        font-weight: 600 !important;
        color: #0c5460 !important;
        display: inline-block !important;
        margin-top: 8px !important;
        max-width: 95% !important;
        word-break: break-all !important;
    }
    """

    st.markdown(f"<style>{file_css}</style>", unsafe_allow_html=True)

inject_css()

# 4) CONTACTS GUIDE

if "show_contacts_guide" not in st.session_state:
    st.session_state.show_contacts_guide = False

def render_contacts_guide() -> None:
    """Display instructions to download contacts file."""
    col_text, col_img = st.columns([1,2])
    with col_text:
        st.header("📝 מדריך הורדת קובץ אנשי קשר")
        st.markdown(
            """
1. התחברו מהמחשב (לא מהטלפון).
2. התקינו את התוסף **Joni**.
3. פתחו **WhatsApp Web**.
4. לחצו על סמל J → **אנשי קשר** → **שמירה לקובץ אקסל**.
5. הקובץ יישמר.
""", unsafe_allow_html=True)
        if st.button("✖️ סגור מדריך"):
            st.session_state.show_contacts_guide = False
            st.rerun()
    with col_img:
        img = find_up(Path(__file__).resolve().parent, "assets", "Joni.png")
        if img: st.image(str(img), width=400)
        else: st.warning("⚠️ אנא הוסף assets/Joni.png")

# 5) AUTHENTICATION FLOW - שילוב של שני הקבצים עם השיפורים מהקובץ השני

def auth_flow() -> bool:
    """Handle phone entry, OTP send & verify, gating by is_user_authorized."""
    # ensure authentication state initialized
    if "auth_state" not in st.session_state:
        st.session_state["auth_state"] = "phone"
    if st.session_state.get("auth_ok"): 
        return True
    
    load_login_css()
    
    # track current step: 'phone' or 'code'
    state = st.session_state["auth_state"]
    
    # כותרות מהקובץ השני - עם אייקונים ועיצוב משופר
    icon = "💬" if state == "phone" else "🔐"
    subtitle = "התחבר באמצעות מספר הטלפון שלך" if state == "phone" else "הכנס את הקוד שנשלח אליך"
    label = "מספר טלפון" if state == "phone" else "קוד אימות"

    # אייקון עגול
    st.markdown(f'<div class="auth-icon">{icon}</div>', unsafe_allow_html=True)
    st.markdown('<div class="auth-title">מערכת שילוב רשימות</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="auth-subtitle">{subtitle}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="phone-label">{label}</div>', unsafe_allow_html=True)
    
    if state == "phone":
        phone = st.text_input("מספר טלפון", placeholder="05X-XXXXXXX",
                              max_chars=10, key="phone_input", label_visibility="hidden")
        
        # הוספת מקלדת מספרים למובייל - מהקובץ השני
        st.markdown("""
        <script>
        document.querySelector('input[data-testid*="phone"]').inputMode = 'numeric';
        document.querySelector('input[data-testid*="phone"]').pattern = '[0-9]*';
        </script>
        """, unsafe_allow_html=True)
        
        if st.button("שלח קוד אימות 💬"):
            p = normalize_phone_basic(phone)
            if not p:
                st.error("מספר לא תקין.")
                return False
            # אימות משתמשים - מהקובץ הראשון
            if not is_user_authorized(p):
                st.error("🚫 מספר לא מורשה")
                return False
            code = "".join(secrets.choice("0123456789") for _ in range(4))
            st.session_state.update({
                "phone": p, "auth_code": code,
                "code_ts": time.time(), "auth_state": "code"
            })
            send_code(p, code)
            st.success("קוד נשלח!")
            st.rerun()
            
    else:  # state == "code"
        entry = st.text_input("קוד אימות", placeholder="הכנס קוד בן 4 ספרות", 
                             max_chars=4, key="code_input", label_visibility="hidden")
        
        # הוספת מקלדת מספרים למובייל - מהקובץ השני
        st.markdown("""
        <script>
        setTimeout(function() {
            var inputs = document.querySelectorAll('input');
            inputs.forEach(function(input) {
                if (input.placeholder && input.placeholder.includes('קוד')) {
                    input.inputMode = 'numeric';
                    input.pattern = '[0-9]*';
                }
            });
        }, 100);
        </script>
        """, unsafe_allow_html=True)
        
        expired = (time.time() - st.session_state.code_ts) > CODE_TTL_SECONDS
        if expired: 
            st.warning("הקוד פג תוקף")
            
        if st.button("אמת 🔓"):
            if expired:
                st.error("הקוד פג תוקף")
                return False
            elif entry == st.session_state.auth_code:
                st.session_state.auth_ok = True
                # הודעת הצלחה מהקובץ השני
                st.markdown('<div style="max-width: 350px; margin: 10px auto; padding: 8px 16px; background: #d4edda; border: 1px solid #c3e6cb; border-radius: 8px; text-align: center; font-size: 14px; color: #155724;">✅ התחברת בהצלחה!</div>', unsafe_allow_html=True)
                time.sleep(1)
                st.rerun()
            else:
                # הגבלת ניסיונות - מהקובץ השני
                att = st.session_state.get("auth_attempts", 0) + 1
                st.session_state.auth_attempts = att
                if att >= MAX_AUTH_ATTEMPTS:
                    st.error("נחרגת ממספר הניסיונות המותר")
                    # איפוס חזרה לשלב הטלפון
                    st.session_state.auth_state = "phone"
                    st.rerun()
                else:
                    st.error(f"קוד שגוי ({MAX_AUTH_ATTEMPTS - att} ניסיונות נותרו)")
    
    return False

# MAIN APPLICATION

# אתחול אינדקס ברירת מחדל אם אין
if "idx" not in st.session_state:
    st.session_state["idx"] = 0

if not auth_flow(): 
    st.stop()

# טעינת CSS לתיבות העלאת קבצים
load_file_uploader_css()

if st.session_state.show_contacts_guide:
    st.title(PAGE_TITLE)
    render_contacts_guide()
    st.stop()

st.title(PAGE_TITLE)

# FILE UPLOAD - שילוב של שני הגישות
if "upload_confirmed" not in st.session_state:
    st.session_state.upload_confirmed = False

if not st.session_state.upload_confirmed:
    with st.sidebar:
        st.subheader("📂 העלאת קבצים")
        if st.button("📖 מדריך להורדת הקובץ", key="contacts_guide_btn"):
            st.session_state.show_contacts_guide = True
            st.rerun()
        
        # כותרות מפורטות מהקובץ השני
        st.markdown("### 👥 קובץ אנשי קשר")
        contacts_file = st.file_uploader(
            "קובץ אנשי קשר", 
            type=["xlsx", "xls", "csv"], 
            key="contacts_uploader",
            label_visibility="collapsed"
        )
        
        st.markdown("### 🎉 קובץ מוזמנים")
        guests_file = st.file_uploader(
            "קובץ מוזמנים", 
            type=["xlsx", "xls", "csv"], 
            key="guests_uploader",
            label_visibility="collapsed"
        )
        
        if st.button("✅ אשר קבצים", disabled=not (contacts_file and guests_file), use_container_width=True):
            with st.spinner("טוען קבצים…"):
                # שמירה לקבצים זמניים - מהקובץ הראשון
                st.session_state["contacts_path"] = str(save_tmp(contacts_file, "contacts", contacts_file.name))
                st.session_state["guests_path"] = str(save_tmp(guests_file, "guests", guests_file.name))
                
                # טעינה לזיכרון גם - מהקובץ השני
                st.session_state.contacts = read_table(st.session_state.contacts_path)
                st.session_state.guests = read_table(st.session_state.guests_path)
                
                # חישוב ציונים
                st.session_state.guests["best_score"] = compute_best_scores(
                    st.session_state.guests, st.session_state.contacts
                )
                
                # שמירה חזרה לקובץ
                persist_guests(st.session_state.guests)
                
            st.session_state.upload_confirmed = True
            st.rerun()
    st.stop()

# SIDEBAR FILTERS - שילוב של שני הגישות
with st.sidebar:
    st.checkbox("רק חסרי מספר", key="filter_no", value=False, 
                on_change=lambda: st.session_state.update(idx=0))
    
    # קבלת הנתונים - תמיכה בשתי הגישות
    if "guests" in st.session_state:
        # גישה מהקובץ השני - נתונים בזיכרון
        df = st.session_state.guests.copy()
        contacts = st.session_state.contacts.copy()
    else:
        # גישה מהקובץ הראשון - נתונים מקבצים
        df = get_guests_df()
        contacts = get_contacts_df()
    
    # סינון לפי חסרי מספר
    if st.session_state.get("filter_no"):
        df = df[df[PHONE_COL].str.strip() == ""]
    
    # סינונים נוספים - מהקובץ הראשון
    all_sides = df[SIDE_COL].dropna().unique().tolist()
    all_groups = df[GROUP_COL].dropna().unique().tolist()
    
    # multiselect עם keys - מהקובץ השני
    selected_sides = st.multiselect("סנן לפי צד", options=all_sides, key="filter_sides")
    selected_groups = st.multiselect("סנן לפי קבוצה", options=all_groups, key="filter_groups")
    
    # החלת הסינונים
    if selected_sides:
        df = df[df[SIDE_COL].isin(selected_sides)]
    if selected_groups:
        df = df[df[GROUP_COL].isin(selected_groups)]
    
    # Progress bar משופר
    filtered_total = len(df)
    idx = st.session_state.get("idx", 0)
    idx = min(idx, filtered_total)  # וידוא שהאינדקס לא חורג
    
    st.markdown(f"**{idx}/{filtered_total} הושלמו**")
    st.progress(idx / filtered_total if filtered_total else 0)
    
    # הורדת קובץ - תיקון הפונקציה
    download_data = to_buf(df)
    st.download_button(
        "💾 הורד Excel",
        data=download_data,
        file_name="רשימת_מסוננים.xlsx",
        use_container_width=True,
    )

# סינון וסידור הנתונים
filtered_df = df.copy()
# סידור לפי ציון ושם - מהקובץ השני
filtered_df = filtered_df.sort_values(["best_score", NAME_COL], ascending=[False, True])

# MAIN LOOP - שילוב מתקדם של שני הקבצים
if st.session_state.idx >= len(filtered_df):
    st.success("🎉 סיימנו!")
    # הורדה סופית - תיקון הפונקציה
    final_data = st.session_state.guests if "guests" in st.session_state else get_guests_df()
    final_download = to_buf(final_data)
    st.download_button(
        "⬇️ הורד תוצאה סופית", 
        data=final_download, 
        file_name="תוצאה_סופית.xlsx", 
        use_container_width=True
    )
    st.stop()

cur = filtered_df.iloc[st.session_state.idx]

# תצוגה משופרת של המוזמן הנוכחי - מהקובץ השני
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

# חישוב התאמות - שילוב של שני הקבצים
matches = contacts.copy()
matches["score"] = matches["norm_name"].apply(lambda c: full_score(cur.norm_name, c))

# אלגוריתם חכם לבחירת מועמדים - מהקובץ השני עם שיפורים
candidates = matches[matches["score"] >= 90].sort_values(["score", NAME_COL], ascending=[False, True]).head(3)
if candidates.empty:
    # אם אין התאמות טובות, קח את הטובות ביותר
    candidates = matches.sort_values(["score", NAME_COL], ascending=[False, True]).head(MAX_DISPLAYED)

# אופציות בחירה - שילוב משני הקבצים
options = ["❌ ללא התאמה"] + [
    f"{int(r.score)}% | {r[NAME_COL]} | {format_phone(r[PHONE_COL])}" 
    for _, r in candidates.iterrows()
] + ["➕ הוסף ידני", "🔍 חפש אנשי קשר"]

# בחירה אוטומטית חכמה - מהקובץ השני
auto_select_index = 1 if not candidates.empty and candidates.iloc[0].score >= AUTO_SELECT_TH else 0

choice = st.radio(
    "בחר התאמה:", 
    options,
    index=auto_select_index,
    label_visibility="collapsed"
)

# טיפול בבחירות מיוחדות - שילוב משני הקבצים
manual_phone = ""
search_phone = ""

if choice == "➕ הוסף ידני":
    manual_phone = st.text_input("טלפון:", placeholder="05XXXXXXXX")
    
elif choice == "🔍 חפש אנשי קשר":
    query = st.text_input("חיפוש:", placeholder="שם/מספר")
    if len(query) >= 2:
        # חיפוש מתקדם - מהקובץ הראשון
        search_results = contacts[
            contacts.norm_name.str.contains(normalize(query), na=False) |
            contacts[PHONE_COL].str.contains(query, na=False)
        ].head(6)
        
        if not search_results.empty:
            search_options = [
                f"{r[NAME_COL]} | {format_phone(r[PHONE_COL])}" 
                for _, r in search_results.iterrows()
            ]
            selected_result = st.selectbox("בחר איש קשר", search_options)
            if selected_result:
                search_phone = selected_result.split("|")[-1].strip()

# כפתורי ניווט משופרים - מהקובץ השני
col1, col2 = st.columns(2)

with col1:
    if st.button("⬅️ חזרה", disabled=(st.session_state.idx == 0), use_container_width=True):
        st.session_state.idx = max(0, st.session_state.idx - 1)
        st.rerun()

with col2:
    if st.button("✅ אישור", use_container_width=True):
        # קביעת הערך הנבחר
        val = None
        
        if manual_phone:
            val = normalize_phone_basic(manual_phone)
        elif search_phone:
            val = search_phone
        elif choice.startswith("❌"):
            val = ""
        else:
            # נבחרה אפשרות מהרשימה
            val = choice.split("|")[-1].strip()
        
        if val is not None:
            # שמירה - תמיכה בשתי הגישות
            formatted_phone = format_phone(val) if val else ""
            
            if "guests" in st.session_state:
                # עדכון בזיכרון - מהקובץ השני
                st.session_state.guests.at[cur.name, PHONE_COL] = formatted_phone
            else:
                # עדכון בקובץ - מהקובץ הראשון
                g_df = get_guests_df()
                g_df.at[cur.name, PHONE_COL] = formatted_phone
                persist_guests(g_df)
            
            # מעבר להבא
            st.session_state.idx += 1
            st.rerun()
        else:
            st.warning("אין ערך תקין לשמירה")

# ╰──────────────────────────────────────────────╯