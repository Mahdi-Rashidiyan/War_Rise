import telebot
from telebot.types import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup

import database
from settings import TELEGRAM_BOT_DIP_API

bot = telebot.TeleBot(TELEGRAM_BOT_DIP_API)
bot.set_my_commands([
    BotCommand("dip", "منوی دیپلماسی و اتحادها"),
    BotCommand("diplomacy", "همان منوی دیپلماسی"),
    BotCommand("start", "شروع و نمایش منو اصلی"),
])
user_states = {}


def get_country_from_chat(chat_id):
    return database.get_country_by_group(chat_id)


def format_alliance_text(alliance, members=None):
    members = members or []
    member_names = ", ".join(m["name"] for m in members) if members else "بدون عضو"
    founder = database.get_country(alliance["founder_country_id"])
    founder_name = founder["name"] if founder else "نامشخص"
    return f"🏛️ {alliance['name']}\n👑 رهبر: {founder_name}\n👥 اعضا: {member_names}"


def get_main_menu():
    markup = InlineKeyboardMarkup(row_width=1)
    buttons = [
        ("🏛️ ساخت اتحاد", "dip_create_alliance"),
        ("📜 نمایش اتحادها", "dip_list_alliances"),
        ("🤝 درخواست عضویت", "dip_request_join"),
        ("✅ بررسی درخواست‌های عضویت", "dip_pending_join_requests"),
        ("🤝 درخواست قرارداد میان اتحادها", "dip_request_agreement"),
        ("✅ بررسی قراردادهای در انتظار", "dip_pending_agreements"),
        ("🗣️ شروع مذاکره", "dip_request_negotiation"),
        ("📨 مذاکره فعال", "dip_active_negotiation"),
        ("🛑 پایان مذاکره", "dip_end_negotiation"),
    ]
    for text, callback in buttons:
        markup.add(InlineKeyboardButton(text, callback_data=callback))
    return markup


def get_alliance_request_menu(country):
    alliances = database.get_alliances()
    markup = InlineKeyboardMarkup(row_width=1)
    if not alliances:
        markup.add(InlineKeyboardButton("❌ اتحاد موجود نیست", callback_data="no_action"))
        return markup

    current_alliances = {a["id"] for a in database.get_country_alliances(country["id"])}
    for alliance in alliances:
        if alliance["id"] in current_alliances:
            continue
        markup.add(
            InlineKeyboardButton(f"🤝 {alliance['name']}", callback_data=f"dip_join_alliance:{alliance['id']}")
        )

    if not markup.keyboard:
        markup.add(InlineKeyboardButton("⚠️ شما در هیچ اتحادیه‌ای نیستید", callback_data="no_action"))
    return markup


@bot.message_handler(commands=["dip", "diplomacy"])
def diplomacy_start(message):
    country = get_country_from_chat(message.chat.id)
    if not country:
        bot.reply_to(message, "⚠️ این گروه به کشور اختصاص ندارد. ابتدا گروه را به کشوری وصل کنید.")
        return

    text = (
        f"🌍 پنل دیپلماسی برای کشور {country['name']}\n"
        "انتخاب کنید:"
    )
    bot.send_message(message.chat.id, text, reply_markup=get_main_menu())


@bot.callback_query_handler(func=lambda call: call.data == "dip_create_alliance")
def create_alliance_prompt(call):
    country = get_country_from_chat(call.message.chat.id)
    if not country:
        bot.answer_callback_query(call.id, "گروه به کشوری متصل نیست.")
        return

    user_states.setdefault(call.from_user.id, {})
    user_states[call.from_user.id]["state"] = "awaiting_alliance_name"
    user_states[call.from_user.id]["country_id"] = country["id"]

    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "🏛️ نام اتحاد جدید را ارسال کنید:")


