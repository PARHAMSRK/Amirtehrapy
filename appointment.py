import os
import re
import random
import tempfile
import telebot
from telebot import types
from handlers.payment import clear_payment_pending, is_payment_pending
from database import (
    get_available_time_slots,
    create_appointment,
    get_user_language
)

user_booking_data = {}

# تعرفه ثابت خدمات مشاوره؛ مبلغ در رکورد نوبت نیز ذخیره می‌شود تا رسید و مدیریت
# همیشه بر اساس همان انتخاب واقعی کاربر عمل کنند.
SESSION_PRICING = {
    "40": {"duration_fa": "۴۰ دقیقه", "duration_en": "40 Minutes", "price_toman": 600000, "price_usd": 10},
    "60": {"duration_fa": "۶۰ دقیقه", "duration_en": "60 Minutes", "price_toman": 800000, "price_usd": 15},
    "80": {"duration_fa": "۸۰ دقیقه", "duration_en": "80 Minutes", "price_toman": 1000000, "price_usd": 20},
}

def _format_toman(amount):
    return f"{amount:,} تومان"

def _duration_label(key, lang):
    item = SESSION_PRICING[key]
    return item["duration_en"] if lang == "en" else item["duration_fa"]

# مسیر مرحله‌ای رزرو؛ فقط وضعیت رابط کاربر را نگه می‌دارد و داده‌های دیتابیس را تغییر نمی‌دهد.
booking_stage = {}


def _set_booking_stage(user_id, stage):
    booking_stage[user_id] = stage


def _clear_booking_stage(user_id):
    booking_stage.pop(user_id, None)


def _clear_user_step_handler(bot, chat_id):
    try:
        bot.clear_step_handler_by_chat_id(chat_id)
    except Exception:
        pass


def _navigation_markup(lang, include_main=True):
    markup = types.InlineKeyboardMarkup(row_width=2)
    return _add_navigation(markup, lang, include_main=include_main)


def _add_navigation(markup, lang, include_main=True):
    buttons = [
        types.InlineKeyboardButton(
            "🔙 Back" if lang == "en" else "🔙 بازگشت",
            callback_data="booking_back"
        )
    ]
    if include_main:
        buttons.append(
            types.InlineKeyboardButton(
                "🏠 Main Menu" if lang == "en" else "🏠 منوی اصلی",
                callback_data="booking_main"
            )
        )
    markup.add(*buttons)
    return markup


def _format_fee_button(item, key, lang):
    if lang == "en":
        return f"⏱ {item['duration_en']} Consultation / ${item['price_usd']} USD"
    return f"⏱ {item['duration_fa']} مشاوره / {_format_toman(item['price_toman'])}"


def _delete_message_safely(bot, chat_id, message_id):
    try:
        bot.delete_message(chat_id, message_id)
    except Exception:
        pass


