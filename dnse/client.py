import httpx
import logging
from typing import List
from dnse.signer import DNSESigner
from dnse.models import AccountInfo, AccountBalance, StockBalance, PositionItem

logger = logging.getLogger(__name__)

class DNSEClient:
    def __init__(self, api_key: str, api_secret: str, base_url: str = "https://openapi.dnse.com.vn"):
        self.signer = DNSESigner(api_key, api_secret)
        self.base_url = base_url
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=10.0)

    async def close(self):
        await self._client.aclose()

    async def get_accounts(self) -> AccountInfo:
        path = "/accounts"
        headers = self.signer.build_headers("GET", path)
        resp = await self._client.get(path, headers=headers)
        resp.raise_for_status()
        return AccountInfo.model_validate(resp.json())

    async def get_balances(self, account_no: str) -> AccountBalance:
        path = f"/accounts/{account_no}/balances"
        headers = self.signer.build_headers("GET", path)
        resp = await self._client.get(path, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        stock_data = data.get("stock", {})
        return AccountBalance(stock=StockBalance.model_validate(stock_data), raw=data)

    async def get_positions(self, account_no: str) -> List[PositionItem]:
        path = f"/accounts/{account_no}/positions"
        query_path = f"{path}?marketType=STOCK"
        headers = self.signer.build_headers("GET", path)
        resp = await self._client.get(query_path, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        raw_items = data.get("positions", [])
        results = []
        for item in raw_items:
            trade_qty = item.get("tradeQuantity", 0) or item.get("openQuantity", 0)
            cost = item.get("costPrice", 0.0)
            market = item.get("marketPrice", cost)
            pnl = (market - cost) * trade_qty
            pnl_pct = ((market - cost) / cost * 100) if cost > 0 else 0.0
            results.append(PositionItem(
                id=item.get("id"),
                symbol=item.get("symbol", ""),
                accountNo=account_no,
                status=item.get("status", "OPEN"),
                side=item.get("side", "NB"),
                tradeQuantity=trade_qty,
                openQuantity=item.get("openQuantity", 0),
                costPrice=cost,
                marketPrice=market,
                unrealizedPnl=pnl,
                pnlPercent=pnl_pct
            ))
        return results
