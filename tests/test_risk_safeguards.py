from core.risk_safeguards import RiskSafeguards, TradingMode

def test_risk_safeguards_limits():
    guard = RiskSafeguards(max_order_value=5000000.0, max_daily_orders=5)

    # 1. Normal order passes
    valid, msg = guard.validate_order("HPG", "NB", 100, 26000.0, reference_price=26000.0)
    assert valid is True

    # 2. Exceeds max order value (100 * 60,000 = 6,000,000 > 5,000,000)
    valid_val, msg_val = guard.validate_order("VHM", "NB", 100, 60000.0)
    assert valid_val is False
    assert "Hạn mức" in msg_val

    # 3. Exceeds HOSE price collar (+7% of 26,000 is 27,820; order at 29,000)
    valid_collar, msg_collar = guard.validate_order("HPG", "NB", 100, 29000.0, reference_price=26000.0)
    assert valid_collar is False
    assert "Trần/Sàn" in msg_collar

    # 4. Daily orders limit
    for _ in range(5):
        guard.record_order_sent()
    valid_daily, msg_daily = guard.validate_order("HPG", "NB", 100, 26000.0)
    assert valid_daily is False
    assert "Số lệnh tối đa" in msg_daily

def test_kill_switch_blocking():
    guard = RiskSafeguards()
    guard.activate_kill_switch("Thị trường sập bất thường")
    assert guard.kill_switch_active is True

    valid, msg = guard.validate_order("HPG", "NB", 100, 26000.0)
    assert valid is False
    assert "Kill Switch" in msg

    guard.deactivate_kill_switch()
    assert guard.kill_switch_active is False
