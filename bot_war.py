import threading

import telebot
from telebot.types import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup

import database
from settings import ADMIN_IDS, NEWS_CHANNEL_ID, TELEGRAM_BOT_WAR_API, TELEGRAM_MAINBOT_API

news_bot = telebot.TeleBot(token=TELEGRAM_MAINBOT_API)


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


bot = telebot.TeleBot(token=TELEGRAM_BOT_WAR_API)
bot.set_my_commands([
    BotCommand("start", "شروع و نمایش منو اصلی"),
    BotCommand("hamle", "شروع درخواست حمله و انتخاب هدف جنگ"),
])
user_data = {}
defense_states = {}
ally_states = {}
war_requests = {}
war_alliance_status = {}

WAR_GOALS = {
    "warning": "🚨 عملیات هشدار آمیز",
    "regional": "🌍 حمله کامل به منطقه کشور",
    "infrastructure": "💥 حمله و نابودی زیرساخت‌ها",
    "collapse": "💣 ساقط کردن کشور",
}


def get_country_for_chat(chat_id):
    return database.get_country_by_group(chat_id)


def country_label(country):
    return database.country_label(country)


def country_menu(exclude_country_id=None):
    markup = InlineKeyboardMarkup(row_width=1)
    countries = database.get_all_countries()
    for country in countries:
        if exclude_country_id is not None and country["id"] == exclude_country_id:
            continue
        markup.add(InlineKeyboardButton(f"{country_label(country)}", callback_data=f"war_target:{country['id']}"))
    return markup


def allied_country_ids(country_id):
    allies = set()
    for alliance in database.get_country_alliances(country_id):
        for member in database.get_alliance_members(alliance["id"]):
            if member["id"] != country_id:
                allies.add(member["id"])
    return allies


def goal_menu(include_ally_invite=False):
    markup = InlineKeyboardMarkup(row_width=1)
    for key, label in WAR_GOALS.items():
        markup.add(InlineKeyboardButton(label, callback_data=f"war_goal:{key}"))
    if include_ally_invite:
        markup.add(InlineKeyboardButton("📨 دعوت از متحد برای حمله", callback_data="war_invite_ally"))
    return markup


def build_weapon_list(country_id, request_id=None, mode="defense"):
    weapons = database.get_country_inventory(country_id)
    markup = InlineKeyboardMarkup(row_width=1)
    if not weapons:
        markup.add(InlineKeyboardButton("❌ هیچ تسلیحه‌ای موجود نیست", callback_data="war_no_weapon"))
        return markup
    for weapon in weapons:
        label = f"{weapon['name']} — تعداد {weapon['quantity']} | ⚔️ {weapon['attack_power']} | 🛡️ {weapon['defense_power']}"
        if request_id and mode == "ally":
            markup.add(InlineKeyboardButton(label, callback_data=f"war_ally_weapon:{weapon['id']}:{request_id}"))
        elif request_id:
            markup.add(InlineKeyboardButton(label, callback_data=f"war_weapon:{weapon['id']}:{request_id}"))
        else:
            markup.add(InlineKeyboardButton(label, callback_data=f"war_weapon:{weapon['id']}"))
    return markup


def notify_country(country_id, text, reply_markup=None):
    group_id = database.get_group_by_country(country_id)
    if group_id:
        bot.send_message(group_id, text, reply_markup=reply_markup)


def build_invalid_request_message(reason):
    return f"⚠️ درخواست حمله نامعتبر است.\n{reason}"


def calculate_weapon_loss(quantity, rate):
    quantity = max(0, int(quantity))
    if quantity == 0 or rate <= 0:
        return 0
    return min(quantity, max(1, int(quantity * rate)))


def consume_weapon_losses(country_id, items, rate, loss_log):
    destroyed = 0
    for item in items:
        weapon_id = item.get("weapon_id")
        if weapon_id is None:
            continue

        available = database.get_weapon_quantity(country_id, weapon_id)
        loss_qty = calculate_weapon_loss(min(item.get("quantity", 0), available), rate)
        if loss_qty == 0:
            continue

        try:
            database.remove_weapon(country_id, weapon_id, loss_qty)
        except ValueError:
            continue
        destroyed += loss_qty
        loss_log.append(f"{item.get('name', 'سلاح')} × {loss_qty}")
    return destroyed


def send_war_alliance_invite(request_id, attacker_country_id, defender_country_id, ally_country_id):
    war_alliance_status.setdefault(request_id, {
        "accepted": set(),
        "declined": set(),
        "requested": set(),
        "ally_items": {},
        "attacker_country_id": attacker_country_id,
        "defender_country_id": defender_country_id,
    })
    status = war_alliance_status[request_id]
    if ally_country_id in {attacker_country_id, defender_country_id} or ally_country_id not in allied_country_ids(attacker_country_id):
        return False
    group_id = database.get_group_by_country(ally_country_id)
    if not group_id:
        return False
    status["requested"].add(ally_country_id)
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("✅ قبول", callback_data=f"war_alliance_accept:{request_id}:{ally_country_id}"),
        InlineKeyboardButton("❌ رد", callback_data=f"war_alliance_reject:{request_id}:{ally_country_id}"),
    )
    bot.send_message(
        group_id,
        f"⚔️ کشور {country_label(database.get_country(attacker_country_id))} برای حمله به {country_label(database.get_country(defender_country_id))} از شما درخواست کمک نظامی کرده است. آیا می‌خواهید عضو ائتلاف شوید؟",
        reply_markup=markup,
    )
    return True


