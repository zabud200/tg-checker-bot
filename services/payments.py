import os, uuid
from aiogram.types import LabeledPrice
from config import SUBSCRIPTION_PRICES

PLAN_DAYS = {"1m": 30, "3m": 90}

async def send_stars_invoice(bot, chat_id, plan):
    price = SUBSCRIPTION_PRICES[plan]
    payload = f"{plan}:{uuid.uuid4().hex[:8]}"
    await bot.send_invoice(
        chat_id=chat_id,
        title=f"Подписка {plan}",
        description=f"Доступ к проверке каналов на {PLAN_DAYS[plan]} дней",
        payload=payload,
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=f"Подписка {plan}", amount=price)],
    )
    return payload