@bot.callback_query_handler(func=lambda call: call.data == "dip_list_alliances")
def list_alliances(call):
    alliances = database.get_alliances()
    if not alliances:
        bot.answer_callback_query(call.id, "هیچ اتحادیه‌ای در بازی وجود ندارد.")
        return

    lines = []
    for alliance in alliances:
        members = database.get_alliance_members(alliance["id"])
        lines.append(format_alliance_text(alliance, members))

    text = "📜 لیست اتحادها\n\n" + "\n\n".join(lines)
    bot.send_message(call.message.chat.id, text)
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data == "dip_request_join")
def request_join_menu(call):
    country = get_country_from_chat(call.message.chat.id)
    if not country:
        bot.answer_callback_query(call.id, "گروه به کشوری متصل نیست.")
        return

    if database.get_country_alliances(country["id"]):
        bot.answer_callback_query(call.id, "شما قبلاً عضو یکی از اتحادها هستید.")
        bot.send_message(call.message.chat.id, "شما قبلاً عضو یک اتحاد هستید؛ برای عضویت جدید باید از اتحاد قبلی خارج شوید.")
        return

    markup = get_alliance_request_menu(country)
    bot.send_message(call.message.chat.id, "🤝 اتحادیه‌ای را برای درخواست عضویت انتخاب کنید:", reply_markup=markup)
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data.startswith("dip_join_alliance:"))
def join_alliance(call):
    country = get_country_from_chat(call.message.chat.id)
    if not country:
        bot.answer_callback_query(call.id, "گروه به کشوری متصل نیست.")
        return

    alliance_id = int(call.data.split(":", 1)[1])
    alliance = database.get_alliance(alliance_id)
    if not alliance:
        bot.answer_callback_query(call.id, "اتحاد پیدا نشد.")
        return

    database.create_alliance_join_request(alliance_id, country["id"], "درخواست عضویت از طریق بات دیپلماسی")

    founder_group = database.get_group_by_country(alliance["founder_country_id"])
    if founder_group:
        bot.send_message(
            founder_group,
            f"📥 درخواست عضویت جدید برای اتحاد {alliance['name']}\n"
            f"کشور: {country['name']}\n\n"
            "برای تایید یا رد از پنل دیپلماسی استفاده کنید."
        )

    bot.answer_callback_query(call.id, "درخواست عضویت شما ثبت شد.")
    bot.send_message(call.message.chat.id, f"✅ درخواست عضویت شما برای اتحاد {alliance['name']} ثبت شد.")


@bot.callback_query_handler(func=lambda call: call.data == "dip_pending_join_requests")
def pending_join_requests(call):
    country = get_country_from_chat(call.message.chat.id)
    if not country:
        bot.answer_callback_query(call.id, "گروه به کشوری متصل نیست.")
        return

    alliances = database.get_country_alliances(country["id"])
    if not alliances:
        bot.answer_callback_query(call.id, "شما رهبر هیچ اتحادیه‌ای نیستید.")
        return

    markup = InlineKeyboardMarkup(row_width=1)
    sent_any = False

    for alliance in alliances:
        requests = database.get_pending_join_requests_for_alliance(alliance["id"])
        if not requests:
            continue

        sent_any = True
        for request in requests:
            markup.add(
                InlineKeyboardButton(
                    f"✅ {request['country_name']} -> {alliance['name']}",
                    callback_data=f"accept_join_request:{request['id']}"
                )
            )

    if not sent_any:
        bot.send_message(call.message.chat.id, "درخواستی برای عضویت در اتحادهای شما وجود ندارد.")
        bot.answer_callback_query(call.id)
        return

    bot.send_message(call.message.chat.id, "📩 درخواست‌های عضویت در اتحادهای شما:", reply_markup=markup)
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data.startswith("accept_join_request:"))
def accept_join_request(call):
    request_id = int(call.data.split(":", 1)[1])
    country = get_country_from_chat(call.message.chat.id)
    if not country:
        bot.answer_callback_query(call.id, "گروه به کشوری متصل نیست.")
        return

    with database.get_connection() as conn:
        row = conn.execute(
            "SELECT ajr.*, a.name AS alliance_name, a.founder_country_id "
            "FROM alliance_join_requests ajr "
            "JOIN alliances a ON a.id = ajr.alliance_id "
            "WHERE ajr.id = ? AND ajr.status = 'pending'",
            (request_id,),
        ).fetchone()

        if not row:
            bot.answer_callback_query(call.id, "درخواست معتبر نیست.")
            return

        if row["founder_country_id"] != country["id"]:
            bot.answer_callback_query(call.id, "فقط رهبر اتحاد می‌تواند این درخواست را تایید کند.")
            return

        conn.execute(
            "INSERT OR IGNORE INTO alliance_members (alliance_id, country_id, joined_at) VALUES (?, ?, ?)",
            (row["alliance_id"], row["country_id"], database.now()),
        )
        conn.execute("UPDATE alliance_join_requests SET status = 'accepted' WHERE id = ?", (request_id,))

    bot.answer_callback_query(call.id, "درخواست عضویت پذیرفته شد.")
    bot.send_message(call.message.chat.id, f"✅ درخواست عضویت پذیرفته شد برای اتحاد {row['alliance_name']}.")

    target_group = database.get_group_by_country(row["country_id"])
    if target_group:
        bot.send_message(target_group, f"✅ شما به اتحاد {row['alliance_name']} اضافه شدید.")