def resolve_war_request(request_id):
    req = war_requests.get(request_id)
    if not req:
        return

    state = defense_states.get(request_id, {})
    if not req.get("defense_items") and state.get("defense_items"):
        req["defense_items"] = state["defense_items"]
    if not req.get("defense_total") and state.get("defense_total"):
        req["defense_total"] = state["defense_total"]

    attacker_country = database.get_country(req["attacker_country_id"])
    defender_country = database.get_country(req["defender_country_id"])
    if not attacker_country or not defender_country:
        return

    ally_attack_items = []
    for ally_country_id in req.get("ally_country_ids", []):
        if ally_country_id in {attacker_country["id"], defender_country["id"]}:
            continue
        ally_country = database.get_country(ally_country_id)
        if not ally_country:
            continue
        for weapon in database.get_country_inventory(ally_country_id):
            quantity = max(1, int(weapon["quantity"] * 0.25)) if weapon["quantity"] > 0 else 0
            if quantity == 0:
                continue
            ally_attack_items.append({
                "weapon_id": weapon["id"],
                "name": f"{country_label(ally_country)} - {weapon['name']}",
                "quantity": quantity,
                "attack_power": quantity * float(weapon["attack_power"]),
                "defense_power": quantity * float(weapon["defense_power"]),
                "country_id": ally_country_id,
            })

    own_attack_items = req.get("weapons", [])
    attack_items = own_attack_items + ally_attack_items
    attack_total = float(req.get("attack_total", 0)) + sum(item["attack_power"] for item in ally_attack_items)
    defense_total = float(req.get("defense_total", 0))
    defense_items = req.get("defense_items", [])

    destroyed_factories = 0
    destroyed_banks = 0
    destroyed_universities = 0
    destroyed_weapons = 0
    attacker_destroyed_factories = 0
    attacker_destroyed_banks = 0
    attacker_destroyed_universities = 0
    defender_destroyed_factories = 0
    defender_destroyed_banks = 0
    defender_destroyed_universities = 0
    attacker_weapon_losses = []
    defender_weapon_losses = []
    attacker_weapon_loss_rate = 0
    defender_weapon_loss_rate = 0
    attacker_casualty_rate = 0
    defender_casualty_rate = 0

    war_id = database.create_war(req["attacker_country_id"], req["defender_country_id"], target=req["goal"])
    power_difference = abs(attack_total - defense_total)
    is_draw = power_difference <= max(attack_total, defense_total, 1) * 0.05
    if is_draw:
        outcome = "🤝 جنگ به تعادل رسید"
        desc = "هر دو طرف قدرت مساوی داشتند و نبرد با تلفات محدود و بدون تخریب کامل زیرساخت‌ها به پایان رسید."
        attacker_weapon_loss_rate = 0.15
        defender_weapon_loss_rate = 0.15
        attacker_casualty_rate = 0.1
        defender_casualty_rate = 0.1
    elif attack_total > defense_total:
        outcome = "✅ حمله موفق شد"
        if req["goal"] == "warning":
            desc = "عملیات هشدار آمیز با موفقیت انجام شد و کشور هدف از قصد جنگ مطلع شد."
            attacker_weapon_loss_rate = 0.05
            defender_weapon_loss_rate = 0.05
            attacker_casualty_rate = 0.05
            defender_casualty_rate = 0.05
        elif req["goal"] == "regional":
            destroyed_factories = min(int(defender_country.get("factories", 0) * 0.25), int(defender_country.get("factories", 0)))
            destroyed_banks = min(int(defender_country.get("banks", 0) * 0.15), int(defender_country.get("banks", 0)))
            destroyed_universities = min(int(defender_country.get("universities", 0) * 0.15), int(defender_country.get("universities", 0)))
            defender_destroyed_factories = destroyed_factories
            defender_destroyed_banks = destroyed_banks
            defender_destroyed_universities = destroyed_universities
            desc = "حمله کامل به منطقه کشور انجام شد و مناطق مرزی آسیب دیدند."
            database.update_country(
                defender_country["id"],
                money=max(0, defender_country.get("money", 0) - 150000),
                factories=max(0, defender_country.get("factories", 0) - destroyed_factories),
                banks=max(0, defender_country.get("banks", 0) - destroyed_banks),
                universities=max(0, defender_country.get("universities", 0) - destroyed_universities),
            )
            attacker_weapon_loss_rate = 0.15
            defender_weapon_loss_rate = 0.25
            attacker_casualty_rate = 0.08
            defender_casualty_rate = 0.2
        elif req["goal"] == "infrastructure":
            destroyed_factories = min(int(defender_country.get("factories", 0) * 0.5), int(defender_country.get("factories", 0)))
            destroyed_banks = min(int(defender_country.get("banks", 0) * 0.5), int(defender_country.get("banks", 0)))
            destroyed_universities = min(int(defender_country.get("universities", 0) * 0.5), int(defender_country.get("universities", 0)))
            defender_destroyed_factories = destroyed_factories
            defender_destroyed_banks = destroyed_banks
            defender_destroyed_universities = destroyed_universities
            desc = "زیرساخت‌های کشور هدف با شدت بالا آسیب دیدند."
            database.update_country(
                defender_country["id"],
                factories=max(0, defender_country.get("factories", 0) - destroyed_factories),
                universities=max(0, defender_country.get("universities", 0) - destroyed_universities),
                banks=max(0, defender_country.get("banks", 0) - destroyed_banks),
            )
            attacker_weapon_loss_rate = 0.25
            defender_weapon_loss_rate = 0.5
            attacker_casualty_rate = 0.12
            defender_casualty_rate = 0.3
        elif req["goal"] == "collapse":
            destroyed_factories = min(int(defender_country.get("factories", 0) * 0.7), int(defender_country.get("factories", 0)))
            destroyed_banks = min(int(defender_country.get("banks", 0) * 0.7), int(defender_country.get("banks", 0)))
            destroyed_universities = min(int(defender_country.get("universities", 0) * 0.7), int(defender_country.get("universities", 0)))
            defender_destroyed_factories = destroyed_factories
            defender_destroyed_banks = destroyed_banks
            defender_destroyed_universities = destroyed_universities
            desc = "حمله به کشور هدف فشار سنگینی وارد کرد، اما هنوز همه زیرساخت‌ها نابود نشده‌اند."
            database.update_country(
                defender_country["id"],
                money=max(0, defender_country.get("money", 0) - 500000),
                factories=max(0, int(defender_country.get("factories", 0)) - destroyed_factories),
                universities=max(0, int(defender_country.get("universities", 0)) - destroyed_universities),
                banks=max(0, int(defender_country.get("banks", 0)) - destroyed_banks),
            )
            attacker_weapon_loss_rate = 0.4
            defender_weapon_loss_rate = 0.7
            attacker_casualty_rate = 0.2
            defender_casualty_rate = 0.5
    else:
        outcome = "🛡️ دفاع موفق بود"
        desc = "دفاع کشور هدف با موفقیت مانع پیشروی حمله شد، اما درگیری باعث کاهش تجهیزات هر دو طرف شد."
        attacker_destroyed_factories = min(int(attacker_country.get("factories", 0) * 0.1), int(attacker_country.get("factories", 0)))
        attacker_destroyed_banks = min(int(attacker_country.get("banks", 0) * 0.1), int(attacker_country.get("banks", 0)))
        attacker_destroyed_universities = min(int(attacker_country.get("universities", 0) * 0.1), int(attacker_country.get("universities", 0)))
        defender_destroyed_factories = min(int(defender_country.get("factories", 0) * 0.05), int(defender_country.get("factories", 0)))
        defender_destroyed_banks = min(int(defender_country.get("banks", 0) * 0.05), int(defender_country.get("banks", 0)))
        defender_destroyed_universities = min(int(defender_country.get("universities", 0) * 0.05), int(defender_country.get("universities", 0)))

        database.update_country(
            attacker_country["id"],
            factories=max(0, int(attacker_country.get("factories", 0)) - attacker_destroyed_factories),
            banks=max(0, int(attacker_country.get("banks", 0)) - attacker_destroyed_banks),
            universities=max(0, int(attacker_country.get("universities", 0)) - attacker_destroyed_universities),
        )
        database.update_country(
            defender_country["id"],
            factories=max(0, int(defender_country.get("factories", 0)) - defender_destroyed_factories),
            banks=max(0, int(defender_country.get("banks", 0)) - defender_destroyed_banks),
            universities=max(0, int(defender_country.get("universities", 0)) - defender_destroyed_universities),
        )

        attacker_weapon_loss_rate = 0.35
        defender_weapon_loss_rate = 0.15
        attacker_casualty_rate = 0.35
        defender_casualty_rate = 0.15

    destroyed_weapons += consume_weapon_losses(
        attacker_country["id"], own_attack_items, attacker_weapon_loss_rate, attacker_weapon_losses
    )
    for ally_country_id in req.get("ally_country_ids", []):
        ally_items = [item for item in ally_attack_items if item.get("country_id") == ally_country_id]
        destroyed_weapons += consume_weapon_losses(
            ally_country_id, ally_items, attacker_weapon_loss_rate, attacker_weapon_losses
        )
    destroyed_weapons += consume_weapon_losses(
        defender_country["id"], defense_items, defender_weapon_loss_rate, defender_weapon_losses
    )

    database.add_war_event(
        war_id,
        attacker_country["id"],
        defender_country["id"],
        req["goal"],
        attacker_losses=int(attack_total * attacker_casualty_rate),
        defender_losses=int(defense_total * defender_casualty_rate),
        description=desc,
    )

    attacker_weapon_text = ", ".join(attacker_weapon_losses) if attacker_weapon_losses else "هیچ سلاحی"
    defender_weapon_text = ", ".join(defender_weapon_losses) if defender_weapon_losses else "هیچ سلاحی"
    report = (
        f"⚔️ نتیجه جنگ بین {country_label(attacker_country)} و {country_label(defender_country)}\n"
        f"🎯 هدف جنگ: {WAR_GOALS.get(req['goal'], req['goal'])}\n"
        f"⚔️ قدرت حمله: {attack_total}\n"
        f"🛡️ قدرت دفاع: {defense_total}\n"
        f"🏭 {country_label(attacker_country)}: {attacker_destroyed_factories} کارخانه، {country_label(defender_country)}: {defender_destroyed_factories} کارخانه نابود شد\n"
        f"🏦 {country_label(attacker_country)}: {attacker_destroyed_banks} بانک، {country_label(defender_country)}: {defender_destroyed_banks} بانک نابود شد\n"
        f"🎓 {country_label(attacker_country)}: {attacker_destroyed_universities} دانشگاه، {country_label(defender_country)}: {defender_destroyed_universities} دانشگاه نابود شد\n"
        f"🔫 سلاح‌های نابودشده توسط {country_label(attacker_country)}: {attacker_weapon_text}\n"
        f"🔫 سلاح‌های نابودشده توسط {country_label(defender_country)}: {defender_weapon_text}\n"
        f"📣 نتیجه: {outcome}\n\n"
        f"📝 جزئیات: {desc}"
    )

    publish_game_news("⚔️ گزارش جنگ", report)
    notify_country(attacker_country["id"], report)
    notify_country(defender_country["id"], report)
    for admin_id in ADMIN_IDS:
        bot.send_message(admin_id, f"📣 گزارش جنگ آماده شد:\n\n{report}")
    war_requests.pop(request_id, None)


