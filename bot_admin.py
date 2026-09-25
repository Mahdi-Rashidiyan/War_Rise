import re

import telebot
from telebot.types import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from settings import ADMIN_IDS, TELEGRAM_BOT_ADMIN_API
import database

def format_country_name(name):
    country = database.get_country_by_name(name)
    return database.country_label(country) if country else name


def parse_country_input(raw_name):
    if not raw_name:
        return raw_name, None

    flag = None
    candidate = raw_name

    if len(raw_name) >= 2 and all(0x1F1E6 <= ord(ch) <= 0x1F1FF for ch in raw_name[-2:]):
        flag = raw_name[-2:]
        candidate = raw_name[:-2]

    if candidate and candidate[-1] in " ":
        candidate = candidate.rstrip()

    return candidate, flag


# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = TELEGRAM_BOT_ADMIN_API

# Telegram user ID of the game administrator
bot = telebot.TeleBot(BOT_TOKEN)
bot.set_my_commands([
    BotCommand("start", "شروع و نمایش منو اصلی"),
])
admin_states = {}

WEAPON_CATEGORY_OPTIONS = {
    "intelligence": {
        "label": "نیروی جاسوسی",
        "items": {
            "intel_info": "جاسوس اطلاعاتی",
            "intel_ops": "جاسوس عملیاتی",
        },
    },
    "air_force": {
        "label": "نیروی هوایی",
        "items": {
            "helicopter": "هلیکوپتر",
            "fighter": "جنگنده",
            "drone": "پهپاد",
        },
    },
    "missile_defense": {
        "label": "نیروی موشکی و پدافندی",
        "items": {
            "cruise": "موشک کروز",
            "ballistic": "موشک بالستیک",
            "icbm": "موشک قاره‌پیما",
            "air_defense": "پدافند هوایی",
        },
    },
    "navy": {
        "label": "نیروی دریایی",
        "items": {
            "destroyer": "ناوشکن",
            "warship": "ناو",
            "submarine": "زیردریایی",
            "carrier": "ناو هواپیمابر",
        },
    },
    "non_conventional": {
        "label": "تسلیحات غیر متعارف",
        "items": {
            "chemical": "بمب شیمیایی",
            "napalm": "بمب ناپالم",
            "nuclear": "بمب هسته‌ای",
        },
    },
}

WEAPON_BUILD_CATEGORY_ORDER = [
    "نیروی جاسوسی",
    "نیروی هوایی",
    "نیروی موشکی و پدافندی",
    "نیروی دریایی",
    "تسلیحات غیر متعارف",
]


# ============================================================
# ADMIN CHECK
# ============================================================

def is_admin(user_id):
    return user_id in ADMIN_IDS


