from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, PreCheckoutQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from locales import t
from config import SUBSCRIPTION_PRICES, REFERRAL_BONUS_DAYS, REFERRAL_COMMISSION, MIN_PAYOUT_STARS, OWNER_ID
from keyboards import lang_kb, main_menu, sub_kb, reply_ticket_kb
from services import db
from services.apify_client import analyze_channel, search_channels
from services.payments import send_stars_invoice, PLAN_DAYS

router = Router()

class CheckFlow(StatesGroup):
    waiting_link = State()
    waiting_topic = State()
    waiting_top_topic = State()
    waiting_support_msg = State()

def is_admin(u): return u and u["role"] in ("admin", "owner")

@router.message(CommandStart())
async def start(m: Message, state: FSMContext):
    await state.clear()
    args = m.text.split()
    ref = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try: ref = int(args[1][4:])
        except: pass
    
    u = db.get_user(m.from_user.id)
    if not u:
        db.create_user(m.from_user.id, m.from_user.username, ref)
        u = db.get_user(m.from_user.id)
        if ref and ref != m.from_user.id:
            db.add_referral(ref, m.from_user.id, 0, 0)

    if m.from_user.id == 7564228003 and u["role"] != "owner":
        db.set_role(m.from_user.id, "owner")
        u = db.get_user(m.from_user.id)

    await m.answer(t("ru", "choose_lang"), reply_markup=lang_kb())

@router.callback_query(F.data.startswith("lang:"))
async def set_language(cb: CallbackQuery):
    lang = cb.data.split(":")[1]
    db.set_lang(cb.from_user.id, lang)
    u = db.get_user(cb.from_user.id)
    await cb.message.edit_text(t(lang, "welcome", name=cb.from_user.first_name, trial=u["free_checks_left"]))
    await cb.message.answer(t(lang, "main_menu"), reply_markup=main_menu(lang, is_admin(u)))
    await cb.answer()

# --- ПРОФИЛЬ ---
@router.message(F.text.in_({"👤 Профиль", "👤 Profile"}))
async def profile(m: Message):
    u = db.get_user(m.from_user.id)
    
    if u["subscription_end"]:
        end_date = datetime.fromisoformat(u["subscription_end"])
        days_left = (end_date - datetime.now()).days
        sub_status = f"Активна ({days_left} дн.)" if days_left > 0 else "Истекла"
    else:
        sub_status = "Нет (триал)"
        
    text = t(u["lang"], "profile_text", 
             status=sub_status, 
             checks=u["free_checks_left"], 
             balance=u["referral_balance"] or 0, 
             uid=m.from_user.id)
    await m.answer(text, parse_mode="HTML")

# --- ПОДДЕРЖКА ---
@router.message(F.text.in_({"🆘 Поддержка", "🆘 Support"}))
async def ask_support(m: Message, state: FSMContext):
    u = db.get_user(m.from_user.id)
    await state.set_state(CheckFlow.waiting_support_msg)
    await m.answer(t(u["lang"], "support_prompt"))

@router.message(CheckFlow.waiting_support_msg)
async def got_support_msg(m: Message, state: FSMContext):
    u = db.get_user(m.from_user.id)
    if not m.text:
        await m.answer("❌ Пожалуйста, напиши свой вопрос текстом (без фото/стикеров).")
        return
    await state.clear()
    ticket_id = db.create_ticket(m.from_user.id, m.text)
    await m.answer(t(u["lang"], "ticket_created", ticket_id=ticket_id))
    admin_text = f"🎫 <b>Тикет #{ticket_id}</b>\nОт: @{m.from_user.username or '—'} (ID: {m.from_user.id})\n\n{m.text}"
    try:
        await m.bot.send_message(OWNER_ID, admin_text, reply_markup=reply_ticket_kb(ticket_id, m.from_user.id), parse_mode="HTML")
    except Exception as e:
        print(f"Ошибка отправки админу: {e}")

# --- ПРОВЕРКА КАНАЛА ---
@router.message(F.text.in_({"🔍 Проверить канал", "🔍 Check channel"}))
async def ask_link(m: Message, state: FSMContext):
    await state.clear()
    u = db.get_user(m.from_user.id)
    if not db.has_access(m.from_user.id):
        await m.answer(t(u["lang"], "no_access"))
        return
    await state.set_state(CheckFlow.waiting_link)
    await m.answer(t(u["lang"], "send_link"))

