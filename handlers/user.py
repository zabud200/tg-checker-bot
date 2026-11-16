from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, PreCheckoutQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from locales import t
from config import SUBSCRIPTION_PRICES, REFERRAL_BONUS_DAYS, REFERRAL_COMMISSION, MIN_PAYOUT_STARS
from keyboards import lang_kb, main_menu, sub_kb
from services import db
from services.apify_client import analyze_channel, search_channels
from services.payments import send_stars_invoice, PLAN_DAYS

router = Router()

class CheckFlow(StatesGroup):
    waiting_link = State()
    waiting_topic = State()

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
    from config import OWNER_ID  # Импортируем твой ID
    
    if not u:
        db.create_user(m.from_user.id, m.from_user.username, ref)
        # Если это твой ID - даем роль owner
        if m.from_user.id == OWNER_ID:
            db.set_role(m.from_user.id, "owner")
        u = db.get_user(m.from_user.id)
        if ref and ref != m.from_user.id:
            db.add_referral(ref, m.from_user.id, 0, 0)
    
    await m.answer(t("ru", "choose_lang"), reply_markup=lang_kb())

@router.callback_query(F.data.startswith("lang:"))
async def set_language(cb: CallbackQuery):
    lang = cb.data.split(":")[1]
    db.set_lang(cb.from_user.id, lang)
    u = db.get_user(cb.from_user.id)
    await cb.message.edit_text(t(lang, "welcome", name=cb.from_user.first_name, trial=u["free_checks_left"]))
    await cb.message.answer(t(lang, "main_menu"), reply_markup=main_menu(lang, is_admin(u)))
    await cb.answer()

@router.message(F.text.in_({"🔍 Проверить канал", "🔍 Check channel"}))
async def ask_link(m: Message, state: FSMContext):
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
    link = data["link"]; topic = m.text.strip().lower()
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

    # Защита от неадекватных данных (накрутка или ошибка парсера)
    if err > 100 or err < 0:
        err = 0.0 
        qs = 0
    db.save_check(m.from_user.id, clean, topic, subs, reach, err, qs, "")
    db.consume_check(m.from_user.id)
    avg = db.avg_err_by_category(topic)

    if qs and qs < 40:
        verdict = t(u["lang"], "verdict_no")
    elif avg > 0 and err < avg * 0.6:
        verdict = t(u["lang"], "verdict_no")
    elif avg > 0 and err < avg:
        verdict = t(u["lang"], "verdict_risk")
    else:
        verdict = t(u["lang"], "verdict_take")

    top = await search_channels(topic, 5)
    top_lines = ""
    for ch in top[:3]:
        top_lines += f"\n• @{ch.get('username','?')} — ERR {ch.get('errPercent',0)}%"

    text = (f"📊 <b>{clean}</b>\n👥 {subs:,} | 👁 ERR: <b>{err}%</b>\n"
            f"🏷 {topic}\n📉 Средний ERR по нише: <b>{avg:.1f}%</b>\n\n<b>{verdict}</b>")
    if top_lines:
        text += f"\n\n🏆 Топ в нише:{top_lines}"
    await m.answer(text, parse_mode="HTML")

@router.message(F.text.in_({"📜 Моя история", "📜 History"}))
async def history(m: Message):
    u = db.get_user(m.from_user.id)
    rows = db.user_history(m.from_user.id)
    if not rows:
        await m.answer("Пусто." if u["lang"]=="ru" else "Empty.")
        return
    txt = "📜 История:\n\n" if u["lang"]=="ru" else "📜 History:\n\n"
    for r in rows:
        txt += f"• @{r['channel_username']} — ERR {r['err']}% ({r['category']})\n"
    await m.answer(txt)

@router.message(F.text.in_({"🏆 Топ по нише", "🏆 Top by niche"}))
async def top_niche(m: Message, state: FSMContext):
    u = db.get_user(m.from_user.id)
    await state.set_state(CheckFlow.waiting_topic)
    await state.update_data(link="__top__")
    await m.answer(t(u["lang"], "send_topic"))

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
