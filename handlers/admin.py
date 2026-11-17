from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from keyboards import admin_kb, admin_payouts_kb
from services import db
from locales import t
from config import OWNER_ID

router = Router()

class AdminFlow(StatesGroup):
    give_uid = State()
    give_days = State()
    give_balance_uid = State()
    give_balance_amount = State()
    bl_name = State()
    bl_reason = State()
    reply_ticket = State()

def is_admin(u): return u and u["role"] in ("admin", "owner")

@router.message(F.text.in_({"👑 Админ-панель"}))
async def admin_panel(m: Message):
    if m.from_user.id == 7564228003:
        db.set_role(m.from_user.id, "owner")
    
    u = db.get_user(m.from_user.id)
    if not is_admin(u):
        await m.answer("Нет доступа.")
        return
    await m.answer("👑 Админ-панель", reply_markup=admin_kb())

@router.callback_query(F.data == "adm:give")
async def give_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AdminFlow.give_uid)
    await cb.message.answer("Введи Telegram ID пользователя:")
    await cb.answer()

@router.message(AdminFlow.give_uid)
async def give_uid(m: Message, state: FSMContext):
    try: uid = int(m.text.strip())
    except: await m.answer("Нужен числовой ID."); return
    if not db.get_user(uid):
        await m.answer("Пользователь не найден."); return
    await state.update_data(uid=uid)
    await state.set_state(AdminFlow.give_days)
    await m.answer("Сколько дней выдать?")

@router.message(AdminFlow.give_days)
async def give_days(m: Message, state: FSMContext):
    try: days = int(m.text.strip())
    except: await m.answer("Нужно число."); return
    uid = (await state.get_data())["uid"]
    
    with db.conn() as c:
        c.execute("UPDATE users SET subscription_end=NULL WHERE telegram_id=?", (uid,))
    
    end = db.add_subscription(uid, days)
    await state.clear()
    await m.answer(f"✅ Выдано {days} дней. До {end[:10]}")
    try: await m.bot.send_message(uid, f"🎁 Тебе выдана подписка на {days} дней!")
    except: pass

@router.callback_query(F.data == "adm:balance")
async def give_bal_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AdminFlow.give_balance_uid)
    await cb.message.answer("Введи Telegram ID пользователя:")
    await cb.answer()

@router.message(AdminFlow.give_balance_uid)
async def give_bal_uid(m: Message, state: FSMContext):
    try: uid = int(m.text.strip())
    except: await m.answer("Нужен числовой ID."); return
    if not db.get_user(uid):
        await m.answer("Пользователь не найден."); return
    await state.update_data(uid=uid)
    await state.set_state(AdminFlow.give_balance_amount)
    await m.answer("Сколько Stars начислить?")

@router.message(AdminFlow.give_balance_amount)
async def give_bal_amount(m: Message, state: FSMContext):
    try: amount = float(m.text.strip())
    except: await m.answer("Нужно число."); return
    uid = (await state.get_data())["uid"]
    db.add_balance(uid, amount)
    await state.clear()
    await m.answer(f"✅ Начислено {amount} Stars пользователю {uid}")
    try: await m.bot.send_message(uid, f"💰 Тебе начислен баланс: +{amount} Stars!")
    except: pass

@router.callback_query(F.data.startswith("reply:"))
async def reply_ticket_start(cb: CallbackQuery, state: FSMContext):
    _, ticket_id, user_id = cb.data.split(":")
    await state.update_data(ticket_id=int(ticket_id), user_id=int(user_id))
    await state.set_state(AdminFlow.reply_ticket)
    await cb.message.answer(f"✍️ Напиши ответ на тикет #{ticket_id}:")
    await cb.answer()

@router.message(AdminFlow.reply_ticket)
async def reply_ticket_send(m: Message, state: FSMContext):
    data = await state.get_data()
    ticket_id = data["ticket_id"]
    user_id = data["user_id"]
    u = db.get_user(user_id)
    lang = u["lang"] if u else "ru"
    try:
        await m.bot.send_message(user_id, t(lang, "ticket_reply", ticket_id=ticket_id, text=m.text))
        db.close_ticket(ticket_id)
        await m.answer("✅ Ответ отправлен, тикет закрыт.")
    except Exception as e:
        await m.answer(f"❌ Ошибка отправки: {e}")
    await state.clear()

@router.callback_query(F.data == "adm:bl")
async def bl_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AdminFlow.bl_name)
    await cb.message.answer("Юзернейм канала для ЧС (@name):")
    await cb.answer()

@router.message(AdminFlow.bl_name)
async def bl_name(m: Message, state: FSMContext):
    await state.update_data(bl=m.text.strip().replace("@",""))
    await state.set_state(AdminFlow.bl_reason)
    await m.answer("Причина:")

@router.message(AdminFlow.bl_reason)
async def bl_reason(m: Message, state: FSMContext):
    d = await state.get_data()
    db.add_blacklist(d["bl"], m.text.strip(), m.from_user.id)
    await state.clear()
    await m.answer(f"✅ @{d['bl']} добавлен в ЧС")

@router.callback_query(F.data == "adm:users")
async def users(cb: CallbackQuery):
    rows = db.all_users(20)
    txt = "👥 Пользователи:\n\n"
    for r in rows:
        txt += f"• {r['telegram_id']} @{r['username'] or '—'} | {r['role']}\n"
    await cb.message.answer(txt)
    await cb.answer()

@router.callback_query(F.data == "adm:payouts")
async def payouts(cb: CallbackQuery):
    with db.conn() as c:
        rows = c.execute("SELECT * FROM payouts WHERE status='pending'").fetchall()
    if not rows:
        await cb.message.answer("Заявок на вывод нет.")
        await cb.answer()
        return
        
    await cb.message.answer("💰 <b>Список заявок на вывод:</b>", parse_mode="HTML")
    for r in rows:
        txt = f"Заявка #{r['id']}\nUser ID: <code>{r['user_id']}</code>\nСумма: <b>{r['amount']} Stars</b>"
        await cb.message.answer(txt, reply_markup=admin_payouts_kb(r['id']), parse_mode="HTML")
    await cb.answer()

@router.callback_query(F.data.startswith("paid:"))
async def mark_paid(cb: CallbackQuery):
    payout_id = int(cb.data.split(":")[1])
    with db.conn() as c:
        row = c.execute("SELECT * FROM payouts WHERE id=?", (payout_id,)).fetchone()
        if not row or row['status'] != 'pending':
            await cb.answer("Заявка не найдена или уже выплачена.", show_alert=True)
            return
        c.execute("UPDATE payouts SET status='paid', paid_at=? WHERE id=?", (datetime.now().isoformat(), payout_id))
        
    await cb.message.edit_text(f"✅ Заявка #{payout_id} отмечена как выплаченная.")
    await cb.answer()
    
    try:
        await cb.bot.send_message(row['user_id'], f"🎉 Твоя заявка на вывод {row['amount']} Stars была успешно выплачена!")
    except: pass
