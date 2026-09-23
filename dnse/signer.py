import hmac
import hashlib
import base64
import uuid
from datetime import datetime, timezone
from email.utils import format_datetime

class DNSESigner:
    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret

    def _create_signing_string(self, method: str, path: str, date_str: str, nonce: str) -> str:
        clean_path = path.split('?')[0]
        return f"(request-target): {method.lower()} {clean_path}\ndate: {date_str}\nnonce: {nonce}"

    def build_headers(self, method: str, path: str) -> dict[str, str]:
        now = datetime.now(timezone.utc)
        date_str = format_datetime(now, usegmt=True)
        nonce = uuid.uuid4().hex

        signing_string = self._create_signing_string(method, path, date_str, nonce)
        raw_sig = hmac.new(
            self.api_secret.encode('utf-8'),
            signing_string.encode('utf-8'),
            hashlib.sha256
        ).digest()
        
        b64_sig = base64.b64encode(raw_sig).decode('ascii')
        encoded_sig = b64_sig.replace('+', '%2B').replace('/', '%2F').replace('=', '%3D')

        sig_header = (
            f'Signature keyId="{self.api_key}",'
            f'algorithm="hmac-sha256",'
            f'headers="(request-target) date",'
            f'signature="{encoded_sig}",'
            f'nonce="{nonce}"'
        )

        return {
            "X-API-Key": self.api_key,
            "X-Signature": sig_header,
            "Date": date_str,
            "User-Agent": "DNSE-TradingBot/1.0"
        }
