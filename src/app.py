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
PAGE_TITLE = "💎 מיזוג טלפונים"
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
# פונקציות CSS ועיצוב
# ===============================
def load_css():
    """טוען את קובץ ה-CSS הרספונסיבי החדש"""
    css_paths = [
        "styles/style.css",
        "../styles/style.css", 
        "./styles/style.css",
        "/app/styles/style.css",
        "src/../styles/style.css",
    ]
    
    css_loaded = False
    for css_path in css_paths:
        try:
            if os.path.exists(css_path):
                with open(css_path, encoding="utf-8") as f:
                    css_content = f.read()
                    st.markdown(f"<style>{css_content}</style>", unsafe_allow_html=True)
                    print(f"✅ CSS נטען בהצלחה: {css_path}")
                    css_loaded = True
                    break
        except Exception as e:
            print(f"⚠️ שגיאה בטעינת {css_path}: {e}")
            continue
    
    if not css_loaded:
        print("❌ לא נמצא קובץ style.css")

def add_app_header():
    """מוסיף כותרת אפליקציה רספונסיבית"""
    st.markdown("""
    <div class="app-header">
        <div class="app-title">💎 מיזוג טלפונים</div>
        <div class="app-subtitle">מערכת שילוב רשימות מתקדמת</div>
    </div>
    """, unsafe_allow_html=True)

def is_mobile():
    """בודק אם המכשיר הוא מובייל"""
    # פשוט נניח שאם הרוחב קטן מ-768px זה מובייל
    return True  # לעת עתה נתייחס לכל המכשירים כמובייל

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
def auth_flow() -> bool:
    """זרימת אימות המשתמש - טלפון וקוד OTP"""
    if st.session_state.get("auth_ok"):
        return True

    state = st.session_state.setdefault("auth_state", "phone")

    # כותרת אימות
    if state == "phone":
        icon = "📱"
        title = "התחברות למערכת"
        subtitle = "הזן את מספר הטלפון שלך"
        label = "מספר טלפון"
    else:
        icon = "🔐" 
        title = "קוד אימות"
        subtitle = "הזן את הקוד שנשלח לטלפון שלך"
        label = "קוד אימות"

    # HTML מעוצב
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
        
        if st.button("📱 שלח קוד אימות", type="primary"):
            p = normalize_phone_basic(phone)
            if not p:
                st.error("❌ מספר לא תקין")
            else:
                code = "".join(secrets.choice("0123456789") for _ in range(4))
                st.session_state.update({
                    "auth_code": code, "phone": p,
                    "code_ts": time.time(), "auth_state": "code"})
                if not send_code(p, code):
                    st.error("❌ לא ניתן לשלוח קוד אימות")
                else:
                    st.success("✅ הקוד נשלח!")
                    force_rerun()

    else:  # state == "code"
        entry = st.text_input("קוד אימות", placeholder="הכנס קוד בן 4 ספרות", 
                              max_chars=4, label_visibility="hidden")
        
        expired = (time.time() - st.session_state.code_ts) > CODE_TTL_SECONDS
        if expired: 
            st.warning("⏰ הקוד פג תוקף")
            
        col1, col2 = st.columns(2)
        with col1:
            if st.button("↩️ חזרה"):
                st.session_state.auth_state = "phone"
                force_rerun()
        with col2:
            if st.button("🔓 אמת קוד", type="primary"):
                if expired: 
                    st.error("❌ הקוד פג תוקף")
                elif entry == st.session_state.auth_code:
                    st.session_state.auth_ok = True
                    st.success("✅ התחברת בהצלחה!")
                    time.sleep(1)
                    force_rerun()
                else:
                    att = st.session_state.get("auth_attempts", 0) + 1
                    st.session_state.auth_attempts = att
                    if att >= MAX_AUTH_ATTEMPTS:
                        st.error("❌ נחרגת ממספר הניסיונות המותר")
                        st.session_state.auth_state = "phone"
                        force_rerun()
                    else:
                        st.error(f"❌ קוד שגוי ({MAX_AUTH_ATTEMPTS - att} ניסיונות נותרו)")

    return False

# סימון שהמערכת פעילה אחרי התחברות
if st.session_state.get("auth_ok", False):
    st.markdown("""
    <script>
    document.body.classList.add('auth-completed');
    document.querySelector('.stApp').classList.add('main-app');
    </script>
    """, unsafe_allow_html=True)

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
        
        # מדריך בצורת steps
        st.markdown("""
        <div class="guide-steps">
            <div>פתח דפדפן <strong>במחשב</strong> (לא בטלפון)</div>
            <div>התקן את התוסף <strong><a href="https://chromewebstore.google.com/detail/joni/aakppiadmnaeffmjijolmgmkcfhpglbh" target="_blank">ג'וני</a></strong> בדפדפן Chrome</div>
            <div>היכנס ל-<strong>WhatsApp Web</strong></div>
            <div>לחץ על סמל <strong>J</strong> בסרגל הכלים</div>
            <div>בחר <strong>אנשי קשר</strong> → <strong>שמירה לקובץ Excel</strong></div>
            <div>הקובץ יורד אוטומטית למחשב</div>
        </div>
        """, unsafe_allow_html=True)
        
        st.info("💡 **חשוב:** התוסף עובד רק בדפדפן Chrome במחשב")
        
        # כפתור סגירה
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            if st.button("✅ הבנתי", key="close_guide", type="primary"):
                st.session_state.show_guide = False
                st.rerun()

