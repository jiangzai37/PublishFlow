import getpass
import json
import os
import subprocess

from cryptography.fernet import Fernet

from app.config import get_settings

PLATFORM_DOMAINS = {
    "csdn": ("csdn.net",),
    "zhihu": ("zhihu.com", "zhimg.com"),
    "bilibili": ("bilibili.com", "biliapi.net"),
}


def secure_key_permissions(path) -> None:
    if os.name == "nt":
        username = getpass.getuser()
        result = subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", f"{username}:(F)"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError("无法限制本机凭证密钥的 Windows 访问权限。")
        return
    os.chmod(path, 0o600)


class CredentialVault:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.key_path = self.settings.data_dir / ".credential.key"

    def _key(self) -> bytes:
        if self.settings.encryption_key:
            return self.settings.encryption_key.encode()
        if not self.key_path.exists():
            key = Fernet.generate_key()
            self.key_path.write_bytes(key)
            secure_key_permissions(self.key_path)
        return self.key_path.read_bytes()

    def encrypt(self, value: str) -> str:
        return Fernet(self._key()).encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        return Fernet(self._key()).decrypt(value.encode()).decode()


def parse_cookie_payload(raw: str, platform: str = "csdn") -> list[dict]:
    roots = PLATFORM_DOMAINS.get(platform)
    if not roots:
        raise ValueError(f"暂不支持平台：{platform}")
    raw = raw.strip()
    if not raw:
        raise ValueError("Cookie 内容不能为空。")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("请粘贴 CookieJSON 浏览器扩展导出的 JSON 数组。") from exc
    if isinstance(parsed, dict) and "cookies" in parsed:
        parsed = parsed["cookies"]
    if not isinstance(parsed, list) or not parsed:
        raise ValueError("Cookie JSON 必须是非空数组。")
    normalized = []
    for cookie in parsed:
        if not isinstance(cookie, dict) or not cookie.get("name") or "value" not in cookie:
            raise ValueError("Cookie 缺少 name 或 value 字段。")
        domain = str(cookie.get("domain", "")).lstrip(".").lower()
        if domain and not any(domain == root or domain.endswith(f".{root}") for root in roots):
            continue
        try:
            expires = float(cookie.get("expirationDate", cookie.get("expires", -1)))
        except (TypeError, ValueError):
            expires = -1
        normalized.append(
            {
                "name": str(cookie["name"]),
                "value": str(cookie["value"]),
                "domain": domain or roots[0],
                "path": str(cookie.get("path", "/")),
                "expires": expires,
                "httpOnly": bool(cookie.get("httpOnly", False)),
                "secure": bool(cookie.get("secure", True)),
                "sameSite": "Lax",
            }
        )
    if not normalized:
        raise ValueError(f"没有找到 {' / '.join(roots)} 域的 Cookie。")
    return normalized