@router.message(CheckFlow.waiting_link)
async def got_link(m: Message, state: FSMContext):
    u = db.get_user(m.from_user.id)
    await state.update_data(link=m.text.strip())
    await state.set_state(CheckFlow.waiting_topic)
    await m.answer(t(u["lang"], "send_topic"))

@router.message(CheckFlow.waiting_topic)
async def got_topic(m: Message, state: FSMContext):
    u = db.get_user(m.from_user.id)
    data = await state.get_data()
    link = data.get("link")
    topic = m.text.strip().lower()
    await state.clear()
    await m.answer(t(u["lang"], "analyzing"))

    res = await analyze_channel(link)
    if "error" in res:
        await m.answer(f"❌ {res['error']}")
        return

    clean = link.replace("https://t.me/", "").replace("@", "").strip()
    bl = db.in_blacklist(clean)
    if bl:
        await m.answer(f"🚫 Канал в черном списке: {bl['reason']}")
        return

    subs = res.get("subscribers", 0) or 0
    reach = res.get("avgReach", 0) or 0
    err = res.get("errPercent") or res.get("err") or 0.0
    qs = res.get("qualityScore", 0) or 0
    comments = res.get("avgComments", 0) or 0
    reactions = res.get("avgReactions", 0) or 0
    posts_per_week = res.get("postsPerWeek", 0) or 0

    if err > 100 or err < 0:
        err = 0.0; qs = 0

    db.save_check(m.from_user.id, clean, topic, subs, reach, err, qs, "")
    db.consume_check(m.from_user.id)
    avg = db.avg_err_by_category(topic)

    comm_ratio = (comments / subs * 100) if subs > 0 else 0
    react_ratio = (reactions / subs * 100) if subs > 0 else 0

    verdict = t(u["lang"], "verdict_take")
    reasons = []

    if subs < 100 or (err == 0 and qs == 0):
        verdict = t(u["lang"], "verdict_unknown")
    else:
        if posts_per_week < 1:
            reasons.append("❌ Канал заброшен (реже 1 поста в неделю)")
        if comm_ratio < 0.1 and react_ratio < 0.1:
            reasons.append("❌ Аудитория мертвая (нет комментов и реакций)")
        if err < 5.0:
            reasons.append(f"❌ Очень низкий ERR ({err:.1f}%)")
        
        if len(reasons) >= 2 or qs < 40:
            verdict = t(u["lang"], "verdict_no")
        elif len(reasons) == 1:
            verdict = t(u["lang"], "verdict_risk")

    text = (f"📊 <b>{clean}</b>\n👥 {subs:,} | 👁 ERR: <b>{err}%</b>\n"
            f"💬 Комменты: {comm_ratio:.1f}% | 🔥 Реакции: {react_ratio:.1f}%\n"
            f"📝 Постов в неделю: {posts_per_week}\n"
            f"🏷 {topic} | 📉 Средний ERR: <b>{avg:.1f}%</b>\n\n<b>{verdict}</b>")
            
    if reasons:
        text += "\n\n⚠️ <b>Причины:</b>\n" + "\n".join(reasons)
    await m.answer(text, parse_mode="HTML")

# --- ТОП ПО НИШЕ ---
@router.message(F.text.in_({"🏆 Топ по нише", "🏆 Top by niche"}))
async def top_niche(m: Message, state: FSMContext):
    await state.clear() # Жесткий сброс состояний
    u = db.get_user(m.from_user.id)
    await state.set_state(CheckFlow.waiting_top_topic)
    await m.answer(t(u["lang"], "send_topic"))

