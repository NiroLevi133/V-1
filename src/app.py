import time, secrets, re
from datetime import datetime
from typing import Optional, Tuple
import base64

import pandas as pd
import streamlit as st
import requests

from logic import (
    NAME_COL, PHONE_COL, COUNT_COL, SIDE_COL, GROUP_COL,
    AUTO_SELECT_TH, load_excel, to_buf,
    format_phone, normalize, compute_best_scores, full_score,
)

PAGE_TITLE = " מיזוג טלפונים 💎"
CODE_TTL_SECONDS  = 300
MAX_AUTH_ATTEMPTS = 5
PHONE_PATTERN     = re.compile(r"^0\d{9}$")

class AppConfig:
    def __init__(self):
        self.green_id = None
        self.green_token = None
        self._load_credentials()
    
    def _load_credentials(self):
        import os
        self.green_id = os.getenv("GREEN_API_ID")
        self.green_token = os.getenv("GREEN_API_TOKEN")
        
        if self.green_id and self.green_token:
            print("✅ נתוני GREEN-API נטענו בהצלחה")
        else:
            print("❌ לא נמצאו נתוני GREEN-API")
    
    def is_valid(self):
        if not self.green_id or not self.green_token:
            return False
        if not self.green_id.isdigit() or len(self.green_id) < 10:
            return False
        if len(self.green_token) < 20:
            return False
        return True

config = AppConfig()
    


st.set_page_config(page_title=PAGE_TITLE, layout="wide")
print("🔄 TEST VERSION 1.0 - 05/08/2025")

def load_main_css():
    """טוען את ה-CSS הראשי של האפליקציה"""
    import os
    
    # רשימת נתיבים אפשריים
    possible_paths = [
        "../styles/style.css",      # נתיב מקורי (מקומי)
        "styles/style.css",         # אם styles בתיקיה הנוכחית
        "/app/styles/style.css",    # נתיב מלא ב-container
        "./styles/style.css",       # נתיב יחסי אחר
    ]
    
    for css_path in possible_paths:
        try:
            if os.path.exists(css_path):
                with open(css_path, encoding="utf-8") as f:
                    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
                    print(f"✅ CSS נטען בהצלחה מ: {css_path}")
                    return
        except Exception as e:
            print(f"⚠️ לא ניתן לטעון CSS מ-{css_path}: {e}")
            continue
    
    print("⚠️ לא נמצא קובץ CSS - ממשיך בלי עיצוב")

