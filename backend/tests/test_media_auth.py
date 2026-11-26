import json

import pytest

from app.auth.credentials import CredentialVault, parse_cookie_payload
from app.core.media.cover import create_cover


def test_cookie_validation_accepts_csdn_and_filters_other_domains():
    raw = json.dumps(
        [
            {"name": "session", "value": "secret", "domain": ".csdn.net"},
            {"name": "other", "value": "ignored", "domain": ".example.com"},
        ]
    )
    cookies = parse_cookie_payload(raw)
    assert len(cookies) == 1
    assert cookies[0]["name"] == "session"


def test_cookie_validation_accepts_zhihu_and_filters_other_domains():
    raw = json.dumps(
        [
            {"name": "session", "value": "secret", "domain": ".zhihu.com"},
            {"name": "image", "value": "token", "domain": "zhimg.com"},
            {"name": "other", "value": "ignored", "domain": ".csdn.net"},
        ]
    )
    cookies = parse_cookie_payload(raw, "zhihu")
    assert [cookie["domain"] for cookie in cookies] == ["zhihu.com", "zhimg.com"]


def test_cookie_validation_rejects_empty_payload():
    with pytest.raises(ValueError):
        parse_cookie_payload("")


def test_credential_vault_round_trip():
    vault = CredentialVault()
    plaintext = '{"name":"session","value":"secret"}'
    encrypted = vault.encrypt(plaintext)
    assert encrypted != plaintext
    assert vault.decrypt(encrypted) == plaintext


def test_cover_is_created():
    cover_url = create_cover("测试封面")
    assert cover_url.startswith("/media/")
    assert cover_url.endswith(".png")
