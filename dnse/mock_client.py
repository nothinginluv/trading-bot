from typing import List
from dnse.models import AccountInfo, SubAccount, AccountBalance, StockBalance, PositionItem

class MockDNSEClient:
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

    async def close(self):
        pass
