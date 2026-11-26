import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.credentials import CredentialVault, parse_cookie_payload
from app.storage.database import get_db
from app.storage.models import Account, PublishTask, SchedulePlan

router = APIRouter(tags=["accounts"])


class CookieImport(BaseModel):
    platform: str = Field(default="csdn", pattern=r"^(csdn|zhihu|bilibili)$")
    nickname: str = Field(default="我的账号", min_length=1, max_length=120)
    cookie_json: str = Field(min_length=10)


def serialize_account(account: Account) -> dict:
    return {
        "id": account.id,
        "platform": account.platform,
        "nickname": account.nickname,
        "login_valid": account.login_valid,
        "created_at": account.created_at.isoformat(),
    }


@router.get("/accounts")
def list_accounts(db: Session = Depends(get_db)):
    accounts = db.scalars(select(Account).order_by(Account.created_at.desc())).all()
    return [serialize_account(account) for account in accounts]


@router.post("/accounts/cookies", status_code=201)
def import_cookies(request: CookieImport, db: Session = Depends(get_db)):
    try:
        cookies = parse_cookie_payload(request.cookie_json, request.platform)
        encrypted = CredentialVault().encrypt(json.dumps(cookies, ensure_ascii=False))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    account = Account(
        platform=request.platform, nickname=request.nickname, cookie_encrypted=encrypted
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return serialize_account(account)


@router.post("/accounts/{account_id}/validate")
def validate_account(account_id: int, db: Session = Depends(get_db)):
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(404, "账号不存在")
    try:
        from publishers.registry import get_adapter

        cookies = json.loads(CredentialVault().decrypt(account.cookie_encrypted))
        profile = get_adapter(account.platform).get_author_profile(cookies)
    except Exception as exc:
        raise HTTPException(
            502, f"无法验证登录态：{type(exc).__name__}。请确认已安装 Playwright 浏览器。"
        ) from exc
    account.login_valid = profile["login_valid"]
    if profile.get("nickname"):
        account.nickname = profile["nickname"][:120]
    db.commit()
    db.refresh(account)
    return {**serialize_account(account), "message": profile["message"]}


@router.delete("/accounts/{account_id}", status_code=204)
def delete_account(account_id: int, db: Session = Depends(get_db)):
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(404, "账号不存在")
    if db.scalar(select(PublishTask.id).where(PublishTask.account_id == account_id).limit(1)):
        raise HTTPException(409, "该账号仍被发布任务引用，不能删除。")
    for plan in db.scalars(select(SchedulePlan)).all():
        if account_id in json.loads(plan.account_ids):
            raise HTTPException(409, "该账号仍被调度计划引用，请先修改或删除计划。")
    db.delete(account)
    db.commit()