@bot.message_handler(commands=["hamle"])
def start_war_command(message):
    attacker_country = get_country_for_chat(message.chat.id)
    if not attacker_country:
        bot.reply_to(message, "⚠️ این گروه به کشوری متصل نیست. ابتدا گروه را به کشور مربوطه متصل کنید.")
        return

    user_data[message.from_user.id] = {"state": "war_select_target", "attacker_country_id": attacker_country["id"]}
    bot.send_message(
        message.chat.id,
        f"🛡️ {country_label(attacker_country)}\nدرخواست حمله جدید را شروع کردید.\nکشور هدف را انتخاب کنید:",
        reply_markup=country_menu(attacker_country["id"]),
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("war_target:"))
def set_war_target(call):
    user = user_data.get(call.from_user.id)
    if not user or user.get("state") != "war_select_target":
        bot.answer_callback_query(call.id, "⚠️ وضعیت درخواست نامعتبر است.")
        return

    defender_country_id = int(call.data.split(":", 1)[1])
    if defender_country_id == user["attacker_country_id"]:
        bot.answer_callback_query(call.id, "❌ حمله به خودتان نامعتبر است.")
        return

    attacker_country = database.get_country(user["attacker_country_id"])
    defender_country = database.get_country(defender_country_id)
    if not attacker_country or not defender_country:
        bot.answer_callback_query(call.id, "⚠️ کشور هدف یا مهاجم نامعتبر است.")
        return

    user["defender_country_id"] = defender_country_id
    user["state"] = "war_select_goal"
    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        "حالا هدف جنگ را انتخاب کنید. در صورت نیاز می‌توانید از متحدان خود دعوت کنید:",
        reply_markup=goal_menu(include_ally_invite=True),
    )


