from datetime import datetime, time
from zoneinfo import ZoneInfo

class MarketHours:
    VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

    # Official Vietnam stock market public holidays (HOSE/HNX)
    VIETNAM_HOLIDAYS = {
        # 2025
        "2025-01-01",
        "2025-01-27", "2025-01-28", "2025-01-29", "2025-01-30", "2025-01-31",
        "2025-04-07",
        "2025-04-30", "2025-05-01", "2025-05-02",
        "2025-09-01", "2025-09-02",
        # 2026
        "2026-01-01",
        "2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20",
        "2026-04-26", "2026-04-27",
        "2026-04-30", "2026-05-01",
        "2026-09-01", "2026-09-02",
        # 2027
        "2027-01-01",
        "2027-02-05", "2027-02-06", "2027-02-07", "2027-02-08", "2027-02-09",
        "2027-04-15",
        "2027-04-30", "2027-05-01",
        "2027-09-02", "2027-09-03",
    }

    @classmethod
    def is_holiday(cls, dt: datetime) -> bool:
        date_str = dt.strftime("%Y-%m-%d")
        return date_str in cls.VIETNAM_HOLIDAYS

    @classmethod
    def get_session(cls, dt: datetime = None) -> str:
        if dt is None:
            dt = datetime.now(cls.VN_TZ)
        elif dt.tzinfo is None:
            dt = dt.replace(tzinfo=cls.VN_TZ)
        else:
            dt = dt.astimezone(cls.VN_TZ)

        # 0 = Monday, 6 = Sunday or public holiday
        if dt.weekday() >= 5 or cls.is_holiday(dt):
            return "CLOSED"

        t = dt.time()
        if t < time(9, 0):
            return "PRE_MARKET"
        elif time(9, 0) <= t < time(9, 15):
            return "ATO"
        elif time(9, 15) <= t < time(11, 30):
            return "CONTINUOUS"
        elif time(11, 30) <= t < time(13, 0):
            return "LUNCH_BREAK"
        elif time(13, 0) <= t < time(14, 30):
            return "CONTINUOUS"
        elif time(14, 30) <= t < time(14, 45):
            return "ATC"
        else:
            return "CLOSED"

    @classmethod
    def is_trading_time(cls, dt: datetime = None) -> bool:
        session = cls.get_session(dt)
        return session in ("ATO", "CONTINUOUS", "ATC")

    @classmethod
    def get_session_display(cls, dt: datetime = None) -> str:
        session = cls.get_session(dt)
        mapping = {
            "PRE_MARKET": "Tiền thị trường (Chờ mở cửa)",
            "ATO": "Khớp lệnh định kỳ mở cửa (ATO)",
            "CONTINUOUS": "Khớp lệnh liên tục",
            "LUNCH_BREAK": "Nghỉ trưa",
            "ATC": "Khớp lệnh định kỳ đóng cửa (ATC)",
            "CLOSED": "Thị trường đóng cửa"
        }
        return mapping.get(session, session)