def admin_only(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(
            message,
            "⛔ شما دسترسی ادمین ندارید."
        )
        return False

    return True


def parse_weapon_name(raw_text):
    text = (raw_text or "").strip()
    if not text:
        raise ValueError("نام سلاح نباید خالی باشد.")

    flag = None
    candidate = text
    if len(text) >= 2 and all(0x1F1E6 <= ord(ch) <= 0x1F1FF for ch in text[-2:]):
        flag = text[-2:]
        candidate = text[:-2].rstrip()

    if not candidate:
        raise ValueError("نام سلاح نامعتبر است.")

    return candidate, flag


def send_weapon_category_menu(chat_id):
    markup = InlineKeyboardMarkup(row_width=1)
    for key, info in WEAPON_CATEGORY_OPTIONS.items():
        markup.add(
            InlineKeyboardButton(info["label"], callback_data=f"addweapon_category:{key}")
        )
    bot.send_message(chat_id, "🧩 دسته سلاح را انتخاب کنید:", reply_markup=markup)


def send_weapon_subtype_menu(chat_id, category_key):
    info = WEAPON_CATEGORY_OPTIONS.get(category_key)
    if not info:
        bot.send_message(chat_id, "❌ دسته نامعتبر است.")
        return

    markup = InlineKeyboardMarkup(row_width=1)
    for item_key, label in info["items"].items():
        markup.add(
            InlineKeyboardButton(label, callback_data=f"addweapon_subtype:{category_key}:{item_key}")
        )
    bot.send_message(chat_id, f"{info['label']} — نوع سلاح را انتخاب کنید:", reply_markup=markup)


def send_country_access_menu(chat_id, weapon_id, weapon_name):
    countries = database.get_all_countries()
    markup = InlineKeyboardMarkup(row_width=1)
    for country in countries:
        requirement = database.get_weapon_requirement(country["id"], weapon_id)
        selected = bool(requirement and requirement.get("is_allowed", 1) == 1)
        label = f"{'✅' if selected else '❌'} {country['name']}"
        markup.add(
            InlineKeyboardButton(label, callback_data=f"weapon_country_toggle:{weapon_id}:{country['id']}")
        )
    markup.add(InlineKeyboardButton("✅ پایان", callback_data=f"weapon_country_done:{weapon_id}"))
    bot.send_message(
        chat_id,
        f"🌍 کشوری را برای ساخت {weapon_name} انتخاب کنید. روی هر کشور کلیک کنید تا مجاز/غیرفعال شود.\n\nبرای هر کشور مجاز، بعد از انتخاب، مقدار صنعت، دانش و پول لازم را به فرم زیر وارد کنید:\nمثال: 8 6 250000",
        reply_markup=markup,
    )


# ============================================================
# START
# ============================================================

@bot.message_handler(commands=["start"])
def start(message):

    if not admin_only(message):
        return

    text = """
👑 پنل مدیریت بازی

🌍 کشورها:
/countries
/addcountry

💰 اقتصاد:
/setmoney
/addmoney
/removemoney

🪖 تجهیزات:
/addweapon_type
/addweapon
/giveweapon
/inventory
/set_weapon_access
/list_weapon_access

🏳️ گروه‌ها:
/setcountry
/groupcountry

ℹ️ اطلاعات:
/country

مثال:

/addcountry Iran 🇮🇷 1000000 10 5 20 50000

/setcountry Iran

/setmoney Iran 5000000

/addmoney Iran 100000

/addweapon_type Tank land 50000 50 30

/giveweapon Iran Tank 100

/inventory Iran
"""

    bot.send_message(
        message.chat.id,
        text
    )


# ============================================================
# COUNTRIES
# ============================================================

@bot.message_handler(commands=["countries"])
def countries(message):

    if not admin_only(message):
        return

    countries = database.get_all_countries()

    if not countries:
        bot.reply_to(
            message,
            "❌ هنوز هیچ کشوری ساخته نشده."
        )
        return

    text = "🌍 کشورهای بازی:\n\n"

    for country in countries:
        country_label = format_country_name(country['name'])
        text += (
            f"🆔 {country['id']}\n"
            f"🏳️ {country_label}\n"
            f"💰 ${country['money']:,.0f}\n"
            f"🏭 کارخانه: {country['factories']}\n"
            f"🏦 بانک: {country['banks']}\n"
            f"🎓 دانشگاه: {country['universities']}\n"
            f"📈 درآمد روزانه: ${country['daily_income']:,.0f}\n"
            f"━━━━━━━━━━━━━━\n"
        )

    bot.send_message(
        message.chat.id,
        text
    )


@bot.message_handler(commands=["addcountry"])
def add_country(message):

    if not admin_only(message):
        return

    args = message.text.split()

    if len(args) not in (7, 8):
        bot.reply_to(
            message,
            """
❌ فرمت اشتباه.

فرمت:

/addcountry NAME [FLAG] MONEY FACTORIES BANKS UNIVERSITIES DAILY_INCOME

مثال:

/addcountry Iran 🇮🇷 1000000 10 5 20 50000

یا

/addcountry Iran 1000000 10 5 20 50000
"""
        )
        return

    try:
        raw_name = args[1]
        name, flag = parse_country_input(raw_name)

        if len(args) == 8:
            flag = args[2] if args[2] and not re.fullmatch(r"-?\d+(?:\.\d+)?", args[2]) else flag
            money = float(args[3])
            factories = int(args[4])
            banks = int(args[5])
            universities = int(args[6])
            daily_income = float(args[7])
        else:
            money = float(args[2])
            factories = int(args[3])
            banks = int(args[4])
            universities = int(args[5])
            daily_income = float(args[6])

        country_id = database.create_country(
            name=name,
            flag=flag or "",
            money=money,
            factories=factories,
            banks=banks,
            universities=universities,
            daily_income=daily_income
        )

        bot.reply_to(
            message,
            f"""
✅ کشور ساخته شد.

🌍 کشور: {format_country_name(name)}
🆔 ID: {country_id}
💰 پول: ${money:,.0f}
🏭 کارخانه: {factories}
🏦 بانک: {banks}
🎓 دانشگاه: {universities}
📈 درآمد روزانه: ${daily_income:,.0f}
"""
        )

    except ValueError as e:

        bot.reply_to(
            message,
            f"❌ خطا: {e}"
        )

    except Exception as e:

        bot.reply_to(
            message,
            f"❌ خطا در ساخت کشور:\n{e}"
        )


# ============================================================
# COUNTRY INFO
# ============================================================

@bot.message_handler(commands=["country"])
def country_info(message):

    if not admin_only(message):
        return

    args = message.text.split()

    if len(args) != 2:
        bot.reply_to(
            message,
            "مثال:\n/country Iran"
        )
        return

    name = args[1]

    country = database.get_country_by_name(name)

    if not country:
        bot.reply_to(
            message,
            "❌ کشور پیدا نشد."
        )
        return

    group_id = database.get_group_by_country(
        country["id"]
    )

    text = (
        f"🌍 {format_country_name(country['name'])}\n\n"
        f"🆔 ID: {country['id']}\n"
        f"💰 پول: ${country['money']:,.0f}\n"
        f"🏭 کارخانه: {country['factories']}\n"
        f"🏦 بانک: {country['banks']}\n"
        f"🎓 دانشگاه: {country['universities']}\n"
        f"📈 درآمد روزانه: ${country['daily_income']:,.0f}\n"
    )

    if group_id:
        text += f"\n💬 Group ID: `{group_id}`"

    else:
        text += "\n💬 گروه: هنوز متصل نشده"

    bot.send_message(
        message.chat.id,
        text,
        parse_mode="Markdown"
    )


# ============================================================
# MONEY
# ============================================================

@bot.message_handler(commands=["setmoney"])
def set_money(message):

    if not admin_only(message):
        return

    args = message.text.split()

    if len(args) != 3:
        bot.reply_to(
            message,
            "مثال:\n/setmoney Iran 5000000"
        )
        return

    country_name = args[1]

    try:
        amount = float(args[2])

        country = database.get_country_by_name(
            country_name
        )

        if not country:
            bot.reply_to(
                message,
                "❌ کشور پیدا نشد."
            )
            return

        database.update_country(
            country["id"],
            money=amount
        )

        bot.reply_to(
            message,
            f"✅ پول {country_name} شد ${amount:,.0f}"
        )

    except ValueError:
        bot.reply_to(
            message,
            "❌ مقدار پول باید عدد باشد."
        )


@bot.message_handler(commands=["addmoney"])
def add_money(message):

    if not admin_only(message):
        return

    args = message.text.split()

    if len(args) != 3:
        bot.reply_to(
            message,
            "مثال:\n/addmoney Iran 50000"
        )
        return

    country_name = args[1]

    try:
        amount = float(args[2])

        country = database.get_country_by_name(
            country_name
        )

        if not country:
            bot.reply_to(
                message,
                "❌ کشور پیدا نشد."
            )
            return

        new_money = database.change_money(
            country["id"],
            amount
        )

        bot.reply_to(
            message,
            f"""
✅ پول اضافه شد.

🌍 {country_name}
➕ ${amount:,.0f}
💰 موجودی جدید: ${new_money:,.0f}
"""
        )

    except ValueError as e:

        bot.reply_to(
            message,
            f"❌ {e}"
        )


@bot.message_handler(commands=["removemoney"])
def remove_money(message):

    if not admin_only(message):
        return

    args = message.text.split()

    if len(args) != 3:
        bot.reply_to(
            message,
            "مثال:\n/removemoney Iran 50000"
        )
        return

    country_name = args[1]

    try:
        amount = float(args[2])

        if amount <= 0:
            raise ValueError(
                "مقدار باید بیشتر از صفر باشد."
            )

        country = database.get_country_by_name(
            country_name
        )

        if not country:
            bot.reply_to(
                message,
                "❌ کشور پیدا نشد."
            )
            return

        new_money = database.change_money(
            country["id"],
            -amount
        )

        bot.reply_to(
            message,
            f"""
✅ پول کم شد.

🌍 {country_name}
➖ ${amount:,.0f}
💰 موجودی جدید: ${new_money:,.0f}
"""
        )

    except ValueError as e:

        bot.reply_to(
            message,
            f"❌ {e}"
        )


# ============================================================
# SET GROUP COUNTRY
# ============================================================

@bot.message_handler(commands=["setcountry"])
def set_country(message):

    if not admin_only(message):
        return

    args = message.text.split()

    if len(args) != 2:
        bot.reply_to(
            message,
            "این دستور را داخل گروه کشور اجرا کن:\n\n"
            "/setcountry Iran"
        )
        return

    country_name = args[1]

    country = database.get_country_by_name(
        country_name
    )

    if not country:
        bot.reply_to(
            message,
            "❌ کشور پیدا نشد."
        )
        return

    chat_id = message.chat.id

    try:

        database.assign_group_to_country(
            chat_id,
            country["id"]
        )

        bot.reply_to(
            message,
            f"""
✅ این گروه به کشور {country_name} متصل شد.

🌍 کشور: {country_name}
🆔 Country ID: {country['id']}
💬 Chat ID: {chat_id}
"""
        )

    except ValueError as e:

        bot.reply_to(
            message,
            f"❌ {e}"
        )


# ============================================================
# GROUP COUNTRY
# ============================================================

@bot.message_handler(commands=["groupcountry"])
def group_country(message):

    if not admin_only(message):
        return

    country = database.get_country_by_group(
        message.chat.id
    )

    if not country:

        bot.reply_to(
            message,
            "❌ این گروه هنوز به هیچ کشوری متصل نشده."
        )
        return

    bot.reply_to(
        message,
        f"""
🌍 کشور این گروه:

{format_country_name(country['name'])}

🆔 Country ID: {country['id']}
"""
    )


@bot.message_handler(commands=["addweapon"])
def add_weapon_start(message):
    if not admin_only(message):
        return

    admin_states[message.from_user.id] = {"stage": "category"}
    send_weapon_category_menu(message.chat.id)


@bot.callback_query_handler(func=lambda call: call.data.startswith("addweapon_category:"))
def addweapon_category(call):
    if not is_admin(call.from_user.id):
        return

    category_key = call.data.split(":", 1)[1]
    admin_states[call.from_user.id] = {"stage": "subtype", "category": category_key}
    send_weapon_subtype_menu(call.message.chat.id, category_key)


@bot.callback_query_handler(func=lambda call: call.data.startswith("addweapon_subtype:"))
def addweapon_subtype(call):
    if not is_admin(call.from_user.id):
        return

    _, category_key, subtype_key = call.data.split(":", 2)
    admin_states[call.from_user.id] = {
        "stage": "name",
        "category": category_key,
        "subtype": subtype_key,
    }
    category_label = WEAPON_CATEGORY_OPTIONS.get(category_key, {}).get("label", "سلاح")
    subtype_label = WEAPON_CATEGORY_OPTIONS.get(category_key, {}).get("items", {}).get(subtype_key, "سلاح")
    bot.send_message(
        call.message.chat.id,
        f"{category_label} → {subtype_label}\n\nنام سلاح را وارد کنید. اگر می‌خواهید پرچم کشور را هم داشته باشد، در انتهای نام پرچم را بگذارید، مثل:\nF-14 Tomcat 🇮🇷",
    )


@bot.message_handler(content_types=["text"])
def handle_admin_text(message):
    if message.text.startswith("/"):
        return

    user_id = message.from_user.id
    state = admin_states.get(user_id)
    if not state:
        return

    stage = state.get("stage")

    if stage == "name":
        category = state.get("category")
        subtype = state.get("subtype")
        subtype_label = WEAPON_CATEGORY_OPTIONS.get(category, {}).get("items", {}).get(subtype, "سلاح")

        try:
            name, flag = parse_weapon_name(message.text)
            display_name = f"{name} {flag}" if flag else name
            admin_states[user_id] = {
                "stage": "stats",
                "category": category,
                "subtype": subtype,
                "weapon_name": display_name,
                "subtype_label": subtype_label,
            }
            bot.send_message(
                message.chat.id,
                f"سلاح: {display_name}\n\nقیمت، حمله، دفاع، هزینه صنعت و هزینه دانش را به این شکل وارد کنید:\nمثال: 1200000 95 75 8 6\n\nاگر نخواهید هزینه مخصوص داشته باشید، می‌توانید 3 عدد هم وارد کنید: 1200000 95 75",
            )
        except ValueError as e:
            bot.reply_to(message, f"❌ {e}")
        return

    if stage == "stats":
        try:
            parts = message.text.strip().split()
            if len(parts) not in (3, 5):
                raise ValueError("فرمت اشتباه است. مثال: 1200000 95 75 8 6")
            price = float(parts[0])
            attack = float(parts[1])
            defense = float(parts[2])
            industry_cost = int(parts[3]) if len(parts) == 5 else 0
            knowledge_cost = int(parts[4]) if len(parts) == 5 else 0
            name = state["weapon_name"]
            subtype_label = state.get("subtype_label", "سلاح")
            category_label = WEAPON_CATEGORY_OPTIONS.get(state["category"], {}).get("label", "سلاح")

            weapon_id = database.create_weapon(
                name=name,
                category=subtype_label,
                price=price,
                attack_power=attack,
                defense_power=defense,
                industry_cost=industry_cost,
                knowledge_cost=knowledge_cost,
                description=f"{category_label} / {subtype_label}",
            )
            database.restrict_weapon_by_default(weapon_id)
            admin_states[user_id] = {
                "stage": "country_access",
                "weapon_id": weapon_id,
                "weapon_name": name,
            }
            send_country_access_menu(message.chat.id, weapon_id, name)
        except ValueError as e:
            bot.reply_to(message, f"❌ {e}")
        return

    if stage == "weapon_requirements":
        try:
            parts = message.text.strip().split()
            if len(parts) != 3:
                raise ValueError("فرمت اشتباه است. مثال: 8 6 250000")
            min_factories = int(parts[0])
            min_universities = int(parts[1])
            min_money = float(parts[2])
            country_id = state["country_id"]
            weapon_id = state["weapon_id"]
            weapon_name = state.get("weapon_name", "سلاح")

            database.set_weapon_requirement(
                country_id=country_id,
                weapon_id=weapon_id,
                min_factories=min_factories,
                min_banks=0,
                min_universities=min_universities,
                min_money=min_money,
                is_allowed=True,
            )

            admin_states[user_id] = {
                "stage": "country_access",
                "weapon_id": weapon_id,
                "weapon_name": weapon_name,
            }
            send_country_access_menu(message.chat.id, weapon_id, weapon_name)
            bot.send_message(
                message.chat.id,
                f"✅ نیازهای ساخت برای {database.get_country(country_id)['name']} ثبت شد.\n\n🏭 صنعت: {min_factories}\n🎓 دانش: {min_universities}\n💰 پول: {min_money:,.0f}",
            )
        except ValueError as e:
            bot.reply_to(message, f"❌ {e}")
        return


@bot.callback_query_handler(func=lambda call: call.data.startswith("weapon_country_toggle:"))
def weapon_country_toggle(call):
    if not is_admin(call.from_user.id):
        return

    _, weapon_id, country_id = call.data.split(":")
    weapon_id = int(weapon_id)
    country_id = int(country_id)
    weapon = database.get_weapon(weapon_id)
    if not weapon:
        bot.send_message(call.message.chat.id, "❌ سلاح پیدا نشد.")
        return

    current = database.get_weapon_requirement(country_id, weapon_id)
    is_allowed = not bool(current and current.get("is_allowed", 1) == 1)

    if is_allowed:
        admin_states[call.from_user.id] = {
            "stage": "weapon_requirements",
            "weapon_id": weapon_id,
            "country_id": country_id,
            "weapon_name": weapon["name"],
        }
        bot.send_message(
            call.message.chat.id,
            f"🌍 {database.get_country(country_id)['name']} انتخاب شد.\n\nبرای این کشور حداقل نیاز ساخت را وارد کنید:\nفرمت: INDUSTRY KNOWLEDGE MONEY\nمثال: 8 6 250000",
        )
        return

    database.set_weapon_requirement(
        country_id=country_id,
        weapon_id=weapon_id,
        min_factories=0,
        min_banks=0,
        min_universities=0,
        min_money=0,
        is_allowed=False,
    )
    admin_states[call.from_user.id] = {"stage": "country_access", "weapon_id": weapon_id, "weapon_name": weapon["name"]}
    send_country_access_menu(call.message.chat.id, weapon_id, weapon["name"])


@bot.callback_query_handler(func=lambda call: call.data.startswith("weapon_country_done:"))
def weapon_country_done(call):
    if not is_admin(call.from_user.id):
        return

    _, weapon_id = call.data.split(":")
    weapon = database.get_weapon(int(weapon_id))
    if weapon:
        bot.send_message(call.message.chat.id, f"✅ تنظیم کشورها برای {weapon['name']} انجام شد.")
    else:
        bot.send_message(call.message.chat.id, "✅ تنظیم سلاح انجام شد.")
    admin_states.pop(call.from_user.id, None)


# ============================================================
# ADD WEAPON TYPE
# ============================================================

@bot.message_handler(commands=["addweapon_type"])
def add_weapon_type(message):

    if not admin_only(message):
        return

    args = message.text.split()

    if len(args) < 7:

        bot.reply_to(
            message,
            """
❌ فرمت:

/addweapon_type NAME CATEGORY PRICE ATTACK DEFENSE

مثال:

/addweapon_type Tank land 50000 50 30
"""
        )
        return

    try:

        name = args[1]
        category = args[2]
        price = float(args[3])
        attack = float(args[4])
        defense = float(args[5])

        description = " ".join(args[6:]) if len(args) > 6 else ""

        weapon_id = database.create_weapon(
            name=name,
            category=category,
            price=price,
            attack_power=attack,
            defense_power=defense,
            description=description
        )
        database.restrict_weapon_by_default(weapon_id)

        bot.reply_to(
            message,
            f"""
✅ نوع سلاح ساخته شد.

🪖 {name}
🆔 ID: {weapon_id}
📂 Category: {category}
💵 Price: ${price:,.0f}
⚔️ Attack: {attack}
🛡 Defense: {defense}
"""
        )

    except ValueError as e:

        bot.reply_to(
            message,
            f"❌ {e}"
        )


@bot.message_handler(commands=["set_weapon_access"])
def set_weapon_access(message):
    if not admin_only(message):
        return

    args = message.text.split()
    if len(args) not in (7, 8):
        bot.reply_to(
            message,
            """
❌ فرمت اشتباه.

/set_weapon_access COUNTRY_NAME WEAPON_NAME FACTORIES BANKS UNIVERSITIES MONEY [allow|deny]

مثال:
/set_weapon_access Iran F-35 2 1 3 200000 allow
"""
        )
        return

    try:
        country = database.get_country_by_name(args[1])
        if not country:
            raise ValueError("کشور پیدا نشد.")

        weapon = database.get_weapon_by_name(args[2])
        if not weapon:
            raise ValueError("سلاح پیدا نشد.")

        min_factories = int(args[3])
        min_banks = int(args[4])
        min_universities = int(args[5])
        min_money = float(args[6])
        allow = args[7].lower() if len(args) == 8 else "allow"
        is_allowed = allow != "deny"

        database.set_weapon_requirement(
            country_id=country["id"],
            weapon_id=weapon["id"],
            min_factories=min_factories,
            min_banks=min_banks,
            min_universities=min_universities,
            min_money=min_money,
            is_allowed=is_allowed,
        )

        bot.reply_to(
            message,
            f"✅ دسترسی سلاح به‌روزرسانی شد.\n\n🌍 {country['name']}\n🪖 {weapon['name']}\n🏭 حداقل کارخانه: {min_factories}\n🏦 حداقل بانک: {min_banks}\n🎓 حداقل دانشگاه: {min_universities}\n💰 حداقل پول: {min_money:,.0f}\n✅ مجاز: {is_allowed}"
        )
    except ValueError as e:
        bot.reply_to(message, f"❌ {e}")


@bot.message_handler(commands=["list_weapon_access"])
def list_weapon_access(message):
    if not admin_only(message):
        return

    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(message, "مثال:\n/list_weapon_access Iran")
        return

    country = database.get_country_by_name(args[1])
    if not country:
        bot.reply_to(message, "❌ کشور پیدا نشد.")
        return

    rows = database.get_country_restricted_weapons(country["id"])
    if not rows:
        bot.reply_to(message, f"❌ برای {country['name']} هیچ محدودیتی برای سلاح‌ها تنظیم نشده است.")
        return

    text = f"🛡 محدودیت‌های سلاح‌های {country['name']}\n\n"
    for row in rows:
        status = "مجاز" if row["is_allowed"] else "غیرفعال"
        text += (
            f"• {row['name']} ({row['category']})\n"
            f"  🏭 {row['min_factories']} | 🏦 {row['min_banks']} | 🎓 {row['min_universities']} | 💰 {row['min_money']:,.0f}\n"
            f"  وضعیت: {status}\n\n"
        )
    bot.send_message(message.chat.id, text)


# ============================================================
# GIVE WEAPON
# ============================================================

@bot.message_handler(commands=["giveweapon"])
def give_weapon(message):

    if not admin_only(message):
        return

    args = message.text.split()

    if len(args) != 4:

        bot.reply_to(
            message,
            "مثال:\n/giveweapon Iran Tank 100"
        )
        return

    country_name = args[1]
    weapon_name = args[2]

    try:
        quantity = int(args[3])

        if quantity <= 0:
            raise ValueError(
                "تعداد باید بیشتر از صفر باشد."
            )

        country = database.get_country_by_name(
            country_name
        )

        if not country:
            bot.reply_to(
                message,
                "❌ کشور پیدا نشد."
            )
            return

        weapon = database.get_weapon_by_name(
            weapon_name
        )

        if not weapon:
            bot.reply_to(
                message,
                "❌ سلاح پیدا نشد."
            )
            return

        database.add_weapon(
            country["id"],
            weapon["id"],
            quantity
        )

        total = database.get_weapon_quantity(
            country["id"],
            weapon["id"]
        )

        bot.reply_to(
            message,
            f"""
✅ تجهیزات اضافه شد.

🌍 کشور: {country_name}
🪖 سلاح: {weapon_name}
➕ تعداد: {quantity}
📦 موجودی فعلی: {total}
"""
        )

    except ValueError as e:

        bot.reply_to(
            message,
            f"❌ {e}"
        )


# ============================================================
# INVENTORY
# ============================================================

@bot.message_handler(commands=["inventory"])
def inventory(message):

    if not admin_only(message):
        return

    args = message.text.split()

    if len(args) != 2:

        bot.reply_to(
            message,
            "مثال:\n/inventory Iran"
        )
        return

    country_name = args[1]

    country = database.get_country_by_name(
        country_name
    )

    if not country:

        bot.reply_to(
            message,
            "❌ کشور پیدا نشد."
        )
        return

    inventory = database.get_country_inventory(
        country["id"]
    )

    if not inventory:

        bot.reply_to(
            message,
            f"📦 {country_name} هیچ تجهیزات نظامی ندارد."
        )
        return

    text = f"🪖 موجودی نظامی {country_name}\n\n"

    for weapon in inventory:

        text += (
            f"• {weapon['name']}\n"
            f"  📂 {weapon['category']}\n"
            f"  📦 {weapon['quantity']}\n"
            f"  ⚔️ {weapon['attack_power']}\n"
            f"  🛡 {weapon['defense_power']}\n\n"
        )

    bot.send_message(
        message.chat.id,
        text
    )


# ============================================================
# RUN BOT
# ============================================================

if __name__ == "__main__":

    print("================================")
    print("ADMIN BOT STARTED")
    print("================================")

    bot.infinity_polling(
        skip_pending=True
    )