@bot.callback_query_handler(func=lambda call: call.data == "war_invite_ally")
def show_war_ally_menu(call):
    user = user_data.get(call.from_user.id)
    if not user or user.get("state") != "war_select_goal":
        bot.answer_callback_query(call.id, "⚠️ وضعیت درخواست نامعتبر است.")
        return

    ally_ids = allied_country_ids(user["attacker_country_id"])
    ally_ids.discard(user.get("defender_country_id"))
    if not ally_ids:
        bot.answer_callback_query(call.id, "⚠️ متحدی برای دعوت وجود ندارد.")
        return

    request_id = f"war_draft_{call.from_user.id}"
    status = war_alliance_status.setdefault(request_id, {"accepted": set(), "declined": set(), "requested": set()})
    markup = InlineKeyboardMarkup(row_width=1)
    for ally_id in sorted(ally_ids):
        ally = database.get_country(ally_id)
        if not ally:
            continue
        if ally_id in status["accepted"]:
            label = f"✅ {ally['name']} (پذیرفته شد)"
        elif ally_id in status["requested"]:
            label = f"⏳ {ally['name']} (دعوت ارسال شد)"
        else:
            label = f"📨 دعوت {ally['name']}"
        markup.add(InlineKeyboardButton(label, callback_data=f"war_invite_send:{ally_id}"))
    markup.add(InlineKeyboardButton("🔙 بازگشت به اهداف جنگ", callback_data="war_invite_back"))
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "متحد مورد نظر را انتخاب کنید:", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data == "war_invite_back")
def back_to_war_goal_menu(call):
    user = user_data.get(call.from_user.id)
    if not user or user.get("state") != "war_select_goal":
        bot.answer_callback_query(call.id, "⚠️ وضعیت درخواست نامعتبر است.")
        return
    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        "هدف جنگ را انتخاب کنید:",
        reply_markup=goal_menu(include_ally_invite=True),
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("war_invite_send:"))
def send_war_ally_invite(call):
    user = user_data.get(call.from_user.id)
    if not user or user.get("state") != "war_select_goal":
        bot.answer_callback_query(call.id, "⚠️ وضعیت درخواست نامعتبر است.")
        return
    ally_country_id = int(call.data.split(":", 1)[1])
    request_id = f"war_draft_{call.from_user.id}"
    sent = send_war_alliance_invite(
        request_id,
        user["attacker_country_id"],
        user["defender_country_id"],
        ally_country_id,
    )
    bot.answer_callback_query(call.id, "✅ دعوت ارسال شد." if sent else "⚠️ ارسال دعوت ممکن نیست.")


