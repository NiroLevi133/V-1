import time, secrets, re
from datetime import datetime
from typing import Optional, Tuple
import base64
import os
import pandas as pd
import streamlit as st
import requests
import subprocess
import sys
from logic import (
    NAME_COL, PHONE_COL, COUNT_COL, SIDE_COL, GROUP_COL,
    AUTO_SELECT_TH, load_excel, to_buf,
    format_phone, normalize, compute_best_scores, full_score,
)

PAGE_TITLE = " מיזוג טלפונים 💎"
CODE_TTL_SECONDS  = 300
MAX_AUTH_ATTEMPTS = 5
PHONE_PATTERN     = re.compile(r"^0\d{9}$")

def detect_mobile():
    """זיהוי אם המשתמש במובייל"""
    try:
        user_agent = st.context.headers.get("user-agent", "").lower()
        mobile_keywords = ["mobile", "android", "iphone", "ipad", "ipod", "blackberry", "opera mini"]
        return any(keyword in user_agent for keyword in mobile_keywords)
    except:
        return False

def redirect_to_mobile():
    """הפעלת האפליקציה למובייל"""
    st.markdown("""
    <div style="
        text-align: center;
        padding: 50px 20px;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border-radius: 20px;
        margin: 20px 0;
    ">
        <h2>📱 מעביר לגרסת מובייל...</h2>
        <p>האפליקציה מותאמת למובייל נטענת</p>
    </div>
    """, unsafe_allow_html=True)
    
    # הפניה לתיקיית styles
    st.markdown("""
    <script>
    setTimeout(function() {
        const currentUrl = window.location.href;
        let newUrl;
        if (currentUrl.includes('app.py')) {
            newUrl = currentUrl.replace('app.py', 'styles/mobile_app.py');
        } else {
            const baseUrl = currentUrl.split('?')[0];
            newUrl = baseUrl + (baseUrl.endsWith('/') ? '' : '/') + 'styles/mobile_app.py';
        }
        window.location.href = newUrl;
    }, 2000);
    </script>
    """, unsafe_allow_html=True)
    
    st.info("💡 אם לא הועברת אוטומטית, גש ל: styles/mobile_app.py")
    
    # הוספת קישור ידני
    st.markdown("""
    <div style="text-align: center; margin-top: 20px;">
        <a href="./styles/mobile_app.py" style="
            background: #28a745;
            color: white;
            padding: 12px 24px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 600;
        ">🔗 לחץ כאן לגרסת מובייל</a>
    </div>
    """, unsafe_allow_html=True)

class AppConfig:
    def __init__(self):
        self.green_id = None
        self.green_token = None
        self._load_credentials()
        
    def _load_credentials(self):
        try:
            from dotenv import load_dotenv
            load_dotenv()
            print("✅ קובץ .env נטען")
        except ImportError:
            print("⚠️ python-dotenv לא מותקן")
        except Exception as e:
            print(f"⚠️ בעיה בטעינת .env: {e}")
        
        self.green_id = os.getenv("GREEN_API_ID")
        self.green_token = os.getenv("GREEN_API_TOKEN")
        
        if self.green_id and self.green_token:
            print("✅ נתוני GREEN-API נטענו בהצלחה")
            print(f"🔍 ID: {self.green_id[:3]}...")
            print(f"🔍 TOKEN: {self.green_token[:10]}...")
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

# זיהוי מובייל והפניה
if detect_mobile():
    redirect_to_mobile()
    st.stop()

