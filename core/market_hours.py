from datetime import datetime, time
from zoneinfo import ZoneInfo

class MarketHours:
    VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

    @classmethod
    def get_session(cls, dt: datetime = None) -> str:
        if dt is None:
            dt = datetime.now(cls.VN_TZ)
        elif dt.tzinfo is None:
            dt = dt.replace(tzinfo=cls.VN_TZ)
        else:
            dt = dt.astimezone(cls.VN_TZ)

        # 0 = Monday, 6 = Sunday
        if dt.weekday() >= 5:
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
