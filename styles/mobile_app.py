import time, secrets, re
from datetime import datetime
from typing import Optional, Tuple
import base64
import os
import pandas as pd
import streamlit as st
import requests
from pathlib import Path
import sys

# הוספת התיקייה הראשית ל-path כדי לייבא את logic
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from logic import (
    NAME_COL, PHONE_COL, COUNT_COL, SIDE_COL, GROUP_COL,
    AUTO_SELECT_TH, load_excel, to_buf,
    format_phone, normalize, compute_best_scores, full_score,
)

PAGE_TITLE = "📱 מיזוג טלפונים"
CODE_TTL_SECONDS = 300
MAX_AUTH_ATTEMPTS = 5
PHONE_PATTERN = re.compile(r"^0\d{9}$")

# הגדרות מובייל
st.set_page_config(
    page_title=PAGE_TITLE, 
    layout="centered",  # במקום wide
    initial_sidebar_state="collapsed"  # סייד בר מוסתר
)

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

def load_mobile_css():
    """CSS מותאם למובייל"""
    mobile_css = """
    /* הסתרת header של streamlit */
    .stAppHeader, .stAppToolbar, header[data-testid="stHeader"], .stDeployButton {
        display: none !important;
    }
    
    /* רקע נקי */
    .stApp {
        background: #f8f9fa !important;
    }
    
    /* מיכל ראשי מותאם למובייל */
    .main .block-container {
        padding: 1rem 0.5rem !important;
        max-width: 100% !important;
        margin: 0 !important;
    }
    
    /* כפתורים גדולים למובייל */
    .stButton > button {
        width: 100% !important;
        padding: 16px !important;
        font-size: 16px !important;
        min-height: 50px !important;
        border-radius: 12px !important;
        font-weight: 600 !important;
        margin: 8px 0 !important;
    }
    
    /* כפתור ראשי */
    .stButton > button[data-testid="baseButton-primary"] {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
        color: white !important;
        border: none !important;
        box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3) !important;
    }
    
    /* רדיו כפתורים למובייל */
    div[data-testid="stRadio"] label {
        padding: 16px !important;
        font-size: 16px !important;
        min-height: 55px !important;
        border-radius: 12px !important;
        margin: 6px 0 !important;
    }
    
    /* שדות טקסט למובייל */
    .stTextInput input {
        font-size: 16px !important;
        padding: 16px !important;
        min-height: 50px !important;
        border-radius: 12px !important;
        border: 2px solid #e9ecef !important;
    }
    
    .stTextInput input:focus {
        border-color: #667eea !important;
        box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.15) !important;
    }
    
    /* קארד מוזמן */
    .guest-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
        border-radius: 16px !important;
        padding: 20px !important;
        margin: 16px 0 !important;
        color: white !important;
        text-align: center !important;
        box-shadow: 0 8px 25px rgba(102, 126, 234, 0.3) !important;
    }
    
    /* פקדי ניהול */
    .mobile-controls {
        background: white !important;
        border-radius: 16px !important;
        padding: 16px !important;
        margin: 16px 0 !important;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1) !important;
    }
    
    /* התקדמות */
    .stProgress > div > div {
        height: 12px !important;
        border-radius: 6px !important;
    }
    
    /* מולטי סלקט למובייל */
    .stMultiSelect label {
        font-size: 16px !important;
        font-weight: 600 !important;
    }
    
    /* עמודות למובייל */
    div[data-testid="column"] {
        padding: 0 4px !important;
    }
    
    /* כותרות */
    .stMarkdown h1 {
        font-size: 28px !important;
        text-align: center !important;
        margin: 16px 0 !important;
    }
    
    .stMarkdown h2 {
        font-size: 22px !important;
        margin: 12px 0 !important;
    }
    
    .stMarkdown h3 {
        font-size: 18px !important;
        margin: 10px 0 !important;
    }
    
    /* הסתרת סייד בר לחלוטין */
    section[data-testid="stSidebar"] {
        display: none !important;
    }
    
    /* מדריך למובייל */
    .mobile-guide {
        background: white !important;
        border-radius: 16px !important;
        padding: 20px !important;
        margin: 16px 0 !important;
        box-shadow: 0 8px 25px rgba(102, 126, 234, 0.15) !important;
        border: 2px solid #667eea !important;
    }
    """
    
    st.markdown(f"<style>{mobile_css}</style>", unsafe_allow_html=True)