@bot.callback_query_handler(func=lambda call: call.data.startswith("war_goal:"))
def set_war_goal(call):
    user = user_data.get(call.from_user.id)
    if not user or user.get("state") != "war_select_goal":
        bot.answer_callback_query(call.id, "⚠️ وضعیت درخواست نامعتبر است.")
        return

    goal = call.data.split(":", 1)[1]
    if goal not in WAR_GOALS:
        bot.answer_callback_query(call.id, "⚠️ هدف جنگ نامعتبر است.")
        return

    user["goal"] = goal
    user["attack_items"] = []
    user["attack_total"] = 0
    user["defense_total"] = 0
    user["state"] = "war_select_weapon"
    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        "⚔️ سلاح مورد نظر برای حمله را انتخاب کنید:\nمی‌توانید چند سلاح را در یک درخواست جمع کنید.",
        reply_markup=build_weapon_list(user["attacker_country_id"]),
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("war_weapon:") and call.data.count(":") == 1)
def select_war_weapon(call):
    user = user_data.get(call.from_user.id)
    if not user or user.get("state") != "war_select_weapon":
        bot.answer_callback_query(call.id, "⚠️ وضعیت درخواست نامعتبر است.")
        return

    weapon_id = int(call.data.split(":", 1)[1])
    weapon = database.get_weapon(weapon_id)
    if not weapon:
        bot.answer_callback_query(call.id, "⚠️ سلاح نامعتبر است.")
        return

    inventory = database.get_country_inventory(user["attacker_country_id"])
    owned = next((item for item in inventory if item["id"] == weapon_id), None)
    if not owned or owned["quantity"] <= 0:
        bot.answer_callback_query(call.id, "⚠️ شما این سلاح را در انبار ندارید.")
        return

    user["weapon_id"] = weapon_id
    user["weapon_name"] = weapon["name"]
    user["state"] = "war_wait_quantity"
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, f"🔢 تعداد {weapon['name']} را وارد کنید. موجودی: {owned['quantity']}")


@bot.callback_query_handler(func=lambda call: call.data.startswith("war_defense_select_weapon:"))
def legacy_defense_selector(call):
    bot.answer_callback_query(call.id, "⚠️ لطفاً از منوی دفاعی جدید استفاده کنید.")


