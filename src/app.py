import time, secrets, re, os
from datetime import datetime
from typing import Optional, Tuple
import pandas as pd
import streamlit as st
import requests
from pathlib import Path

from logic import (
    NAME_COL, PHONE_COL, COUNT_COL, SIDE_COL, GROUP_COL,
    AUTO_SELECT_TH, load_excel, to_buf,
    format_phone, normalize, compute_best_scores, full_score,
)

# ===============================
# קבועים ותצורה
# ===============================
PAGE_TITLE = " מיזוג טלפונים 💎"
CODE_TTL_SECONDS = 300
MAX_AUTH_ATTEMPTS = 5
PHONE_PATTERN = re.compile(r"^0\d{9}$")

# ===============================
# מחלקת תצורה
# ===============================
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

# ===============================
# פונקציות CSS
# ===============================

def load_css():
    possible_paths = ["styles/", "../styles/", "./styles/", "/app/styles/", "src/../styles/"]

    if st.session_state.get("auth_ok", False):
        css_files = ["components.css", "main.css", "mobile.css", "style.css"]  # ← הוסף כאן
    else:
        css_files = ["components.css", "login.css", "style.css"]               # ← וגם כאן

    for css_file in css_files:
        for base_path in possible_paths:
            css_path = os.path.join(base_path, css_file)
            try:
                if os.path.exists(css_path):
                    with open(css_path, encoding="utf-8") as f:
                        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
                        break
            except Exception:
                continue

def debug_css_paths():
    """בדיקת נתיבים לקבצי CSS"""
    possible_paths = [
        "styles/",
        "../styles/", 
        "./styles/",
        "/app/styles/",
        "src/../styles/",
    ]
    
    css_files = ["components.css", "login.css", "main.css", "mobile.css"]
    
    print("🔍 בדיקת נתיבי CSS:")
    for base_path in possible_paths:
        print(f"\n📁 בדיקת תיקיה: {base_path}")
        try:
            if os.path.exists(base_path):
                files_in_dir = os.listdir(base_path)
                print(f"   קבצים בתיקיה: {files_in_dir}")
                
                for css_file in css_files:
                    css_path = os.path.join(base_path, css_file)
                    if os.path.exists(css_path):
                        print(f"   ✅ {css_file} - קיים")
                    else:
                        print(f"   ❌ {css_file} - לא קיים")
            else:
                print(f"   ❌ התיקיה לא קיימת")
        except Exception as e:
            print(f"   🚨 שגיאה: {e}")

# ===============================
# פונקציות עזר
# ===============================
def normalize_phone_basic(p: str) -> Optional[str]:
    """נרמול בסיסי של מספר טלפון"""
    d = re.sub(r"\D", "", p or "")
    return d if PHONE_PATTERN.match(d) else None

def send_code(phone: str, code: str) -> bool:
    """שליחת קוד אימות"""
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

# ===============================
# זרימת אימות
# ===============================
# החלף את ה-HTML במסך התחברות:

def auth_flow() -> bool:
    """זרימת אימות המשתמש - טלפון וקוד OTP"""
    if st.session_state.get("auth_ok"):
        return True

    state = st.session_state.setdefault("auth_state", "phone")

    # כותרת אימות מתוקנת
    if state == "phone":
        icon = "💬"
        title = "מערכת שילוב רשימות"
        subtitle = "התחבר באמצעות מספר הטלפון שלך"
        label = "מספר טלפון"
    else:
        icon = "🔐" 
        title = "קוד אימות"
        subtitle = "הזן את הקוד שנשלח לטלפון שלך"
        label = "קוד אימות"

    # HTML מתוקן
    st.markdown(f"""
    <div class="auth-header">
        <div class="auth-icon">{icon}</div>
        <h1 class="auth-title">{title}</h1>
        <p class="auth-subtitle">{subtitle}</p>
        <div class="phone-label">{label}</div>
    </div>
    """, unsafe_allow_html=True)

    if state == "phone":
        phone = st.text_input("מספר טלפון", placeholder="05X-XXXXXXX",
                              max_chars=10, key="phone_input", label_visibility="hidden")
        
        if st.button("שלח קוד אימות 💬", type="primary"):
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
            
        col1, col2 = st.columns(2)
        with col1:
            if st.button("אמת 🔓", type="primary"):
                if expired: 
                    st.error("הקוד פג תוקף")
                elif entry == st.session_state.auth_code:
                    st.session_state.auth_ok = True
                    # הודעה מרוכזת
                    st.markdown("""
                    <div style="text-align: center; margin: 10px 0;">
                        <div style="background: #d4edda; color: #155724; padding: 12px; border-radius: 8px; display: inline-block;">
                            ✅ התחברת בהצלחה!
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
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
        
        with col2:
            if st.button("↩️ חזרה"):
                st.session_state.auth_state = "phone"
                force_rerun()

    return False

# ===============================
# מדריך הורדת קבצים
# ===============================
def show_download_guide():
    """מציג מדריך הורדת אנשי קשר"""
    if st.session_state.get("show_guide", False):
        st.markdown("""
        <div class="guide-modal">
            <h3>📖 מדריך הורדת אנשי קשר מ-WhatsApp</h3>
        </div>
        """, unsafe_allow_html=True)
        
        col_text, col_image = st.columns([1.3, 1])
        
        with col_text:
            st.markdown("#### 📋 שלבי ההורדה:")
            
            st.markdown("""
            <div class="guide-steps">
                <div>פתח דפדפן במחשב</div>
                <div>התקן תוסף <strong><a href="https://chromewebstore.google.com/detail/joni/aakppiadmnaeffmjijolmgmkcfhpglbh">ג'וני</a></strong> ב-Chrome</div>
                <div>היכנס ל-WhatsApp Web</div>
                <div>לחץ על סמל <strong>J</strong> בסרגל הכלים</div>
                <div>בחר <strong>אנשי קשר</strong> → <strong>שמירה לקובץ Excel</strong></div>
                <div>הקובץ יורד אוטומטית</div>
            </div>
            """, unsafe_allow_html=True)
            
            st.info("💡 **חשוב:** התוסף עובד רק ב-Chrome במחשב")
        
        with col_image:
            # חיפוש תמונה
            possible_image_paths = [
                "assets/Joni.png",
                "../assets/Joni.png", 
                "./assets/Joni.png",
                "/app/assets/Joni.png",
            ]
            
            image_found = False
            for img_path in possible_image_paths:
                try:
                    if os.path.exists(img_path):
                        st.image(img_path, caption="התוסף ג'וני", use_container_width=True)
                        image_found = True
                        break
                except:
                    continue
            
            if not image_found:
                st.markdown("""
                <div style="
                    background: #f0f4ff;
                    border: 2px dashed #4A90E2;
                    border-radius: 8px;
                    padding: 30px;
                    text-align: center;
                    color: #4A90E2;
                    font-size: 14px;
                ">
                    🖼️<br>תמונת המדריך<br>תוצג כאן
                </div>
                """, unsafe_allow_html=True)
        
        # שינוי ה-key כדי למנוע כפילות!
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            if st.button("✅ סגור", key="close_main_guide", type="primary"):  # ← שינוי כאן!
                st.session_state.show_guide = False
                st.rerun()

# ===============================
# רכיבי ממשק משתמש
# ===============================
def create_radio_options(candidates: pd.DataFrame) -> list:
    """יוצר רשימת אופציות לרדיו כפתורים"""
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
    """מציג פרופיל מוזמן"""
    st.markdown(f"""
    <div class="guest-profile">
        <h2>🎯 {cur[NAME_COL]}</h2>
        <div class="guest-meta">
            <div>
                <span>🧭</span>
                <strong>צד:</strong> {cur[SIDE_COL]}
            </div>
            <div>
                <span>🧩</span>
                <strong>קבוצה:</strong> {cur[GROUP_COL]}
            </div>
            <div>
                <span>👥</span>
                <strong>כמות:</strong> {cur[COUNT_COL]}
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_match_selection(cur, contacts_df: pd.DataFrame) -> str:
    """רנדור בחירת התאמות"""
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
    st.markdown('<div class="manual-input">', unsafe_allow_html=True)
    st.markdown("#### 📱 הזנת מספר ידנית:")
    manual_phone = st.text_input(
        "מספר טלפון:", 
        placeholder="05XXXXXXXX",
        key=f"manual_input_{st.session_state.get('idx', 0)}"
    )
    if manual_phone and not normalize_phone_basic(manual_phone):
        st.error("❌ מספר טלפון לא תקין")
        return ""
    st.markdown('</div>', unsafe_allow_html=True)
    return manual_phone

def handle_contact_search(contacts_df: pd.DataFrame) -> str:
    """טיפול בחיפוש באנשי קשר"""
    st.markdown('<div class="search-section">', unsafe_allow_html=True)
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
                st.markdown('</div>', unsafe_allow_html=True)
                return selected_result.split("|")[-1].strip()
        else:
            st.info("🔍 לא נמצאו תוצאות")
    elif query:
        st.info("הקלד לפחות 2 תווים לחיפוש")
    
    st.markdown('</div>', unsafe_allow_html=True)
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

# ===============================
# הגדרות Streamlit וקונפיגורציה
# ===============================
config = AppConfig()
st.set_page_config(page_title=PAGE_TITLE, layout="wide")
print("🔄 TEST VERSION 1.0 - 05/08/2025")

# אתחול משתנים
if "upload_confirmed" not in st.session_state:
    st.session_state.upload_confirmed = False
if "show_guide" not in st.session_state:
    st.session_state.show_guide = False
if "idx" not in st.session_state:
    st.session_state.idx = 0

# טעינת CSS
load_css()

# בדיקת אימות
if not auth_flow():
    st.stop()

# ===============================
# מערכת ראשית
# ===============================

if not st.session_state.get('upload_confirmed', False):
    st.title(PAGE_TITLE)
else:
    # כותרת נסתרת/קטנה למערכת פעילה
    st.markdown('<div style="height: 8px;"></div>', unsafe_allow_html=True)

# הצגת המדריך
show_download_guide()

# שלב העלאת קבצים
# החלף את החלק של העלאת הקבצים ב-app.py עם הקוד הזה:

# שלב העלאת קבצים - גרסה מתוקנת
# שלב העלאת קבצים - גרסה מתוקנת עם הזחות נכונות
if not st.session_state.upload_confirmed:
    
    with st.sidebar:
        st.markdown("## 📂 העלאת קבצים")
        
        # כפתור מדריך מתוקן
        st.markdown("### 👥 קובץ אנשי קשר")
        
        col1, col2 = st.columns([4, 1])  # יחס רחב יותר
        with col2:
            if st.button("📖", key="help_contacts_sidebar", help="מדריך הורדת קבצים", use_container_width=True):
                st.session_state.show_guide = True
                force_rerun()
        
        contacts_file = st.file_uploader(
            "קובץ אנשי קשר", 
            type=["xlsx", "xls", "csv"], 
            key="contacts_uploader",
            label_visibility="collapsed"
        )
        
        # Debug - בדוק אם יש קובץ
        if contacts_file:
            st.success(f"✅ קובץ אנשי קשר: {contacts_file.name}")
            print(f"📁 קובץ אנשי קשר נבחר: {contacts_file.name}")
        
        st.markdown("### 🎉 קובץ מוזמנים")
        
        # העלאת קובץ מוזמנים
        guests_file = st.file_uploader(
            "קובץ מוזמנים", 
            type=["xlsx", "xls", "csv"], 
            key="guests_uploader",
            label_visibility="collapsed"
        )
        
        # Debug - בדוק אם יש קובץ
        if guests_file:
            st.success(f"✅ קובץ מוזמנים: {guests_file.name}")
            print(f"📁 קובץ מוזמנים נבחר: {guests_file.name}")

        # כפתור אישור - עם debug
        files_ready = bool(contacts_file and guests_file)
        print(f"🔍 קבצים מוכנים: {files_ready} (contacts: {bool(contacts_file)}, guests: {bool(guests_file)})")
        
        if st.button("✅ אשר קבצים", 
                    disabled=not files_ready, 
                    type="primary",
                    key="confirm_files_btn"):
            
            print("🚀 לחיצה על כפתור אישור קבצים!")
            
            try:
                with st.spinner("⏳ טוען קבצים..."):
                    print("📊 מתחיל לטעון קבצים...")
                    
                    # טעינת קבצים
                    st.session_state.contacts = load_excel(contacts_file)
                    print(f"✅ קובץ אנשי קשר נטען: {len(st.session_state.contacts)} שורות")
                    
                    st.session_state.guests = load_excel(guests_file)
                    print(f"✅ קובץ מוזמנים נטען: {len(st.session_state.guests)} שורות")
                    
                    # חישוב ציונים
                    print("🧮 מחשב ציוני התאמה...")
                    st.session_state.guests["best_score"] = compute_best_scores(
                        st.session_state.guests, st.session_state.contacts
                    )
                    print("✅ ציוני התאמה חושבו")
                
                # סימון שהקבצים אושרו
                st.session_state.upload_confirmed = True
                st.session_state.show_guide = False
                
                print("🎉 קבצים אושרו בהצלחה!")
                st.success("🎉 קבצים נטענו בהצלחה!")
                
                # המתן קצר ורענן
                time.sleep(1)
                force_rerun()
                
            except Exception as e:
                print(f"🚨 שגיאה בטעינת קבצים: {str(e)}")
                st.error(f"שגיאה בטעינת קבצים: {str(e)}")
                st.session_state.upload_confirmed = False
    

# אם לא הושלמה העלאת קבצים - עצור כאן
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

# מיון והכנת נתונים
df = filtered_df.sort_values(["best_score", NAME_COL], ascending=[False, True])

# בדיקה אם סיימנו
if st.session_state.idx >= len(df):
    st.markdown("""
    <div class="completion-card">
        <h2>🎉 סיימנו!</h2>
        <p>כל המוזמנים עובדו בהצלחה</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.download_button(
        "📥 הורד קובץ סופי",
        data=to_buf(st.session_state.guests),
        file_name="סיום.xlsx",
        type="primary",
        use_container_width=True
    )
    st.stop()

# המוזמן הנוכחי
cur = df.iloc[st.session_state.idx]

# תצוגת פרטי המוזמן
render_guest_profile(cur)

# בחירת התאמות
choice = render_match_selection(cur, st.session_state.contacts)

# טיפול בהזנות נוספות
manual_phone = ""
search_phone = ""

if choice.startswith("➕"):
    manual_phone = handle_manual_input()
elif choice.startswith("🔍"):
    search_phone = handle_contact_search(st.session_state.contacts)

# כפתורי ניווט
st.markdown("---")
st.markdown('<div class="navigation-buttons">', unsafe_allow_html=True)
col1, col2 = st.columns(2)

# כפתור אישור בצד שמאל (col1)
with col1:
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
    
    if st.button("✅ אישור", disabled=not can_save, type="primary", use_container_width=True):
        # שמירת הערך
        formatted_phone = format_phone(save_value) if save_value else ""
        st.session_state.guests.at[cur.name, PHONE_COL] = formatted_phone
        
        # מעבר להבא
        st.session_state.idx += 1
        force_rerun()

# כפתור חזרה בצד ימין (col2)
with col2:
    if st.button("⬅️ חזרה", disabled=(st.session_state.idx == 0), use_container_width=True):
        st.session_state.idx = max(0, st.session_state.idx - 1)
        force_rerun()

st.markdown('</div>', unsafe_allow_html=True)