@bot.callback_query_handler(func=lambda call: call.data == "dip_request_agreement")
def request_agreement_menu(call):
    country = get_country_from_chat(call.message.chat.id)
    if not country:
        bot.answer_callback_query(call.id, "گروه به کشوری متصل نیست.")
        return

    alliances = database.get_country_alliances(country["id"])
    if not alliances:
        bot.answer_callback_query(call.id, "شما عضو هیچ اتحادیه‌ای نیستید.")
        bot.send_message(call.message.chat.id, "برای درخواست قرارداد میان اتحادها، ابتدا باید عضو یک اتحاد باشید.")
        return

    leader_alliance = None
    for alliance in alliances:
        if alliance["founder_country_id"] == country["id"]:
            leader_alliance = alliance
            break

    if not leader_alliance:
        bot.answer_callback_query(call.id, "فقط رهبر اتحاد می‌تواند قرارداد جدید ارسال کند.")
        bot.send_message(call.message.chat.id, "فقط رهبر اتحاد می‌تواند درخواست قرارداد میان اتحادها ارسال کند.")
        return

    markup = InlineKeyboardMarkup(row_width=1)
    for alliance in database.get_alliances():
        if alliance["id"] == leader_alliance["id"]:
            continue
        markup.add(
            InlineKeyboardButton(f"📜 {alliance['name']}", callback_data=f"dip_agreement_target:{leader_alliance['id']}:{alliance['id']}")
        )

    if not markup.keyboard:
        markup.add(InlineKeyboardButton("⚠️ اتحاد هدف موجود نیست", callback_data="no_action"))

    bot.send_message(call.message.chat.id, "🤝 اتحادیه هدف برای قرارداد را انتخاب کنید:", reply_markup=markup)
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data.startswith("dip_agreement_target:"))
def create_agreement_request(call):
    country = get_country_from_chat(call.message.chat.id)
    if not country:
        bot.answer_callback_query(call.id, "گروه به کشوری متصل نیست.")
        return

    parts = call.data.split(":")
    if len(parts) < 3:
        bot.answer_callback_query(call.id, "داده قرارداد نامعتبر است.")
        return

    alliance_a_id = int(parts[1])
    target_alliance_id = int(parts[2])

    alliance_a = database.get_alliance(alliance_a_id)
    if not alliance_a or alliance_a["founder_country_id"] != country["id"]:
        bot.answer_callback_query(call.id, "فقط رهبر اتحاد مجاز به ارسال درخواست قرارداد است.")
        return

    if alliance_a_id == target_alliance_id:
        bot.answer_callback_query(call.id, "اتحاد نمیتواند قرارداد با خودش داشته باشد.")
        return

    try:
        database.create_alliance_agreement(alliance_a_id, target_alliance_id)
    except ValueError:
        bot.answer_callback_query(call.id, "قرارداد برای همین اتحاد نامعتبر است.")
        return

    alliance = database.get_alliance(target_alliance_id)
    if not alliance:
        bot.answer_callback_query(call.id, "اتحاد هدف پیدا نشد.")
        return

    leader_group = database.get_group_by_country(alliance["founder_country_id"])
    if leader_group:
        bot.send_message(
            leader_group,
            f"📜 درخواست قرارداد میان اتحادها\n"
            f"اتحاد درخواست‌کننده: {alliance_a['name']}\n"
            f"درخواست کننده: {country['name']}\n\n"
            "برای قبول، از پنل دیپلماسی اقدام کنید."
        )

    bot.answer_callback_query(call.id, "درخواست قرارداد ثبت شد.")
    bot.send_message(call.message.chat.id, f"✅ درخواست قرارداد با اتحاد {alliance['name']} ارسال شد.")


