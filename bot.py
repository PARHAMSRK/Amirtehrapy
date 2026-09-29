import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import telebot
from telebot import types
from dotenv import load_dotenv

from database import init_db, set_user_language, get_user_language
from handlers.admin import register_admin_handlers
from handlers.appointment import register_appointment_handlers
from handlers.payment import register_payment_handlers, is_payment_pending, process_payment_text

load_dotenv()
TOKEN = os.getenv("TELEBOT_TOKEN")

if not TOKEN:
    raise ValueError("توکن ربات تلگرام در فایل .env یافت نشد!")

# راه‌اندازی سشن سفارشی با قابلیت Retry برای پایداری بیشتر روی پایتون‌انی‌ویر
session = requests.Session()
retries = Retry(total=5, backoff_factor=1, status_forcelist=[502, 503, 504])
session.mount('https://', HTTPAdapter(max_retries=retries))

bot = telebot.TeleBot(TOKEN, threaded=False)
bot.telebot_session = session

init_db()

register_admin_handlers(bot)
register_appointment_handlers(bot)
register_payment_handlers(bot)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id

    # During payment, /start must not break the payment flow.
    if is_payment_pending(user_id):
        process_payment_text(message)
        return

    current_lang = get_user_language(user_id)

    if not current_lang:
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("🇮🇷 فارسی", callback_data="set_lang_fa"),
            types.InlineKeyboardButton("🇬🇧 English", callback_data="set_lang_en")
        )
        bot.send_message(
            message.chat.id,
            "لطفاً زبان خود را انتخاب کنید / Please choose your language:",
            reply_markup=markup
        )
        return

    show_main_menu(message.chat.id, user_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("set_lang_"))
def set_language_callback(call):
    user_id = call.from_user.id
    lang = "fa" if call.data == "set_lang_fa" else "en"
    set_user_language(user_id, lang)
    bot.answer_callback_query(call.id, "✅ زبان تنظیم شد" if lang == "fa" else "✅ Language set")

    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass

    show_main_menu(call.message.chat.id, user_id)