def load_radio_css():
    """טוען CSS מעוצב לרדיו כפתורים קטנים ופשוטים ללא מסגרות"""
    radio_css = """
    /* ========================================
       עיצוב Radio Buttons פשוט וקטן
       ======================================== */
    
    /* מיכל הרדיו הראשי - הסרת המסגרת והקטנה */
    div[data-testid="stRadio"] {
        background: transparent !important;
        border: none !important;
        border-radius: 0 !important;
        padding: 10px 0 !important;
        box-shadow: none !important;
        margin: 10px 0 !important;
    }
    
    /* הסתרת הכותרת */
    div[data-testid="stRadio"] > label {
        display: none !important;
    }
    
    /* מיכל האופציות - קטן יותר */
    div[data-testid="stRadio"] > div {
        display: flex;
        flex-direction: column;
        gap: 4px !important;
    }
    
    /* עיצוב כל אופציה - קטנה ופשוטה */
    div[data-testid="stRadio"] label {
        display: flex !important;
        align-items: center !important;
        padding: 8px 12px !important;
        border: 1px solid #e9ecef !important;
        border-radius: 6px !important;
        cursor: pointer !important;
        transition: all 0.15s ease !important;
        background: #fafafa !important;
        margin: 0 !important;
        font-size: 13px !important;
        font-weight: 500 !important;
        color: #495057 !important;
        min-height: 36px !important;
        max-height: 36px !important;
    }
    
    /* הוברר על אופציה */
    div[data-testid="stRadio"] label:hover {
        background: #f8f9fa !important;
        border-color: #4A90E2 !important;
        transform: none !important;
        box-shadow: 0 1px 3px rgba(74,144,226,0.1) !important;
    }
    
    /* אופציה נבחרת */
    div[data-testid="stRadio"] label:has(input:checked) {
        background: #e3f2fd !important;
        border-color: #4A90E2 !important;
        color: #1976d2 !important;
        font-weight: 600 !important;
        box-shadow: 0 1px 4px rgba(74,144,226,0.15) !important;
    }
    
    /* התאמה מושלמת - 100% - הדגשה בירוק קטנה */
    div[data-testid="stRadio"] label[title*="התאמה מושלמת"] {
        background: #f1f8e9 !important;
        border: 1px solid #4caf50 !important;
        color: #2e7d32 !important;
        font-weight: 600 !important;
        position: relative !important;
    }
    
    div[data-testid="stRadio"] label[title*="התאמה מושלמת"]:hover {
        background: #e8f5e8 !important;
        border-color: #388e3c !important;
        box-shadow: 0 1px 4px rgba(76,175,80,0.2) !important;
    }
    
    div[data-testid="stRadio"] label[title*="התאמה מושלמת"]:has(input:checked) {
        background: #dcedc8 !important;
        border-color: #2e7d32 !important;
        box-shadow: 0 1px 6px rgba(76,175,80,0.25) !important;
    }
    
    /* סמן מושלמות קטן */
    div[data-testid="stRadio"] label[title*="התאמה מושלמת"]::after {
        content: "🎯";
        position: absolute;
        right: 8px;
        font-size: 12px;
    }
    
    /* עיצוב הרדיו button עצמו - קטן יותר */
    div[data-testid="stRadio"] input[type="radio"] {
        width: 16px !important;
        height: 16px !important;
        margin-left: 8px !important;
        margin-right: 0 !important;
        accent-color: #4A90E2 !important;
    }
    
    /* עיצוב מיוחד לאופציות מיוחדות - קטן יותר */
    div[data-testid="stRadio"] label:has([value*="ללא התאמה"]) {
        background: #fffbf0 !important;
        border-color: #ffc107 !important;
        color: #856404 !important;
    }
    
    div[data-testid="stRadio"] label:has([value*="הוסף ידני"]) {
        background: #f0f9ff !important;
        border-color: #17a2b8 !important;
        color: #0c5460 !important;
    }
    
    div[data-testid="stRadio"] label:has([value*="חפש אנשי קשר"]) {
        background: #f8f9fa !important;
        border-color: #6c757d !important;
        color: #495057 !important;
    }
    
    /* Responsive למובייל */
    @media (max-width: 768px) {
        div[data-testid="stRadio"] label {
            padding: 6px 10px !important;
            font-size: 12px !important;
            min-height: 32px !important;
            max-height: 32px !important;
        }
        
        div[data-testid="stRadio"] input[type="radio"] {
            width: 14px !important;
            height: 14px !important;
            margin-left: 6px !important;
        }
    }
    """
    
    st.markdown(f"<style>{radio_css}</style>", unsafe_allow_html=True)

def normalize_phone_basic(p: str) -> Optional[str]:
    """נרמול בסיסי של מספר טלפון"""
    d = re.sub(r"\D", "", p or "")
    return d if PHONE_PATTERN.match(d) else None

def send_code(phone: str, code: str) -> bool:
    """פונקציה משופרת לשליחת קוד אימות"""
    
    # בדיקה אם יש לנו נתוני התחברות תקינים
    if not config.is_valid():
        st.error("🚫 שגיאה בהגדרות המערכת")
        return False  # ← 8 רווחים (2 רמות הזחה)
    
    try:  # ← 4 רווחים (1 רמה)
        # הכנת מספר הטלפון
        if phone.startswith("0"):  # ← 8 רווחים (2 רמות)
            chat = "972" + phone[1:] + "@c.us"  # ← 12 רווחים (3 רמות)
        else:
            chat = phone + "@c.us"
        
        # שליחת הבקשה
        response = requests.post(url, json=payload, timeout=10)
        
        if response.status_code == 200:  # ← 8 רווחים
            return True  # ← 12 רווחים
        else:
            return False  # ← 12 רווחים
            
    except Exception as e:  # ← 4 רווחים
        st.error("שגיאה בשליחת הודעה")
        return False  # ← 8 רווחים
            
    except Exception as e:  # תפיסת שגיאות לא צפויות
        print(f"❌ שגיאה בשליחת הודעה: {e}")
        st.error("שגיאה בשליחת הודעה - נסה שוב")
        return False