def register_appointment_handlers(bot: telebot.TeleBot):

    # بخش درباره روانشناس
    @bot.callback_query_handler(func=lambda call: call.data == "about_psychologist")
    def send_psychologist_about(call):
        bot.answer_callback_query(call.id)
        chat_id = call.message.chat.id
        _delete_message_safely(bot, chat_id, call.message.message_id)
        user_id = call.from_user.id
        lang = get_user_language(user_id) or "fa"

        if lang == "en":
            about_text = (
                "🌿 **About AMIR PSYCHOLOGY Smart System**\n\n"
                "👨‍⚕️ **Hossein Moshaveri**\n"
                "• Psychology & Counseling Specialist\n"
                "• Documented professional background\n"
                "• Member of the Psychology and Counseling Organization\n\n"
                "📍 **Specialized Fields:** Individual / Family / Addiction / Hypnosis\n"
                "📞 Support: @Revenant1001\n\n"
                "The official professional resume is attached below."
            )
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(
                types.InlineKeyboardButton("💬 Contact Support", url="https://t.me/Revenant1001"),
                types.InlineKeyboardButton("🔙 Back", callback_data="back_to_main")
            )
        else:
            about_text = (
                "🌿 **درباره سیستم هوشمند AMIR PSYCHOLOGY**\n\n"
                "👨‍⚕️ **حسین مشاوری**\n"
                "• متخصص روانشناسی / مشاوره\n"
                "• دارای رزومه / سوابق مشخص\n"
                "• عضو سازمان نظام روان‌شناسی و مشاوره\n\n"
                "📍 **حوزه‌های تخصصی:** فردی / خانواده / اعتیاد / هیپنوتیزم\n"
                "📞 پشتیبانی: @Revenant1001\n\n"
                "رزومه جامع جهت مطالعه در فایل ارسالی :"
            )
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(
                types.InlineKeyboardButton("💬 ارتباط با پشتیبانی", url="https://t.me/Revenant1001"),
                types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")
            )

        bot.send_message(chat_id, about_text, parse_mode="Markdown", reply_markup=markup)

        # Resume file supplied separately by the project owner.
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        resume_candidates = [
            os.path.join(base_dir, "Amir Psychology.pdf"),
            os.path.join(base_dir, "Amir Psychology.docx"),
        ]
        resume_path = next((path for path in resume_candidates if os.path.isfile(path)), None)

        if resume_path:
            try:
                with open(resume_path, "rb") as resume_file:
                    bot.send_document(
                        chat_id,
                        resume_file,
                        caption="فایل رزومه رسمی متخصص" if lang != "en" else "Official Specialist Resume File"
                    )
            except Exception as e:
                print(f"Error sending resume file: {e}")
        else:
            # Do not fabricate a placeholder resume. The real file will be added later.
            print("Resume file not found: Amir Psychology.pdf / Amir Psychology.docx")

    # شروع رزرو نوبت (دو زبانه)
    @bot.callback_query_handler(func=lambda call: call.data == "appointment")
    def start_appointment(call):
        bot.answer_callback_query(call.id)
        _delete_message_safely(bot, call.message.chat.id, call.message.message_id)
        user_id = call.from_user.id
        lang = get_user_language(user_id) or "fa"
        slots = get_available_time_slots()
        
        if not slots:
            markup = types.InlineKeyboardMarkup()
            _add_navigation(markup, lang, include_main=False)
            bot.send_message(
                call.message.chat.id,
                "⏳ No available time slots at the moment." if lang=="en" else "⏳ در حال حاضر هیچ تایم خالی برای رزرو وجود ندارد.",
                reply_markup=markup
            )
            return

        markup = types.InlineKeyboardMarkup(row_width=1)
        for s_id, s_time in slots:
            markup.add(types.InlineKeyboardButton(f"🕰️ {s_time}", callback_data=f"book_slot_{s_id}"))
        _add_navigation(markup, lang, include_main=False)

        _set_booking_stage(user_id, "time")
        text_msg = "🗓 **Select Consultation Time:**\nPlease choose an available time slot:" if lang=="en" else "🗓 **انتخاب زمان مشاوره:**\n\nلطفاً یکی از تایم‌های آزاد زیر را انتخاب کنید:"
        bot.send_message(call.message.chat.id, text_msg, parse_mode="Markdown", reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("book_slot_"))
    def select_slot(call):
        bot.answer_callback_query(call.id)
        user_id = call.from_user.id
        lang = get_user_language(user_id) or "fa"
        
        slot_id = call.data.replace("book_slot_", "")
        selected_slot_time = next(
            (s_time for s_id, s_time in get_available_time_slots() if str(s_id) == str(slot_id)),
            None
        )

        # Validate the slot again at click time so a stale button cannot create
        # an appointment for a slot that is no longer available.
        if selected_slot_time is None:
            error_text = (
                "⚠️ This time slot is no longer available. Please return and choose another time."
                if lang == "en"
                else "⚠️ این تایم دیگر در دسترس نیست. لطفاً به مرحله انتخاب زمان برگردید و تایم دیگری را انتخاب کنید."
            )
            bot.send_message(call.message.chat.id, error_text)
            return

        user_booking_data[user_id] = {
            "slot_id": slot_id,
            "slot_time": selected_slot_time,
        }

        markup = types.InlineKeyboardMarkup(row_width=1)
        if lang == "en":
            markup.add(
                types.InlineKeyboardButton("👨‍👩‍👧 Family", callback_data="service_family"),
                types.InlineKeyboardButton("🧒 Child & Adolescent", callback_data="service_child"),
                types.InlineKeyboardButton("🧩 Addiction", callback_data="service_addiction"),
                types.InlineKeyboardButton("🧠 Depression & Anxiety", callback_data="service_anxiety"),
                types.InlineKeyboardButton("❔Initial Assessment / Not Sure", callback_data="service_other"),
                types.InlineKeyboardButton("🔙 Back", callback_data="booking_back"),
                types.InlineKeyboardButton("🏠 Main Menu", callback_data="booking_main")
            )
            msg_text = "🎯 **Select Consultation Specialty:**"
        else:
            markup.add(
                types.InlineKeyboardButton("👨‍👩‍👧 خانواده", callback_data="service_family"),
                types.InlineKeyboardButton("🧒 کودک و نوجوان", callback_data="service_child"),
                types.InlineKeyboardButton("🧩 اعتیاد", callback_data="service_addiction"),
                types.InlineKeyboardButton("🧠 افسردگی و اضطراب", callback_data="service_anxiety"),
                types.InlineKeyboardButton("❔بررسی اولیه / مطمئن نیستم", callback_data="service_other"),
                types.InlineKeyboardButton("🔙 بازگشت", callback_data="booking_back"),
                types.InlineKeyboardButton("🏠 منوی اصلی", callback_data="booking_main")
            )
            msg_text = "🎯 **انتخاب حوزه تخصصی مشاوره:**"

        bot.edit_message_text(msg_text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("service_"))
    def select_service_type(call):
        bot.answer_callback_query(call.id)
        user_id = call.from_user.id
        lang = get_user_language(user_id) or "fa"
        
        services_map_fa = {
            "service_family": "خانواده",
            "service_child": "کودک و نوجوان",
            "service_addiction": "اعتیاد",
            "service_anxiety": "افسردگی و اضطراب",
            "service_other": "بررسی اولیه / مطمئن نیستم"
        }
        services_map_en = {
            "service_family": "Family",
            "service_child": "Child & Adolescent",
            "service_addiction": "Addiction",
            "service_anxiety": "Depression & Anxiety",
            "service_other": "Initial Assessment / Not Sure"
        }
        
        c_type = services_map_en.get(call.data, "General") if lang == "en" else services_map_fa.get(call.data, "مشاوره عمومی")
        
        if user_id in user_booking_data:
            user_booking_data[user_id]["consultation_type"] = c_type

        # مدت جلسه و تعرفه در یک منوی مستقل و شفاف انتخاب می‌شود.
        markup = types.InlineKeyboardMarkup(row_width=1)
        if lang == "en":
            for key in ("40", "60", "80"):
                item = SESSION_PRICING[key]
                markup.add(types.InlineKeyboardButton(
                    _format_fee_button(item, key, lang),
                    callback_data=f"duration_{key}"
                ))
            markup.add(types.InlineKeyboardButton("🔙 Back", callback_data="booking_back"),
                types.InlineKeyboardButton("🏠 Main Menu", callback_data="booking_main"))
            prompt_text = (
                "💎 **Select Your Consultation Duration & Fee**\n\n"
                "Choose the session length that suits you. The selected fee will be shown again before payment."
            )
        else:
            for key in ("40", "60", "80"):
                item = SESSION_PRICING[key]
                markup.add(types.InlineKeyboardButton(
                    _format_fee_button(item, key, lang),
                    callback_data=f"duration_{key}"
                ))
            markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="booking_back"),
                types.InlineKeyboardButton("🏠 منوی اصلی", callback_data="booking_main"))
            prompt_text = (
                "💎 **انتخاب مدت جلسه و تعرفه**\n\n"
                "لطفاً مدت زمان موردنظر خود را انتخاب کنید. مبلغ انتخابی قبل از پرداخت نیز دوباره نمایش داده می‌شود."
            )

        _set_booking_stage(user_id, "duration")
        bot.edit_message_text(
            prompt_text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("duration_"))
    def select_duration(call):
        bot.answer_callback_query(call.id)
        user_id = call.from_user.id
        lang = get_user_language(user_id) or "fa"
        duration_key = call.data.replace("duration_", "", 1)
        item = SESSION_PRICING.get(duration_key)
        if not item:
            bot.answer_callback_query(call.id, "❌ گزینه تعرفه نامعتبر است.", show_alert=True)
            return

        data = user_booking_data.get(user_id)
        if not data or not data.get("slot_time"):
            bot.answer_callback_query(call.id, "⚠️ Booking information was not found. Please start the appointment process again.", show_alert=True)
            return

        data.update({
            "duration_key": duration_key,
            "duration": item["duration_en"] if lang == "en" else item["duration_fa"],
            "price_toman": item["price_toman"],
            "price_usd": item["price_usd"],
        })

        _set_booking_stage(user_id, "name")
        _delete_current_message(call)
        markup = types.InlineKeyboardMarkup()
        _add_navigation(markup, lang)
        prompt_text = (
            f"✍️ **Selected:** {item['duration_en']} Consultation / **${item['price_usd']} USD**\n\n"
            "Please enter your **Full Name**:\n*(At least 3 characters)*"
            if lang == "en" else
            f"✍️ **انتخاب شما:** {item['duration_fa']} مشاوره / **{_format_toman(item['price_toman'])}**\n\n"
            "لطفاً **نام و نام خانوادگی** کامل خود را ارسال کنید:\n*(حداقل ۳ کاراکتر)*"
        )
        msg = bot.send_message(call.message.chat.id, prompt_text, parse_mode="Markdown", reply_markup=markup)
        bot.register_next_step_handler(msg, get_user_name_step)

    def get_user_name_step(message):
        if message.text and message.text.startswith("/"):
            return
            
        user_id = message.from_user.id
        lang = get_user_language(user_id) or "fa"
        name = message.text.strip() if message.text else ""
        
        if len(name) < 3:
            markup = types.InlineKeyboardMarkup()
            _add_navigation(markup, lang)
            err_text = "⚠️ Invalid name. Please enter your full name (at least 3 characters):" if lang=="en" else "⚠️ نام وارد شده نامعتبر است. لطفاً نام و نام خانوادگی خود را کامل‌تر وارد کنید (حداقل ۳ کاراکتر):"
            msg = bot.send_message(message.chat.id, err_text, reply_markup=markup)
            bot.register_next_step_handler(msg, get_user_name_step)
            return

        if user_id in user_booking_data:
            user_booking_data[user_id]["name"] = name

        _set_booking_stage(user_id, "phone")
        markup = types.InlineKeyboardMarkup()
        _add_navigation(markup, lang)

        phone_prompt = "📞 Please send a valid **Phone Number** (e.g., `09123456789`):" if lang=="en" else "📞 لطفاً **شماره تماس** معتبر خود در ایران را ارسال کنید (مثلاً `09123456789`):"
        msg = bot.send_message(message.chat.id, phone_prompt, parse_mode="Markdown", reply_markup=markup)
        bot.register_next_step_handler(msg, get_user_phone_step)

    def get_user_phone_step(message):
        if message.text and message.text.startswith("/"):
            return

        user_id = message.from_user.id
        lang = get_user_language(user_id) or "fa"
        phone = message.text.strip() if message.text else ""
        
        iran_phone_pattern = r"^(09\d{9}|\+989\d{9})$"
        if not re.match(iran_phone_pattern, phone):
            markup = types.InlineKeyboardMarkup()
            _add_navigation(markup, lang)
            err_phone = "⚠️ Invalid phone format. Please enter correctly (e.g., 09123456789):" if lang=="en" else "⚠️ فرمت شماره تلفن نادرست است. لطفاً شماره موبایل خود را به شکل صحیح وارد کنید (مثلا 09123456789):"
            msg = bot.send_message(message.chat.id, err_phone, reply_markup=markup)
            bot.register_next_step_handler(msg, get_user_phone_step)
            return

        data = user_booking_data.get(user_id, {})
        data["phone"] = phone
        track_code = f"AMIR-{random.randint(10000, 99999)}"
        data["track_code"] = track_code

        try:
            create_appointment(
                user_id=user_id,
                consultation_type=data.get("consultation_type", "General Counseling" if lang == "en" else "مشاوره"),
                duration=data.get("duration") or ("60 Minutes" if lang == "en" else "۶۰ دقیقه"),
                preferred_time=data.get("slot_time") or (f"Slot ID: {data.get('slot_id')}" if lang == "en" else f"اسلات شناسه: {data.get('slot_id')}"),
                full_name=data.get("name"),
                phone=phone,
                track_code=track_code,
                price_toman=data.get("price_toman", 800000),
                price_usd=data.get("price_usd", 15)
            )

            _set_booking_stage(user_id, "payment_method")
            markup = types.InlineKeyboardMarkup(row_width=2)
            if lang == "en":
                markup.add(
                    types.InlineKeyboardButton("💳 Card-to-Card", callback_data="pay_card"),
                    types.InlineKeyboardButton("🪙 USDT-TRC20", callback_data="pay_usdt"),
                    types.InlineKeyboardButton("🔙 Back", callback_data="booking_back"),
                types.InlineKeyboardButton("🏠 Main Menu", callback_data="booking_main")
                )
                success_text = (
                    f"✅ **Your information has been successfully registered!**\n\n"
                    f"🆔 Tracking Code: `{track_code}`\n"
                    f"⏱ Session: {data.get('duration', '60 Minutes')}\n"
                    f"💰 Fee: ${data.get('price_usd', 15)} USD\n\n"
                    f"💳 Please choose your payment method to finalize the appointment:"
                )
            else:
                markup.add(
                    types.InlineKeyboardButton("💳 کارت به کارت", callback_data="pay_card"),
                    types.InlineKeyboardButton("🪙 USDT-TRC20", callback_data="pay_usdt"),
                    types.InlineKeyboardButton("🔙 بازگشت", callback_data="booking_back"),
                types.InlineKeyboardButton("🏠 منوی اصلی", callback_data="booking_main")
                )
                success_text = (
                    f"✅ **اطلاعات شما با موفقیت ثبت شد!**\n\n"
                    f"🆔 کد پیگیری: `{track_code}`\n"
                    f"⏱ مدت جلسه: {data.get('duration', '۶۰ دقیقه')}\n"
                    f"💰 تعرفه خدمات: {_format_toman(data.get('price_toman', 800000))}\n\n"
                    f"💳 لطفاً برای نهایی شدن رزرو، روش پرداخت خود را انتخاب کنید:"
                )

            bot.send_message(message.chat.id, success_text, parse_mode="Markdown", reply_markup=markup)
        except Exception as e:
            err_db = "⚠️ An error occurred. Please try again with /start." if lang=="en" else "⚠️ خطایی رخ داد. لطفاً مجدداً با دستور /start تلاش کنید."
            bot.send_message(message.chat.id, err_db)
            print(f"Error booking: {e}")

    def _delete_current_message(call):
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass

    def _show_time_menu(chat_id, user_id):
        lang = get_user_language(user_id) or "fa"
        slots = get_available_time_slots()
        markup = types.InlineKeyboardMarkup(row_width=1)
        for s_id, s_time in slots:
            markup.add(types.InlineKeyboardButton(f"🕰️ {s_time}", callback_data=f"book_slot_{s_id}"))
        _add_navigation(markup, lang, include_main=False)
        text_msg = "🗓 **Select Consultation Time:**\nPlease choose an available time slot:" if lang == "en" else "🗓 **انتخاب زمان مشاوره:**\n\nلطفاً یکی از تایم‌های آزاد زیر را انتخاب کنید:"
        _set_booking_stage(user_id, "time")
        bot.send_message(chat_id, text_msg, parse_mode="Markdown", reply_markup=markup)

    def _show_service_menu(chat_id, user_id):
        lang = get_user_language(user_id) or "fa"
        markup = types.InlineKeyboardMarkup(row_width=1)
        if lang == "en":
            markup.add(
                types.InlineKeyboardButton("👨‍👩‍👧 Family", callback_data="service_family"),
                types.InlineKeyboardButton("🧒 Child & Adolescent", callback_data="service_child"),
                types.InlineKeyboardButton("🧩 Addiction", callback_data="service_addiction"),
                types.InlineKeyboardButton("🧠 Depression & Anxiety", callback_data="service_anxiety"),
                types.InlineKeyboardButton("❔Initial Assessment / Not Sure", callback_data="service_other")
            )
            msg_text = "🎯 **Select Consultation Specialty:**"
        else:
            markup.add(
                types.InlineKeyboardButton("👨‍👩‍👧 خانواده", callback_data="service_family"),
                types.InlineKeyboardButton("🧒 کودک و نوجوان", callback_data="service_child"),
                types.InlineKeyboardButton("🧩 اعتیاد", callback_data="service_addiction"),
                types.InlineKeyboardButton("🧠 افسردگی و اضطراب", callback_data="service_anxiety"),
                types.InlineKeyboardButton("❔بررسی اولیه / مطمئن نیستم", callback_data="service_other")
            )
            msg_text = "🎯 **انتخاب حوزه تخصصی مشاوره:**"
        _add_navigation(markup, lang)
        _set_booking_stage(user_id, "service")
        bot.send_message(chat_id, msg_text, parse_mode="Markdown", reply_markup=markup)

    def _show_duration_menu(chat_id, user_id):
        lang = get_user_language(user_id) or "fa"
        markup = types.InlineKeyboardMarkup(row_width=1)
        for key in ("40", "60", "80"):
            item = SESSION_PRICING[key]
            markup.add(types.InlineKeyboardButton(_format_fee_button(item, key, lang), callback_data=f"duration_{key}"))
        _add_navigation(markup, lang)
        prompt_text = (
            "💎 **Select Your Consultation Duration & Fee**\n\nChoose the session length that suits you. The selected fee will be shown again before payment."
            if lang == "en" else
            "💎 **انتخاب مدت جلسه و تعرفه**\n\nلطفاً مدت زمان موردنظر خود را انتخاب کنید. مبلغ انتخابی قبل از پرداخت نیز دوباره نمایش داده می‌شود."
        )
        _set_booking_stage(user_id, "duration")
        bot.send_message(chat_id, prompt_text, parse_mode="Markdown", reply_markup=markup)

    def _show_name_prompt(chat_id, user_id):
        lang = get_user_language(user_id) or "fa"
        data = user_booking_data.get(user_id, {})
        item = SESSION_PRICING.get(data.get("duration_key", "60"), SESSION_PRICING["60"])
        markup = types.InlineKeyboardMarkup()
        _add_navigation(markup, lang)
        prompt = (
            f"✍️ **Selected:** {item['duration_en']} Consultation / **${item['price_usd']} USD**\n\nPlease enter your **Full Name**:\n*(At least 3 characters)*"
            if lang == "en" else
            f"✍️ **انتخاب شما:** {item['duration_fa']} مشاوره / **{_format_toman(item['price_toman'])}**\n\nلطفاً **نام و نام خانوادگی** کامل خود را ارسال کنید:\n*(حداقل ۳ کاراکتر)*"
        )
        _set_booking_stage(user_id, "name")
        msg = bot.send_message(chat_id, prompt, parse_mode="Markdown", reply_markup=markup)
        bot.register_next_step_handler(msg, get_user_name_step)

    def _show_phone_prompt(chat_id, user_id):
        lang = get_user_language(user_id) or "fa"
        markup = types.InlineKeyboardMarkup()
        _add_navigation(markup, lang)
        prompt = "📞 Please send a valid **Phone Number** (e.g., `09123456789`):" if lang == "en" else "📞 لطفاً **شماره تماس** معتبر خود در ایران را ارسال کنید (مثلاً `09123456789`):"
        _set_booking_stage(user_id, "phone")
        msg = bot.send_message(chat_id, prompt, parse_mode="Markdown", reply_markup=markup)
        bot.register_next_step_handler(msg, get_user_phone_step)

    def _show_payment_method_menu(chat_id, user_id):
        lang = get_user_language(user_id) or "fa"
        data = user_booking_data.get(user_id, {})
        track_code = data.get("track_code", "")
        duration = data.get("duration", "60 Minutes" if lang == "en" else "۶۰ دقیقه")
        price_toman = data.get("price_toman", 800000)
        price_usd = data.get("price_usd", 15)
        markup = types.InlineKeyboardMarkup(row_width=2)
        if lang == "en":
            markup.add(types.InlineKeyboardButton("💳 Card-to-Card", callback_data="pay_card"), types.InlineKeyboardButton("🪙 USDT-TRC20", callback_data="pay_usdt"))
            text = f"✅ **Your information has been successfully registered!**\n\n🆔 Tracking Code: `{track_code}`\n⏱ Session: {duration} / 💰 ${price_usd} USD\n\n💳 Please choose your payment method to finalize the appointment:"
        else:
            markup.add(types.InlineKeyboardButton("💳 کارت به کارت", callback_data="pay_card"), types.InlineKeyboardButton("🪙 USDT-TRC20", callback_data="pay_usdt"))
            text = f"✅ **اطلاعات شما با موفقیت ثبت شد!**\n\n🆔 کد پیگیری: `{track_code}`\n⏱ مدت جلسه: {duration} / 💰 {_format_toman(price_toman)}\n\n💳 لطفاً برای نهایی شدن رزرو، روش پرداخت خود را انتخاب کنید:"
        _add_navigation(markup, lang)
        _set_booking_stage(user_id, "payment_method")
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data == "booking_back")
    def booking_back(call):
        user_id = call.from_user.id
        lang = get_user_language(user_id) or "fa"
        current = "payment_info" if is_payment_pending(user_id) else booking_stage.get(user_id, "time")
        bot.answer_callback_query(
            call.id,
            "🔙 بازگشت به منوی قبل" if lang == "fa" else "🔙 Back to the previous menu",
            show_alert=True
        )
        _delete_current_message(call)
        _clear_user_step_handler(bot, call.message.chat.id)
        if current == "payment_info":
            clear_payment_pending(user_id)
            _show_payment_method_menu(call.message.chat.id, user_id)
        elif current == "payment_method":
            clear_payment_pending(user_id)
            _show_phone_prompt(call.message.chat.id, user_id)
        elif current == "phone":
            _show_name_prompt(call.message.chat.id, user_id)
        elif current == "name":
            _show_duration_menu(call.message.chat.id, user_id)
        elif current == "duration":
            _show_service_menu(call.message.chat.id, user_id)
        elif current == "service":
            _show_time_menu(call.message.chat.id, user_id)
        else:
            # Back from the first booking menu returns to the main menu.
            _clear_booking_stage(user_id)
            user_booking_data.pop(user_id, None)
            # The main menu is rendered by bot.py's registered callback.
            try:
                from bot import show_main_menu
                show_main_menu(call.message.chat.id, user_id)
            except Exception:
                pass

    @bot.callback_query_handler(func=lambda call: call.data == "booking_main")
    def booking_main(call):
        user_id = call.from_user.id
        lang = get_user_language(user_id) or "fa"
        bot.answer_callback_query(
            call.id,
            "🏠 بازگشت به منوی اصلی" if lang == "fa" else "🏠 Back to the main menu",
            show_alert=True
        )
        _delete_current_message(call)
        _clear_user_step_handler(bot, call.message.chat.id)
        clear_payment_pending(user_id)
        _clear_booking_stage(user_id)
        user_booking_data.pop(user_id, None)
        try:
            from bot import show_main_menu
            show_main_menu(call.message.chat.id, user_id)
        except Exception:
            pass