@bot.callback_query_handler(func=lambda call: call.data == "change_language")
def change_language_menu(call):
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🇮🇷 فارسی", callback_data="set_lang_fa"),
        types.InlineKeyboardButton("🇬🇧 English", callback_data="set_lang_en"),
        types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")
    )
    bot.edit_message_text(
        "🌐 لطفاً زبان مورد نظر خود را انتخاب کنید:\nChoose your preferred language:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )

def show_main_menu(chat_id, user_id):
    lang = get_user_language(user_id) or "fa"

    markup = types.InlineKeyboardMarkup(row_width=2)
    if lang == "en":
        markup.add(
            types.InlineKeyboardButton("📅 Book Appointment", callback_data="appointment"),
            types.InlineKeyboardButton("💰 Service Pricing", callback_data="service_pricing"),
            types.InlineKeyboardButton("🌐 Change Language", callback_data="change_language"),
            types.InlineKeyboardButton("👨‍⚕️ About Psychologist", callback_data="about_psychologist"),
            types.InlineKeyboardButton("💬 Support", url="https://t.me/Revenant1001")
        )
        welcome_text = "Welcome to Smart Psychology / Counseling System 🌿 **AMIR PSYCHOLOGY**"
    else:
        markup.add(
            types.InlineKeyboardButton("📅 رزرو نوبت", callback_data="appointment"),
            types.InlineKeyboardButton("💰 تعرفه خدمات", callback_data="service_pricing"),
            types.InlineKeyboardButton("🌐 تغییر زبان", callback_data="change_language"),
            types.InlineKeyboardButton("👨‍⚕️ درباره روانشناس", callback_data="about_psychologist"),
            types.InlineKeyboardButton("💬 پشتیبانی", url="https://t.me/Revenant1001")
        )
        welcome_text = "به سیستم هوشمند روانشناسی / مشاوره 🌿 **AMIR PSYCHOLOGY** خوش آمدید"

    bot.send_message(chat_id, welcome_text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "service_pricing")
def show_service_pricing(call):
    user_id = call.from_user.id
    lang = get_user_language(user_id) or "fa"
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup(row_width=1)
    if lang == "en":
        text = (
            "💎 **AMIR PSYCHOLOGY — Consultation Fees**\n\n"
            "Please select a fee below for information only.\n"
            "The displayed fees are informational and are not a reservation."
        )
        markup.add(
            types.InlineKeyboardButton("⏱ 40 Minutes Consultation / $10 USD", callback_data="pricing_info_40"),
            types.InlineKeyboardButton("⏱ 60 Minutes Consultation / $15 USD", callback_data="pricing_info_60"),
            types.InlineKeyboardButton("⏱ 80 Minutes Consultation / $20 USD", callback_data="pricing_info_80"),
            types.InlineKeyboardButton("📅 Book Appointment", callback_data="appointment")
        )
        markup.add(types.InlineKeyboardButton("🏠 Main Menu", callback_data="pricing_main"))
    else:
        text = (
            "💎 **تعرفه خدمات AMIR PSYCHOLOGY**\n\n"
            "برای مشاهده جزئیات هر تعرفه، گزینه موردنظر را انتخاب کنید.\n"
            "این تعرفه‌ها صرفاً جهت اطلاع هستند و به معنی ثبت رزرو نیستند."
        )
        markup.add(
            types.InlineKeyboardButton("⏱ ۴۰ دقیقه مشاوره / ۶۰۰٬۰۰۰ تومان", callback_data="pricing_info_40"),
            types.InlineKeyboardButton("⏱ ۶۰ دقیقه مشاوره / ۸۰۰٬۰۰۰ تومان", callback_data="pricing_info_60"),
            types.InlineKeyboardButton("⏱ ۸۰ دقیقه مشاوره / ۱٬۰۰۰٬۰۰۰ تومان", callback_data="pricing_info_80"),
            types.InlineKeyboardButton("📅 رزرو نوبت", callback_data="appointment")
        )
        markup.add(types.InlineKeyboardButton("🏠 منوی اصلی", callback_data="pricing_main"))
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ["pricing_info_40", "pricing_info_60", "pricing_info_80"])
def pricing_info_notice(call):
    lang = get_user_language(call.from_user.id) or "fa"
    notice = (
        "جهت رزرو نوبت به منوی اصلی بازگردید!"
        if lang == "fa" else
        "To book an appointment, please return to the main menu!"
    )
    bot.answer_callback_query(call.id, text=notice, show_alert=True)


@bot.callback_query_handler(func=lambda call: call.data == "pricing_main")
def pricing_main(call):
    user_id = call.from_user.id
    lang = get_user_language(user_id) or "fa"
    bot.answer_callback_query(
        call.id,
        "🏠 بازگشت به منوی اصلی" if lang == "fa" else "🏠 Back to the main menu",
        show_alert=True
    )
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass
    show_main_menu(call.message.chat.id, user_id)


@bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
def back_to_main_menu(call):
    lang = get_user_language(call.from_user.id) or "fa"
    bot.answer_callback_query(
        call.id,
        "🔙 بازگشت به منوی اصلی" if lang == "fa" else "🔙 Back to the main menu",
        show_alert=True
    )
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass
    show_main_menu(call.message.chat.id, call.from_user.id)

@bot.message_handler(func=lambda message: True)
def handle_fallback_messages(message):
    # While waiting for payment proof, never send the user back to the main menu.
    if is_payment_pending(message.from_user.id):
        process_payment_text(message)
        return
    send_welcome(message)

if __name__ == "__main__":
    print("🤖 ربات سیستم هوشمند AMIR PSYCHOLOGY با موفقیت روشن شد و آماده به کار است...")
    try:
        bot.infinity_polling(
            timeout=60,
            long_polling_timeout=30,
            interval=2
        )
    except KeyboardInterrupt:
        print("\n🛑 ربات توسط کاربر به صورت امن متوقف شد.")