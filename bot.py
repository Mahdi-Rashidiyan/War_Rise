import telebot
from settings import CHANNEL_ID, NEWS_CHANNEL_ID, TELEGRAM_MAINBOT_API
from telebot.types import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup

bot = telebot.TeleBot(token=TELEGRAM_MAINBOT_API)
bot.set_my_commands([
    BotCommand("start", "شروع و نمایش منو اصلی"),
    BotCommand("inv", "نمایش موجودی، اقتصاد و سرمایه‌گذاری کشور"),
    BotCommand("spy", "منوی عملیات جاسوسی و ضدجاسوسی"),
    BotCommand("dip", "منوی دیپلماسی و اتحادها"),
    BotCommand("statement", "ارسال بیانیه به کانال"),
])
def format_news_post(title, message):
    return (
        "📰 WAR RISE NEWS\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 {title}\n\n"
        f"{message}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "⚔️ Game Update"
    )


def publish_game_news(title, message):
    bot.send_message(NEWS_CHANNEL_ID, format_news_post(title, message))


user_data = {}

markup = InlineKeyboardMarkup(row_width=1)
btn_attack = InlineKeyboardButton("درخواست حمله", callback_data="attack")
btn_statement = InlineKeyboardButton("ارسال بیانیه به کانال", callback_data="statement")

markup.add(btn_attack, btn_statement)

@bot.message_handler(commands=["start"])
def welcome_war(message):
    bot.send_message(
        message.chat.id,
        "به بات بازی خوش امدید \n لطفا یکی از بخش های زیر را انتخاب کنید: ",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "attack")
def start_attack_from_main(call):
    bot.answer_callback_query(call.id, "در حال اجرای درخواست حمله...")
    bot.send_message(
        call.message.chat.id,
        "⚔️ برای شروع درخواست حمله، در بات جنگ دستور /hamle را اجرا کنید.\nاین بات فقط برای منو اصلی و پیام‌رسانی عمومی است.",
    )
    bot.send_message(
        call.message.chat.id,
        "🧭 دستورات موجود در این بات:\n/start - شروع و نمایش منو\n/inv - موجودی و اقتصاد\n/spy - جاسوسی\n/dip - دیپلماسی\n/statement - ارسال بیانیه به کانال",
    )


@bot.callback_query_handler(func=lambda call: call.data == "statement")
def start_statement(call):
    user_id = call.from_user.id
    user_data[user_id] = {"state": "awaiting_statement",
                          "photo": None,
                          "text": None}
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "لطفا اول عکس بیانیه را ارسال کنید.")

@bot.message_handler(content_types=["photo"])
def recive_photo(message):
    user_id = message.from_user.id
    if user_id not in user_data:
        return 
    if user_data[user_id]["state"] != "awaiting_statement":
        return
    photo = message.photo[-1]
    user_data[user_id]["photo"] = photo.file_id
    user_data[user_id]["state"] = "awaiting_text"
    bot.send_message(message.chat.id, "عکس دریافت شد. لطفا متن بیانیه را ارسال کنید.")

@bot.message_handler(content_types=["text"])
def receive_text(message):
    user_id = message.from_user.id
    if user_id not in user_data:
        return
    if user_data[user_id]["state"] != "awaiting_text":
        return
    text = message.text
    user_data[user_id]["text"] = text
    user_data[user_id]["state"] = "confirm"

    markup = InlineKeyboardMarkup(row_width=1)
    confirm_btn = InlineKeyboardButton("تایید ارسال بیانیه", callback_data="confirm_statement")
    edit_btn = InlineKeyboardButton("ویرایش متن بیانیه", callback_data="edit_statement")
    markup.add(confirm_btn, edit_btn)

    bot.send_photo(message.chat.id,
                   photo=user_data[user_id]["photo"],
                   caption=f"متن بیانیه:\n\n{text}", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "confirm_statement")
def confirm_statement(call):
    user_id = call.from_user.id
    if user_id not in user_data:
        bot.answer_callback_query(call.id, "خطا: داده کاربر یافت نشد.")
        return
    data = user_data[user_id]
    bot.send_photo(CHANNEL_ID, photo=data["photo"], caption=data["text"])
    bot.answer_callback_query(call.id, "بیانیه با موفقیت ارسال شد.")
    bot.send_message(call.message.chat.id, "بیانیه با موفقیت به کانال ارسال شد.")

    del user_data[user_id]

@bot.callback_query_handler(func=lambda call: call.data == "edit_statement")
def edit_statement(call):
    user_id = call.from_user.id
    if user_id not in user_data:
        bot.answer_callback_query(call.id, "خطا: داده کاربر یافت نشد.")
        return
    user_data[user_id]["state"] = "awaiting_text"
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "لطفا متن جدید بیانیه را ارسال کنید.")


print("Bot is running...")

bot.infinity_polling()