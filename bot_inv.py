import re

import telebot
from telebot.types import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup

import database
from settings import TELEGRAM_BOT_INV_API

bot = telebot.TeleBot(TELEGRAM_BOT_INV_API)
bot.set_my_commands([
    BotCommand("inv", "نمایش موجودی، اقتصاد و سرمایه‌گذاری کشور"),
    BotCommand("start", "شروع و نمایش منو اصلی"),
])

user_states = {}

BUILDING_COSTS = {
    "factories": 400,
    "banks": 400,
    "universities": 300,
}

BUILDING_INCOME = {
    "factories": {"money": 200, "industry": 300},
    "banks": {"money": 300, "industry": 100},
    "universities": {"knowledge": 250},
}


def money_text(value):
    return f"${float(value):,.0f}"


def get_country_from_chat_or_name(chat_id, name=None):
    if name:
        country = database.get_country_by_name(name)
        if country:
            return country
    return database.get_country_by_group(chat_id)


def get_active_sanctions_for_country(country_id):
    with database.get_connection() as conn:
        rows = conn.execute(
            """
            SELECT s.*, c.name AS target_name
            FROM sanctions s
            JOIN countries c ON c.id = s.target_country_id
            WHERE s.imposer_country_id = ? AND s.sanctioned = 1
            ORDER BY c.name
            """,
            (country_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def notify_sanction_watchers(target_country_id, action_text):
    with database.get_connection() as conn:
        rows = conn.execute(
            """
            SELECT s.imposer_country_id, c.name AS imposer_name
            FROM sanctions s
            JOIN countries c ON c.id = s.imposer_country_id
            WHERE s.target_country_id = ? AND s.sanctioned = 1
            """,
            (target_country_id,),
        ).fetchall()

    for row in rows:
        group_chat_id = database.get_group_by_country(row["imposer_country_id"])
        if group_chat_id:
            bot.send_message(
                group_chat_id,
                f"⚠️ هشدار تحریم\n\n{action_text}\n\nکشوری که تحریم شما را نادیده گرفت: {database.get_country(target_country_id)['name']}"
            )


def notify_country_receipt(target_country_id, action_text, sender_country_name=None, amount=None, item_name=None, item_count=None):
    group_chat_id = database.get_group_by_country(target_country_id)
    if not group_chat_id:
        return

    details = action_text
    if sender_country_name:
        details += f"\nفرستنده: {sender_country_name}"
    if amount is not None:
        details += f"\nمبلغ دریافت‌شده: {money_text(amount)}"
    if item_name:
        details += f"\nنام وسیله: {item_name}"
    if item_count is not None:
        details += f"\nتعداد: {item_count}"

    bot.send_message(
        group_chat_id,
        f"📥 اعلان دریافت\n\n{details}\n\nکشور دریافت‌کننده: {database.get_country(target_country_id)['name']}"
    )


def country_summary(country):
    return (
        f"🌍 کشور: {country['name']}\n"
        f"💰 پول: {money_text(country['money'])}\n"
        f"🏭 کارخانه: {country['factories']}\n"
        f"🏦 بانک: {country['banks']}\n"
        f"🎓 دانشگاه: {country['universities']}\n"
        f"🏭 صنعت موجود: {country.get('daily_industry_income', 0)}\n"
        f"🎓 دانش موجود: {country.get('daily_knowledge_income', 0)}\n"
        f"📈 درآمد روزانه پول: {money_text(country.get('daily_money_income', 0))}\n"
        f"📈 درآمد روزانه صنعت: {country.get('daily_industry_income', 0)}\n"
        f"📈 درآمد روزانه دانش: {country.get('daily_knowledge_income', 0)}\n"
    )


def build_main_menu(country_id):
    markup = InlineKeyboardMarkup(row_width=1)
    buttons = [
        ("📦 نمایش اینونتوری", f"inv_show:{country_id}"),
        ("🧰 ساخت تجهیزات", f"inv_build_weapon:{country_id}"),
        ("🔫 انتقال تجهیزات به کشور دیگر", f"inv_transfer_weapon:{country_id}"),
        ("💰 انتقال پول", f"inv_transfer_money:{country_id}"),
        ("📈 اقتصاد و آموزش", f"inv_economy:{country_id}"),
        ("💼 سرمایه گذاری خارجی", f"inv_invest:{country_id}"),
        ("⚠️ سیستم تحریم", f"inv_sanctions:{country_id}"),
    ]
    for text, data in buttons:
        markup.add(InlineKeyboardButton(text, callback_data=data))
    return markup


def build_asset_cost(asset_name, quantity=1):
    price = BUILDING_COSTS.get(asset_name, 0) * quantity
    income = {}
    for key, value in BUILDING_INCOME.get(asset_name, {}).items():
        income[key] = value * quantity
    return price, income


def get_asset_label(asset_name):
    labels = {
        "factories": "🏭 کارخانه",
        "banks": "🏦 بانک",
        "universities": "🎓 دانشگاه",
    }
    return labels.get(asset_name, asset_name)


def get_economy_status_text(country):
    return (
        "📊 وضعیت اقتصاد و آموزش\n"
        f"🏭 کارخانه: {country['factories']}\n"
        f"🏦 بانک: {country['banks']}\n"
        f"🎓 دانشگاه: {country['universities']}\n"
        f"💰 پول ذخیره: {money_text(country.get('money', 0))}\n"
        f"🏭 صنعت ذخیره: {country.get('daily_industry_income', 0)}\n"
        f"🎓 دانش ذخیره: {country.get('daily_knowledge_income', 0)}\n"
        f"📈 درآمد روزانه پول: {money_text(country.get('daily_money_income', 0))}\n"
        f"📈 درآمد روزانه صنعت: {country.get('daily_industry_income', 0)}\n"
        f"📈 درآمد روزانه دانش: {country.get('daily_knowledge_income', 0)}\n"
    )


def get_asset_selection_prompt(country, asset, target_country=None, mode="build"):
    asset_name = asset
    asset_label = get_asset_label(asset_name)
    cost_per_unit = BUILDING_COSTS.get(asset_name, 0)
    max_units = int(country["money"] // cost_per_unit) if cost_per_unit > 0 else 0
    target_text = f" در {target_country['name']}" if target_country else ""

    if mode == "investment":
        return (
            f"💼 سرمایه گذاری{target_text}\n\n"
            f"💰 پول شما: {money_text(country['money'])}\n"
            f"{asset_label}\n"
            f"💵 هزینه هر واحد: {money_text(cost_per_unit)}\n"
            f"📦 حداکثر تعداد قابل سرمایه‌گذاری: {max_units}\n\n"
            f"تعداد مورد نظر را وارد کنید:"
        )

    return (
        f"🏗️ ساخت {asset_label}{target_text}\n\n"
        f"{get_economy_status_text(country)}\n"
        f"💵 هزینه هر واحد: {money_text(cost_per_unit)}\n"
        f"📦 حداکثر تعداد قابل ساخت: {max_units}\n\n"
        f"تعداد مورد نظر را وارد کنید:"
    )


def revert_investments_for_sanction(investor_country_id, target_country_id, removed_investments):
    if not removed_investments:
        return 0

    investor_country = database.get_country(investor_country_id)
    target_country = database.get_country(target_country_id)
    if not investor_country or not target_country:
        return 0

    removed_total = 0
    factories_removed = 0
    banks_removed = 0
    universities_removed = 0
    investor_money_income_removed = 0
    investor_industry_income_removed = 0
    investor_knowledge_income_removed = 0
    target_money_income_removed = 0
    target_industry_income_removed = 0
    target_knowledge_income_removed = 0

    for investment in removed_investments:
        asset = investment["asset"]
        qty = int(investment["quantity"])
        removed_total += qty

        income_split = {
            key: value * qty / 2
            for key, value in BUILDING_INCOME.get(asset, {}).items()
        }

        if asset == "factories":
            factories_removed += qty
        elif asset == "banks":
            banks_removed += qty
        elif asset == "universities":
            universities_removed += qty

        investor_money_income_removed += income_split.get("money", 0)
        investor_industry_income_removed += income_split.get("industry", 0)
        investor_knowledge_income_removed += income_split.get("knowledge", 0)
        target_money_income_removed += income_split.get("money", 0)
        target_industry_income_removed += income_split.get("industry", 0)
        target_knowledge_income_removed += income_split.get("knowledge", 0)

    target_update = {
        "factories": max(0, target_country["factories"] - factories_removed),
        "banks": max(0, target_country["banks"] - banks_removed),
        "universities": max(0, target_country["universities"] - universities_removed),
        "daily_money_income": max(0, target_country.get("daily_money_income", 0) - target_money_income_removed),
        "daily_industry_income": max(0, target_country.get("daily_industry_income", 0) - target_industry_income_removed),
        "daily_knowledge_income": max(0, target_country.get("daily_knowledge_income", 0) - target_knowledge_income_removed),
    }
    database.update_country(target_country_id, **target_update)

    investor_update = {
        "daily_money_income": max(0, investor_country.get("daily_money_income", 0) - investor_money_income_removed),
        "daily_industry_income": max(0, investor_country.get("daily_industry_income", 0) - investor_industry_income_removed),
        "daily_knowledge_income": max(0, investor_country.get("daily_knowledge_income", 0) - investor_knowledge_income_removed),
    }
    database.update_country(investor_country_id, **investor_update)
    return removed_total


def build_weapon_cost(weapon, quantity=1):
    industry_need = int(weapon.get("industry_cost", 0) or 0) * quantity
    knowledge_need = int(weapon.get("knowledge_cost", 0) or 0) * quantity
    cost = float(weapon.get("price", 0) or 0) * quantity
    return cost, industry_need, knowledge_need


def get_weapon_build_limits(country, weapon):
    cost_per_unit = float(weapon.get("price", 0) or 0)
    industry_per_unit = int(weapon.get("industry_cost", 0) or 0)
    knowledge_per_unit = int(weapon.get("knowledge_cost", 0) or 0)
    current_industry = float(country.get("daily_industry_income", 0) or 0)
    current_knowledge = float(country.get("daily_knowledge_income", 0) or 0)
    max_by_money = int(country["money"] // cost_per_unit) if cost_per_unit > 0 else 0
    max_by_industry = int(current_industry // industry_per_unit) if industry_per_unit > 0 else 0
    max_by_knowledge = int(current_knowledge // knowledge_per_unit) if knowledge_per_unit > 0 else 0
    max_buildable = min(max_by_money, max_by_industry, max_by_knowledge) if (cost_per_unit or industry_per_unit or knowledge_per_unit) else 0
    return {
        "cost_per_unit": cost_per_unit,
        "industry_per_unit": industry_per_unit,
        "knowledge_per_unit": knowledge_per_unit,
        "max_buildable": max_buildable,
    }


@bot.message_handler(commands=["inv"])
def inv_start(message):
    args = message.text.split()
    country = None

    if len(args) > 1:
        country = database.get_country_by_name(args[1])
    else:
        country = database.get_country_by_group(message.chat.id)

    if not country:
        bot.reply_to(
            message,
            "❌ کشوری برای این گروه یا نام وارد شده پیدا نشد.\n\nمثال:\n/inv\nیا\n/inv Iran"
        )
        return

    text = country_summary(country)
    bot.send_message(
        message.chat.id,
        text,
        reply_markup=build_main_menu(country["id"]),
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("inv_"))
def menu_router(call):
    bot.answer_callback_query(call.id)
    parts = call.data.split(":")
    action = parts[0]
    country_id = int(parts[1]) if len(parts) > 1 else None
    if not country_id:
        return

    country = database.get_country(country_id)
    if not country:
        bot.send_message(call.message.chat.id, "❌ کشور پیدا نشد.")
        return

    if action == "inv_show":
        show_inventory(call.message.chat.id, country_id)
    elif action == "inv_build_weapon":
        list_weapons_for_building(call.message.chat.id, country_id)
    elif action == "inv_transfer_weapon":
        list_transferable_weapons(call.message.chat.id, country_id)
    elif action == "inv_transfer_money":
        ask_transfer_money_prompt(call.message.chat.id, call.from_user.id, country_id)
    elif action == "inv_economy":
        show_economy_menu(call.message.chat.id, country_id)
    elif action == "inv_invest":
        choose_investment_target(call.message.chat.id, country_id)
    elif action == "inv_sanctions":
        show_sanctions_menu(call.message.chat.id, country_id)


@bot.callback_query_handler(func=lambda call: call.data.startswith("build_weapon:"))
def select_weapon_to_build(call):
    _, country_id, weapon_id = call.data.split(":")
    country_id = int(country_id)
    weapon_id = int(weapon_id)
    weapon = database.get_weapon(weapon_id)
    if not weapon:
        bot.send_message(call.message.chat.id, "❌ سلاح پیدا نشد.")
        return

    country = database.get_country(country_id)
    if not country:
        bot.send_message(call.message.chat.id, "❌ کشور پیدا نشد.")
        return

    req = database.get_weapon_requirement(country_id, weapon_id)
    if req is not None and req.get("is_allowed", 0) == 0:
        bot.send_message(call.message.chat.id, f"⛔ ساخت {weapon['name']} برای کشور {country['name']} مجاز نیست.")
        return

    limits = get_weapon_build_limits(country, weapon)
    user_states[call.from_user.id] = {
        "action": "build_weapon",
        "country_id": country_id,
        "weapon_id": weapon_id,
    }
    bot.send_message(
        call.message.chat.id,
        f"🪖 سلاح انتخاب شد: {weapon['name']}\n\n"
        f"💰 پول شما: {money_text(country['money'])}\n"
        f"🏭 صنعت موجود: {country.get('daily_industry_income', 0)}\n"
        f"🎓 دانش موجود: {country.get('daily_knowledge_income', 0)}\n"
        f"💵 هزینه هر واحد: {money_text(limits['cost_per_unit'])}\n"
        f"🏭 هزینه صنعت هر واحد: {limits['industry_per_unit']}\n"
        f"🎓 هزینه دانش هر واحد: {limits['knowledge_per_unit']}\n"
        f"📦 حداکثر تعداد قابل ساخت: {limits['max_buildable']}\n\n"
        f"تعداد مورد نظر را وارد کنید:",
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("transfer_weapon_country:"))
def select_transfer_weapon_country(call):
    _, source_country_id, target_country_id = call.data.split(":")
    source_country_id = int(source_country_id)
    target_country_id = int(target_country_id)
    inventory = database.get_country_inventory(source_country_id)
    if not inventory:
        bot.send_message(call.message.chat.id, "❌ شما هیچ سلاحی برای انتقال ندارید.")
        return

    user_states[call.from_user.id] = {
        "action": "transfer_weapon_select_item",
        "country_id": source_country_id,
        "target_country_id": target_country_id,
    }

    markup = InlineKeyboardMarkup(row_width=1)
    for item in inventory:
        markup.add(
            InlineKeyboardButton(
                f"{item['name']} — {item['quantity']}",
                callback_data=f"transfer_weapon_item:{source_country_id}:{target_country_id}:{item['id']}",
            )
        )

    bot.send_message(
        call.message.chat.id,
        f"📦 سلاحی را برای انتقال به {database.get_country(target_country_id)['name']} انتخاب کنید:",
        reply_markup=markup,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("transfer_weapon_item:"))
def select_weapon_for_transfer(call):
    _, source_country_id, target_country_id, weapon_id = call.data.split(":")
    source_country_id = int(source_country_id)
    target_country_id = int(target_country_id)
    weapon_id = int(weapon_id)
    weapon = database.get_weapon(weapon_id)
    if not weapon:
        bot.send_message(call.message.chat.id, "❌ سلاح پیدا نشد.")
        return

    user_states[call.from_user.id] = {
        "action": "transfer_weapon_quantity",
        "country_id": source_country_id,
        "target_country_id": target_country_id,
        "weapon_id": weapon_id,
    }
    bot.send_message(
        call.message.chat.id,
        f"🔫 تعداد {weapon['name']} را برای انتقال به {database.get_country(target_country_id)['name']} وارد کنید:",
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("transfer_money_country:"))
def choose_transfer_money_country(call):
    _, source_country_id, target_country_id = call.data.split(":")
    source_country_id = int(source_country_id)
    target_country_id = int(target_country_id)
    user_states[call.from_user.id] = {
        "action": "transfer_money_quantity",
        "country_id": source_country_id,
        "target_country_id": target_country_id,
    }
    bot.send_message(
        call.message.chat.id,
        f"💸 مبلغی که می‌خواهید به {database.get_country(target_country_id)['name']} انتقال دهید را وارد کنید:",
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("economy_build:"))
def select_asset_to_build(call):
    _, country_id, asset = call.data.split(":")
    country_id = int(country_id)
    country = database.get_country(country_id)
    if not country:
        bot.send_message(call.message.chat.id, "❌ کشور پیدا نشد.")
        return

    user_states[call.from_user.id] = {
        "action": "economy_build_quantity",
        "country_id": country_id,
        "asset": asset,
    }
    bot.send_message(
        call.message.chat.id,
        get_asset_selection_prompt(country, asset, mode="build"),
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("invest_target:"))
def select_investment_target(call):
    _, source_country_id, target_country_id = call.data.split(":")
    source_country_id = int(source_country_id)
    target_country_id = int(target_country_id)
    source_country = database.get_country(source_country_id)
    target_country = database.get_country(target_country_id)
    if not source_country or not target_country:
        bot.send_message(call.message.chat.id, "❌ کشور مورد نظر پیدا نشد.")
        return

    markup = InlineKeyboardMarkup(row_width=1)
    for asset, label in [("factories", "🏭 کارخانه"), ("banks", "🏦 بانک"), ("universities", "🎓 دانشگاه")]:
        markup.add(
            InlineKeyboardButton(
                f"{label} — {money_text(BUILDING_COSTS.get(asset, 0))} هر واحد",
                callback_data=f"invest_asset:{source_country_id}:{target_country_id}:{asset}",
            )
        )

    bot.send_message(
        call.message.chat.id,
        f"💼 نوع سرمایه گذاری در {target_country['name']} را انتخاب کنید:",
        reply_markup=markup,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("invest_asset:"))
def select_investment_asset(call):
    _, source_country_id, target_country_id, asset = call.data.split(":")
    source_country_id = int(source_country_id)
    target_country_id = int(target_country_id)
    source_country = database.get_country(source_country_id)
    target_country = database.get_country(target_country_id)
    if not source_country or not target_country:
        bot.send_message(call.message.chat.id, "❌ کشور مورد نظر پیدا نشد.")
        return

    user_states[call.from_user.id] = {
        "action": "investment_quantity",
        "country_id": source_country_id,
        "target_country_id": target_country_id,
        "asset": asset,
    }
    bot.send_message(
        call.message.chat.id,
        get_asset_selection_prompt(source_country, asset, target_country=target_country, mode="investment"),
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_sanction:"))
def toggle_sanction(call):
    _, country_id, target_id = call.data.split(":")
    country_id = int(country_id)
    target_id = int(target_id)

    with database.get_connection() as conn:
        row = conn.execute(
            "SELECT sanctioned FROM sanctions WHERE imposer_country_id = ? AND target_country_id = ?",
            (country_id, target_id),
        ).fetchone()

    if row and row["sanctioned"] == 1:
        database.lift_sanction(country_id, target_id)
        bot.send_message(call.message.chat.id, "✅ تحریم کشور لغو شد.")
    else:
        database.impose_sanction(country_id, target_id, True)
        removed_investments = database.clear_foreign_investments(country_id, target_id)
        removed_count = revert_investments_for_sanction(country_id, target_id, removed_investments)
        sanction_message = f"🚫 کشور {database.get_country(country_id)['name']} تحریم شما را اعمال کرد."
        notify_country_receipt(target_id, sanction_message, sender_country_name=database.get_country(country_id)['name'])
        if removed_count > 0:
            bot.send_message(
                call.message.chat.id,
                f"✅ تحریم اعمال شد و {removed_count} واحد سرمایه‌گذاری از {database.get_country(target_id)['name']} به حالت اولیه بازگشتند."
            )
        else:
            bot.send_message(call.message.chat.id, "✅ تحریم روی کشور اعمال شد.")

    show_sanctions_menu(call.message.chat.id, country_id)


def show_inventory(chat_id, country_id):
    country = database.get_country(country_id)
    if not country:
        bot.send_message(chat_id, "❌ کشور پیدا نشد.")
        return

    inventory = database.get_country_inventory(country_id)
    text = f"📦 موجودی اسلحه‌های {country['name']}\n\n"

    if not inventory:
        text += "هیچ سلاحی در انبار شما نیست."
    else:
        for item in inventory:
            text += f"• {item['name']} | تعداد: {item['quantity']}\n"

    bot.send_message(chat_id, text, reply_markup=build_main_menu(country_id))


def get_weapon_group_label(weapon):
    description = (weapon.get("description") or "").strip()
    if " / " in description:
        prefix = description.split(" / ", 1)[0].strip()
        if prefix in {
            "نیروی جاسوسی",
            "نیروی هوایی",
            "نیروی موشکی و پدافندی",
            "نیروی دریایی",
            "تسلیحات غیر متعارف",
        }:
            return prefix

    category = (weapon.get("category") or "").strip()
    if category in {
        "نیروی جاسوسی",
        "نیروی هوایی",
        "نیروی موشکی و پدافندی",
        "نیروی دریایی",
        "تسلیحات غیر متعارف",
    }:
        return category

    if category:
        return category
    return "سایر"


def get_weapon_build_group_order():
    return [
        "نیروی جاسوسی",
        "نیروی هوایی",
        "نیروی موشکی و پدافندی",
        "نیروی دریایی",
        "تسلیحات غیر متعارف",
    ]


def list_weapons_for_building(chat_id, country_id):
    weapons = database.get_all_weapons()
    country = database.get_country(country_id)
    if not weapons:
        bot.send_message(chat_id, "❌ هنوز هیچ نوع تسلیحاتی ثبت نشده است.")
        return

    grouped = {}
    for weapon in weapons:
        req = database.get_weapon_requirement(country_id, weapon["id"])
        if req is not None and req.get("is_allowed", 0) == 0:
            continue
        group_label = get_weapon_group_label(weapon)
        grouped.setdefault(group_label, []).append(weapon)

    if not grouped:
        bot.send_message(chat_id, "❌ برای این کشور هنوز سلاحی مجاز برای ساخت وجود ندارد.")
        return

    markup = InlineKeyboardMarkup(row_width=1)
    for group_label in get_weapon_build_group_order():
        if group_label in grouped:
            markup.add(
                InlineKeyboardButton(
                    f"🧩 {group_label}",
                    callback_data=f"weapon_group:{country_id}:{group_label}",
                )
            )

    for group_label, items in sorted(grouped.items()):
        if group_label not in get_weapon_build_group_order():
            markup.add(
                InlineKeyboardButton(
                    f"🧩 {group_label}",
                    callback_data=f"weapon_group:{country_id}:{group_label}",
                )
            )
    bot.send_message(chat_id, "🪖 دسته سلاح را انتخاب کنید:", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith("weapon_group:"))
def show_weapons_by_group(call):
    _, country_id, group_label = call.data.split(":", 2)
    country_id = int(country_id)
    country = database.get_country(country_id)
    weapons = database.get_all_weapons()
    filtered = []
    for weapon in weapons:
        req = database.get_weapon_requirement(country_id, weapon["id"])
        if req is not None and req.get("is_allowed", 0) == 0:
            continue
        if get_weapon_group_label(weapon) == group_label:
            filtered.append(weapon)

    markup = InlineKeyboardMarkup(row_width=1)
    if not filtered:
        bot.send_message(call.message.chat.id, f"❌ در دسته {group_label} هیچ سلاحی برای این کشور مجاز نیست.")
        return

    for weapon in filtered:
        req = database.get_weapon_requirement(country_id, weapon["id"])
        allowed = req is None or req.get("is_allowed", 0) == 1
        limits = get_weapon_build_limits(country, weapon) if country else {"max_buildable": 0}
        status = "✅" if allowed else "⛔"
        label = f"{status} {weapon['name']} — {money_text(weapon['price'])} | Max: {limits['max_buildable']}"
        markup.add(
            InlineKeyboardButton(label, callback_data=f"build_weapon:{country_id}:{weapon['id']}")
        )
    markup.add(InlineKeyboardButton("🔙 بازگشت", callback_data=f"inv_build_weapon:{country_id}"))
    bot.send_message(call.message.chat.id, f"🪖 سلاح‌های دسته {group_label}:", reply_markup=markup)


def list_transferable_weapons(chat_id, country_id):
    countries = database.get_all_countries()
    markup = InlineKeyboardMarkup(row_width=1)
    for country in countries:
        if country["id"] == country_id:
            continue
        markup.add(
            InlineKeyboardButton(
                country["name"],
                callback_data=f"transfer_weapon_country:{country_id}:{country['id']}",
            )
        )

    if not markup.keyboard:
        bot.send_message(chat_id, "❌ هیچ کشوری برای انتقال سلاح وجود ندارد.")
        return

    bot.send_message(chat_id, "🌍 کشور مقصد را برای انتقال تجهیزات انتخاب کنید:", reply_markup=markup)


def ask_transfer_money_prompt(chat_id, user_id, country_id):
    countries = database.get_all_countries()
    markup = InlineKeyboardMarkup(row_width=1)
    for country in countries:
        if country["id"] == country_id:
            continue
        markup.add(
            InlineKeyboardButton(country["name"], callback_data=f"transfer_money_country:{country_id}:{country['id']}")
        )

    if not markup.keyboard:
        bot.send_message(chat_id, "❌ هیچ کشوری برای انتقال پول وجود ندارد.")
        return

    user_states[user_id] = {
        "action": "select_transfer_money_country",
        "country_id": country_id,
    }
    bot.send_message(
        chat_id,
        "💸 کشور مقصد را از لیست انتخاب کنید:",
        reply_markup=markup,
    )


def show_economy_menu(chat_id, country_id):
    country = database.get_country(country_id)
    if not country:
        bot.send_message(chat_id, "❌ کشور پیدا نشد.")
        return

    markup = InlineKeyboardMarkup(row_width=1)
    for asset, label in [("factories", "🏭 ساخت کارخانه"), ("banks", "🏦 ساخت بانک"), ("universities", "🎓 ساخت دانشگاه")]:
        markup.add(InlineKeyboardButton(label, callback_data=f"economy_build:{country_id}:{asset}"))
    bot.send_message(
        chat_id,
        f"{get_economy_status_text(country)}\n🏗️ برای ساخت یکی از بخش‌ها را انتخاب کنید:",
        reply_markup=markup,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("economy_build:"))
def select_asset_to_build(call):
    _, country_id, asset = call.data.split(":")
    country_id = int(country_id)
    country = database.get_country(country_id)
    if not country:
        bot.send_message(call.message.chat.id, "❌ کشور پیدا نشد.")
        return

    user_states[call.from_user.id] = {
        "action": "economy_build_quantity",
        "country_id": country_id,
        "asset": asset,
    }
    bot.send_message(
        call.message.chat.id,
        get_asset_selection_prompt(country, asset, mode="build"),
    )


def get_investment_summary_text(country_id):
    rows = database.get_foreign_investments_by_investor(country_id)
    if not rows:
        return "💼 شما هنوز در هیچ کشوری سرمایه گذاری نکرده‌اید."

    summary_lines = ["💼 سرمایه‌گذاری‌های فعلی شما:"]
    grouped = {}
    for row in rows:
        target_name = row["target_name"]
        grouped.setdefault(target_name, [])
        grouped[target_name].append((row["asset"], row["quantity"]))

    for target_name, items in sorted(grouped.items()):
        details = ", ".join(
            f"{get_asset_label(asset)}: {qty}"
            for asset, qty in items
        )
        summary_lines.append(f"• {target_name}: {details}")

    return "\n".join(summary_lines)


def choose_investment_target(chat_id, country_id):
    countries = database.get_all_countries()
    markup = InlineKeyboardMarkup(row_width=1)
    for country in countries:
        if country["id"] == country_id:
            continue
        markup.add(
            InlineKeyboardButton(country["name"], callback_data=f"invest_target:{country_id}:{country['id']}")
        )

    summary = get_investment_summary_text(country_id)
    bot.send_message(chat_id, f"{summary}\n\n🌍 کشوری را برای سرمایه گذاری انتخاب کنید:", reply_markup=markup)


def show_sanctions_menu(chat_id, country_id):
    markup = InlineKeyboardMarkup(row_width=1)
    countries = database.get_all_countries()
    current_sanctions = get_active_sanctions_for_country(country_id)
    current_targets = {row["target_country_id"] for row in current_sanctions}

    for country in countries:
        if country["id"] == country_id:
            continue
        label = f"🚫 {country['name']}" if country["id"] in current_targets else f"✅ {country['name']}"
        markup.add(InlineKeyboardButton(label, callback_data=f"toggle_sanction:{country_id}:{country['id']}"))

    text = f"🛑 تحریم‌های فعلی کشور {database.get_country(country_id)['name']}\n\n"
    if not current_sanctions:
        text += "هیچ کشوری تحریم نشده است."
    else:
        text += "کشورهای تحریم‌شده:\n"
        for row in current_sanctions:
            text += f"• {database.get_country(row['target_country_id'])['name']}\n"

    bot.send_message(chat_id, text, reply_markup=markup)


@bot.message_handler(content_types=["text"])
def handle_text_input(message):
    if message.text.startswith("/"):
        return

    user_id = message.from_user.id
    state = user_states.get(user_id)
    if not state:
        return

    action = state.get("action")
    country_id = state.get("country_id")
    target_country_id = state.get("target_country_id")

    try:
        if action == "build_weapon":
            qty = int(message.text.strip())
            if qty <= 0:
                raise ValueError("تعداد باید بیشتر از صفر باشد.")
            weapon = database.get_weapon(state["weapon_id"])
            if not weapon:
                raise ValueError("سلاح پیدا نشد.")
            country = database.get_country(country_id)
            req = database.get_weapon_requirement(country_id, weapon["id"])
            if req is not None and req.get("is_allowed", 0) == 0:
                raise ValueError(f"ساخت {weapon['name']} برای این کشور مجاز نیست.")
            if req is not None:
                if country.get("daily_industry_income", 0) < int(req.get("min_factories", 0)):
                    raise ValueError(f"صنعت کافی نیست. حداقل نیاز: {req.get('min_factories', 0)}")
                if country.get("daily_knowledge_income", 0) < int(req.get("min_universities", 0)):
                    raise ValueError(f"دانش کافی نیست. حداقل نیاز: {req.get('min_universities', 0)}")
                if country["money"] < float(req.get("min_money", 0)):
                    raise ValueError(f"پول کافی نیست. حداقل نیاز: {money_text(req.get('min_money', 0))}")
            cost, industry_need, knowledge_need = build_weapon_cost(weapon, qty)
            if country["money"] < cost:
                raise ValueError("پول کافی ندارید.")
            if country.get("daily_industry_income", 0) < industry_need:
                raise ValueError(f"صنعت کافی نیست. حداقل نیاز: {industry_need}")
            if country.get("daily_knowledge_income", 0) < knowledge_need:
                raise ValueError(f"دانش کافی نیست. حداقل نیاز: {knowledge_need}")

            database.change_money(country_id, -cost)
            database.add_weapon(country_id, weapon["id"], qty)
            bot.send_message(
                message.chat.id,
                f"✅ {weapon['name']} به تعداد {qty} ساخته شد.\n\n💰 هزینه: {money_text(cost)}\n🏭 صنعت مصرفی: {industry_need}\n🎓 دانش مصرفی: {knowledge_need}",
            )

        elif action == "transfer_weapon_quantity":
            target_country_id = state.get("target_country_id")
            qty = int(message.text.strip())
            if qty <= 0:
                raise ValueError("تعداد باید بیشتر از صفر باشد.")
            if not target_country_id:
                raise ValueError("کشور مقصد انتخاب نشده است.")

            target_country = database.get_country(target_country_id)
            if not target_country:
                raise ValueError("کشور مقصد پیدا نشد.")
            if target_country["id"] == country_id:
                raise ValueError("کشور مقصد نمی‌تواند همان کشور باشد.")

            weapon = database.get_weapon(state["weapon_id"])
            if not weapon:
                raise ValueError("سلاح پیدا نشد.")
            source_quantity = database.get_weapon_quantity(country_id, weapon["id"])
            if source_quantity < qty:
                raise ValueError("تعداد سلاح در انبار شما کافی نیست.")

            database.remove_weapon(country_id, weapon["id"], qty)
            database.add_weapon(target_country["id"], weapon["id"], qty)
            transfer_message = (
                f"🚚 انتقال تجهیزات\n"
                f"{database.get_country(country_id)['name']} به {target_country['name']}\n"
                f"سلاح: {weapon['name']} | تعداد: {qty}"
            )
            notify_sanction_watchers(target_country["id"], transfer_message)
            notify_country_receipt(
                target_country["id"],
                "🚚 یک انتقال تجهیزات به کشور شما رسید.",
                sender_country_name=database.get_country(country_id)['name'],
                item_name=weapon['name'],
                item_count=qty,
            )
            bot.send_message(
                message.chat.id,
                f"✅ {weapon['name']} به تعداد {qty} به {target_country['name']} منتقل شد.",
            )

        elif action == "transfer_money_quantity":
            target_country_id = state.get("target_country_id")
            if not target_country_id:
                raise ValueError("کشور مقصد انتخاب نشده است.")

            target_country = database.get_country(target_country_id)
            if not target_country:
                raise ValueError("کشور مقصد پیدا نشد.")

            amount = float(message.text.strip())
            if amount <= 0:
                raise ValueError("مبلغ باید بیشتر از صفر باشد.")

            source_country = database.get_country(country_id)
            if source_country["money"] < amount:
                raise ValueError("پول کافی برای انتقال ندارید.")

            database.change_money(country_id, -amount)
            database.change_money(target_country["id"], amount)
            transfer_message = (
                f"💸 انتقال پول\n"
                f"{source_country['name']} مبلغ {money_text(amount)} را به {target_country['name']} منتقل کرد."
            )
            notify_sanction_watchers(target_country["id"], transfer_message)
            notify_country_receipt(
                target_country["id"],
                "💸 مبلغی به حساب شما واریز شد.",
                sender_country_name=source_country['name'],
                amount=amount,
            )
            bot.send_message(
                message.chat.id,
                f"✅ {money_text(amount)} به {target_country['name']} منتقل شد.",
            )

        elif action in {"economy_build_quantity", "economy_build"}:
            asset = state["asset"]
            qty = int(message.text.strip())
            if qty <= 0:
                raise ValueError("تعداد باید بیشتر از صفر باشد.")
            country = database.get_country(country_id)
            cost, gain = build_asset_cost(asset, qty)
            if country["money"] < cost:
                raise ValueError("پول کافی برای ساخت این بخش ندارید.")

            database.change_money(country_id, -cost)
            if asset == "factories":
                database.update_country(country_id, factories=country["factories"] + qty)
            elif asset == "banks":
                database.update_country(country_id, banks=country["banks"] + qty)
            elif asset == "universities":
                database.update_country(country_id, universities=country["universities"] + qty)

            new_country = database.get_country(country_id)
            update_payload = {}
            if "money" in gain:
                update_payload["daily_money_income"] = new_country.get("daily_money_income", 0) + gain["money"]
            if "industry" in gain:
                update_payload["daily_industry_income"] = new_country.get("daily_industry_income", 0) + gain["industry"]
            if "knowledge" in gain:
                update_payload["daily_knowledge_income"] = new_country.get("daily_knowledge_income", 0) + gain["knowledge"]
            if update_payload:
                database.update_country(country_id, **update_payload)
            bot.send_message(
                message.chat.id,
                f"✅ {qty} عدد {get_asset_label(asset)} ساخته شد.\n\n💰 هزینه: {money_text(cost)}\n📈 درآمد روزانه افزوده شد: {gain}",
            )

        elif action in {"investment", "investment_quantity"}:
            asset = state.get("asset")
            if not asset:
                value = message.text.strip().lower()
                parts = value.split()
                if len(parts) != 2:
                    raise ValueError("فرمت اشتباه است. مثال: factory 2")
                asset_name, qty_text = parts
                asset_map = {"factory": "factories", "bank": "banks", "university": "universities"}
                if asset_name not in asset_map:
                    raise ValueError("نوع سرمایه گذاری نامعتبر است. فقط factory | bank | university")
                asset = asset_map[asset_name]
                qty = int(qty_text)
            else:
                qty = int(message.text.strip())

            if qty <= 0:
                raise ValueError("تعداد باید بیشتر از صفر باشد.")

            target_country = database.get_country(target_country_id)
            source_country = database.get_country(country_id)
            if not target_country:
                raise ValueError("کشور مقصد پیدا نشد.")

            cost = BUILDING_COSTS[asset] * qty
            if source_country["money"] < cost:
                raise ValueError(f"پول کافی برای سرمایه گذاری ندارید. حداکثر تعداد قابل سرمایه‌گذاری: {int(source_country['money'] // BUILDING_COSTS[asset])}")

            database.change_money(country_id, -cost)
            current_target = database.get_country(target_country_id)
            database.update_country(target_country_id, **{asset: current_target[asset] + qty})
            database.record_foreign_investment(country_id, target_country_id, asset, qty)

            notify_country_receipt(
                target_country_id,
                "💼 سرمایه گذاری خارجی به کشور شما وارد شد.",
                sender_country_name=source_country['name'],
                item_name=get_asset_label(asset),
                item_count=qty,
            )

            income_delta = BUILDING_INCOME[asset]
            investor_income_update = {}
            target_income_update = {}
            for income_key, delta_value in income_delta.items():
                split_value = (delta_value * qty) / 2
                income_column = {
                    "money": "daily_money_income",
                    "industry": "daily_industry_income",
                    "knowledge": "daily_knowledge_income",
                }[income_key]
                investor_income_update[income_column] = source_country.get(income_column, 0) + split_value
                target_income_update[income_column] = current_target.get(income_column, 0) + split_value

            database.update_country(country_id, **investor_income_update)
            database.update_country(target_country_id, **target_income_update)
            notify_sanction_watchers(
                target_country_id,
                f"💼 سرمایه گذاری خارجی\n{source_country['name']} {qty} عدد {get_asset_label(asset)} در {target_country['name']} ایجاد کرد.",
            )
            bot.send_message(
                message.chat.id,
                f"✅ سرمایه گذاری انجام شد.\n\n{source_country['name']} {qty} عدد {get_asset_label(asset)} در {target_country['name']} ساخت.",
            )

        else:
            raise ValueError("درخواست نامشخص است.")

    except ValueError as exc:
        bot.send_message(message.chat.id, f"❌ {exc}")
    finally:
        user_states.pop(user_id, None)


if __name__ == "__main__":
    print("Inventory Bot started...")
    bot.infinity_polling(skip_pending=True)
