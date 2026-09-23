import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from storage.repository import PaperTradingRepository
from strategy.models import (
    PaperAccount, PaperPosition, PaperOrder,
    OrderSide, OrderStatus, OrderType
)

def get_next_business_day(cur_date: datetime) -> datetime:
    next_day = cur_date + timedelta(days=1)
    while next_day.weekday() >= 5:  # 5=Sat, 6=Sun
        next_day += timedelta(days=1)
    return next_day

def compute_settlement_date(from_date: datetime, business_days: int = 2) -> str:
    """Calculates settlement date by skipping weekends for T+2 clearing."""
    cur = from_date
    for _ in range(business_days):
        cur = get_next_business_day(cur)
    return cur.strftime("%Y-%m-%d")

class PaperEngine:
    """
    Simulated Paper Broker matching engine.
    Applies standard HOSE/HNX fee (0.15% buy) and fee+tax (0.25% sell).
    Enforces T+2 clearing for available sellable shares.
    """
    def __init__(self, repository: PaperTradingRepository):
        self.repo = repository

    async def initialize(self, initial_capital: float = 5_000_000.0) -> PaperAccount:
        return await self.repo.get_or_create_account(initial_capital)

    async def execute_buy(
        self,
        symbol: str,
        quantity: int,
        price: float,
        order_type: OrderType = OrderType.MP
    ) -> PaperOrder:
        symbol = symbol.upper()
        order_id = f"BUY-{int(datetime.now().timestamp())}-{uuid.uuid4().hex[:6]}"
        
        if quantity <= 0 or price <= 0:
            order = PaperOrder(
                order_id=order_id,
                symbol=symbol,
                side=OrderSide.BUY,
                quantity=quantity,
                price=price,
                order_type=order_type,
                status=OrderStatus.REJECTED
            )
            await self.repo.record_order(order)
            return order

        fee_rate = 0.0015
        gross_cost = price * quantity
        fee = round(gross_cost * fee_rate, 2)
        total_required = gross_cost + fee

        account = await self.repo.get_or_create_account()
        if account.cash_balance < total_required:
            order = PaperOrder(
                order_id=order_id,
                symbol=symbol,
                side=OrderSide.BUY,
                quantity=quantity,
                price=price,
                order_type=order_type,
                status=OrderStatus.REJECTED,
                fee=0.0
            )
            await self.repo.record_order(order)
            return order

        # Deduct cash
        new_cash = account.cash_balance - total_required
        await self.repo.update_account_balance(new_cash)

        # Update position
        existing_pos = await self.repo.get_position(symbol)
        now = datetime.now()
        buy_date_str = now.strftime("%Y-%m-%d")
        settle_date_str = compute_settlement_date(now, 2)

        if existing_pos and existing_pos.total_quantity > 0:
            total_qty = existing_pos.total_quantity + quantity
            # Volume-weighted average price (VWAP)
            new_avg_price = (
                (existing_pos.total_quantity * existing_pos.avg_buy_price) + (quantity * price)
            ) / total_qty
            highest_price = max(existing_pos.highest_price, price)
            available_qty = existing_pos.available_quantity  # Newly bought shares are unsettled
            await self.repo.upsert_position(symbol, total_qty, available_qty, new_avg_price, highest_price)
        else:
            await self.repo.upsert_position(symbol, quantity, 0, price, price)

        # Record settlement tranche for T+2
        await self.repo.add_settlement_tranche(symbol, quantity, buy_date_str, settle_date_str)

        # Record order and trade
        order = PaperOrder(
            order_id=order_id,
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=quantity,
            price=price,
            order_type=order_type,
            status=OrderStatus.FILLED,
            fee=fee,
            tax=0.0,
            matched_at=now
        )
        await self.repo.record_order(order)
        await self.repo.record_trade(
            order_id=order_id,
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=quantity,
            price=price,
            fee=fee,
            tax=0.0,
            realized_pnl=0.0
        )
        return order

    async def execute_sell(
        self,
        symbol: str,
        quantity: int,
        price: float,
        order_type: OrderType = OrderType.MP
    ) -> PaperOrder:
        symbol = symbol.upper()
        order_id = f"SELL-{int(datetime.now().timestamp())}-{uuid.uuid4().hex[:6]}"
        now = datetime.now()

        if quantity <= 0 or price <= 0:
            order = PaperOrder(
                order_id=order_id,
                symbol=symbol,
                side=OrderSide.SELL,
                quantity=quantity,
                price=price,
                order_type=order_type,
                status=OrderStatus.REJECTED
            )
            await self.repo.record_order(order)
            return order

        existing_pos = await self.repo.get_position(symbol)
        if not existing_pos or existing_pos.available_quantity < quantity:
            # Rejection due to insufficient available (T+2 settled) shares
            order = PaperOrder(
                order_id=order_id,
                symbol=symbol,
                side=OrderSide.SELL,
                quantity=quantity,
                price=price,
                order_type=order_type,
                status=OrderStatus.REJECTED
            )
            await self.repo.record_order(order)
            return order

        # Financials: fee 0.15%, tax 0.10%
        fee_rate = 0.0015
        tax_rate = 0.0010
        gross_proceeds = price * quantity
        fee = round(gross_proceeds * fee_rate, 2)
        tax = round(gross_proceeds * tax_rate, 2)
        net_received = gross_proceeds - fee - tax

        # Realized PnL = Net Received - Cost Basis
        cost_basis = existing_pos.avg_buy_price * quantity
        realized_pnl = round(net_received - cost_basis, 2)

        # Update cash balance
        account = await self.repo.get_or_create_account()
        new_cash = account.cash_balance + net_received
        await self.repo.update_account_balance(new_cash)

        # Update or remove position
        new_total_qty = existing_pos.total_quantity - quantity
        new_avail_qty = existing_pos.available_quantity - quantity
        if new_total_qty <= 0:
            await self.repo.delete_position(symbol)
        else:
            await self.repo.upsert_position(
                symbol,
                new_total_qty,
                new_avail_qty,
                existing_pos.avg_buy_price,
                existing_pos.highest_price
            )

        # Record order and trade
        order = PaperOrder(
            order_id=order_id,
            symbol=symbol,
            side=OrderSide.SELL,
            quantity=quantity,
            price=price,
            order_type=order_type,
            status=OrderStatus.FILLED,
            fee=fee,
            tax=tax,
            matched_at=now
        )
        await self.repo.record_order(order)
        await self.repo.record_trade(
            order_id=order_id,
            symbol=symbol,
            side=OrderSide.SELL,
            quantity=quantity,
            price=price,
            fee=fee,
            tax=tax,
            realized_pnl=realized_pnl
        )
        return order

    async def get_account_summary(self, current_prices: Optional[Dict[str, float]] = None) -> PaperAccount:
        if current_prices is None:
            current_prices = {}

        account = await self.repo.get_or_create_account()
        positions = await self.repo.get_positions()

        stock_val = 0.0
        for pos in positions:
            mkt_price = current_prices.get(pos.symbol, pos.avg_buy_price)
            stock_val += pos.total_quantity * mkt_price

        total_realized = await self.repo.get_total_realized_pnl()
        nav = round(account.cash_balance + stock_val, 2)

        account.stock_value = round(stock_val, 2)
        account.nav = nav
        account.total_realized_pnl = total_realized
        return account

    async def update_highest_prices(self, current_prices: Dict[str, float]):
        positions = await self.repo.get_positions()
        for pos in positions:
            if pos.symbol in current_prices:
                price = current_prices[pos.symbol]
                if price > pos.highest_price:
                    await self.repo.upsert_position(
                        pos.symbol,
                        pos.total_quantity,
                        pos.available_quantity,
                        pos.avg_buy_price,
                        price
                    )
