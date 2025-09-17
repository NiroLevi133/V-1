# whatsapp_utils.py - גרסה מתוקנת ומושלמת

import gspread
from google.oauth2 import service_account
import re

# הנתיב לקובץ ה־JSON בתוך Render
CREDENTIALS_PATH = "/etc/secrets/gcp_credentials.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

creds = service_account.Credentials.from_service_account_file(
    CREDENTIALS_PATH,
    scopes=SCOPES
)
gc = gspread.authorize(creds)

SPREADSHEET_ID = "1kMilBqKmldMBuvHtOdJsEGfo6Kb-J0W5rEXAhmG57b0"
sheet = gc.open_by_key(SPREADSHEET_ID).worksheet("גיליון1")


def parse_permission_message(message: str):
    """
    פענוח הודעת הרשאה מ-WhatsApp
    פורמט מצופה:
    - "הוסף [שם] [מספר טלפון]" או "add [name] [phone]"
    - "הסר [שם]" או "remove [name]"
    """
    if not message:
        return None
    
    message = message.strip()
    
    # דפוסי הוספה
    add_patterns = [
        r"הוסף\s+(.+?)\s+(0\d{8,9})",
        r"add\s+(.+?)\s+(0\d{8,9})",
        r"הוסף\s+(.+?)\s+(\d{10})",
        r"add\s+(.+?)\s+(\d{10})",
    ]
    
    for pattern in add_patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            phone = match.group(2).strip()
            return {
                "action": "add",
                "name": name,
                "phone": phone
            }
    
    # דפוסי הסרה
    remove_patterns = [
        r"הסר\s+(.+)",
        r"remove\s+(.+)",
        r"מחק\s+(.+)",
        r"delete\s+(.+)",
    ]
    
    for pattern in remove_patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            return {
                "action": "remove",
                "name": name
            }
    
    return None


def add_user_to_excel(name: str, phone: str):
    """הוספת משתמש לגיליון עם בדיקת כפילויות"""
    try:
        # בדוק אם המשתמש כבר קיים (לפי שם או מספר)
        existing = sheet.get_all_records()
        clean_new_phone = re.sub(r"\D", "", phone)
        
        for row in existing:
            existing_name = row.get("שם", "")
            existing_phone = str(row.get("טלפון", ""))
            clean_existing_phone = re.sub(r"\D", "", existing_phone)
            
            if existing_name == name:
                print(f"המשתמש {name} כבר קיים - מעדכן מספר טלפון.")
                # עדכן את המספר במקום להוסיף רשומה חדשה
                row_index = existing.index(row) + 2  # +2 כי Google Sheets מתחיל מ-1 ויש שורת כותרות
                sheet.update_cell(row_index, 2, phone)  # עמודה B (טלפון)
                print(f"המספר של {name} עודכן ל-{phone}")
                return
            
            if clean_new_phone == clean_existing_phone and clean_new_phone:
                print(f"המספר {phone} כבר קיים עבור {existing_name} - לא נוסף.")
                return

        # הוסף שורה חדשה
        sheet.append_row([name, phone])
        print(f"המשתמש {name} נוסף עם מספר {phone}.")
        
    except Exception as e:
        print(f"שגיאה בהוספת משתמש: {e}")


def remove_user_from_excel(name: str):
    """הסרת משתמש מהגיליון"""
    try:
        all_rows = sheet.get_all_values()
        
        for i, row in enumerate(all_rows):
            if row and len(row) > 0 and row[0] == name:
                sheet.delete_rows(i + 1)  # Google Sheets הוא 1-based
                print(f"המשתמש {name} נמחק.")
                return
        
        print(f"המשתמש {name} לא נמצא.")
        
    except Exception as e:
        print(f"שגיאה בהסרת משתמש: {e}")


def list_all_users():
    """הצגת כל המשתמשים הרשומים"""
    try:
        records = sheet.get_all_records()
        print(f"📋 רשימת משתמשים מורשים ({len(records)} משתמשים):")
        print("-" * 50)
        
        for i, row in enumerate(records, 1):
            name = row.get("שם", "ללא שם")
            phone = row.get("טלפון", "ללא טלפון")
            print(f"{i:2d}. {name:20} | {phone}")
            
        return records
        
    except Exception as e:
        print(f"שגיאה בקריאת רשימת משתמשים: {e}")
        return []


def is_user_authorized(phone: str) -> bool:
    """בדיקה האם משתמש מורשה"""
    try:
        records = sheet.get_all_records()
        clean_phone = re.sub(r"\D", "", phone)
        
        for row in records:
            existing_phone = str(row.get("טלפון", ""))
            clean_existing_phone = re.sub(r"\D", "", existing_phone)
            
            if clean_phone == clean_existing_phone:
                return True
        
        return False
        
    except Exception as e:
        print(f"שגיאה בבדיקת הרשאה: {e}")
        return False


# פונקציות עזר נוספות
def normalize_phone(phone: str) -> str:
    """נורמליזציה של מספר טלפון"""
    if not phone:
        return ""
    
    # הסר כל מה שלא ספרה
    digits = re.sub(r"\D", "", phone)
    
    # המר מפורמט בינלאומי לישראלי
    if digits.startswith("972"):
        digits = "0" + digits[3:]
    
    return digits


def validate_phone(phone: str) -> bool:
    """בדיקת תקינות מספר טלפון ישראלי"""
    normalized = normalize_phone(phone)
    
    # בדוק פורמט ישראלי: 10 ספרות המתחילות ב-05
    if re.match(r"^05\d{8}$", normalized):
        return True
    
    return False


# בדיקת הקובץ אם רץ ישירות
if __name__ == "__main__":
    print("🧪 בדיקת whatsapp_utils.py")
    
    # בדיקת חיבור
    try:
        count = len(sheet.get_all_records())
        print(f"✅ חיבור תקין - נמצאו {count} משתמשים")
        
        # הצג רשימה
        list_all_users()
        
    except Exception as e:
        print(f"❌ שגיאה בחיבור: {e}")
    
    # בדיקת פענוח הודעות
    test_messages = [
        "הוסף יוסי כהן 0501234567",
        "add john doe 0529876543",
        "הסר יוסי כהן",
        "remove john doe"
    ]
    
    print("\n🧪 בדיקת פענוח הודעות:")
    for msg in test_messages:
        result = parse_permission_message(msg)
        print(f"'{msg}' -> {result}")