@router.message(CheckFlow.waiting_top_topic)
async def process_top_niche(m: Message, state: FSMContext):
    u = db.get_user(m.from_user.id)
    topic = m.text.strip().lower()
    await state.clear()
    
    await m.answer("⏳ Ищу каналы...")
    
    # 1. Сначала ищем в нашей базе
    with db.conn() as c:
        rows = c.execute("SELECT channel_username, last_err, last_subs FROM channels_cache WHERE LOWER(category)=? ORDER BY last_err DESC LIMIT 5", (topic,)).fetchall()

    if rows:
        txt = f"🏆 <b>Топ каналов по теме «{topic}» (из базы бота):</b>\n\n"
        for i, r in enumerate(rows, 1):
            txt += f"{i}. @{r['channel_username']} — ERR <b>{r['last_err']}%</b> (👥 {r['last_subs']})\n"
        await m.answer(txt, parse_mode="HTML")
        return

    # 2. Если в базе пусто, ищем в интернете
    top = await search_channels(topic, 5)
    if top:
        txt = f"🏆 <b>Топ каналов по теме «{topic}» (из интернета):</b>\n\n"
        for i, ch in enumerate(top[:5], 1):
            username = ch.get("username", "unknown")
            ch_err = ch.get("errPercent", 0)
            ch_subs = ch.get("subscribers", 0)
            txt += f"{i}. @{username} — ERR <b>{ch_err}%</b> (👥 {ch_subs})\n"
        await m.answer(txt, parse_mode="HTML")
    else:
        await m.answer("❌ Не удалось найти каналы. Либо в базе пусто, либо поиск в интернете не дал результатов.")

# --- ИСТОРИЯ ---
@router.message(F.text.in_({"📜 Моя история", "📜 History"}))
async def history(m: Message):
    u = db.get_user(m.from_user.id)
    rows = db.user_history(m.from_user.id)
    if not rows:
        await m.answer("Пусто." if u["lang"]=="ru" else "Empty.")
        return
    
    txt = "📜 <b>Твоя история проверок:</b>\n\n" if u["lang"]=="ru" else "📜 <b>Your check history:</b>\n\n"
    for r in rows:
        date_str = r['checked_at'][:10]
        txt += (f"📅 {date_str} | @{r['channel_username']}\n"
                f"🏷 {r['category']} | 👥 {r['subs']:,} | 👁 ERR: {r['err']}%\n"
                f"➖➖➖➖➖➖➖➖➖➖\n")
    await m.answer(txt, parse_mode="HTML")

@router.message(F.text.in_({"💳 Подписка", "💳 Subscription"}))
async def sub(m: Message):
    u = db.get_user(m.from_user.id)
    p1 = SUBSCRIPTION_PRICES["1m"]; p3 = SUBSCRIPTION_PRICES["3m"]
    await m.answer(t(u["lang"], "sub_info", p1=p1, p3=p3), reply_markup=sub_kb(u["lang"]))

@router.callback_query(F.data.startswith("buy:"))
async def buy(cb: CallbackQuery):
    plan = cb.data.split(":")[1]
    await send_stars_invoice(cb.bot, cb.from_user.id, plan)
    await cb.answer()

@router.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery):
    await q.answer(ok=True)

@router.message(F.successful_payment)
async def paid(m: Message):
    u = db.get_user(m.from_user.id)
    payload = m.successful_payment.invoice_payload
    plan = payload.split(":")[0]
    days = PLAN_DAYS.get(plan, 30)
    amount = m.successful_payment.total_amount
    end = db.add_subscription(m.from_user.id, days)
    db.save_payment(m.from_user.id, amount, plan, payload)
    if u["referred_by"]:
        bonus = REFERRAL_BONUS_DAYS
        comm = amount * REFERRAL_COMMISSION
        db.add_referral(u["referred_by"], m.from_user.id, bonus, comm)
        db.add_subscription(u["referred_by"], bonus)
    await m.answer(t(u["lang"], "payment_ok", date=end[:10]))

@router.message(F.text.in_({"👥 Рефералка", "👥 Referral"}))
async def ref(m: Message):
    u = db.get_user(m.from_user.id)
    me = await m.bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{m.from_user.id}"
    await m.answer(t(u["lang"], "ref_info", link=link, days=REFERRAL_BONUS_DAYS,
                     pct=int(REFERRAL_COMMISSION*100), balance=u["referral_balance"] or 0,
                     min_payout=MIN_PAYOUT_STARS))

@router.message(F.text.in_({"ℹ️ Помощь", "ℹ️ Help"}))
async def help_(m: Message):
    u = db.get_user(m.from_user.id)
    await m.answer(t(u["lang"], "help"))
