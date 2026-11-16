from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from keyboards import admin_kb
from services import db

router = Router()

class AdminFlow(StatesGroup):
    give_uid = State()
    give_days = State()
    bl_name = State()
    bl_reason = State()

def is_admin(u): return u and u["role"] in ("admin", "owner")

@router.message(F.text.in_({"👑 Админ-панель"}))
async def admin_panel(m: Message):
    # Принудительно делаем тебя владельцем при нажатии
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
    end = db.add_subscription(uid, days)
    await state.clear()
    await m.answer(f"✅ Выдано {days} дней. До {end[:10]}")
    try: await m.bot.send_message(uid, f"🎁 Тебе выдана подписка на {days} дней!")
    except: pass

@router.callback_query(F.data == "adm:bl")
async def bl_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AdminFlow.bl_name)
    await cb.message.answer("Юзернейм канала для черного списка (@name):")
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
        txt += f"• {r['telegram_id']} @{r['username'] or '—'} | {r['role']} | до {r['subscription_end'][:10] if r['subscription_end'] else '—'}\n"
    await cb.message.answer(txt)
    await cb.answer()

@router.callback_query(F.data == "adm:payouts")
async def payouts(cb: CallbackQuery):
    with db.conn() as c:
        rows = c.execute("SELECT * FROM payouts WHERE status='pending'").fetchall()
    if not rows:
        await cb.message.answer("Заявок нет.")
    else:
        txt = "💰 Заявки:\n"
        for r in rows:
            txt += f"• #{r['id']} user {r['user_id']} — {r['amount']} Stars\n"
        await cb.message.answer(txt)
    await cb.answer()
