import os
from dotenv import load_dotenv
import telebot
from telebot import types
from database import (
    get_pending_appointments,
    update_pending_appointment_status,
    get_admin_stats,
    get_connection,
    add_time_slot,
    get_available_time_slots,
    delete_time_slot,
    get_user_language
)

load_dotenv()
ADMIN_ID = os.getenv("ADMIN_ID")

def is_admin(user_id):
    if not ADMIN_ID:
        return False
    return str(user_id).strip() == str(ADMIN_ID).strip()

def register_admin_handlers(bot: telebot.TeleBot):

    def get_admin_keyboard():
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("📋 نوبت‌های در انتظار", callback_data="admin_pending"),
            types.InlineKeyboardButton("📊 آمار و گزارش درآمد", callback_data="admin_stats"),
            types.InlineKeyboardButton("👥 لیست مراجعین سیستم هوشمند", callback_data="admin_users"),
            types.InlineKeyboardButton("⏰ مدیریت زنده تایم‌های رزرو", callback_data="admin_slots_menu"),
        )
        return markup

    @bot.callback_query_handler(func=lambda call: call.data == "admin")
    def back_to_admin_panel(call):
        if not is_admin(call.from_user.id):
            return

        bot.answer_callback_query(call.id, "🔙 بازگشت به پنل مدیریت", show_alert=True)
        try:
            bot.edit_message_text(
                "👑 **پنل مدیریت جامع سیستم هوشمند AMIR PSYCHOLOGY**\n\nلطفاً بخش مورد نظر را انتخاب کنید:",
                call.message.chat.id,
                call.message.message_id,
                parse_mode="Markdown",
                reply_markup=get_admin_keyboard()
            )
        except Exception:
            bot.send_message(
                call.message.chat.id,
                "👑 **پنل مدیریت جامع سیستم هوشمند AMIR PSYCHOLOGY**\n\nلطفاً بخش مورد نظر را انتخاب کنید:",
                parse_mode="Markdown",
                reply_markup=get_admin_keyboard()
            )

    def admin_back_markup():
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("🔙 بازگشت به پنل مدیریت", callback_data="admin"))
        return markup

    @bot.message_handler(commands=["admin"])
    def admin_panel(message):
        user_id = message.from_user.id
        if not is_admin(user_id):
            bot.send_message(
                message.chat.id, 
                f"❌ **دسترسی غیرمجاز**\n\nآیدی تلگرام شما: `{user_id}`",
                parse_mode="Markdown"
            )
            return

        remove_kb = types.ReplyKeyboardRemove()
        bot.send_message(message.chat.id, "⚙️ در حال ورود به پنل مدیریت...", reply_markup=remove_kb)

        bot.send_message(
            message.chat.id,
            "👑 **پنل مدیریت جامع سیستم هوشمند AMIR PSYCHOLOGY**\n\nلطفاً بخش مورد نظر را انتخاب کنید:",
            parse_mode="Markdown",
            reply_markup=get_admin_keyboard()
        )

    @bot.callback_query_handler(func=lambda call: call.data == "admin_pending")
    def show_pending_appointments(call):
        if not is_admin(call.from_user.id):
            return

        bot.answer_callback_query(call.id)
        pending = get_pending_appointments()

        if not pending:
            bot.send_message(
                call.message.chat.id,
                "✅ هیچ نوبتِ در انتظار تاییدی وجود ندارد.",
                reply_markup=admin_back_markup()
            )
            return

        for app in pending:
            (
                app_id,
                u_id,
                c_type,
                duration,
                pref_time,
                name,
                phone,
                track_code,
                status,
                price_toman,
                price_usd,
                source,
                receipt_file_id,
                tx_text,
            ) = app

            source_label = "🌐 Web" if source == "web" else "🤖 Telegram"

            contact_line = (
                f"💬 **آیدی تلگرام:** `{u_id}`\\n"
                if source == "telegram"
                else "💬 **ارتباط تلگرامی:** ندارد (رزرو از Web)\\n"
            )

            msg_text = (
                f"🆔 **کد پیگیری:** `{track_code}`\\n"
                f"👤 **نام مراجع:** {name}\\n"
                f"📞 **شماره تماس:** `{phone}`\\n"
                f"{contact_line}"
                f"🌐 **منبع ثبت:** {source_label}\\n"
                f"📋 **نوع مشاوره:** {c_type}\\n"
                f"⏱ **مدت:** {duration}\\n"
                f"📅 **زمان ترجیحی:** {pref_time}\\n"
                f"💰 **تعرفه:** {price_toman:,} تومان | ${price_usd} USD"
            )

            if tx_text:
                msg_text += f"\\n\\n🔗 **TX / TXID:**\\n`{tx_text}`"

            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(
                types.InlineKeyboardButton(
                    "✅ تایید نوبت",
                    callback_data=f"confirm_app_{app_id}"
                )
            )
            markup.add(
                types.InlineKeyboardButton(
                    "❌ رد نوبت",
                    callback_data=f"reject_app_{app_id}"
                )
            )
            markup.add(
                types.InlineKeyboardButton(
                    "⏰ تغییر زمان نوبت",
                    callback_data=f"change_time_app_{app_id}"
                )
            )
            markup.add(
                types.InlineKeyboardButton(
                    "🔙 بازگشت به پنل مدیریت",
                    callback_data="admin"
                )
            )

            if receipt_file_id:
                try:
                    bot.send_photo(
                        call.message.chat.id,
                        receipt_file_id,
                        caption=msg_text,
                        parse_mode="Markdown",
                        reply_markup=markup
                    )
                except Exception as e:
                    print(f"خطا در ارسال رسید نوبت {app_id}: {e}")
                    bot.send_message(
                        call.message.chat.id,
                        msg_text,
                        parse_mode="Markdown",
                        reply_markup=markup
                    )
            else:
                bot.send_message(
                    call.message.chat.id,
                    msg_text,
                    parse_mode="Markdown",
                    reply_markup=markup
                )

    @bot.callback_query_handler(
        func=lambda call: (
            call.data.startswith("confirm_app_")
            or call.data.startswith("reject_app_")
            or call.data.startswith("change_time_app_")
        )
    )
    def handle_appointment_status(call):
        if not is_admin(call.from_user.id):
            return

        try:
            action, app_id_text = call.data.rsplit("_", 1)
            app_id = int(app_id_text)
        except (ValueError, AttributeError):
            bot.answer_callback_query(call.id, "❌ شناسه نوبت نامعتبر است.", show_alert=True)
            return

        status_map = {
            "confirm_app": "confirmed",
            "reject_app": "rejected",
            "change_time_app": "confirmed_time_change",
        }
        new_status = status_map.get(action)
        if not new_status:
            bot.answer_callback_query(call.id, "❌ عملیات نامعتبر است.", show_alert=True)
            return

        try:
            result = update_pending_appointment_status(app_id, new_status)
        except Exception as e:
            print(f"خطا در تغییر وضعیت نوبت {app_id}: {e}")
            bot.answer_callback_query(call.id, "⚠️ خطایی در ثبت وضعیت نوبت رخ داد.", show_alert=True)
            return

        if not result:
            bot.answer_callback_query(
                call.id,
                "⚠️ این نوبت قبلاً تعیین تکلیف شده یا دیگر در انتظار تایید نیست.",
                show_alert=True
            )
            return

        (
            appointment_id,
            user_id,
            consultation_type,
            duration,
            preferred_time,
            full_name,
            phone,
            track_code,
            final_status,
            price_toman,
            price_usd,
            source,
        ) = result
        bot.answer_callback_query(call.id, "✅ وضعیت نوبت ثبت شد.")

        user_lang = get_user_language(user_id) or "fa"
        if new_status == "confirmed":
            admin_text = f"✅ نوبت با کد پیگیری `{track_code}` تایید شد."
            user_msg = (
                "🎉 Your appointment with AMIR PSYCHOLOGY has been confirmed!\n\n"
                "Our support team will contact you for final coordination.\n"
                f"Tracking Code: #{track_code}"
                if user_lang == "en" else
                "🎉 نوبت شما در سیستم AMIR PSYCHOLOGY تایید شد!\n\n"
                "کاربر گرامی تیم پشتیبانی جهت هماهنگی نهایی با شما ارتباط خواهد گرفت\n"
                f"کد پیگیری: #{track_code}"
            )
        elif new_status == "confirmed_time_change":
            admin_text = f"⏰ درخواست تغییر زمان برای نوبت با کد پیگیری `{track_code}` ثبت شد."
            user_msg = (
                "🎉 Your appointment with AMIR PSYCHOLOGY has been confirmed, but unfortunately the consultation cannot be provided at your selected time.\n\n"
                "Our support team will contact you for final coordination.\n"
                f"Tracking Code: #{track_code}"
                if user_lang == "en" else
                "🎉 نوبت شما در سیستم AMIR PSYCHOLOGY تایید شد اما متاسفانه امکان ارائه مشاوره در زمان انتخابی شما وجود نداشت\n\n"
                "کاربر گرامی تیم پشتیبانی جهت هماهنگی نهایی با شما ارتباط خواهد گرفت.\n"
                f"کد پیگیری: #{track_code}"
            )
        else:
            admin_text = f"❌ نوبت با کد پیگیری `{track_code}` رد شد."
            user_msg = (
                "⚠️ Your appointment request was not accepted.\n\n"
                f"Tracking Code: #{track_code}"
                if user_lang == "en" else
                "⚠️ درخواست نوبت شما پذیرفته نشد.\n\n"
                f"کد پیگیری: #{track_code}"
            )

        source_label = "🌐 Web" if source == "web" else "🤖 Telegram"
        contact_line = (
            f"💬 **آیدی تلگرام:** `{user_id}`\n"
            if source == "telegram"
            else "💬 **ارتباط تلگرامی:** ندارد (رزرو از Web)\n"
        )

        final_admin_text = (
            f"{admin_text}\n\n"
            f"👤 **نام مراجع:** {full_name}\n"
            f"📞 **شماره تماس:** `{phone}`\n"
            f"{contact_line}"
            f"🌐 **منبع ثبت:** {source_label}\n"
            f"📋 **نوع مشاوره:** {consultation_type}\n"
            f"⏱ **مدت:** {duration}\n"
            f"📅 **زمان ترجیحی:** {preferred_time}\n"
            f"💰 **تعرفه:** {price_toman:,} تومان | ${price_usd} USD\n"
            f"🆔 **کد پیگیری:** `{track_code}`"
        )

        final_markup = types.InlineKeyboardMarkup(row_width=1)

        if source == "telegram":
            final_markup.add(
                types.InlineKeyboardButton(
                    "💬 ارتباط با کاربر",
                    url=f"tg://user?id={user_id}"
                )
            )

        final_markup.add(
            types.InlineKeyboardButton(
                "🔙 بازگشت به پنل مدیریت",
                callback_data="admin"
            )
        )

        try:
            if getattr(call.message, "content_type", None) == "photo":
                bot.edit_message_caption(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    caption=final_admin_text,
                    parse_mode="Markdown",
                    reply_markup=final_markup
                )
            else:
                bot.edit_message_text(
                    final_admin_text,
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode="Markdown",
                    reply_markup=final_markup
                )
        except Exception as e:
            # Database state is already committed; editing the admin message is secondary.
            print(f"خطا در ویرایش پیام پنل مدیریت برای نوبت {app_id}: {e}")

        if source == "telegram":
            try:
                bot.send_message(user_id, user_msg)
            except Exception as e:
                print(f"خطا در ارسال پیام وضعیت نوبت به کاربر {user_id}: {e}")

    @bot.callback_query_handler(func=lambda call: call.data == "admin_stats")
    def show_stats(call):
        if not is_admin(call.from_user.id):
            return

        bot.answer_callback_query(call.id)
        stats = get_admin_stats()
        
        stats_msg = (
            f"📊 **گزارش جامع و آمار سیستم هوشمند AMIR PSYCHOLOGY**\n\n"
            f"👥 **کل کاربران ثبت‌شده:** {stats['total_users']}\n"
            f"📅 **کل درخواست‌های نوبت:** {stats['total_appointments']}\n"
            f"⏳ **نوبت‌های در انتظار تایید:** {stats['pending_appointments']}\n\n"
            f"💰 **وضعیت درآمدهای سیستم هوشمند:** فعال (کارت به کارت و تتر USDT)"
        )
        bot.send_message(call.message.chat.id, stats_msg, parse_mode="Markdown", reply_markup=admin_back_markup())

    @bot.callback_query_handler(func=lambda call: call.data == "admin_users")
    def show_users_list(call):
        if not is_admin(call.from_user.id):
            return

        bot.answer_callback_query(call.id)
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, language, created_at FROM users ORDER BY created_at DESC LIMIT 10")
        users = cursor.fetchall()
        conn.close()

        if not users:
            bot.send_message(call.message.chat.id, "📭 هیچ کاربری هنوز در سیستم ثبت نشده است.")
            return

        msg = "👥 **آخرین مراجعین ثبت‌شده در ربات:**\n\n"
        for u in users:
            msg += f"• آیدی: `{u[0]}` | زبان: `{u[1]}` | تاریخ: `{u[2]}`\n"

        bot.send_message(call.message.chat.id, msg, parse_mode="Markdown", reply_markup=admin_back_markup())

    # مدیریت زنده تایم‌ها توسط امیر
    @bot.callback_query_handler(func=lambda call: call.data == "admin_slots_menu")
    def admin_slots_menu(call):
        if not is_admin(call.from_user.id):
            return
        bot.answer_callback_query(call.id)
        
        slots = get_available_time_slots()
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        for s_id, s_time in slots:
            markup.add(types.InlineKeyboardButton(f"❌ حذف تایم: {s_time}", callback_data=f"del_slot_{s_id}"))
            
        markup.add(types.InlineKeyboardButton("➕ افزودن تایم جدید", callback_data="add_slot_prompt"))
        markup.add(types.InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="admin"))
        
        bot.edit_message_text(
            "⏰ **مدیریت زنده تایم‌های پذیرش سیستم هوشمند**\n\nتایم‌های فعال زیر به صورت لحظه‌ای در بخش رزرو مراجعین نمایش داده می‌شوند:",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )

    @bot.callback_query_handler(func=lambda call: call.data == "add_slot_prompt")
    def prompt_add_slot(call):
        if not is_admin(call.from_user.id):
            return
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            call.message.chat.id,
            "✍️ لطفاً تایم جدید را به همراه روز و ساعت ارسال کنید (مثلاً: `پنجشنبه ساعت ۱۸:۰۰`):",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, save_new_slot_step)

    def save_new_slot_step(message):
        if not is_admin(message.from_user.id):
            return
        slot_text = message.text.strip()
        success = add_time_slot(slot_text)
        if success:
            bot.send_message(message.chat.id, f"✅ تایم `{slot_text}` با موفقیت به لیست زنده مراجعین اضافه شد.", parse_mode="Markdown", reply_markup=admin_back_markup())
        else:
            bot.send_message(message.chat.id, "⚠️ این تایم از قبل وجود دارد یا خطایی رخ داد.", reply_markup=admin_back_markup())

    @bot.callback_query_handler(func=lambda call: call.data.startswith("del_slot_"))
    def remove_slot(call):
        if not is_admin(call.from_user.id):
            return
        bot.answer_callback_query(call.id)
        slot_id = call.data.replace("del_slot_", "")
        delete_time_slot(slot_id)
        bot.send_message(call.message.chat.id, "🗑 تایم مورد نظر از لیست زنده مراجعین حذف شد.", reply_markup=admin_back_markup())