@bot.callback_query_handler(func=lambda call: call.data == "dip_pending_agreements")
def pending_agreements(call):
    country = get_country_from_chat(call.message.chat.id)
    if not country:
        bot.answer_callback_query(call.id, "گروه به کشوری متصل نیست.")
        return

    alliances = database.get_country_alliances(country["id"])
    leader_alliances = [a for a in alliances if a["founder_country_id"] == country["id"]]
    if not leader_alliances:
        bot.answer_callback_query(call.id, "فقط رهبر اتحاد می‌تواند قراردادهای در انتظار را ببیند.")
        bot.send_message(call.message.chat.id, "فقط رهبر اتحاد می‌تواند قراردادهای در انتظار را بررسی کند.")
        return

    markup = InlineKeyboardMarkup(row_width=1)
    sent_any = False
    for alliance in leader_alliances:
        pending = database.get_pending_agreements_for_alliance(alliance["id"])
        for row in pending:
            other_alliance_id = row["alliance_b_id"] if row["alliance_a_id"] == alliance["id"] else row["alliance_a_id"]
            other_alliance = database.get_alliance(other_alliance_id)
            if not other_alliance:
                continue
            sent_any = True
            markup.add(
                InlineKeyboardButton(
                    f"✅ {alliance['name']} ↔ {other_alliance['name']}",
                    callback_data=f"accept_agreement_request:{row['id']}"
                )
            )

    if not sent_any:
        bot.send_message(call.message.chat.id, "درخواستی برای قرارداد میان اتحادهای شما وجود ندارد.")
        bot.answer_callback_query(call.id)
        return

    bot.send_message(call.message.chat.id, "📜 قراردادهای در انتظار برای اتحادهای شما:", reply_markup=markup)
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data.startswith("accept_agreement_request:"))
def accept_agreement_request(call):
    agreement_id = int(call.data.split(":", 1)[1])
    country = get_country_from_chat(call.message.chat.id)
    if not country:
        bot.answer_callback_query(call.id, "گروه به کشوری متصل نیست.")
        return

    with database.get_connection() as conn:
        row = conn.execute(
            "SELECT aa.*, a1.name AS alliance_a_name, a2.name AS alliance_b_name, a1.founder_country_id AS a_leader, a2.founder_country_id AS b_leader "
            "FROM alliance_agreements aa "
            "JOIN alliances a1 ON a1.id = aa.alliance_a_id "
            "JOIN alliances a2 ON a2.id = aa.alliance_b_id "
            "WHERE aa.id = ? AND aa.status = 'pending'",
            (agreement_id,),
        ).fetchone()

        if not row:
            bot.answer_callback_query(call.id, "درخواست قرارداد معتبر نیست.")
            return

        if row["a_leader"] != country["id"] and row["b_leader"] != country["id"]:
            bot.answer_callback_query(call.id, "فقط رهبر اتحاد می‌تواند قرارداد را بپذیرد.")
            return

        conn.execute(
            "UPDATE alliance_agreements SET status = 'active', accepted_at = ? WHERE id = ?",
            (database.now(), agreement_id),
        )

    bot.answer_callback_query(call.id, "قرارداد میان اتحادها پذیرفته شد.")
    bot.send_message(call.message.chat.id, f"✅ قرارداد میان {row['alliance_a_name']} و {row['alliance_b_name']} فعال شد.")


