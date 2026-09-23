import pytest
from dnse.mock_client import MockDNSEClient
from dnse.models import LiveOrder, OrderPlacementResult

@pytest.mark.asyncio
async def test_mock_dnse_live_order_operations():
    client = MockDNSEClient()
    account_no = "0001880229"

    # 1. Test get loan packages
    pkgs = await client.get_loan_packages(account_no, "HPG")
    assert len(pkgs) > 0
    assert pkgs[0]["id"] == 1258

    # 2. Test place order
    res = await client.place_order(
        account_no=account_no,
        symbol="HPG",
        side="NB",
        order_type="LO",
        quantity=100,
        price=26000.0,
        loan_package_id=1258
    )
    assert res.success is True
    assert res.order_id is not None
    assert "HPG" in res.message

    # 3. Test get orders
    orders = await client.get_orders(account_no)
    assert len(orders) > 0
    assert orders[0].symbol == "HPG"
    assert orders[0].quantity == 100

    # 4. Test cancel order
    cancel_res = await client.cancel_order(account_no, res.order_id)
    assert cancel_res.get("success") is True

    await client.close()