@bot.message_handler(content_types=["text"])
def handle_war_text_input(message):
    user = user_data.get(message.from_user.id)
    if user and user.get("state") == "war_wait_quantity":
        try:
            quantity = int(message.text.strip())
        except ValueError:
            bot.send_message(message.chat.id, "⚠️ لطفاً فقط عدد وارد کنید.")
            return

        if quantity <= 0:
            bot.send_message(message.chat.id, "⚠️ تعداد باید بزرگ‌تر از صفر باشد.")
            return

        weapon = database.get_weapon(user["weapon_id"])
        if not weapon:
            bot.send_message(message.chat.id, build_invalid_request_message("سلاح انتخاب شده وجود ندارد."))
            return

        inventory = database.get_country_inventory(user["attacker_country_id"])
        owned = next((item for item in inventory if item["id"] == user["weapon_id"]), None)
        if not owned or owned["quantity"] < quantity:
            bot.send_message(message.chat.id, build_invalid_request_message("تعداد درخواستی بیشتر از موجودی شماست."))
            return

        total_attack = quantity * float(weapon["attack_power"])
        total_defense = quantity * float(weapon["defense_power"])
        user.setdefault("attack_items", [])
        user["attack_items"].append({
            "weapon_id": weapon["id"],
            "name": weapon["name"],
            "quantity": quantity,
            "attack_power": total_attack,
            "defense_power": total_defense,
        })
        user["attack_total"] = sum(item["attack_power"] for item in user["attack_items"])
        user["defense_total"] = sum(item["defense_power"] for item in user["attack_items"])
        user["quantity"] = quantity
        user["state"] = "war_confirm_request"

        goal_label = WAR_GOALS.get(user["goal"], user["goal"])
        weapons_summary = ", ".join(f"{item['name']} × {item['quantity']}" for item in user["attack_items"])
        summary = (
            f"📋 خلاصه درخواست حمله\n"
            f"🇨🇦 مهاجم: {database.get_country(user['attacker_country_id'])['name']}\n"
            f"🎯 هدف: {database.get_country(user['defender_country_id'])['name']}\n"
            f"🧭 هدف جنگ: {goal_label}\n"
            f"🔫 سلاح‌ها: {weapons_summary}\n"
            f"⚔️ قدرت حمله کل: {user['attack_total']}\n"
            f"🛡️ قدرت دفاع کل: {user['defense_total']}"
        )

        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(
            InlineKeyboardButton("✅ افزودن سلاح دیگر", callback_data="war_add_more_weapon"),
            InlineKeyboardButton("✅ ارسال به ادمین", callback_data="war_submit_admin"),
            InlineKeyboardButton("↩️ ویرایش مجدد", callback_data="war_edit_request"),
        )
        bot.send_message(message.chat.id, summary, reply_markup=markup)
        return

    for request_id, state in list(defense_states.items()):
        if state.get("chat_id") != message.chat.id:
            continue
        if state.get("state") != "war_defense_wait_quantity":
            continue

        try:
            quantity = int(message.text.strip())
        except ValueError:
            bot.send_message(message.chat.id, "⚠️ لطفاً فقط عدد معتبر وارد کنید.")
            return
        if quantity <= 0:
            bot.send_message(message.chat.id, "⚠️ تعداد باید بیشتر از صفر باشد.")
            return

        weapon = database.get_weapon(state["selected_weapon_id"])
        if not weapon:
            bot.send_message(message.chat.id, build_invalid_request_message("سلاح انتخاب شده نامعتبر است."))
            return

        inventory = database.get_country_inventory(state["country_id"])
        owned = next((item for item in inventory if item["id"] == state["selected_weapon_id"]), None)
        if not owned or owned["quantity"] < quantity:
            bot.send_message(message.chat.id, build_invalid_request_message("تعداد دفاعی بیشتر از موجودی شماست."))
            return

        power = quantity * float(weapon["defense_power"])
        state["defense_total"] += power
        state["defense_items"].append({
            "weapon_id": weapon["id"],
            "name": weapon["name"],
            "quantity": quantity,
            "power": power,
        })
        state["state"] = "war_defense_wait_more"
        summary = (
            f"🛡️ خلاصه دفاع\n"
            f"🔫 سلاح: {weapon['name']}\n"
            f"🔢 تعداد: {quantity}\n"
            f"⚔️ قدرت دفاع این سلاح: {power}\n"
            f"📊 مجموع دفاع فعلی: {state['defense_total']}"
        )
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(
            InlineKeyboardButton("✅ افزودن سلاح دفاعی دیگر", callback_data=f"war_defense_more:yes:{request_id}"),
            InlineKeyboardButton("🎯 پایان دفاع", callback_data=f"war_defense_more:no:{request_id}"),
        )
        bot.send_message(message.chat.id, summary, reply_markup=markup)
        return


@bot.callback_query_handler(func=lambda call: call.data == "war_add_more_weapon")
def add_more_war_weapon(call):
    user = user_data.get(call.from_user.id)
    if not user or user.get("state") != "war_confirm_request":
        bot.answer_callback_query(call.id, "⚠️ وضعیت درخواست نامعتبر است.")
        return

    user["state"] = "war_select_weapon"
    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        "⚔️ سلاح دیگری برای حمله انتخاب کنید:\nمی‌توانید چند سلاح را در یک حمله ترکیب کنید.",
        reply_markup=build_weapon_list(user["attacker_country_id"]),
    )


@bot.callback_query_handler(func=lambda call: call.data == "war_edit_request")
def edit_war_request(call):
    user = user_data.get(call.from_user.id)
    if not user:
        bot.answer_callback_query(call.id, "⚠️ درخواست پیدا نشد.")
        return
    user["state"] = "war_select_target"
    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        "🔁 کشور هدف را دوباره انتخاب کنید:",
        reply_markup=country_menu(user["attacker_country_id"]),
    )