@bot.callback_query_handler(func=lambda call: call.data == "dip_request_negotiation")
def negotiation_request_menu(call):
    country = get_country_from_chat(call.message.chat.id)
    if not country:
        bot.answer_callback_query(call.id, "گروه به کشوری متصل نیست.")
        return

    if database.get_active_negotiation_for_country(country["id"]):
        bot.answer_callback_query(call.id, "شما در حال مذاکره فعال هستید.")
        return

    countries = database.get_all_countries()
    markup = InlineKeyboardMarkup(row_width=1)
    for other in countries:
        if other["id"] == country["id"]:
            continue
        markup.add(
            InlineKeyboardButton(f"💬 {other['name']}", callback_data=f"dip_negotiation_target:{other['id']}")
        )

    if not markup.keyboard:
        markup.add(InlineKeyboardButton("❌ کشوری موجود نیست", callback_data="no_action"))

    bot.send_message(call.message.chat.id, "🌍 کشوری را برای شروع مذاکره انتخاب کنید:", reply_markup=markup)
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data.startswith("dip_negotiation_target:"))
def negotiation_target_selected(call):
    country = get_country_from_chat(call.message.chat.id)
    if not country:
        bot.answer_callback_query(call.id, "گروه به کشوری متصل نیست.")
        return

    target_country_id = int(call.data.split(":", 1)[1])
    if target_country_id == country["id"]:
        bot.answer_callback_query(call.id, "نمی‌توانید با خودتان مذاکره کنید.")
        return

    try:
        database.create_negotiation_request(country["id"], target_country_id)
    except ValueError:
        bot.answer_callback_query(call.id, "درخواست نامعتبر است.")
        return

    with database.get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM negotiation_requests WHERE requester_country_id = ? AND target_country_id = ? AND status = 'pending' ORDER BY id DESC LIMIT 1",
            (country["id"], target_country_id),
        ).fetchone()
        request_id = row["id"] if row else None

    target_group = database.get_group_by_country(target_country_id)
    if target_group:
        text = (
            f"📩 درخواست مذاکره جدید\n"
            f"کشور درخواست‌کننده: {country['name']}\n\n"
            "برای قبول، روی دکمه زیر کلیک کنید."
        )
        bot.send_message(target_group, text)
        target_markup = InlineKeyboardMarkup(row_width=1)
        target_markup.add(
            InlineKeyboardButton("✅ قبول مذاکره", callback_data=f"accept_negotiation_request:{request_id}")
        )
        bot.send_message(target_group, "درخواست مذاکره را قبول کنید:", reply_markup=target_markup)

    bot.answer_callback_query(call.id, "درخواست مذاکره ارسال شد.")
    bot.send_message(call.message.chat.id, "✅ درخواست مذاکره به کشور مقصد ارسال شد.")


@bot.callback_query_handler(func=lambda call: call.data.startswith("accept_negotiation_request:"))
def accept_negotiation_request(call):
    request_id = int(call.data.split(":", 1)[1])
    country = get_country_from_chat(call.message.chat.id)
    if not country:
        bot.answer_callback_query(call.id, "گروه به کشوری متصل نیست.")
        return

    with database.get_connection() as conn:
        request = conn.execute(
            "SELECT * FROM negotiation_requests WHERE id = ? AND status = 'pending'",
            (request_id,),
        ).fetchone()
        if not request:
            bot.answer_callback_query(call.id, "درخواست معتبر نیست.")
            return
        if request["target_country_id"] != country["id"]:
            bot.answer_callback_query(call.id, "این درخواست برای شما نیست.")
            return

    result = database.accept_negotiation_request(request_id)
    if not result:
        bot.answer_callback_query(call.id, "درخواست پذیرفته نشد.")
        return

    sender_group = database.get_group_by_country(request["requester_country_id"])
    if sender_group:
        bot.send_message(sender_group, "✅ درخواست مذاکره شما پذیرفته شد. اکنون می‌توانید پیام‌تان را ارسال کنید.")

    bot.answer_callback_query(call.id, "مذاکره شروع شد.")
    bot.send_message(call.message.chat.id, "✅ مذاکره شروع شد. پیام‌ها از اینجا به طرف مقابل ارسال می‌شود.")


