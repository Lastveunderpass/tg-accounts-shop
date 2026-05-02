from __future__ import annotations

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.handlers.admin._filters import AdminFilter
from src.services import stats_service
from src.utils.money import fmt_rub

router = Router(name="admin_stats")
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())


@router.callback_query(F.data == "adm:stats")
async def cb_stats(callback: CallbackQuery, session: AsyncSession) -> None:
    now = stats_service.utc_now()
    d1 = stats_service.since_days(1)
    d7 = stats_service.since_days(7)
    d30 = stats_service.since_days(30)

    rev_total = await stats_service.revenue_total(session)
    rev_24h = await stats_service.revenue_for_period(session, d1)
    rev_7d = await stats_service.revenue_for_period(session, d7)
    rev_30d = await stats_service.revenue_for_period(session, d30)

    tops_total = await stats_service.topups_total(session)
    tops_30d = await stats_service.topups_for_period(session, d30)

    users = await stats_service.users_count(session)
    new_24h = await stats_service.new_users_for_period(session, d1)
    new_7d = await stats_service.new_users_for_period(session, d7)

    orders_24h = await stats_service.orders_count_for_period(session, d1)
    orders_30d = await stats_service.orders_count_for_period(session, d30)

    by_cat = await stats_service.revenue_by_category(session, d30)
    top_v = await stats_service.top_variants(session, d30, limit=5)

    cat_lines = "\n".join(f"  • {n} — {fmt_rub(s)} ({c} шт.)" for n, s, c in by_cat[:10]) or "  —"
    var_lines = (
        "\n".join(f"  • {p} / {v} — {c} шт. ({fmt_rub(s)})" for p, v, c, s in top_v) or "  —"
    )

    text = (
        f"📊 <b>Статистика</b>\n"
        f"<i>сейчас: {now:%Y-%m-%d %H:%M UTC}</i>\n\n"
        f"<b>Выручка (paid)</b>\n"
        f"  За 24ч: {fmt_rub(rev_24h)}\n"
        f"  За 7 дн: {fmt_rub(rev_7d)}\n"
        f"  За 30 дн: {fmt_rub(rev_30d)}\n"
        f"  Всего: <b>{fmt_rub(rev_total)}</b>\n\n"
        f"<b>Пополнения</b>\n"
        f"  За 30 дн: {fmt_rub(tops_30d)}\n"
        f"  Всего: <b>{fmt_rub(tops_total)}</b>\n\n"
        f"<b>Пользователи</b>\n"
        f"  Всего: {users}\n"
        f"  Новых за 24ч: {new_24h}\n"
        f"  Новых за 7 дн: {new_7d}\n\n"
        f"<b>Заказы</b>\n"
        f"  За 24ч: {orders_24h}\n"
        f"  За 30 дн: {orders_30d}\n\n"
        f"<b>По категориям (30 дн)</b>\n{cat_lines}\n\n"
        f"<b>Топ варианты (30 дн)</b>\n{var_lines}"
    )
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="← В меню", callback_data="adm:menu")]]
        ),
    )
    await callback.answer()
