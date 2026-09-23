import uuid
from typing import List, Optional
from dnse.models import (
    AccountInfo, SubAccount, AccountBalance, StockBalance,
    PositionItem, LiveOrder, OrderPlacementResult
)

class MockDNSEClient:
    def __init__(self):
        self.orders: List[LiveOrder] = []

    async def get_accounts(self) -> AccountInfo:
        return AccountInfo(
            name="Nguyễn Doãn Minh Hiếu",
            custodyCode="064C551408",
            investorId="1001382802",
            accounts=[SubAccount(id="0001880229", dealAccount=True, derivativeAccount=False)]
        )

    async def get_balances(self, account_no: str) -> AccountBalance:
        return AccountBalance(
            stock=StockBalance(
                totalCash=27860.0,
                availableCash=27856.0,
                withdrawableCash=27856.0,
                depositInterest=4.0,
                totalDebt=0.0
            )
        )

    async def get_positions(self, account_no: str) -> List[PositionItem]:
        return [
            PositionItem(
                symbol="HPG",
                accountNo=account_no,
                status="OPEN",
                tradeQuantity=1000,
                openQuantity=1000,
                costPrice=28500.0,
                marketPrice=29200.0,
                unrealizedPnl=700000.0,
                pnlPercent=2.45
            )
        ]

    async def get_loan_packages(self, account_no: str, symbol: str) -> List[dict]:
        return [
            {
                "id": 1258,
                "name": "ZaloPay",
                "type": "N",
                "brokerFirmBuyingFeeRate": 0.0012,
                "brokerFirmSellingFeeRate": 0.0012
            }
        ]

    async def place_order(
        self,
        account_no: str,
        symbol: str,
        side: str,
        order_type: str,
        quantity: int,
        price: float,
        loan_package_id: Optional[int] = None,
        trading_token: Optional[str] = None
    ) -> OrderPlacementResult:
        order_id = f"MOCK-ORD-{uuid.uuid4().hex[:8]}"
        order = LiveOrder(
            id=order_id,
            symbol=symbol.upper(),
            side=side.upper(),
            orderType=order_type.upper(),
            quantity=quantity,
            price=price,
            orderStatus="PENDING",
            loanPackageId=loan_package_id or 1258
        )
        self.orders.append(order)
        return OrderPlacementResult(
            success=True,
            order_id=order_id,
            message=f"Đặt lệnh thật thành công: {side} {quantity:,} {symbol.upper()} giá {price:,.0f} đ",
            raw={"orderId": order_id}
        )

    async def get_orders(self, account_no: str) -> List[LiveOrder]:
        return list(self.orders)

    async def cancel_order(self, account_no: str, order_id: str) -> dict:
        for o in self.orders:
            if o.id == order_id:
                o.orderStatus = "CANCELLED"
                return {"success": True, "message": f"Hủy lệnh {order_id} thành công"}
        return {"success": False, "message": f"Không tìm thấy lệnh {order_id}"}

    async def close(self):
        pass