@bot.callback_query_handler(func=lambda call: call.data == "war_submit_admin")
def submit_war_to_admin(call):
    user = user_data.get(call.from_user.id)
    if not user or user.get("state") != "war_confirm_request":
        bot.answer_callback_query(call.id, "⚠️ درخواست معتبر نیست.")
        return

    attacker_country = database.get_country(user["attacker_country_id"])
    defender_country = database.get_country(user["defender_country_id"])
    if not attacker_country or not defender_country:
        bot.answer_callback_query(call.id, "⚠️ اطلاعات درخواست ناقص است.")
        return

    attack_items = user.get("attack_items", [])
    if not attack_items:
        bot.answer_callback_query(call.id, "⚠️ حداقل یک سلاح باید انتخاب شود.")
        return

    request_id = f"war_{call.from_user.id}_{len(war_requests) + 1}"
    draft_status = war_alliance_status.pop(
        f"war_draft_{call.from_user.id}",
        {"accepted": set(), "declined": set(), "requested": set()},
    )
    war_requests[request_id] = {
        "attacker_country_id": user["attacker_country_id"],
        "defender_country_id": user["defender_country_id"],
        "goal": user["goal"],
        "weapons": attack_items,
        "attack_total": user["attack_total"],
        "defense_total": user["defense_total"],
        "defense_items": [],
        "ally_country_ids": sorted(draft_status["accepted"]),
        "status": "pending_admin",
    }
    war_alliance_status[request_id] = draft_status

    weapons_summary = ", ".join(f"{item['name']} × {item['quantity']}" for item in attack_items)
    admin_text = (
        f"⚔️ درخواست حمله جدید\n"
        f"🇨🇦 مهاجم: {attacker_country['name']}\n"
        f"🎯 هدف: {defender_country['name']}\n"
        f"🧭 هدف جنگ: {WAR_GOALS.get(user['goal'], user['goal'])}\n"
        f"🔫 سلاح‌ها: {weapons_summary}\n"
        f"⚔️ قدرت حمله کل: {user['attack_total']}\n"
        f"🛡️ قدرت دفاع کل: {user['defense_total']}"
    )

    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("✅ تایید حمله", callback_data=f"war_admin_confirm:{request_id}"))
    for admin_id in ADMIN_IDS:
        bot.send_message(admin_id, admin_text, reply_markup=markup)

    notify_country(
        user["defender_country_id"],
        f"⚔️ کشور {attacker_country['name']} درخواست حمله به شما ارسال کرد.\n🎯 هدف جنگ: {WAR_GOALS.get(user['goal'], user['goal'])}\n⏳ منتظر تایید مدیر هستید.",
    )

    bot.answer_callback_query(call.id, "✅ درخواست به ادمین ارسال شد.")
    bot.send_message(call.message.chat.id, "✅ درخواست حمله به ادمین ارسال شد و منتظر تایید او هستید.")
    user_data.pop(call.from_user.id, None)


@bot.callback_query_handler(func=lambda call: call.data.startswith("war_admin_confirm:"))
def confirm_war_by_admin(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "⛔ فقط ادمین می‌تواند تایید کند.")
        return

    request_id = call.data.split(":", 1)[1]
    req = war_requests.get(request_id)
    if not req:
        bot.answer_callback_query(call.id, "⚠️ درخواست یافت نشد.")
        return

    req["status"] = "pending_defense"
    bot.answer_callback_query(call.id, "✅ حمله تایید شد.")

    attacker_country = database.get_country(req["attacker_country_id"])
    defender_country = database.get_country(req["defender_country_id"])

    notify_country(
        req["defender_country_id"],
        f"⚔️ درخواست حمله از {attacker_country['name']} به شما تایید شد.\n🎯 هدف جنگ: {WAR_GOALS.get(req['goal'], req['goal'])}\n\n🛡️ لطفاً سلاح‌های دفاعی خود را انتخاب کنید و تعداد هر کدام را وارد کنید.\n⏳ تنها 3 ساعت فرصت پاسخ دارید.",
    )
    notify_country(
        req["attacker_country_id"],
        f"⚔️ درخواست حمله به {defender_country['name']} توسط ادمین تایید شد.\nاکنون کشور هدف باید پاسخ دفاعی بدهد.",
    )

    defender_group_id = database.get_group_by_country(req["defender_country_id"])
    defense_states[request_id] = {
        "chat_id": defender_group_id,
        "country_id": req["defender_country_id"],
        "request_id": request_id,
        "state": "war_defense_select_weapon",
        "defense_total": 0,
        "defense_items": [],
    }
    req["defense_total"] = 0
    req["defense_items"] = []
    if defender_group_id is not None:
        bot.send_message(
            defender_group_id,
            "🛡️ سلاح دفاعی خود را انتخاب کنید:\nهمه سلاح‌ها، از جمله جاسوس اطلاعاتی و جاسوس عملیاتی، در دفاع قابل استفاده‌اند.",
            reply_markup=build_weapon_list(req["defender_country_id"], request_id=request_id),
        )

    timer = threading.Timer(10800, resolve_war_request, args=(request_id,))
    timer.daemon = True
    timer.start()


