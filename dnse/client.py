import httpx
import logging
from typing import List, Optional
from dnse.signer import DNSESigner
from dnse.models import (
    AccountInfo, AccountBalance, StockBalance,
    PositionItem, LiveOrder, OrderPlacementResult
)

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

    async def get_loan_packages(self, account_no: str, symbol: str) -> List[dict]:
        path = f"/accounts/{account_no}/loan-packages"
        query_path = f"{path}?symbol={symbol.upper()}&marketType=STOCK"
        headers = self.signer.build_headers("GET", path)
        resp = await self._client.get(query_path, headers=headers)
        if resp.status_code == 200:
            return resp.json().get("loanPackages", [])
        logger.warning(f"Failed to fetch loan packages for {symbol}: {resp.status_code} {resp.text}")
        return []

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
        symbol = symbol.upper()
        # Automatically resolve normal cash-only loan package if not provided (strictly NO MARGIN)
        if not loan_package_id:
            pkgs = await self.get_loan_packages(account_no, symbol)
            if pkgs:
                normal_pkgs = [
                    p for p in pkgs
                    if str(p.get("type", "")).upper() == "N"
                    or "thường" in str(p.get("name", "")).lower()
                    or "normal" in str(p.get("name", "")).lower()
                ]
                loan_package_id = normal_pkgs[0].get("id") if normal_pkgs else pkgs[0].get("id")

        path = f"/accounts/{account_no}/orders"
        query_path = f"{path}?marketType=STOCK&orderCategory=NORMAL"
        headers = self.signer.build_headers("POST", path)
        if trading_token:
            headers["trading-token"] = trading_token

        payload = {
            "symbol": symbol,
            "side": side.upper(),
            "orderType": order_type.upper(),
            "quantity": quantity,
            "price": price,
            "loanPackageId": loan_package_id
        }

        try:
            resp = await self._client.post(query_path, headers=headers, json=payload)
            data = resp.json() if resp.text else {}
            if resp.status_code in (200, 201):
                order_id = str(data.get("orderId") or data.get("id") or "")
                return OrderPlacementResult(
                    success=True,
                    order_id=order_id,
                    message=f"Đặt lệnh thật thành công: {side} {quantity:,} {symbol} giá {price:,.0f} đ",
                    raw=data
                )
            else:
                err_msg = data.get("message") or data.get("code") or resp.text
                logger.error(f"DNSE place_order error ({resp.status_code}): {err_msg}")
                return OrderPlacementResult(
                    success=False,
                    message=f"Lỗi đặt lệnh từ DNSE ({resp.status_code}): {err_msg}",
                    raw=data
                )
        except Exception as e:
            logger.error(f"Exception placing order to DNSE: {e}")
            return OrderPlacementResult(
                success=False,
                message=f"Lỗi kết nối đặt lệnh: {e}",
                raw={}
            )

    async def get_orders(self, account_no: str) -> List[LiveOrder]:
        path = f"/accounts/{account_no}/orders"
        query_path = f"{path}?marketType=STOCK"
        headers = self.signer.build_headers("GET", path)
        resp = await self._client.get(query_path, headers=headers)
        if resp.status_code != 200:
            logger.warning(f"Failed to fetch orders: {resp.status_code} {resp.text}")
            return []
        
        data = resp.json()
        raw_orders = data.get("orders", [])
        results = []
        for o in raw_orders:
            results.append(LiveOrder(
                id=str(o.get("id") or o.get("orderId") or ""),
                symbol=o.get("symbol", ""),
                side=o.get("side", "NB"),
                orderType=o.get("orderType", "LO"),
                quantity=o.get("quantity", 0),
                price=o.get("price", 0.0),
                orderStatus=o.get("orderStatus", "PENDING"),
                filledQuantity=o.get("filledQuantity", 0),
                loanPackageId=o.get("loanPackageId"),
                createdTime=o.get("createdTime")
            ))
        return results

    async def cancel_order(self, account_no: str, order_id: str) -> dict:
        path = f"/accounts/{account_no}/orders/{order_id}"
        query_path = f"{path}?marketType=STOCK"
        headers = self.signer.build_headers("DELETE", path)
        try:
            resp = await self._client.delete(query_path, headers=headers)
            data = resp.json() if resp.text else {}
            if resp.status_code in (200, 204):
                return {"success": True, "message": f"Hủy lệnh {order_id} thành công", "raw": data}
            return {
                "success": False,
                "message": f"Lỗi hủy lệnh từ DNSE ({resp.status_code}): {data.get('message', resp.text)}",
                "raw": data
            }
        except Exception as e:
            return {"success": False, "message": f"Lỗi kết nối hủy lệnh: {e}", "raw": {}}