def force_rerun():
    """כפיית ריענון של האפליקציה"""
    st.rerun()

from pathlib import Path

def find_up(start_path, *path_parts):
    """מחפש קובץ במסלול"""
    current = Path(start_path)
    for parent in [current] + list(current.parents):
        candidate = parent.joinpath(*path_parts)
        if candidate.exists():
            return candidate
    return None

def show_download_guide():
    """מציג מדריך הורדת אנשי קשר בחלונית מתקפלת"""
    if st.session_state.get("show_guide", False):
        with st.expander("📱 מדריך הורדת אנשי קשר", expanded=True):
            col_text, col_img = st.columns([1, 2])
            with col_text:
                st.markdown("""
                <div style="
                    background: #ffffff;
                    border-radius: 16px;
                    padding: 20px;
                    box-shadow: 0 4px 20px rgba(0,0,0,0.1);
                    margin: 20px 0;
                    border-left: 5px solid #4A90E2;
                ">
                    <h3 style="color: #4A90E2; margin-bottom: 16px;">📱 איך להוריד אנשי קשר?</h3>
                    
                    <div style="margin-bottom: 12px;">
                        <strong>1. התחברו מהמחשב</strong> (לא מהטלפון)
                    </div>
                    
                    <div style="margin-bottom: 12px;">
                        <strong>2. התקינו את התוסף Joni</strong>
                    </div>
                    
                    <div style="margin-bottom: 12px;">
                        <strong>3. פתחו WhatsApp Web</strong>
                    </div>
                    
                    <div style="margin-bottom: 12px;">
                        <strong>4. לחצו על סמל J → אנשי קשר → שמירה לקובץ אקסל</strong>
                    </div>
                    
                    <div style="background: #f0f8ff; padding: 12px; border-radius: 8px; margin-top: 16px;">
                        <strong>💡 טיפ:</strong> הקובץ יישמר אוטומטית
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            with col_img:
                img = find_up(Path(__file__).resolve().parent, "assets", "Joni.png")
                if img: 
                    st.image(str(img), width=400)
                else: 
                    st.info("🖼️ תמונת הדרכה תוצג כאן")
            
            if st.button("❌ סגור מדריך", key="close_guide"):
                st.session_state.show_guide = False
                force_rerun()

def load_login_css():
    """טוען CSS למסך הכניסה"""
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
    """CSS מותאם לתיבות העלאת קבצים - נקיות ומסודרות"""
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
    
    /* עיצוב כפתור העזרה */
    .help-button {
        background: #f8f9fa !important;
        border: 1px solid #dee2e6 !important;
        border-radius: 8px !important;
        padding: 8px 12px !important;
        font-size: 12px !important;
        color: #6c757d !important;
        cursor: pointer !important;
        transition: all 0.2s ease !important;
        margin-top: 10px !important;
        width: 100% !important;
    }
    
    .help-button:hover {
        background: #e9ecef !important;
        border-color: #4A90E2 !important;
        color: #4A90E2 !important;
    }
    """
    
    st.markdown(f"<style>{file_css}</style>", unsafe_allow_html=True)

def auth_flow() -> bool:
    """זרימת אימות המשתמש - טלפון וקוד OTP"""
    if st.session_state.get("auth_ok"):
        return True

    load_login_css()
    state = st.session_state.setdefault("auth_state", "phone")

    # כותרות ללא wrapper - עכשיו הכל בתוך המסגרת הלבנה
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
        
        # הוספת מקלדת מספרים למובייל
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
            else:
                code = "".join(secrets.choice("0123456789") for _ in range(4))
                st.session_state.update({
                    "auth_code": code, "phone": p,
                    "code_ts": time.time(), "auth_state": "code"})
                if not send_code(p, code):
                    st.error("לא ניתן לשלוח קוד אימות - בדוק את החיבור")
                else:
                    st.success("הקוד נשלח."); force_rerun()
                

    else:  # state == "code"
        entry = st.text_input("קוד אימות", placeholder="הכנס קוד בן 4 ספרות", max_chars=4, label_visibility="hidden")
        
        # הוספת מקלדת מספרים למובייל
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
            elif entry == st.session_state.auth_code:
                st.session_state.auth_ok = True
                # הודעת הצלחה קטנה וממורכזת
                st.markdown('<div style="max-width: 350px; margin: 10px auto; padding: 8px 16px; background: #d4edda; border: 1px solid #c3e6cb; border-radius: 8px; text-align: center; font-size: 14px; color: #155724;">✅ התחברת בהצלחה!</div>', unsafe_allow_html=True)
                time.sleep(1)
                force_rerun()
            else:
                att = st.session_state.get("auth_attempts", 0) + 1
                st.session_state.auth_attempts = att
                if att >= MAX_AUTH_ATTEMPTS:
                    st.error("נחרגת ממספר הניסיונות המותר")
                    # איפוס חזרה לשלב הטלפון
                    st.session_state.auth_state = "phone"
                    force_rerun()
                else:
                    st.error(f"קוד שגוי ({MAX_AUTH_ATTEMPTS - att} ניסיונות נותרו)")

    return False

def create_radio_options(candidates: pd.DataFrame) -> list:
    """יוצר רשימת אופציות לרדיו כפתורים עם פורמט מיוחד"""
    options = ["❌ ללא התאמה"]
    
    # הוספת מועמדים
    for _, candidate in candidates.iterrows():
        name = candidate[NAME_COL]
        phone = format_phone(candidate[PHONE_COL])
        score = int(candidate["score"])
        
        # פורמט בסיסי
        option_text = f"{name} | {phone}"
        
        # הוספת title attribute להתאמה מושלמת
        if score == 100:
            options.append(f"🎯 {option_text}")
        else:
            options.append(option_text)
    
    # הוספת אופציות מיוחדות
    options.extend(["➕ הוסף ידני", "🔍 חפש אנשי קשר"])
    
    return options

def get_auto_select_index(candidates: pd.DataFrame, options: list) -> int:
    """מחזיר אינדקס לבחירה אוטומטית חכמה"""
    if candidates.empty:
        return 0
    
    best_score = candidates.iloc[0]["score"]
    if best_score >= AUTO_SELECT_TH:
        # מוצא את המיקום של ההתאמה הטובה ביותר ברשימה
        best_name = candidates.iloc[0][NAME_COL]
        for i, option in enumerate(options):
            if best_name in option and not option.startswith(("❌", "➕", "🔍")):
                return i
    
    return 0  # ברירת מחדל - ללא התאמה

def render_guest_profile(cur):
    """מציג פרופיל מוזמן מעוצב ויפה"""
    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 16px;
        padding: 24px;
        margin: 20px 0;
        box-shadow: 0 8px 32px rgba(102, 126, 234, 0.3);
        border: 1px solid rgba(255,255,255,0.2);
        text-align: center;
        color: white;
    ">
        <div style="font-size: 28px; font-weight: 700; margin-bottom: 16px; text-shadow: 0 2px 4px rgba(0,0,0,0.2);">
            🎯 {cur[NAME_COL]}
        </div>
        <div style="display: flex; justify-content: center; gap: 30px; flex-wrap: wrap; font-size: 16px;">
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 20px;">🧭</span>
                <strong>צד:</strong> {cur[SIDE_COL]}
            </div>
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 20px;">🧩</span>
                <strong>קבוצה:</strong> {cur[GROUP_COL]}
            </div>
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 20px;">👥</span>
                <strong>כמות:</strong> {cur[COUNT_COL]}
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_match_selection(cur, contacts_df: pd.DataFrame) -> str:
    # … חישוב התאמות …
    matches = contacts_df.copy()
    matches["score"] = matches["norm_name"].map(lambda c: full_score(cur.norm_name, c))

    # בחר מועמדים על פי התנאים החדשים
    best_score = matches["score"].max() if not matches.empty else 0

    if best_score >= 100:
        # אם יש מישהו עם התאמה מושלמת → רק מעל 90% ועד 3 מועמדים
        candidates = matches[matches["score"] >= 90]\
                        .sort_values(["score", NAME_COL], ascending=[False, True])\
                        .head(3)
    else:
        # אחרת → התאמות מעל 70% ועד 5 מועמדים
        candidates = matches[matches["score"] >= 70]\
                        .sort_values(["score", NAME_COL], ascending=[False, True])\
                        .head(5)


    # יצירת אופציות לרדיו
    options = create_radio_options(candidates)
    
    # טעינת CSS לרדיו
    load_radio_css()
    
    # בחירה אוטומטית
    auto_index = get_auto_select_index(candidates, options)
    
    # הצגת הרדיו כפתורים
    choice = st.radio(
        "בחר איש קשר מתאים:",
        options,
        index=auto_index,
        key=f"radio_choice_{st.session_state.get('idx', 0)}",
        label_visibility="collapsed"
    )
    
    return choice

def handle_manual_input() -> str:
    """טיפול בהזנת מספר ידנית"""
    st.markdown("#### 📱 הזנת מספר ידנית:")
    manual_phone = st.text_input(
        "מספר טלפון:", 
        placeholder="05XXXXXXXX",
        key=f"manual_input_{st.session_state.get('idx', 0)}"
    )
    if manual_phone and not normalize_phone_basic(manual_phone):
        st.error("❌ מספר טלפון לא תקין")
        return ""
    return manual_phone

def handle_contact_search(contacts_df: pd.DataFrame) -> str:
    """טיפול בחיפוש באנשי קשר"""
    st.markdown("#### 🔍 חיפוש באנשי קשר:")
    query = st.text_input(
        "חיפוש:", 
        placeholder="הקלד שם או מספר טלפון",
        key=f"search_query_{st.session_state.get('idx', 0)}"
    )
    
    if len(query) >= 2:
        # ביצוע החיפוש
        search_results = contacts_df[
            contacts_df.norm_name.str.contains(normalize(query), na=False) |
            contacts_df[PHONE_COL].str.contains(query, na=False)
        ].head(6)
        
        if not search_results.empty:
            st.markdown("**תוצאות חיפוש:**")
            search_options = ["בחר תוצאה..."] + [
                f"{r[NAME_COL]} | {format_phone(r[PHONE_COL])}" 
                for _, r in search_results.iterrows()
            ]
            selected_result = st.selectbox(
                "בחר איש קשר:", 
                search_options,
                key=f"search_result_{st.session_state.get('idx', 0)}"
            )
            if selected_result and selected_result != "בחר תוצאה...":
                return selected_result.split("|")[-1].strip()
        else:
            st.info("🔍 לא נמצאו תוצאות")
    elif query:
        st.info("הקלד לפחות 2 תווים לחיפוש")
    
    return ""

def extract_phone_from_choice(choice: str) -> str:
    """מחלץ מספר טלפון מבחירה"""
    if choice.startswith("❌"):
        return ""
    elif choice.startswith(("➕", "🔍")):
        return ""
    else:
        # הסרת אמוג'י והחלצת המספר
        clean_choice = choice.replace("🎯 ", "")
        return clean_choice.split("|")[-1].strip()

# טעינת CSS ראשי
load_main_css()

# בדיקת אימות
if not auth_flow():
    st.stop()

# טעינת CSS לתיבות העלאת קבצים
load_file_uploader_css()

st.title(PAGE_TITLE)

# הצגת המדריך רק אם נדרש
show_download_guide()

# שלב העלאת קבצים
if "upload_confirmed" not in st.session_state:
    st.session_state.upload_confirmed = False

if not st.session_state.upload_confirmed:
    with st.sidebar:
        st.markdown("## 📂 העלאת קבצים")
        
        # כותרת קובץ אנשי קשר עם כפתור עזרה
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown("### 👥 קובץ אנשי קשר")
        with col2:
            if st.button("❓ עזרה", key="help_contacts", help="איך להוריד קובץ אנשי קשר?"):
                st.session_state.show_guide = True
                force_rerun()
        
        contacts_file = st.file_uploader(
            "קובץ אנשי קשר", 
            type=["xlsx", "xls", "csv"], 
            key="contacts_uploader",
            label_visibility="collapsed"
        )
        
        # כותרת קובץ מוזמנים
        st.markdown("### 🎉 קובץ מוזמנים")
        guests_file = st.file_uploader(
            "קובץ מוזמנים", 
            type=["xlsx", "xls", "csv"], 
            key="guests_uploader",
            label_visibility="collapsed"
        )

        if st.button("✅ אשר קבצים", disabled=not (contacts_file and guests_file), use_container_width=True):
            with st.spinner("טוען קבצים…"):
                st.session_state.contacts = load_excel(contacts_file)
                st.session_state.guests   = load_excel(guests_file)
                st.session_state.guests["best_score"] = compute_best_scores(
                    st.session_state.guests, st.session_state.contacts
                )
            st.session_state.upload_confirmed = True
            force_rerun()

if not st.session_state.upload_confirmed:
    st.stop()

# Sidebar עם פילטרים וניהול
with st.sidebar:
    st.checkbox("רק חסרי מספר", key="filter_no", on_change=lambda: st.session_state.update(idx=0))

    # הכנת DataFrame מפוטר
    filtered_df = st.session_state.guests.copy()
    if st.session_state.get("filter_no"):
        filtered_df = filtered_df[filtered_df[PHONE_COL].str.strip() == ""]

    # פילטרים נוספים
    all_sides   = st.session_state.guests[SIDE_COL].dropna().unique().tolist()
    all_groups  = st.session_state.guests[GROUP_COL].dropna().unique().tolist()

    st.multiselect("סנן לפי צד", options=all_sides, key="filter_sides")
    st.multiselect("סנן לפי קבוצה", options=all_groups, key="filter_groups")

    # החלת פילטרים
    if st.session_state.get("filter_sides"):
        filtered_df = filtered_df[filtered_df[SIDE_COL].isin(st.session_state.filter_sides)]
    if st.session_state.get("filter_groups"):
        filtered_df = filtered_df[filtered_df[GROUP_COL].isin(st.session_state.filter_groups)]

    # התקדמות
    filtered_total = len(filtered_df)
    complete_idx   = st.session_state.get("idx", 0)
    complete_idx   = min(complete_idx, filtered_total)

    st.markdown(f"**{complete_idx}/{filtered_total} הושלמו**")
    st.progress(complete_idx / filtered_total if filtered_total else 0)

    # הורדת קובץ
    st.download_button(
        "💾 הורד Excel",
        data=to_buf(filtered_df),
        file_name="רשימת_מסוננים.xlsx",
        use_container_width=True,
    )

# מיון והכנת נתונים לעבודה
df = filtered_df.sort_values(["best_score", NAME_COL], ascending=[False, True])
if "idx" not in st.session_state:
    st.session_state.idx = 0

# בדיקה אם סיימנו
if st.session_state.idx >= len(df):
    st.success("🎉 סיימנו!")
    st.download_button("⬇️ סיום", data=to_buf(st.session_state.guests,), file_name="סיום.xlsx", use_container_width=True)
    st.stop()

# המוזמן הנוכחי
cur = df.iloc[st.session_state.idx]

# תצוגת פרטי המוזמן המעוצבת
render_guest_profile(cur)

# בחירת התאמות עם radio buttons
choice = render_match_selection(cur, st.session_state.contacts)

# טיפול בהזנות נוספות
manual_phone = ""
search_phone = ""

if choice.startswith("➕"):
    manual_phone = handle_manual_input()
elif choice.startswith("🔍"):
    search_phone = handle_contact_search(st.session_state.contacts)

# מרווח לפני הכפתורים
st.markdown("---")

# כפתורי ניווט
col1, col2 = st.columns(2)

with col1:
    if st.button("⬅️ חזרה", disabled=(st.session_state.idx == 0), use_container_width=True):
        st.session_state.idx = max(0, st.session_state.idx - 1)
        force_rerun()

with col2:
    # בדיקה אם יש ערך לשמירה
    can_save = False
    save_value = None
    
    if manual_phone:
        save_value = normalize_phone_basic(manual_phone)
        can_save = save_value is not None
    elif search_phone:
        save_value = search_phone
        can_save = True
    elif choice.startswith("❌"):
        save_value = ""
        can_save = True
    elif choice and not choice.startswith(("➕", "🔍")):
        save_value = extract_phone_from_choice(choice)
        can_save = True
    
    if st.button("✅ אישור", disabled=not can_save, use_container_width=True):
        # שמירת הערך
        formatted_phone = format_phone(save_value) if save_value else ""
        st.session_state.guests.at[cur.name, PHONE_COL] = formatted_phone
        
        # מעבר להבא
        st.session_state.idx += 1
        force_rerun()