@bot.callback_query_handler(func=lambda call: call.data.startswith("war_alliance_accept:"))
def accept_alliance(call):
    _, request_id, country_id = call.data.split(":")
    country_id = int(country_id)
    war_alliance_status.setdefault(request_id, {"accepted": set(), "declined": set(), "requested": set()})
    status = war_alliance_status[request_id]
    if country_id not in status["requested"]:
        bot.answer_callback_query(call.id, "⚠️ این دعوت معتبر نیست.")
        return
    status["accepted"].add(country_id)
    status["declined"].discard(country_id)
    bot.answer_callback_query(call.id, "✅ درخواست ائتلاف پذیرفته شد.")


@bot.callback_query_handler(func=lambda call: call.data.startswith("war_alliance_reject:"))
def reject_alliance(call):
    _, request_id, country_id = call.data.split(":")
    country_id = int(country_id)
    war_alliance_status.setdefault(request_id, {"accepted": set(), "declined": set(), "requested": set()})
    status = war_alliance_status[request_id]
    if country_id not in status["requested"]:
        bot.answer_callback_query(call.id, "⚠️ این دعوت معتبر نیست.")
        return
    status["declined"].add(country_id)
    status["accepted"].discard(country_id)
    bot.answer_callback_query(call.id, "❌ درخواست ائتلاف رد شد.")


@bot.callback_query_handler(func=lambda call: call.data.startswith("war_weapon:") and call.data.count(":") >= 2)
def handle_defense_selection(call):
    parts = call.data.split(":")
    request_id = parts[2]
    state = defense_states.get(request_id)
    if not state:
        bot.answer_callback_query(call.id, "⚠️ وضعیت دفاع نامعتبر است.")
        return

    weapon_id = int(parts[1])
    weapon = database.get_weapon(weapon_id)
    if not weapon:
        bot.answer_callback_query(call.id, "⚠️ سلاح نامعتبر است.")
        return

    inventory = database.get_country_inventory(state["country_id"])
    owned = next((item for item in inventory if item["id"] == weapon_id), None)
    if not owned or owned["quantity"] <= 0:
        bot.answer_callback_query(call.id, "⚠️ شما این سلاح را ندارید.")
        return

    state["selected_weapon_id"] = weapon_id
    state["state"] = "war_defense_wait_quantity"
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, f"🔢 تعداد {weapon['name']} را برای دفاع وارد کنید. موجودی: {owned['quantity']}")




@bot.callback_query_handler(func=lambda call: call.data.startswith("war_defense_more:"))
def handle_defense_more(call):
    parts = call.data.split(":")
    request_id = parts[2] if len(parts) >= 3 else None
    if request_id:
        state = defense_states.get(request_id)
        if not state:
            bot.answer_callback_query(call.id, "⚠️ وضعیت دفاع نامعتبر است.")
            return
        choice = parts[1]
        if choice == "yes":
            state["state"] = "war_defense_select_weapon"
            bot.answer_callback_query(call.id)
            bot.send_message(call.message.chat.id, "🛡️ سلاح دفاعی بعدی را انتخاب کنید:", reply_markup=build_weapon_list(state["country_id"], request_id=request_id))
            return
        req = war_requests.get(request_id)
        if not req:
            bot.answer_callback_query(call.id, "⚠️ درخواست دفاع نامعتبر است.")
            return
        req["defense_total"] = state["defense_total"]
        resolve_war_request(request_id)
        bot.answer_callback_query(call.id, "✅ دفاع تکمیل شد.")
        defense_states.pop(request_id, None)
        return

    user = user_data.get(call.from_user.id)
    if not user or user.get("state") != "war_defense_wait_more":
        bot.answer_callback_query(call.id, "⚠️ وضعیت دفاع نامعتبر است.")
        return

    choice = parts[1]
    if choice == "yes":
        user["state"] = "war_defense_select_weapon"
        bot.answer_callback_query(call.id)
        country_id = user.get("defender_country_id") or user.get("country_id")
        if country_id is not None:
            bot.send_message(call.message.chat.id, "🛡️ سلاح دفاعی بعدی را انتخاب کنید:", reply_markup=build_weapon_list(country_id))
        return

    req = war_requests.get(user.get("request_id"))
    if not req:
        bot.answer_callback_query(call.id, "⚠️ درخواست دفاع نامعتبر است.")
        return

    req["defense_total"] = user["defense_total"]
    req["defense_items"] = user["defense_items"]
    resolve_war_request(user["request_id"])
    bot.answer_callback_query(call.id, "✅ دفاع تکمیل شد.")
    user_data.pop(call.from_user.id, None)


print("War bot is running...")
bot.infinity_polling()
