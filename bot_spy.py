import random
import threading

import telebot
from telebot.types import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup

import database
from settings import NEWS_CHANNEL_ID, TELEGRAM_BOT_SPY_API, TELEGRAM_MAINBOT_API

news_bot = telebot.TeleBot(TELEGRAM_MAINBOT_API)


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
    news_bot.send_message(NEWS_CHANNEL_ID, format_news_post(title, message))


bot = telebot.TeleBot(TELEGRAM_BOT_SPY_API)
bot.set_my_commands([
    BotCommand("spy", "منوی عملیات جاسوسی، ضدجاسوسی و ترور"),
    BotCommand("start", "شروع و نمایش منو اصلی"),
])
user_states = {}

SPY_WEAPONS = {
    "intel": "جاسوس اطلاعاتی",
    "ops": "جاسوس عملیاتی",
}
MAX_COUNTER_LEVEL = 5
MAX_REQUIRES_SCHOLASTIC_SPY = 100
COUNTER_ESPIONAGE_UPGRADE_COST = 500


def get_country_from_chat(chat_id):
    return database.get_country_by_group(chat_id)


def get_country_weapon_quantity(country_id, weapon_name):
    with database.get_connection() as conn:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(cw.quantity), 0) AS total
            FROM country_weapons cw
            JOIN weapons w ON w.id = cw.weapon_id
            WHERE cw.country_id = ? AND w.name = ?
            """,
            (country_id, weapon_name),
        ).fetchone()
        return int(row["total"]) if row else 0


def get_counter_espionage_level(country_id):
    return database.get_country_spy_level(country_id)


def set_counter_espionage_level(country_id, level):
    return database.set_country_spy_level(country_id, level)


def upgrade_counter_espionage(country_id):
    current = get_counter_espionage_level(country_id)
    if current >= MAX_COUNTER_LEVEL:
        return current, False

    country = database.get_country(country_id)
    if not country:
        return current, False
    if country["money"] < COUNTER_ESPIONAGE_UPGRADE_COST:
        return current, False

    database.change_money(country_id, -COUNTER_ESPIONAGE_UPGRADE_COST)
    new_level = current + 1
    set_counter_espionage_level(country_id, new_level)
    return new_level, True


def required_spy_floor_for_target(target_country_id):
    return 1


def has_required_spies(country_id, operation=None, target_country_id=None):
    intel = get_country_weapon_quantity(country_id, SPY_WEAPONS["intel"])
    ops = get_country_weapon_quantity(country_id, SPY_WEAPONS["ops"])
    minimum = required_spy_floor_for_target(target_country_id) if target_country_id is not None else 1
    return intel >= minimum and ops >= minimum


def consume_spy_units(country_id, intel_used=1, ops_used=1):
    intel_weapon = database.get_weapon_by_name(SPY_WEAPONS["intel"])
    ops_weapon = database.get_weapon_by_name(SPY_WEAPONS["ops"])

    if intel_weapon and get_country_weapon_quantity(country_id, SPY_WEAPONS["intel"]) >= intel_used:
        database.remove_weapon(country_id, intel_weapon["id"], intel_used)
    if ops_weapon and get_country_weapon_quantity(country_id, SPY_WEAPONS["ops"]) >= ops_used:
        database.remove_weapon(country_id, ops_weapon["id"], ops_used)

    return {
        "intel": get_country_weapon_quantity(country_id, SPY_WEAPONS["intel"]),
        "ops": get_country_weapon_quantity(country_id, SPY_WEAPONS["ops"]),
    }


def format_country_list(countries, selected_country_id=None):
    markup = InlineKeyboardMarkup(row_width=1)
    for country in countries:
        label = "✅ " if selected_country_id and country["id"] == selected_country_id else ""
        markup.add(
            InlineKeyboardButton(f"{label}{country['name']}", callback_data=f"spy_target:{country['id']}")
        )
    return markup


def build_main_menu():
    markup = InlineKeyboardMarkup(row_width=1)
    for text, data in [
        ("🕵️ عملیات جاسوسی", "spy_menu_operations"),
        ("🛡️ ضد جاسوسی", "spy_menu_counter"),
        ("💣 عملیات ترور", "spy_menu_assassination"),
        ("📊 وضعیت جاسوس‌ها", "spy_status"),
    ]:
        markup.add(InlineKeyboardButton(text, callback_data=data))
    return markup


def build_operation_menu():
    markup = InlineKeyboardMarkup(row_width=1)
    for text, data in [
        ("📡 جاسوسی اطلاعاتی", "spy_op:info"),
        ("🧰 دزدیدن تجهیزات", "spy_op:steal"),
        ("💥 عملیات خرابکاری", "spy_op:sabotage"),
        ("🔙 بازگشت", "spy_main"),
    ]:
        markup.add(InlineKeyboardButton(text, callback_data=data))
    return markup


def build_counter_menu(country_id):
    current = get_counter_espionage_level(country_id)
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton(f"🛡️ سطح ضد جاسوسی: {current}/{MAX_COUNTER_LEVEL}", callback_data="spy_counter_status"))
    if current < MAX_COUNTER_LEVEL:
        markup.add(InlineKeyboardButton("⬆️ ارتقای سطح ضد جاسوسی", callback_data="spy_counter_upgrade"))
    else:
        markup.add(InlineKeyboardButton("✅ حداکثر سطح ضد جاسوسی", callback_data="spy_counter_status"))
    markup.add(InlineKeyboardButton("🔙 بازگشت", callback_data="spy_main"))
    return markup


def build_sabotage_target_menu():
    markup = InlineKeyboardMarkup(row_width=1)
    for text, data in [
        ("🏭 کارخانه", "spy_sabotage_target:factories"),
        ("🏦 بانک", "spy_sabotage_target:banks"),
        ("🎓 دانشگاه", "spy_sabotage_target:universities"),
        ("🔙 بازگشت", "spy_main"),
    ]:
        markup.add(InlineKeyboardButton(text, callback_data=data))
    return markup


def build_assassination_menu():
    markup = InlineKeyboardMarkup(row_width=1)
    for text, data in [
        ("👑 ترور رئیس‌جمهور / نخست‌وزیر", "spy_assassination:president"),
        ("🛡️ ترور وزیر دفاع", "spy_assassination:defense"),
        ("💰 ترور وزیر اقتصاد", "spy_assassination:economy"),
        ("🧠 ترور دانشمندان", "spy_assassination:scientists"),
        ("🔙 بازگشت", "spy_main"),
    ]:
        markup.add(InlineKeyboardButton(text, callback_data=data))
    return markup


ASSASSINATION_ROLE_LABELS = {
    "president": "👑 رئیس‌جمهور / نخست‌وزیر",
    "defense": "🛡️ وزیر دفاع",
    "economy": "💰 وزیر اقتصاد",
    "scientists": "🧠 دانشمندان",
}


def safe_country_list(exclude_country_id=None):
    countries = database.get_all_countries()
    if exclude_country_id is not None:
        return [c for c in countries if c["id"] != exclude_country_id]
    return countries


def get_country_status(country):
    intel = get_country_weapon_quantity(country["id"], SPY_WEAPONS["intel"])
    ops = get_country_weapon_quantity(country["id"], SPY_WEAPONS["ops"])
    defense = get_counter_espionage_level(country["id"])
    return (
        f"🕵️ وضعیت جاسوسی کشور {country['name']}\n"
        f"📡 جاسوس اطلاعاتی: {intel}\n"
        f"🧰 جاسوس عملیاتی: {ops}\n"
        f"🛡️ سطح ضد جاسوسی: {defense}/{MAX_COUNTER_LEVEL}\n"
        f"💰 پول: ${float(country.get('money', 0)):,.0f}\n"
        f"🏭 کارخانه: {country.get('factories', 0)}\n"
        f"🎓 دانشگاه: {country.get('universities', 0)}"
    )


def notify_target_country(country_id, attacker_country_name, title, details):
    group_id = database.get_group_by_country(country_id)
    if not group_id:
        return
    bot.send_message(
        group_id,
        f"🚨 {title}\n"
        f"کشور {attacker_country_name} عملیات جاسوسی را علیه شما آغاز کرد.\n\n"
        f"{details}",
    )


def evaluate_operation_outcome(attacker_country, target_country, operation, target_asset=None):
    intel_count = get_country_weapon_quantity(attacker_country["id"], SPY_WEAPONS["intel"])
    ops_count = get_country_weapon_quantity(attacker_country["id"], SPY_WEAPONS["ops"])
    defense_level = get_counter_espionage_level(target_country["id"])
    required_spies = required_spy_floor_for_target(target_country["id"])

    if intel_count < required_spies or ops_count < required_spies:
        return {
            "success": False,
            "message": f"⚠️ برای انجام این عملیات در برابر کشور {target_country['name']} باید حداقل {required_spies} جاسوس اطلاعاتی و {required_spies} جاسوس عملیاتی داشته باشید.",
            "type": "blocked",
        }

    if operation == "assassination" and defense_level >= MAX_COUNTER_LEVEL:
        return {
            "success": False,
            "message": f"❌ Mission failed — the assassination plot against {target_country['name']} was detected, the team was exposed, and the operation collapsed before it could reach its target.",
            "type": "failed",
        }

    total_spies = intel_count + ops_count
    success_chance = 0.72 + (total_spies / 200.0) - (defense_level * 0.12)
    success_chance = max(0.10, min(0.95, success_chance))
    success = random.random() < success_chance

    if success:
        return {"success": True, "message": "✅ عملیات موفق بود.", "type": "success"}

    if defense_level >= MAX_COUNTER_LEVEL:
        if random.random() < 0.55:
            return {
                "success": False,
                "message": f"❌ Mission failed — the spy sent to {target_country['name']} was arrested by the target’s counter-espionage service before he could complete the mission.",
                "type": "arrested",
            }
        return {
            "success": False,
            "message": f"❌ Mission failed — the target country detected the operation and deliberately fed false information to your intelligence network.",
            "type": "false_info",
        }

    if random.random() < 0.5:
        return {
            "success": False,
            "message": f"⚠️ اطلاعاتی که دریافت کردید نادرست بود و کشور {target_country['name']} شما را فریب داد.",
            "type": "false_info",
        }

    return {
        "success": False,
        "message": f"❌ عملیات روی {target_country['name']} ناموفق بود و تیم جاسوسی شما کشف شد.",
        "type": "failed",
    }


def execute_delayed_operation(chat_id, attacker_country, target_country, operation, target_asset=None):
    if not has_required_spies(attacker_country["id"], target_country_id=target_country["id"]):
        bot.send_message(chat_id, f"❌ Mission failed — the operative team for {attacker_country['name']} was not ready for this mission.")
        publish_game_news(
            "❌ Mission failed",
            f"کشور {attacker_country['name']} بخاطر کمبود نیروهای جاسوسی برای عملیات علیه {target_country['name']} شکست خورد.",
        )
        return

    consume_spy_units(attacker_country["id"], 1, 1)
    result = evaluate_operation_outcome(attacker_country, target_country, operation, target_asset)
    if result["type"] == "blocked":
        bot.send_message(chat_id, result["message"])
        publish_game_news(
            "⚠️ عملیات جاسوسی رد شد",
            f"کشور {attacker_country['name']} تلاش کرد عملیات جاسوسی را روی {target_country['name']} انجام دهد اما شکست خورد.\n\n{result['message']}",
        )
        return

    if operation == "info":
        if result["success"]:
            message = (
                f"📡 عملیات جاسوسی اطلاعاتی برای {target_country['name']} موفق بود.\n"
                f"مبنا: {target_country['name']}\n"
                f"پول: ${float(target_country.get('money', 0)):,.0f}\n"
                f"کارخانه: {target_country.get('factories', 0)}\n"
                f"دانشگاه: {target_country.get('universities', 0)}"
            )
            bot.send_message(chat_id, message)
            publish_game_news(
                "📡 عملیات جاسوسی",
                f"کشور {attacker_country['name']} عملیات اطلاعاتی را روی {target_country['name']} انجام داد و موفق شد.\n\n{message}",
            )
            notify_target_country(
                target_country["id"],
                attacker_country["name"],
                "📡 جاسوسی اطلاعاتی",
                "عملیات جاسوسی اطلاعاتی از سوی کشور شما به موفقیت رسید و اطلاعات مهمی از کشور شما جمع‌آوری شد.",
            )
            database.record_spy_event(attacker_country["id"], target_country["id"], "info", 1, "جاسوسی اطلاعاتی موفق")
        else:
            bot.send_message(chat_id, result["message"])
            publish_game_news(
                "❌ Mission failed",
                f"کشور {attacker_country['name']} به {target_country['name']} تلاش برای جاسوسی اطلاعاتی کرد اما شکست خورد.\n\n{result['message']}",
            )
            notify_target_country(
                target_country["id"],
                attacker_country["name"],
                "❌ Mission failed",
                f"کشور {attacker_country['name']} تلاش کرد اطلاعات شما را جمع‌آوری کند اما عملیات شکست خورد. {result['message']}",
            )
            database.record_spy_event(attacker_country["id"], target_country["id"], "info", 0, result["message"])
        return

    if operation == "steal":
        if result["success"]:
            target_weapons = database.get_country_inventory(target_country["id"])
            if not target_weapons:
                bot.send_message(chat_id, "🧰 کشوری که هدف قرار گرفته، هیچ تجهیزاتی ندارد.")
                notify_target_country(
                    target_country["id"],
                    attacker_country["name"],
                    "🧰 تلاش برای سرقت تجهیز",
                    f"کشور {attacker_country['name']} سعی کرد تجهیزات شما را سرقت کند، اما شما هیچ تجهیز قابل سرقتی نداشتید.",
                )
                return
            stolen = random.choice(target_weapons)
            with database.get_connection() as conn:
                conn.execute(
                    "UPDATE country_weapons SET quantity = quantity - 1 WHERE country_id = ? AND weapon_id = ?",
                    (target_country["id"], stolen["id"]),
                )
                conn.execute(
                    "INSERT INTO country_weapons (country_id, weapon_id, quantity) VALUES (?, ?, 1) ON CONFLICT(country_id, weapon_id) DO UPDATE SET quantity = country_weapons.quantity + 1",
                    (attacker_country["id"], stolen["id"]),
                )
            database.record_spy_event(attacker_country["id"], target_country["id"], "steal", 1, f"دزدیدن {stolen['name']}")
            bot.send_message(chat_id, f"🧰 عملیات سرقت موفق بود. سلاح {stolen['name']} به کشور شما منتقل شد.")
            publish_game_news(
                "🧰 سرقت تجهیزات",
                f"کشور {attacker_country['name']} در عملیات جاسوسی موفق شد سلاح {stolen['name']} را از {target_country['name']} به سرقت ببرد.",
            )
            notify_target_country(
                target_country["id"],
                attacker_country["name"],
                "🧰 سرقت تجهیزات",
                f"کشور {attacker_country['name']} موفق شد سلاح {stolen['name']} را از کشور شما بدزدد.",
            )
        else:
            bot.send_message(chat_id, result["message"])
            publish_game_news(
                "❌ Mission failed",
                f"کشور {attacker_country['name']} تلاش کرد از {target_country['name']} تجهیزاتی بدزدد اما شکست خورد.\n\n{result['message']}",
            )
            notify_target_country(
                target_country["id"],
                attacker_country["name"],
                "❌ Mission failed",
                f"کشور {attacker_country['name']} تلاش کرد تجهیزاتی از کشور شما بدزدد اما عملیات شکست خورد. {result['message']}",
            )
            database.record_spy_event(attacker_country["id"], target_country["id"], "steal", 0, result["message"])
        return

    if operation == "sabotage":
        target_asset = target_asset or "factories"
        if result["success"]:
            if target_asset == "factories":
                current_amount = int(target_country.get("factories", 0))
                damage_amount = min(current_amount, max(1, int(current_amount * 0.25))) if current_amount > 0 else 0
                new_value = max(0, int(target_country.get("factories", 0)) - damage_amount)
                database.update_country(target_country["id"], factories=new_value)
                msg = f"💥 کارخانه‌های کشور {target_country['name']} به میزان {damage_amount} آسیب دیدند."
                asset_label = "کارخانه‌ها"
            elif target_asset == "banks":
                current_amount = int(target_country.get("banks", 0))
                damage_amount = min(current_amount, max(1, int(current_amount * 0.25))) if current_amount > 0 else 0
                new_value = max(0, int(target_country.get("banks", 0)) - damage_amount)
                database.update_country(target_country["id"], banks=new_value)
                msg = f"💥 بانک‌های کشور {target_country['name']} به میزان {damage_amount} آسیب دیدند."
                asset_label = "بانک‌ها"
            else:
                current_amount = int(target_country.get("universities", 0))
                damage_amount = min(current_amount, max(1, int(current_amount * 0.25))) if current_amount > 0 else 0
                new_value = max(0, int(target_country.get("universities", 0)) - damage_amount)
                database.update_country(target_country["id"], universities=new_value)
                msg = f"💥 دانشگاه‌های کشور {target_country['name']} به میزان {damage_amount} آسیب دیدند."
                asset_label = "دانشگاه‌ها"
            database.record_spy_event(attacker_country["id"], target_country["id"], "sabotage", 1, f"خرابکاری روی {target_asset} موفق")
            bot.send_message(chat_id, msg)
            publish_game_news(
                "💥 خرابکاری",
                f"کشور {attacker_country['name']} عملیات خرابکاری را روی {target_country['name']} انجام داد و به {asset_label} آسیب وارد کرد.\n\nمیزان خسارت: {damage_amount}",
            )
            notify_target_country(
                target_country["id"],
                attacker_country["name"],
                "💥 خرابکاری",
                f"کشور {attacker_country['name']} موفق شد به {asset_label} شما آسیب وارد کند. میزان خسارت: {damage_amount}.",
            )
        else:
            bot.send_message(chat_id, result["message"])
            publish_game_news(
                "❌ Mission failed",
                f"کشور {attacker_country['name']} تلاش کرد روی {target_country['name']} خرابکاری انجام دهد اما شکست خورد.\n\n{result['message']}",
            )
            notify_target_country(
                target_country["id"],
                attacker_country["name"],
                "❌ Mission failed",
                f"کشور {attacker_country['name']} تلاش کرد به زیرساخت‌های شما آسیب بزند اما عملیات شکست خورد. {result['message']}",
            )
            database.record_spy_event(attacker_country["id"], target_country["id"], "sabotage", 0, result["message"])
        return

    if operation == "assassination":
        target_role = target_asset or "president"
        role_label = ASSASSINATION_ROLE_LABELS.get(target_role, "🎯 هدف انتخاب‌شده")
        role_name = {
            "president": "رئیس‌جمهور / نخست‌وزیر",
            "defense": "وزیر دفاع",
            "economy": "وزیر اقتصاد",
            "scientists": "دانشمندان",
        }.get(target_role, "هدف ترور")

        if result["success"]:
            if target_role == "scientists":
                outcome_text = f"{role_label} در کشور {target_country['name']} کشته شدند و تیم علمی کشور آسیب جدی دید."
                target_notice = f"کشور {attacker_country['name']} موفق شد بخش مهمی از {role_label} شما را از بین ببرد. دانشمندان شما کشته شدند و پروژه‌های علمی با اختلال مواجه شدند."
            else:
                outcome_text = f"{role_label} در کشور {target_country['name']} ترور شد و رهبر/مقام اصلی هدف حذف شد."
                target_notice = f"کشور {attacker_country['name']} موفق شد {role_name} شما را ترور کند. {role_name} کشته شد و دولت شما در شوک سیاسی قرار گرفت."

            bot.send_message(chat_id, f"💣 عملیات ترور موفق بود.\n\n{outcome_text}\n\nکشور: {target_country['name']}")
            publish_game_news(
                "💣 ترور موفق",
                f"کشور {attacker_country['name']} عملیات ترور را علیه {target_country['name']} انجام داد و {role_label} را هدف قرار داد.\n\n{outcome_text}",
            )
            notify_target_country(
                target_country["id"],
                attacker_country["name"],
                "💣 ترور موفق",
                target_notice,
            )
            database.record_spy_event(attacker_country["id"], target_country["id"], "assassination", 1, f"ترور موفق روی {role_name}")
        else:
            if target_role == "scientists":
                outcome_text = f"{role_label} در کشور {target_country['name']} زنده ماندند و هیچ‌یک از دانشمندان کشته نشدند."
            else:
                outcome_text = f"{role_label} در کشور {target_country['name']} زنده ماند و عملیات ترور ناموفق بود."

            bot.send_message(chat_id, f"⚠️ عملیات ترور ناموفق بود.\n\n{outcome_text}\n\nجزئیات: {result['message']}")
            publish_game_news(
                "⚠️ تلاش ترور ناموفق",
                f"کشور {attacker_country['name']} عملیات ترور را علیه {target_country['name']} انجام داد اما {role_label} زنده ماند.\n\nجزئیات: {result['message']}",
            )
            notify_target_country(
                target_country["id"],
                attacker_country["name"],
                "⚠️ تلاش ترور",
                f"کشور {attacker_country['name']} تلاش کرد {role_name} شما را ترور کند اما ناموفق بود و {role_name} زنده ماند. {result['message']}",
            )
            database.record_spy_event(attacker_country["id"], target_country["id"], "assassination", 0, f"ترور ناموفق روی {role_name}: {result['message']}")
        return

    bot.send_message(chat_id, result["message"])
    publish_game_news(
        "📡 عملیات جاسوسی",
        f"کشور {attacker_country['name']} عملیات روی {target_country['name']} انجام داد.\n\n{result['message']}",
    )


@bot.message_handler(commands=["spy"])
def start_spy(message):
    country = get_country_from_chat(message.chat.id)
    if not country:
        bot.reply_to(message, "⚠️ این گروه به کشوری متصل نیست. برای شروع عملیات جاسوسی، گروه را به یک کشور وصل کنید.")
        return

    user_states[message.from_user.id] = {"country_id": country["id"], "state": "spy_main"}
    bot.send_message(
        message.chat.id,
        f"🕵️ پنل عملیات جاسوسی برای {country['name']}\n\nچیزی را انتخاب کنید:",
        reply_markup=build_main_menu(),
    )


@bot.callback_query_handler(func=lambda call: call.data == "spy_main")
def spy_main(call):
    country = get_country_from_chat(call.message.chat.id)
    if not country:
        bot.answer_callback_query(call.id, "گروه به کشوری متصل نیست.")
        return

    user_states[call.from_user.id] = {"country_id": country["id"], "state": "spy_main"}
    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        f"🕵️ پنل عملیات جاسوسی برای {country['name']}\n\nچیزی را انتخاب کنید:",
        reply_markup=build_main_menu(),
    )


@bot.callback_query_handler(func=lambda call: call.data == "spy_menu_operations")
def spy_menu_operations(call):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "🕵️ عملیات جاسوسی\nنوع عملیات را انتخاب کنید:", reply_markup=build_operation_menu())


@bot.callback_query_handler(func=lambda call: call.data == "spy_menu_counter")
def spy_menu_counter(call):
    country = get_country_from_chat(call.message.chat.id)
    if not country:
        bot.answer_callback_query(call.id, "گروه به کشوری متصل نیست.")
        return
    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        f"🛡️ ضد جاسوسی\nسطح فعلی: {get_counter_espionage_level(country['id'])}/{MAX_COUNTER_LEVEL}\n💰 هزینه هر سطح: {COUNTER_ESPIONAGE_UPGRADE_COST} پول\nبا ارتقا سطح ضد جاسوسی، عملیات دشمنان شما بیشتر رد می‌شود.",
        reply_markup=build_counter_menu(country["id"]),
    )


@bot.callback_query_handler(func=lambda call: call.data == "spy_counter_status")
def spy_counter_status(call):
    country = get_country_from_chat(call.message.chat.id)
    if not country:
        bot.answer_callback_query(call.id, "گروه به کشوری متصل نیست.")
        return
    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        f"🛡️ سطح ضد جاسوسی کشور {country['name']}: {get_counter_espionage_level(country['id'])}/{MAX_COUNTER_LEVEL}",
        reply_markup=build_counter_menu(country["id"]),
    )


@bot.callback_query_handler(func=lambda call: call.data == "spy_counter_upgrade")
def spy_counter_upgrade(call):
    country = get_country_from_chat(call.message.chat.id)
    if not country:
        bot.answer_callback_query(call.id, "گروه به کشوری متصل نیست.")
        return
    if country["money"] < COUNTER_ESPIONAGE_UPGRADE_COST:
        bot.answer_callback_query(call.id, f"💸 برای ارتقا ضد جاسوسی به {COUNTER_ESPIONAGE_UPGRADE_COST} پول نیاز دارید.")
        return

    level, changed = upgrade_counter_espionage(country["id"])
    if not changed:
        bot.answer_callback_query(call.id, "سطح ضد جاسوسی در حداکثر مقدار قرار دارد یا پول کافی ندارید.")
        return

    bot.answer_callback_query(call.id, "ارتقا انجام شد.")
    bot.send_message(
        call.message.chat.id,
        f"🛡️ سطح ضد جاسوسی کشور {country['name']} به {level}/{MAX_COUNTER_LEVEL} ارتقا یافت.\n💸 {COUNTER_ESPIONAGE_UPGRADE_COST} پول هزینه شد.",
        reply_markup=build_counter_menu(country["id"]),
    )


@bot.callback_query_handler(func=lambda call: call.data == "spy_menu_assassination")
def spy_menu_assassination(call):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "💣 عملیات ترور\nهدف را انتخاب کنید:", reply_markup=build_assassination_menu())


@bot.callback_query_handler(func=lambda call: call.data == "spy_status")
def spy_status(call):
    country = get_country_from_chat(call.message.chat.id)
    if not country:
        bot.answer_callback_query(call.id, "گروه به کشوری متصل نیست.")
        return

    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, get_country_status(country))


@bot.callback_query_handler(func=lambda call: call.data.startswith("spy_op:"))
def select_spy_operation(call):
    country = get_country_from_chat(call.message.chat.id)
    if not country:
        bot.answer_callback_query(call.id, "گروه به کشوری متصل نیست.")
        return

    operation = call.data.split(":", 1)[1]
    if not has_required_spies(country["id"]):
        bot.answer_callback_query(call.id, "برای این عملیات باید حداقل 1 جاسوس اطلاعاتی و 1 جاسوس عملیاتی داشته باشید.")
        return

    if operation == "sabotage":
        user_states[call.from_user.id] = {"country_id": country["id"], "state": "spy_sabotage_target", "operation": operation}
        bot.answer_callback_query(call.id)
        bot.send_message(
            call.message.chat.id,
            "💥 هدف خرابکاری را انتخاب کنید:",
            reply_markup=build_sabotage_target_menu(),
        )
        return

    user_states[call.from_user.id] = {"country_id": country["id"], "state": "spy_target", "operation": operation}
    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        "🎯 کشوری را برای اجرای عملیات انتخاب کنید:",
        reply_markup=format_country_list(safe_country_list(country["id"])),
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("spy_sabotage_target:"))
def select_sabotage_asset(call):
    country = get_country_from_chat(call.message.chat.id)
    if not country:
        bot.answer_callback_query(call.id, "گروه به کشوری متصل نیست.")
        return

    state = user_states.get(call.from_user.id, {})
    if state.get("state") != "spy_sabotage_target":
        bot.answer_callback_query(call.id, "وضعیت عملیات نامعتبر است.")
        return

    asset = call.data.split(":", 1)[1]
    target_country_id = state.get("target_country_id")
    if target_country_id is None:
        user_states[call.from_user.id] = {"country_id": country["id"], "state": "spy_sabotage_target", "operation": "sabotage", "asset": asset}
        bot.answer_callback_query(call.id)
        bot.send_message(
            call.message.chat.id,
            "🎯 کشوری را برای اجرای خرابکاری انتخاب کنید:",
            reply_markup=format_country_list(safe_country_list(country["id"])),
        )
        return

    target_country = database.get_country(target_country_id)
    if not target_country or target_country["id"] == country["id"]:
        bot.answer_callback_query(call.id, "کشور هدف نامعتبر است.")
        return

    user_states.pop(call.from_user.id, None)
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "⏳ عملیات خرابکاری شروع شد. لطفاً کمی صبر کنید...")
    threading.Timer(3, execute_delayed_operation, args=(call.message.chat.id, country, target_country, "sabotage", asset)).start()


@bot.callback_query_handler(func=lambda call: call.data.startswith("spy_assassination:"))
def select_assassination(call):
    country = get_country_from_chat(call.message.chat.id)
    if not country:
        bot.answer_callback_query(call.id, "گروه به کشوری متصل نیست.")
        return

    target = call.data.split(":", 1)[1]
    if not has_required_spies(country["id"]):
        bot.answer_callback_query(call.id, "❌ Mission failed — your spy team was not ready for this operation.")
        return

    user_states[call.from_user.id] = {"country_id": country["id"], "state": "spy_assassination_target", "operation": "assassination", "assassination_target": target}
    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        f"💣 هدف ترور: {ASSASSINATION_ROLE_LABELS.get(target, 'هدف انتخابی')}\nکشور مورد نظر را انتخاب کنید:",
        reply_markup=format_country_list(safe_country_list(country["id"])),
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("spy_target:"))
def apply_targeted_spy_action(call):
    country = get_country_from_chat(call.message.chat.id)
    if not country:
        bot.answer_callback_query(call.id, "گروه به کشوری متصل نیست.")
        return

    state = user_states.get(call.from_user.id, {})
    if state.get("state") not in {"spy_target", "spy_sabotage_target", "spy_assassination_target"}:
        bot.answer_callback_query(call.id, "وضعیت عملیات نامعتبر است.")
        return

    target_country_id = int(call.data.split(":", 1)[1])
    if target_country_id == country["id"]:
        bot.answer_callback_query(call.id, "امکان اجرای عملیات روی خودش وجود ندارد.")
        return

    target_country = database.get_country(target_country_id)
    if not target_country:
        bot.answer_callback_query(call.id, "کشور هدف پیدا نشد.")
        return

    operation = state.get("operation")
    if state.get("state") == "spy_sabotage_target":
        asset = state.get("asset")
        if not asset:
            bot.answer_callback_query(call.id)
            user_states[call.from_user.id] = {"country_id": country["id"], "state": "spy_sabotage_target", "operation": "sabotage", "target_country_id": target_country_id}
            bot.send_message(call.message.chat.id, "💥 نوع آسیب‌زیستی را انتخاب کنید:", reply_markup=build_sabotage_target_menu())
            return
        user_states.pop(call.from_user.id, None)
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "⏳ عملیات خرابکاری شروع شد. لطفاً کمی صبر کنید...")
        threading.Timer(3, execute_delayed_operation, args=(call.message.chat.id, country, target_country, "sabotage", asset)).start()
        return

    if state.get("state") == "spy_assassination_target":
        assassination_target = state.get("assassination_target", "president")
        user_states.pop(call.from_user.id, None)
        bot.answer_callback_query(call.id)
        bot.send_message(
            call.message.chat.id,
            f"⏳ عملیات ترور روی {ASSASSINATION_ROLE_LABELS.get(assassination_target, 'هدف انتخابی')} شروع شد. لطفاً کمی صبر کنید...",
        )
        threading.Timer(
            3,
            execute_delayed_operation,
            args=(call.message.chat.id, country, target_country, "assassination", assassination_target),
        ).start()
        return

    if not has_required_spies(country["id"], target_country_id=target_country_id):
        bot.answer_callback_query(call.id, f"❌ Mission failed — the operation against {target_country['name']} could not begin.")
        return

    user_states.pop(call.from_user.id, None)
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "⏳ عملیات شروع شد. لطفاً کمی صبر کنید...")
    threading.Timer(3, execute_delayed_operation, args=(call.message.chat.id, country, target_country, operation, None)).start()


bot.infinity_polling()
