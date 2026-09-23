from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
import time

router = Router()

@router.message(Command("balance"))
@router.message(lambda msg: msg.text == "💰 Số dư")
async def cmd_balance(message: Message, state_obj, client, repo):
    # Fetch or use cache
    if not state_obj.is_cache_valid(ttl_seconds=15.0) and client and state_obj.account:
        sub_id = state_obj.account.accounts[0].id
        bal = await client.get_balances(sub_id)
        state_obj.set_balance(bal)
        await repo.save_balance_snapshot(
            sub_id, bal.stock.totalCash, bal.stock.availableCash, bal.stock.totalDebt, bal.stock.withdrawableCash
        )

    if not state_obj.balance:
        await message.answer("⚠️ Chưa có dữ liệu số dư từ DNSE. Hãy bấm /sync để tải lại.")
        return

    s = state_obj.balance.stock
    acc = state_obj.account
    text = (
        f"👤 **Tài khoản:** {acc.name if acc else 'N/A'} (`{acc.custodyCode if acc else 'N/A'}`)\n"
        f"🏦 **Tiểu khoản:** `{acc.accounts[0].id if acc and acc.accounts else 'N/A'}`\n"
        "──────────────────────\n"
        f"💵 **Tiền khả dụng:** `{s.availableCash:,.0f} đ`\n"
        f"💰 **Tổng tiền mặt:** `{s.totalCash:,.0f} đ`\n"
        f"💳 **Nợ vay margin:** `{s.totalDebt:,.0f} đ`\n"
        f"🕒 **Cập nhật:** {time.strftime('%H:%M:%S', time.localtime(state_obj.last_sync_time))}"
    )
    await message.answer(text, parse_mode="Markdown")

@router.message(Command("positions"))
@router.message(lambda msg: msg.text == "📊 Vị thế")
async def cmd_positions(message: Message, state_obj, client):
    if not state_obj.is_cache_valid(ttl_seconds=15.0) and client and state_obj.account:
        sub_id = state_obj.account.accounts[0].id
        pos = await client.get_positions(sub_id)
        state_obj.set_positions(pos)

    if not state_obj.positions:
        await message.answer("📊 **DANH MỤC VỊ THẾ**\n──────────────────────\nHiện tại tài khoản chưa mở vị thế cổ phiếu nào.")
        return

    lines = ["📊 **DANH MỤC VỊ THẾ (VN30)**\n──────────────────────"]
    total_pnl = 0.0
    for p in state_obj.positions:
        icon = "🟢" if p.unrealizedPnl > 0 else ("🔴" if p.unrealizedPnl < 0 else "⚪")
        lines.append(
            f"{icon} **{p.symbol}**: {p.tradeQuantity:,} CP\n"
            f"   • Giá vốn: `{p.costPrice:,.0f}` | Thị giá: `{p.marketPrice:,.0f}`\n"
            f"   • Lãi/Lỗ: `{p.unrealizedPnl:+,.0f} đ` ({p.pnlPercent:+.2f}%)"
        )
        total_pnl += p.unrealizedPnl
    lines.append("──────────────────────")
    lines.append(f"**Tổng lãi/lỗ tạm tính:** `{total_pnl:+,.0f} đ`")
    await message.answer("\n".join(lines), parse_mode="Markdown")

@router.message(Command("sync"))
@router.message(lambda msg: msg.text == "🔄 Làm mới")
async def cmd_sync(message: Message, state_obj, client, repo):
    await message.answer("🔄 Đang đồng bộ dữ liệu mới nhất từ DNSE...")
    if not client or not state_obj.account:
        await message.answer("❌ Lỗi: Chưa kết nối được tài khoản DNSE.")
        return

    sub_id = state_obj.account.accounts[0].id
    start = time.time()
    bal = await client.get_balances(sub_id)
    pos = await client.get_positions(sub_id)
    latency = (time.time() - start) * 1000

    state_obj.latency_ms = latency
    state_obj.set_balance(bal)
    state_obj.set_positions(pos)
    await repo.save_balance_snapshot(
        sub_id, bal.stock.totalCash, bal.stock.availableCash, bal.stock.totalDebt, bal.stock.withdrawableCash
    )
    await message.answer(f"✅ Đã làm mới xong ({latency:.0f}ms)! Bấm 💰 Số dư hoặc 📊 Vị thế để xem.")