# ===============================
# העלאת קבצים (למובייל ומחשב)
# ===============================
def show_file_upload():
    """מציג העלאת קבצים בצורה רספונסיבית"""
    
    if is_mobile():
        # במובייל - העלאה בתוכן הראשי
        st.markdown("### 📂 העלאת קבצים")
        
        # קובץ אנשי קשר
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
        
        if contacts_file:
            st.markdown("""
            <div class="file-uploaded">
                <div class="file-uploaded-indicator">
                    <span>✅</span>
                    <span>קובץ אנשי קשר נטען בהצלחה</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        # קובץ מוזמנים
        st.markdown("**🎉 קובץ מוזמנים**")
        guests_file = st.file_uploader(
            "קובץ מוזמנים", 
            type=["xlsx", "xls", "csv"],
            key="guests_mobile",
            label_visibility="collapsed"
        )
        
        if guests_file:
            st.markdown("""
            <div class="file-uploaded">
                <div class="file-uploaded-indicator">
                    <span>✅</span>
                    <span>קובץ מוזמנים נטען בהצלחה</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        return contacts_file, guests_file
    
    else:
        # במחשב - בסייד בר (הקוד הקיים)
        return None, None

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
        
        if score == 100:
            option_text = f"🎯 {name} | {phone}"
        else:
            option_text = f"{name} | {phone}"
        
        options.append(option_text)
    
    options.extend(["➕ הזנה ידנית", "🔍 חיפוש אנשי קשר"])
    
    return options

def get_auto_select_index(candidates: pd.DataFrame, options: list) -> int:
    """מחזיר אינדקס לבחירה אוטומטית (93%+)"""
    if candidates.empty:
        return 0
    
    best_score = candidates.iloc[0]["score"]
    if best_score >= AUTO_SELECT_TH:
        best_name = candidates.iloc[0][NAME_COL]
        for i, option in enumerate(options):
            if best_name in option and not option.startswith(("❌", "➕", "🔍")):
                # הצגת הודעה על בחירה אוטומטית
                st.success(f"✅ נבחר אוטומטית: התאמה של {best_score}%")
                return i
    
    return 0

def render_guest_profile(cur):
    """מציג פרופיל מוזמן בעיצוב חדש"""
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
        key=f"manual_input_{st.session_state.get('idx', 0)}",
        label_visibility="collapsed"
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
        key=f"search_query_{st.session_state.get('idx', 0)}",
        label_visibility="collapsed"
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

def render_navigation_buttons():
    """מציג כפתורי ניווט קבועים למטה"""
    st.markdown('<div class="navigation-buttons">', unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        back_disabled = st.session_state.get("idx", 0) == 0
        back_btn = st.button(
            "⬅️ הקודם", 
            disabled=back_disabled, 
            key="back_btn"
        )
    
    with col2:
        # בדיקה אם יש ערך לשמירה
        can_save = st.session_state.get("can_save", False)
        next_btn = st.button(
            "✅ הבא ➡️", 
            disabled=not can_save, 
            type="primary",
            key="next_btn"
        )
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    return back_btn, next_btn

# ===============================
# הגדרות Streamlit וקונפיגורציה
# ===============================
config = AppConfig()
st.set_page_config(page_title=PAGE_TITLE, layout="wide")
print("🔄 RESPONSIVE VERSION - 2025")

# אתחול משתנים
if "upload_confirmed" not in st.session_state:
    st.session_state.upload_confirmed = False
if "show_guide" not in st.session_state:
    st.session_state.show_guide = False
if "idx" not in st.session_state:
    st.session_state.idx = 0
if "can_save" not in st.session_state:
    st.session_state.can_save = False

# טעינת CSS
load_css()

# בדיקת אימות
if not auth_flow():
    st.stop()

# הוספת כותרת אפליקציה
add_app_header()

# הצגת המדריך
show_download_guide()

# שלב העלאת קבצים
if not st.session_state.upload_confirmed:
    
    # במובייל - העלאה בתוכן הראשי
    if is_mobile():
        contacts_file, guests_file = show_file_upload()
        
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
            force_rerun()
    
    else:
        # במחשב - בסייד בר (הקוד הקיים)
        with st.sidebar:
            st.markdown('<div class="sidebar-header">📂 העלאת קבצים</div>', unsafe_allow_html=True)
            
            # קובץ אנשי קשר
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown("**👥 קובץ אנשי קשר**")
            with col2:
                if st.button("📖", key="guide_btn_desktop", help="מדריך"):
                    st.session_state.show_guide = True
                    st.rerun()
            
            contacts_file = st.file_uploader(
                "קובץ אנשי קשר", 
                type=["xlsx", "xls", "csv"], 
                key="contacts_uploader",
                label_visibility="collapsed"
            )
            
            if contacts_file:
                st.markdown("""
                <div class="file-uploaded">
                    <div class="file-uploaded-indicator">
                        <span>✅</span>
                        <span>קובץ אנשי קשר נטען</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            # קובץ מוזמנים
            st.markdown("**🎉 קובץ מוזמנים**")
            guests_file = st.file_uploader(
                "קובץ מוזמנים", 
                type=["xlsx", "xls", "csv"], 
                key="guests_uploader",
                label_visibility="collapsed"
            )
            
            if guests_file:
                st.markdown("""
                <div class="file-uploaded">
                    <div class="file-uploaded-indicator">
                        <span>✅</span>
                        <span>קובץ מוזמנים נטען</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            # כפתור אישור
            if st.button("✅ אשר קבצים", 
                        disabled=not (contacts_file and guests_file), 
                        type="primary",
                        key="confirm_files_btn"):
                
                try:
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
                    force_rerun()
                    
                except Exception as e:
                    st.error(f"❌ שגיאה בטעינת קבצים: {str(e)}")

# אם לא הושלמה העלאת קבצים - עצור כאן
if not st.session_state.upload_confirmed:
    st.stop()

# Sidebar עם פילטרים וניהול - רק במחשב
if not is_mobile():
    with st.sidebar:
        st.checkbox("רק חסרי מספר", key="filter_no", on_change=lambda: st.session_state.update(idx=0))

        filtered_df = st.session_state.guests.copy()
        if st.session_state.get("filter_no"):
            filtered_df = filtered_df[filtered_df[PHONE_COL].str.strip() == ""]

        all_sides = st.session_state.guests[SIDE_COL].dropna().unique().tolist()
        all_groups = st.session_state.guests[GROUP_COL].dropna().unique().tolist()

        st.multiselect("סנן לפי צד", options=all_sides, key="filter_sides")
        st.multiselect("סנן לפי קבוצה", options=all_groups, key="filter_groups")

        if st.session_state.get("filter_sides"):
            filtered_df = filtered_df[filtered_df[SIDE_COL].isin(st.session_state.filter_sides)]
        if st.session_state.get("filter_groups"):
            filtered_df = filtered_df[filtered_df[GROUP_COL].isin(st.session_state.filter_groups)]

        filtered_total = len(filtered_df)
        complete_idx = st.session_state.get("idx", 0)
        complete_idx = min(complete_idx, filtered_total)

        st.markdown(f"**{complete_idx}/{filtered_total} הושלמו**")
        st.progress(complete_idx / filtered_total if filtered_total else 0)

        st.download_button(
            "💾 הורד Excel",
            data=to_buf(filtered_df),
            file_name="רשימת_מסוננים.xlsx",
            use_container_width=True,
        )

# הכנת נתונים
filtered_df = st.session_state.guests.copy()
if st.session_state.get("filter_no"):
    filtered_df = filtered_df[filtered_df[PHONE_COL].str.strip() == ""]

# פילטרים נוספים
if st.session_state.get("filter_sides"):
    filtered_df = filtered_df[filtered_df[SIDE_COL].isin(st.session_state.filter_sides)]
if st.session_state.get("filter_groups"):
    filtered_df = filtered_df[filtered_df[GROUP_COL].isin(st.session_state.filter_groups)]

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

# הצגת התקדמות במובייל
if is_mobile():
    progress_pct = ((st.session_state.idx + 1) / len(df)) * 100
    st.markdown(f"""
    <div class="progress-bar">
        <div class="progress-text">מוזמן {st.session_state.idx + 1} מתוך {len(df)}</div>
        <div class="progress-track">
            <div class="progress-fill" style="width: {progress_pct:.1f}%"></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

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

# עדכון מצב שמירה
save_value = None
if manual_phone:
    save_value = normalize_phone_basic(manual_phone)
    st.session_state.can_save = save_value is not None
elif search_phone:
    save_value = search_phone
    st.session_state.can_save = True
elif choice.startswith("❌"):
    save_value = ""
    st.session_state.can_save = True
elif choice and not choice.startswith(("➕", "🔍")):
    save_value = extract_phone_from_choice(choice)
    st.session_state.can_save = True
else:
    st.session_state.can_save = False

# כפתורי ניווט
back_btn, next_btn = render_navigation_buttons()

# טיפול בלחיצות
if back_btn and st.session_state.idx > 0:
    st.session_state.idx -= 1
    st.session_state.can_save = False
    force_rerun()

if next_btn and st.session_state.can_save:
    # שמירת הערך
    formatted_phone = format_phone(save_value) if save_value else ""
    st.session_state.guests.at[cur.name, PHONE_COL] = formatted_phone
    
    # מעבר להבא
    st.session_state.idx += 1
    st.session_state.can_save = False
    force_rerun()