def normalize_phone_basic(p: str) -> Optional[str]:
    """נרמול בסיסי של מספר טלפון"""
    d = re.sub(r"\D", "", p or "")
    return d if PHONE_PATTERN.match(d) else None

def send_code(phone: str, code: str) -> bool:
    """שליחת קוד אימות"""
    if not config.is_valid():
        st.error("🚫 שגיאה בהגדרות המערכת")
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
        payload = {"chatId": chat, "message": f"קוד האימות שלך: {code}"}
        
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        st.error("שגיאה בשליחת הודעה")
        return False

def mobile_auth_flow() -> bool:
    """זרימת אימות מותאמת למובייל"""
    if st.session_state.get("auth_ok"):
        return True

    state = st.session_state.setdefault("auth_state", "phone")
    
    # כותרת מעוצבת
    st.markdown("""
    <div style="
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 30px 20px;
        border-radius: 20px;
        text-align: center;
        margin-bottom: 30px;
        box-shadow: 0 8px 25px rgba(102, 126, 234, 0.3);
    ">
        <h1 style="margin: 0; font-size: 24px;">📱 מערכת שילוב רשימות</h1>
        <p style="margin: 10px 0 0 0; opacity: 0.9;">התחבר עם מספר הטלפון שלך</p>
    </div>
    """, unsafe_allow_html=True)

    if state == "phone":
        st.markdown("### 📞 הזן מספר טלפון")
        phone = st.text_input(
            "מספר טלפון", 
            placeholder="05X-XXXXXXX",
            max_chars=10, 
            key="phone_input",
            label_visibility="collapsed"
        )
        
        if st.button("📱 שלח קוד אימות", type="primary"):
            p = normalize_phone_basic(phone)
            if not p:
                st.error("❌ מספר לא תקין")
            else:
                code = "".join(secrets.choice("0123456789") for _ in range(4))
                st.session_state.update({
                    "auth_code": code, "phone": p,
                    "code_ts": time.time(), "auth_state": "code"
                })
                if send_code(p, code):
                    st.success("✅ הקוד נשלח!")
                    st.rerun()
                else:
                    st.error("❌ שגיאה בשליחה")

    else:  # state == "code"
        st.markdown("### 🔐 הזן קוד אימות")
        entry = st.text_input(
            "קוד אימות", 
            placeholder="הכנס קוד בן 4 ספרות", 
            max_chars=4,
            label_visibility="collapsed"
        )
        
        expired = (time.time() - st.session_state.code_ts) > CODE_TTL_SECONDS
        if expired:
            st.warning("⏰ הקוד פג תוקף")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔓 אמת קוד", type="primary"):
                if expired:
                    st.error("❌ הקוד פג תוקף")
                elif entry == st.session_state.auth_code:
                    st.session_state.auth_ok = True
                    st.success("✅ התחברת בהצלחה!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("❌ קוד שגוי")
        
        with col2:
            if st.button("↩️ חזרה"):
                st.session_state.auth_state = "phone"
                st.rerun()

    return False

def find_up(start_path, *path_parts):
    """מחפש קובץ במסלול"""
    current = Path(start_path)
    for parent in [current] + list(current.parents):
        candidate = parent.joinpath(*path_parts)
        if candidate.exists():
            return candidate
    return None

def mobile_guide():
    """מדריך מותאם למובייל"""
    if st.session_state.get("show_guide", False):
        st.markdown('<div class="mobile-guide">', unsafe_allow_html=True)
        
        st.markdown("### 📖 מדריך הורדת אנשי קשר")
        
        # תמונה למעלה
        img_path = find_up(Path(__file__).resolve().parent, "assets", "Joni.png")
        if img_path and img_path.exists():
            st.image(str(img_path), caption="התוסף ג'וני ב-WhatsApp Web", use_container_width=True)
        
        st.markdown("#### 📋 שלבי ההורדה:")
        
        steps = [
            "פתח דפדפן **במחשב** (לא בטלפון)",
            "התקן את התוסף **[ג'וני](https://chromewebstore.google.com/detail/joni/aakppiadmnaeffmjijolmgmkcfhpglbh)** בדפדפן Chrome",
            "היכנס ל-**WhatsApp Web**",
            "לחץ על סמל **J** בסרגל הכלים",
            "בחר **אנשי קשר** ➜ **שמירה לקובץ Excel**",
            "הקובץ יורד אוטומטית"
        ]
        
        for i, step in enumerate(steps, 1):
            st.markdown(f"**{i}.** {step}")
        
        st.info("💡 **חשוב:** התוסף עובד רק בדפדפן Chrome במחשב")
        
        if st.button("✅ הבנתי", key="close_guide", type="primary"):
            st.session_state.show_guide = False
            st.rerun()
        
        st.markdown('</div>', unsafe_allow_html=True)

def mobile_file_upload():
    """העלאת קבצים למובייל"""
    st.markdown("### 📂 העלאת קבצים")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown("**👥 קובץ אנשי קשר**")
    with col2:
        if st.button("📖", key="guide_btn", help="מדריך"):
            st.session_state.show_guide = True
            st.rerun()
    
    contacts_file = st.file_uploader(
        "קובץ אנשי קשר", 
        type=["xlsx", "xls", "csv"],
        key="contacts_mobile",
        label_visibility="collapsed"
    )
    
    st.markdown("**🎉 קובץ מוזמנים**")
    guests_file = st.file_uploader(
        "קובץ מוזמנים", 
        type=["xlsx", "xls", "csv"],
        key="guests_mobile",
        label_visibility="collapsed"
    )
    
    if st.button("✅ אשר קבצים", disabled=not (contacts_file and guests_file), type="primary"):
        with st.spinner("⏳ טוען קבצים..."):
            st.session_state.contacts = load_excel(contacts_file)
            st.session_state.guests = load_excel(guests_file)
            st.session_state.guests["best_score"] = compute_best_scores(
                st.session_state.guests, st.session_state.contacts
            )
        st.session_state.upload_confirmed = True
        st.session_state.show_guide = False
        st.success("✅ קבצים נטענו בהצלחה!")
        time.sleep(1)
        st.rerun()

def mobile_controls():
    """פקדי ניהול למובייל"""
    st.markdown('<div class="mobile-controls">', unsafe_allow_html=True)
    st.markdown("### ⚙️ הגדרות וסינון")
    
    # פילטרים
    col1, col2 = st.columns(2)
    
    with col1:
        filter_no = st.checkbox("רק חסרי מספר", key="filter_no")
        if filter_no:
            st.session_state.idx = 0
    
    with col2:
        if st.session_state.get("guests") is not None:
            filtered_df = st.session_state.guests.copy()
            if filter_no:
                filtered_df = filtered_df[filtered_df[PHONE_COL].str.strip() == ""]
            
            st.download_button(
                "💾 הורד",
                data=to_buf(filtered_df),
                file_name="רשימה.xlsx",
                use_container_width=True
            )
    
    # התקדמות
    if st.session_state.get("guests") is not None:
        filtered_df = st.session_state.guests.copy()
        if filter_no:
            filtered_df = filtered_df[filtered_df[PHONE_COL].str.strip() == ""]
        
        total = len(filtered_df)
        current = min(st.session_state.get("idx", 0), total)
        
        st.markdown(f"**התקדמות: {current}/{total}**")
        st.progress(current / total if total > 0 else 0)
    
    st.markdown('</div>', unsafe_allow_html=True)

def render_guest_profile_mobile(cur):
    """פרופיל מוזמן למובייל"""
    st.markdown(f"""
    <div class="guest-card">
        <h2 style="margin: 0 0 16px 0; font-size: 24px;">🎯 {cur[NAME_COL]}</h2>
        <div style="display: flex; justify-content: center; gap: 20px; flex-wrap: wrap;">
            <div><strong>צד:</strong> {cur[SIDE_COL]}</div>
            <div><strong>קבוצה:</strong> {cur[GROUP_COL]}</div>
            <div><strong>כמות:</strong> {cur[COUNT_COL]}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

def create_radio_options_mobile(candidates: pd.DataFrame) -> list:
    """אופציות רדיו למובייל"""
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
    
    options.extend(["➕ הזנה ידנית", "🔍 חיפוש"])
    return options

def render_match_selection_mobile(cur, contacts_df: pd.DataFrame) -> str:
    """בחירת התאמות למובייל"""
    matches = contacts_df.copy()
    matches["score"] = matches["norm_name"].map(lambda c: full_score(cur.norm_name, c))
    
    best_score = matches["score"].max() if not matches.empty else 0
    
    if best_score >= 100:
        candidates = matches[matches["score"] >= 90].sort_values(["score", NAME_COL], ascending=[False, True]).head(3)
    else:
        candidates = matches[matches["score"] >= 70].sort_values(["score", NAME_COL], ascending=[False, True]).head(5)
    
    options = create_radio_options_mobile(candidates)
    
    choice = st.radio(
        "בחר איש קשר:",
        options,
        index=0,
        key=f"radio_mobile_{st.session_state.get('idx', 0)}",
        label_visibility="collapsed"
    )
    
    return choice

def extract_phone_from_choice_mobile(choice: str) -> str:
    """החלצת מספר מבחירה"""
    if choice.startswith("❌"):
        return ""
    elif choice.startswith(("➕", "🔍")):
        return ""
    else:
        clean_choice = choice.replace("🎯 ", "")
        return clean_choice.split("|")[-1].strip()

# הרצת האפליקציה
load_mobile_css()

# אתחול משתנים
if "upload_confirmed" not in st.session_state:
    st.session_state.upload_confirmed = False
if "show_guide" not in st.session_state:
    st.session_state.show_guide = False
if "idx" not in st.session_state:
    st.session_state.idx = 0

# בדיקת אימות
if not mobile_auth_flow():
    st.stop()

st.title(PAGE_TITLE)

# הצגת מדריך
mobile_guide()

# העלאת קבצים
if not st.session_state.upload_confirmed:
    mobile_file_upload()
    st.stop()

# פקדי ניהול
mobile_controls()

# עבודה עם הנתונים
filtered_df = st.session_state.guests.copy()
if st.session_state.get("filter_no"):
    filtered_df = filtered_df[filtered_df[PHONE_COL].str.strip() == ""]

df = filtered_df.sort_values(["best_score", NAME_COL], ascending=[False, True])

# בדיקה אם סיימנו
if st.session_state.idx >= len(df):
    st.success("🎉 סיימנו! כל המוזמנים עובדו.")
    st.download_button(
        "📥 הורד קובץ סופי",
        data=to_buf(st.session_state.guests),
        file_name="רשימה_סופית.xlsx",
        type="primary"
    )
    st.stop()

# המוזמן הנוכחי
cur = df.iloc[st.session_state.idx]

# הצגת פרטי המוזמן
render_guest_profile_mobile(cur)

# בחירת התאמות
choice = render_match_selection_mobile(cur, st.session_state.contacts)

# טיפול בהזנות מיוחדות
manual_phone = ""
search_phone = ""

if choice.startswith("➕"):
    st.markdown("### 📱 הזנת מספר ידנית")
    manual_phone = st.text_input(
        "מספר טלפון:", 
        placeholder="05XXXXXXXX",
        key=f"manual_mobile_{st.session_state.get('idx', 0)}",
        label_visibility="collapsed"
    )
    if manual_phone and not normalize_phone_basic(manual_phone):
        st.error("❌ מספר לא תקין")
        manual_phone = ""

elif choice.startswith("🔍"):
    st.markdown("### 🔍 חיפוש באנשי קשר")
    query = st.text_input(
        "חיפוש:", 
        placeholder="הקלד שם או מספר",
        key=f"search_mobile_{st.session_state.get('idx', 0)}",
        label_visibility="collapsed"
    )
    
    if len(query) >= 2:
        search_results = st.session_state.contacts[
            st.session_state.contacts.norm_name.str.contains(normalize(query), na=False) |
            st.session_state.contacts[PHONE_COL].str.contains(query, na=False)
        ].head(5)
        
        if not search_results.empty:
            search_options = ["בחר תוצאה..."] + [
                f"{r[NAME_COL]} | {format_phone(r[PHONE_COL])}" 
                for _, r in search_results.iterrows()
            ]
            selected = st.selectbox(
                "בחר:", 
                search_options,
                key=f"search_result_mobile_{st.session_state.get('idx', 0)}",
                label_visibility="collapsed"
            )
            if selected and selected != "בחר תוצאה...":
                search_phone = selected.split("|")[-1].strip()

# כפתורי ניווט
st.markdown("---")
col1, col2 = st.columns(2)

with col1:
    if st.button("⬅️ הקודם", disabled=(st.session_state.idx == 0)):
        st.session_state.idx = max(0, st.session_state.idx - 1)
        st.rerun()

with col2:
    # בדיקה מה לשמור
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
        save_value = extract_phone_from_choice_mobile(choice)
        can_save = True
    
    if st.button("✅ הבא", disabled=not can_save, type="primary"):
        # שמירה
        formatted_phone = format_phone(save_value) if save_value else ""
        st.session_state.guests.at[cur.name, PHONE_COL] = formatted_phone
        
        # מעבר הבא
        st.session_state.idx += 1
        st.rerun()