def load_main_css_fixed():
    """טוען את ה-CSS הראשי עם תיקונים"""
    basic_css = """
    .stMarkdown, .stMarkdown * {
        color: inherit !important;
        font-family: inherit !important;
    }
    
    .stMarkdown div {
        display: block !important;
    }
    
    .stMarkdown strong {
        font-weight: bold !important;
    }
    """
    
    st.markdown(f"<style>{basic_css}</style>", unsafe_allow_html=True)
    
    possible_paths = [
        "../styles/style.css",      
        "styles/style.css",         
        "/app/styles/style.css",    
        "./styles/style.css",       
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
    
    print("⚠️ לא נמצא קובץ CSS - ממשיך עם CSS בסיסי")

def load_radio_css():
    """טוען CSS מעוצב לרדיו כפתורים"""
    radio_css = """
    div[data-testid="stRadio"] {
        background: transparent !important;
        border: none !important;
        padding: 10px 0 !important;
        margin: 10px 0 !important;
    }
    
    div[data-testid="stRadio"] > label {
        display: none !important;
    }
    
    div[data-testid="stRadio"] label {
        display: flex !important;
        align-items: center !important;
        padding: 8px 12px !important;
        border: 1px solid #e9ecef !important;
        border-radius: 6px !important;
        cursor: pointer !important;
        background: #fafafa !important;
        margin: 4px 0 !important;
        font-size: 13px !important;
        color: #495057 !important;
        min-height: 36px !important;
    }
    
    div[data-testid="stRadio"] label:hover {
        background: #f8f9fa !important;
        border-color: #4A90E2 !important;
    }
    
    div[data-testid="stRadio"] label:has(input:checked) {
        background: #e3f2fd !important;
        border-color: #4A90E2 !important;
        color: #1976d2 !important;
        font-weight: 600 !important;
    }
    """
    
    st.markdown(f"<style>{radio_css}</style>", unsafe_allow_html=True)

def normalize_phone_basic(p: str) -> Optional[str]:
    """נרמול בסיסי של מספר טלפון"""
    d = re.sub(r"\D", "", p or "")
    return d if PHONE_PATTERN.match(d) else None

def send_code(phone: str, code: str) -> bool:
    """פונקציה משופרת לשליחת קוד אימות"""
    if not config.is_valid():
        st.error("🚫 שגיאה בהגדרות המערכת - נתוני GREEN-API חסרים")
        return False
    
    try:
        clean_phone = "".join(filter(str.isdigit, phone))
        
        if clean_phone.startswith("0"):
            chat = "972" + clean_phone[1:] + "@c.us"
        elif clean_phone.startswith("972"):
            chat = clean_phone + "@c.us"
        else:
            chat = "972" + clean_phone + "@c.us"
        
        url = f"https://api.green-api.com/waInstance{config.green_id}/sendMessage/{config.green_token}"
        
        payload = {
            "chatId": chat,
            "message": f"קוד האימות שלך: {code}"
        }
        
        response = requests.post(url, json=payload, timeout=10)
        
        if response.status_code == 200:
            return True
        else:
            st.error(f"שגיאה בשליחת הודעה: {response.status_code}")
            return False
            
    except Exception as e:
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
    """מציג מדריך הורדת אנשי קשר כחלונית בולטת"""
    if st.session_state.get("show_guide", False):
        st.markdown("""
        <div style="
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 15px;
            margin: 20px 0;
            box-shadow: 0 15px 35px rgba(102, 126, 234, 0.4);
            border: 3px solid #4A90E2;
        ">
            <div style="text-align: center; margin-bottom: 20px;">
                <h2 style="margin: 0; font-size: 28px; font-weight: 700;">
                    📖 מדריך הורדת אנשי קשר מ-WhatsApp
                </h2>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        with st.container():
            st.markdown("""
            <div style="
                background: white;
                padding: 30px;
                border-radius: 15px;
                box-shadow: 0 8px 25px rgba(0,0,0,0.1);
                border: 1px solid #e3f2fd;
                margin-top: -10px;
            ">
            """, unsafe_allow_html=True)
            
            col_text, col_image = st.columns([1.2, 1])
            
            with col_text:
                st.markdown("### 📱 איך להוריד את רשימת אנשי הקשר?")
                st.markdown("#### שלבי ההורדה:")
                
                st.markdown("**שלב 1:** פתח את הדפדפן **במחשב** (לא בטלפון)")
                
                st.markdown(
                    "**שלב 2:** התקן את התוסף **[ג'וני](https://chromewebstore.google.com/detail/joni/aakppiadmnaeffmjijolmgmkcfhpglbh)** "
                    "בדפדפן Chrome"
                )
                
                st.markdown("**שלב 3:** היכנס ל-**WhatsApp Web** באותו דפדפן")
                
                st.markdown("**שלב 4:** לחץ על הסמל **J** (של ג'וני) בסרגל הכלים")
                
                st.markdown("**שלב 5:** בחר **אנשי קשר** ➜ **שמירה לקובץ Excel**")
                
                st.markdown("**שלב 6:** הקובץ יורד אוטומטית לתיקיית ההורדות")
                
                st.info("💡 **טיפים חשובים:**\n\n"
                       "• וודא שאתה מחובר ל-WhatsApp Web\n\n"
                       "• התוסף עובד רק בדפדפן Chrome\n\n"
                       "• הקובץ נשמר בפורמט Excel מוכן לשימוש")
            
            with col_image:
                img_path = find_up(Path(__file__).resolve().parent, "assets", "Joni.png")
                if img_path and img_path.exists():
                    st.image(str(img_path), caption="כך נראה התוסף ג'וני ב-WhatsApp Web", use_container_width=True)
                else:
                    st.info("🖼️ תמונת הדרכה תוצג כאן")
            
            st.markdown("</div>", unsafe_allow_html=True)
        
        st.markdown("---")
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            if st.button("❌ סגור מדריך", key="close_guide", use_container_width=True, type="primary"):
                st.session_state.show_guide = False
                st.rerun()

def load_guide_css():
    """CSS מיוחד למדריך ואתחול משתנים"""
    if "upload_confirmed" not in st.session_state:
        st.session_state.upload_confirmed = False

    if "show_guide" not in st.session_state:
        st.session_state.show_guide = False

    if "idx" not in st.session_state:
        st.session_state.idx = 0
        
    guide_css = """
    .stMarkdown a {
        color: #4A90E2 !important;
        text-decoration: none !important;
        font-weight: 600 !important;
        border-bottom: 2px solid #4A90E2 !important;
        padding-bottom: 1px !important;
        transition: all 0.2s ease !important;
    }
    
    .stMarkdown a:hover {
        color: #2980b9 !important;
        border-bottom-color: #2980b9 !important;
        transform: translateY(-1px) !important;
    }
    """
    
    st.markdown(f"<style>{guide_css}</style>", unsafe_allow_html=True)
    
def load_modal_css():
    """CSS לעיצוב המדריך הבולט"""
    modal_css = """
    button[data-testid="baseButton-primary"] {
        background: linear-gradient(135deg, #ff6b6b 0%, #ee5a5a 100%) !important;
        border: none !important;
        border-radius: 10px !important;
        padding: 12px 24px !important;
        font-size: 16px !important;
        font-weight: 600 !important;
        color: white !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 4px 15px rgba(255, 107, 107, 0.3) !important;
    }
    
    button[data-testid="baseButton-primary"]:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 8px 25px rgba(255, 107, 107, 0.4) !important;
    }
    """
    
    st.markdown(f"<style>{modal_css}</style>", unsafe_allow_html=True)
    
def load_login_css():
    """טוען CSS למסך הכניסה"""
    login_css = """
    .stAppHeader, .stAppToolbar, header[data-testid="stHeader"], .stDeployButton {display:none!important;}
    
    .stApp {
      background: linear-gradient(135deg,#E8EEFF 0%,#DBE6FF 100%)!important;
      min-height: 100vh!important;
    }
    
    .main .block-container {
      padding: 2rem!important;
      max-width: 600px!important;
      margin: 0 auto!important;
      background: white!important;
      border-radius: 20px!important;
      box-shadow: 0 10px 30px rgba(0,0,0,0.1)!important;
      margin-top: 3rem!important;
    }
    
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
    }
    
    .stTextInput > div > div {
      border: none!important;
      background: transparent!important;
      max-width: 350px!important;
      width: 100%!important;
    }
    
    .stTextInput > div > div > input:focus {
      border-color: #4A90E2!important;
      box-shadow: 0 0 0 3px rgba(74,144,226,.12)!important;
      outline: none!important;
    }
    
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
    """
    
    st.markdown(f"<style>{login_css}</style>", unsafe_allow_html=True)

def load_file_uploader_css():
    """CSS מותאם לתיבות העלאת קבצים"""
    file_css = """
    div[data-testid="stFileUploader"] {
        margin: 15px 0 !important;
        padding: 0 !important;
    }
    
    section[data-testid="stFileUploadDropzone"] {
        border: 2px dashed #dee2e6 !important;
        border-radius: 12px !important;
        background: white !important;
        padding: 20px 15px !important;
        text-align: center !important;
        transition: all 0.3s ease !important;
        margin: 0 !important;
        min-height: 80px !important;
    }
    
    section[data-testid="stFileUploadDropzone"]:hover {
        border-color: #4A90E2 !important;
        background: #f8f9fa !important;
        box-shadow: 0 2px 8px rgba(74,144,226,0.15) !important;
    }
    """
    
    st.markdown(f"<style>{file_css}</style>", unsafe_allow_html=True)

def auth_flow() -> bool:
    """זרימת אימות המשתמש - טלפון וקוד OTP"""
    if st.session_state.get("auth_ok"):
        return True

    load_login_css()
    state = st.session_state.setdefault("auth_state", "phone")

    icon = "💬" if state == "phone" else "🔐"
    subtitle = "התחבר באמצעות מספר הטלפון שלך" if state == "phone" else "הכנס את הקוד שנשלח אליך"
    label = "מספר טלפון" if state == "phone" else "קוד אימות"

    st.markdown(f'<div class="auth-icon">{icon}</div>', unsafe_allow_html=True)
    st.markdown('<div class="auth-title">מערכת שילוב רשימות</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="auth-subtitle">{subtitle}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="phone-label">{label}</div>', unsafe_allow_html=True)

    if state == "phone":
        phone = st.text_input("מספר טלפון", placeholder="05X-XXXXXXX",
                              max_chars=10, key="phone_input", label_visibility="hidden")
        
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
        
        expired = (time.time() - st.session_state.code_ts) > CODE_TTL_SECONDS
        if expired: 
            st.warning("הקוד פג תוקף")
        if st.button("אמת 🔓"):
            if expired: 
                st.error("הקוד פג תוקף")
            elif entry == st.session_state.auth_code:
                st.session_state.auth_ok = True
                st.success("✅ התחברת בהצלחה!")
                time.sleep(1)
                force_rerun()
            else:
                att = st.session_state.get("auth_attempts", 0) + 1
                st.session_state.auth_attempts = att
                if att >= MAX_AUTH_ATTEMPTS:
                    st.error("נחרגת ממספר הניסיונות המותר")
                    st.session_state.auth_state = "phone"
                    force_rerun()
                else:
                    st.error(f"קוד שגוי ({MAX_AUTH_ATTEMPTS - att} ניסיונות נותרו)")

    return False

def create_radio_options(candidates: pd.DataFrame) -> list:
    """יוצר רשימת אופציות לרדיו כפתורים עם פורמט מיוחד"""
    options = ["❌ ללא התאמה"]
    
    for _, candidate in candidates.iterrows():
        name = candidate[NAME_COL]
        phone = format_phone(candidate[PHONE_COL])
        score = int(candidate["score"])
        
        option_text = f"{name} | {phone}"
        
        if score == 100:
            options.append(f"🎯 {option_text}")
        else:
            options.append(option_text)
    
    options.extend(["➕ הוסף ידני", "🔍 חפש אנשי קשר"])
    
    return options

def get_auto_select_index(candidates: pd.DataFrame, options: list) -> int:
    """מחזיר אינדקס לבחירה אוטומטית חכמה"""
    if candidates.empty:
        return 0
    
    best_score = candidates.iloc[0]["score"]
    if best_score >= AUTO_SELECT_TH:
        best_name = candidates.iloc[0][NAME_COL]
        for i, option in enumerate(options):
            if best_name in option and not option.startswith(("❌", "➕", "🔍")):
                return i
    
    return 0

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
    matches = contacts_df.copy()
    matches["score"] = matches["norm_name"].map(lambda c: full_score(cur.norm_name, c))

    best_score = matches["score"].max() if not matches.empty else 0

    if best_score >= 100:
        candidates = matches[matches["score"] >= 90]\
                        .sort_values(["score", NAME_COL], ascending=[False, True])\
                        .head(3)
    else:
        candidates = matches[matches["score"] >= 70]\
                        .sort_values(["score", NAME_COL], ascending=[False, True])\
                        .head(5)

    options = create_radio_options(candidates)
    
    load_radio_css()
    
    auto_index = get_auto_select_index(candidates, options)
    
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
        clean_choice = choice.replace("🎯 ", "")
        return clean_choice.split("|")[-1].strip()

# טעינת CSS ראשי
load_main_css_fixed()
load_guide_css()
load_modal_css()

# בדיקת אימות
if not auth_flow():
    st.stop()

# טעינת CSS לתיבות העלאת קבצים
load_file_uploader_css()

st.title(PAGE_TITLE)

# הצגת המדריך רק אם נדרש
show_download_guide()

# שלב העלאת קבצים
if not st.session_state.upload_confirmed:
    with st.sidebar:
        st.markdown("## 📂 העלאת קבצים")
        
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown("### 👥 קובץ אנשי קשר")
        with col2:
            if st.button("📖 מדריך", key="help_contacts", help="איך להוריד קובץ אנשי קשר?"):
                st.session_state.show_guide = True
                force_rerun()
        
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
                st.session_state.contacts = load_excel(contacts_file)
                st.session_state.guests   = load_excel(guests_file)
                st.session_state.guests["best_score"] = compute_best_scores(
                    st.session_state.guests, st.session_state.contacts
                )
            st.session_state.upload_confirmed = True
            st.session_state.show_guide = False
            force_rerun()

if not st.session_state.upload_confirmed:
    st.stop()

# Sidebar עם פילטרים וניהול
with st.sidebar:
    st.checkbox("רק חסרי מספר", key="filter_no", on_change=lambda: st.session_state.update(idx=0))

    filtered_df = st.session_state.guests.copy()
    if st.session_state.get("filter_no"):
        filtered_df = filtered_df[filtered_df[PHONE_COL].str.strip() == ""]

    all_sides   = st.session_state.guests[SIDE_COL].dropna().unique().tolist()
    all_groups  = st.session_state.guests[GROUP_COL].dropna().unique().tolist()

    st.multiselect("סנן לפי צד", options=all_sides, key="filter_sides")
    st.multiselect("סנן לפי קבוצה", options=all_groups, key="filter_groups")

    if st.session_state.get("filter_sides"):
        filtered_df = filtered_df[filtered_df[SIDE_COL].isin(st.session_state.filter_sides)]
    if st.session_state.get("filter_groups"):
        filtered_df = filtered_df[filtered_df[GROUP_COL].isin(st.session_state.filter_groups)]

    filtered_total = len(filtered_df)
    complete_idx   = st.session_state.get("idx", 0)
    complete_idx   = min(complete_idx, filtered_total)

    st.markdown(f"**{complete_idx}/{filtered_total} הושלמו**")
    st.progress(complete_idx / filtered_total if filtered_total else 0)

    st.download_button(
        "💾 הורד Excel",
        data=to_buf(filtered_df),
        file_name="רשימת_מסוננים.xlsx",
        use_container_width=True,
    )

# מיון והכנת נתונים לעבודה
df = filtered_df.sort_values(["best_score", NAME_COL], ascending=[False, True])

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