@bot.callback_query_handler(func=lambda call: call.data == "dip_active_negotiation")
def active_negotiation_info(call):
    country = get_country_from_chat(call.message.chat.id)
    if not country:
        bot.answer_callback_query(call.id, "گروه به کشوری متصل نیست.")
        return

    negotiation = database.get_active_negotiation_for_country(country["id"])
    if not negotiation:
        bot.answer_callback_query(call.id, "هیچ مذاکره فعالی ندارید.")
        return

    other_country_id = negotiation["country_b_id"] if negotiation["country_a_id"] == country["id"] else negotiation["country_a_id"]
    other = database.get_country(other_country_id)
    text = f"📨 مذاکره فعال\nکشور مقابل: {other['name']}"
    bot.send_message(call.message.chat.id, text)
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data == "dip_end_negotiation")
def end_negotiation_button(call):
    country = get_country_from_chat(call.message.chat.id)
    if not country:
        bot.answer_callback_query(call.id, "گروه به کشوری متصل نیست.")
        return

    negotiation = database.get_active_negotiation_for_country(country["id"])
    if not negotiation:
        bot.answer_callback_query(call.id, "مذاکره فعالی وجود ندارد.")
        return

    if database.end_negotiation_for_country(country["id"]):
        other_country_id = negotiation["country_b_id"] if negotiation["country_a_id"] == country["id"] else negotiation["country_a_id"]
        other = database.get_country(other_country_id)
        other_group = database.get_group_by_country(other_country_id)
        if other_group:
            bot.send_message(other_group, f"🛑 مذاکره با کشور {country['name']} پایان یافت.")
        bot.answer_callback_query(call.id, "مذاکره پایان یافت.")
        bot.send_message(call.message.chat.id, f"✅ مذاکره با کشور {other['name']} به پایان رسید.")
    else:
        bot.answer_callback_query(call.id, "امکان پایان مذاکره وجود ندارد.")


@bot.message_handler(commands=["end_negotiation"])
def direct_end_negotiation(message):
    country = get_country_from_chat(message.chat.id)
    if not country:
        return

    negotiation = database.get_active_negotiation_for_country(country["id"])
    if not negotiation:
        bot.reply_to(message, "مذاکره فعالی برای شما وجود ندارد.")
        return

    if database.end_negotiation_for_country(country["id"]):
        other_country_id = negotiation["country_b_id"] if negotiation["country_a_id"] == country["id"] else negotiation["country_a_id"]
        other = database.get_country(other_country_id)
        other_group = database.get_group_by_country(other_country_id)
        if other_group:
            bot.send_message(other_group, f"🛑 مذاکره با کشور {country['name']} پایان یافت.")
        bot.reply_to(message, f"✅ مذاکره با کشور {other['name']} پایان یافت.")
    else:
        bot.reply_to(message, "امکان پایان مذاکره وجود ندارد.")


@bot.message_handler(content_types=["text"])
def handle_text_messages(message):
    if message.text and message.text.startswith("/"):
        return

    user_data = user_states.get(message.from_user.id)
    if user_data and user_data.get("state") == "awaiting_alliance_name":
        alliance_name = message.text.strip()
        if not alliance_name:
            bot.reply_to(message, "نام اتحاد نمی‌تواند خالی باشد.")
            return

        existing = database.get_alliances()
        if any(item["name"].strip().lower() == alliance_name.lower() for item in existing):
            bot.reply_to(message, "این نام برای یک اتحاد قبلاً استفاده شده است.")
            return

        country_id = user_data.get("country_id")
        alliance_id = database.create_alliance(alliance_name, country_id)
        user_states.pop(message.from_user.id, None)
        bot.reply_to(message, f"✅ اتحاد {alliance_name} با موفقیت ساخته شد. شناسه اتحاد: {alliance_id}")
        return

    country = get_country_from_chat(message.chat.id)
    if not country:
        return

    negotiation = database.get_active_negotiation_for_country(country["id"])
    if not negotiation:
        return

    other_country_id = negotiation["country_b_id"] if negotiation["country_a_id"] == country["id"] else negotiation["country_a_id"]
    other_group = database.get_group_by_country(other_country_id)
    if not other_group:
        return

    bot.send_message(other_group, f"📩 پیام از {country['name']}\n{message.text}")


bot.infinity_polling()
