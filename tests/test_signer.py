from dnse.signer import DNSESigner

def test_signature_headers():
    signer = DNSESigner(
        api_key="test_key_123",
        api_secret="test_secret_456"
    )
    headers = signer.build_headers("GET", "/accounts/0001880229/positions?marketType=STOCK")
    
    assert "X-API-Key" in headers
    assert headers["X-API-Key"] == "test_key_123"
    assert "Date" in headers
    assert "X-Signature" in headers
    
    sig = headers["X-Signature"]
    assert 'keyId="test_key_123"' in sig
    assert 'algorithm="hmac-sha256"' in sig
    assert 'headers="(request-target) date"' in sig
    assert 'signature="' in sig
    assert 'nonce="' in sig

def test_signature_strips_query_string():
    signer = DNSESigner("k", "s")
    # Query string must be stripped in (request-target)
    signing_string = signer._create_signing_string("GET", "/accounts/123/positions?marketType=STOCK", "Wed, 23 Sep 2026 02:45:00 GMT", "nonce123")
    assert "(request-target): get /accounts/123/positions" in signing_string
    assert "marketType" not in signing_string
