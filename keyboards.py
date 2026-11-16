from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from locales import t
from config import SUBSCRIPTION_PRICES

def lang_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru")],
        [InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:en")],
    ])

def main_menu(lang, is_admin=False):
    rows = [
        [KeyboardButton(text=t(lang, "btn_check")), KeyboardButton(text=t(lang, "btn_profile"))],
        [KeyboardButton(text=t(lang, "btn_history")), KeyboardButton(text=t(lang, "btn_top"))],
        [KeyboardButton(text=t(lang, "btn_sub")), KeyboardButton(text=t(lang, "btn_ref"))],
        [KeyboardButton(text=t(lang, "btn_help")), KeyboardButton(text=t(lang, "btn_support"))]
    ]
    if is_admin:
        rows.append([KeyboardButton(text=t(lang, "btn_admin"))])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

def sub_kb(lang):
    p1 = SUBSCRIPTION_PRICES["1m"]; p3 = SUBSCRIPTION_PRICES["3m"]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "btn_buy_1m", p1=p1), callback_data="buy:1m")],
        [InlineKeyboardButton(text=t(lang, "btn_buy_3m", p3=p3), callback_data="buy:3m")],
    ])

def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Выдать подписку", callback_data="adm:give")],
        [InlineKeyboardButton(text="💰 Выдать баланс", callback_data="adm:balance")],
        [InlineKeyboardButton(text="🚫 Черный список", callback_data="adm:bl")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="adm:users")],
        [InlineKeyboardButton(text="💰 Заявки на вывод", callback_data="adm:payouts")],
    ])

def reply_ticket_kb(ticket_id, user_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Ответить", callback_data=f"reply:{ticket_id}:{user_id}")]
    ])

def payout_request_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💸 Запросить вывод Stars", callback_data="request_payout")]
    ])

def admin_payouts_kb(payout_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Выплачено", callback_data=f"paid:{payout_id}")]
    ])
