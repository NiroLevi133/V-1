# webhook_server.py - גרסה מתוקנת ומושלמת

from flask import Flask, request, jsonify
from whatsapp_utils import parse_permission_message, add_user_to_excel, remove_user_from_excel, list_all_users
import logging

# הגדרת logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    """Webhook לקבלת הודעות מ-Green API"""
    try:
        data = request.json
        logger.info(f"📩 הודעה נכנסה: {data}")

        # זה המבנה האמיתי של ההודעה מה-Green API
        message_data = data.get("messageData", {})
        text_data = message_data.get("textMessageData", {})
        message = text_data.get("textMessage", "")
        
        # מידע נוסף על השולח
        sender_data = data.get("senderData", {})
        sender_name = sender_data.get("senderName", "לא ידוע")
        sender_id = sender_data.get("chatId", "")
        
        if not message:
            logger.warning("הודעה ללא תוכן טקסט")
            return jsonify({"status": "ignored", "reason": "no message"})

        logger.info(f"📝 הודעה מ-{sender_name} ({sender_id}): {message}")

        # פענוח ההודעה
        parsed_result = parse_permission_message(message)
        
        if parsed_result:
            action = parsed_result["action"]
            
            if action == "add":
                name = parsed_result["name"]
                phone = parsed_result["phone"]
                add_user_to_excel(name, phone)
                logger.info(f"✅ נוסף: {name} ({phone})")
                
                return jsonify({
                    "status": "success",
                    "action": "add",
                    "message": f"המשתמש {name} נוסף בהצלחה",
                    "parsed": parsed_result
                })
                
            elif action == "remove":
                name = parsed_result["name"]
                remove_user_from_excel(name)
                logger.info(f"❌ הוסר: {name}")
                
                return jsonify({
                    "status": "success", 
                    "action": "remove",
                    "message": f"המשתמש {name} הוסר בהצלחה",
                    "parsed": parsed_result
                })
                
        else:
            logger.warning("⚠️ לא זוהתה פעולה מתאימה")
            return jsonify({
                "status": "ignored", 
                "reason": "no match",
                "message": message,
                "help": "פורמט נכון: 'הוסף [שם] [טלפון]' או 'הסר [שם]'"
            })
            
    except Exception as e:
        logger.error(f"❌ שגיאה בעיבוד webhook: {e}")
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    """בדיקת תקינות השרת"""
    return jsonify({
        "status": "healthy",
        "message": "Webhook server is running"
    })

@app.route('/users', methods=['GET'])
def get_users():
    """קבלת רשימת כל המשתמשים המורשים"""
    try:
        users = list_all_users()
        return jsonify({
            "status": "success",
            "users": users,
            "count": len(users)
        })
    except Exception as e:
        logger.error(f"❌ שגיאה בקריאת משתמשים: {e}")
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

@app.route('/test', methods=['POST'])
def test_parse():
    """בדיקת פענוח הודעה"""
    try:
        data = request.json
        message = data.get("message", "")
        
        result = parse_permission_message(message)
        
        return jsonify({
            "status": "success",
            "message": message,
            "parsed": result,
            "valid": result is not None
        })
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

if __name__ == "__main__":
    logger.info("🚀 Webhook server starting...")
    
    # בדיקה ראשונית
    try:
        from whatsapp_utils import sheet
        count = len(sheet.get_all_records())
        logger.info(f"✅ חיבור לגוגל שיטס תקין - {count} משתמשים רשומים")
    except Exception as e:
        logger.error(f"❌ שגיאה בחיבור לגוגל שיטס: {e}")
    
    logger.info("🚀 Webhook server started on http://127.0.0.1:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)