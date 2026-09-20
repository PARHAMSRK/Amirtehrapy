import os
import sqlite3
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

TOKEN = "8770717041:AAGyJyV2aHz2Bb8CXBXYBfmU2ZL8a29KjW8"
ADMIN_ID = 6336833078

# مسیر دیتابیس (می‌تواند به دیتابیس مشترک یا ابری متصل شود)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "database.db")

bot = telebot.TeleBot(TOKEN)

MESSAGES = {
    'fa': {
        'welcome_admin': (
            "🌿 **سلام و درود، استاد AMIR MOSHAVERI عزیز!**\n\n"
            "به پنل مدیریت کلینیک **AMIR PSYCARE** خوش آمدید. ✨"
        ),
        'welcome_client': (
            "🌿 **به کلینیک تخصصی روانشناختی AMIR PSYCARE خوش آمدید.**\n\n"
            "جهت رزرو نوبت مشاوره آنلاین، از دکمه زیر استفاده کنید:"
        ),
        'btn_book': "📅 درخواست وقت مشاوره / Book Session",
        'btn_contact': "💬 ارتباط با پشتیبانی / مدیریت",
        'btn_lang': "🌐 تغییر زبان / Change Language",
        'btn_reports': "📊 پنل گزارش‌ها و مالی",
        'btn_stats': "📈 آمار سریع رزروها",
        'btn_webapp': "🌐 ورود به وب‌اپلیکیشن",
        'lang_set': "✅ زبان شما با موفقیت روی **فارسی** تنظیم شد."
    },
    'en': {
        'welcome_admin': (
            "🌿 **Welcome, Dr. AMIR MOSHAVERI!**\n\n"
            "Welcome to the **AMIR PSYCARE** Management Panel. ✨"
        ),
        'welcome_client': (
            "🌿 **Welcome to AMIR PSYCARE Clinic.**\n\n"
            "Please use the button below to book an online consultation:"
        ),
        'btn_book': "📅 Book a Session",
        'btn_contact': "💬 Contact Support / Admin",
        'btn_lang': "🌐 Change Language / تغییر زبان",
        'btn_reports': "📊 Financial & Reports Panel",
        'btn_stats': "📈 Quick Statistics",
        'btn_webapp': "🌐 Open Web App",
        'lang_set': "✅ Your language has been set to **English**."
    }
}

def get_user_lang(user_id):
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT language FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else 'fa'
    except Exception:
        return 'fa'

def set_user_lang(user_id, lang):
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO users (user_id, language) VALUES (?, ?)", (user_id, lang))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"DB Error: {e}")

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    lang = get_user_lang(user_id)
    msg = MESSAGES.get(lang, MESSAGES['fa'])
    
    if int(user_id) == int(ADMIN_ID):
        markup = InlineKeyboardMarkup(row_width=2)
        btn_reports = InlineKeyboardButton(msg['btn_reports'], url="https://Amirtherapy.pythonanywhere.com/reports")
        btn_stats = InlineKeyboardButton(msg['btn_stats'], callback_data="admin_stats")
        btn_web_app = InlineKeyboardButton(msg['btn_webapp'], web_app=WebAppInfo(url="https://Amirtherapy.pythonanywhere.com"))
        markup.add(btn_reports, btn_stats, btn_web_app)
        bot.send_message(message.chat.id, msg['welcome_admin'], parse_mode="Markdown", reply_markup=markup)
    else:
        markup = InlineKeyboardMarkup(row_width=1)
        btn_app = InlineKeyboardButton(msg['btn_book'], web_app=WebAppInfo(url=f"https://Amirtherapy.pythonanywhere.com?lang={lang}"))
        btn_contact = InlineKeyboardButton(msg['btn_contact'], url="https://t.me/Revenant1001")
        markup.add(btn_app, btn_contact)
        bot.send_message(message.chat.id, msg['welcome_client'], parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "admin_stats")
def show_admin_stats(call):
    if int(call.from_user.id) == int(ADMIN_ID):
        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*), status FROM appointments GROUP BY status")
            stats = cursor.fetchall()
            conn.close()

            stats_msg = "📊 **آمار سریع سیستم AMIR PSYCARE:**\n\n"
            if stats:
                for count, status in stats:
                    stats_msg += f"• وضعیت `{status}`: *{count}* نوبت\n"
            else:
                stats_msg += "هنوز رزروی در سیستم ثبت نشده است."

            bot.answer_callback_query(call.id)
            bot.send_message(call.message.chat.id, stats_msg, parse_mode="Markdown")
        except Exception:
            bot.answer_callback_query(call.id, "خطا در دریافت آمار!")

if __name__ == "__main__":
    print("Bot is running in polling mode...")
    bot.infinity_polling()