import json
import time
from pathlib import Path

import yaml
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

from app.config import get_settings
from publishers.base import Adapter, PublishResult

SELECTORS_PATH = Path(__file__).resolve().parents[1] / "selectors" / "bilibili.yaml"


class BilibiliAdapter(Adapter):
    platform = "bilibili"
    display_name = "哔哩哔哩"
    content_types = frozenset({"video"})
    title_limit = 80

    def __init__(self) -> None:
        self.selectors = yaml.safe_load(SELECTORS_PATH.read_text(encoding="utf-8"))

    def login(self, cookie_json: str) -> dict:
        return {"platform": self.platform, "cookies": json.loads(cookie_json)}

    def _browser(self, cookies: list[dict]):
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": 1440, "height": 960},
            locale="zh-CN",
            accept_downloads=True,
        )
        context.add_cookies(cookies)
        return playwright, browser, context

    def _first(self, page, key: str, timeout: int = 12000):
        for selector in self.selectors[key]:
            locator = page.locator(selector).first
            try:
                locator.wait_for(state="visible", timeout=timeout if selector == self.selectors[key][0] else 1800)
                return locator
            except PlaywrightTimeout:
                continue
        return None

    def _manual_marker(self, page) -> str:
        for marker in self.selectors["manual_markers"]:
            locator = page.locator(f"text={marker}").first
            if locator.count() and locator.is_visible():
                return marker
        return ""

    def _manual_result(self, page) -> PublishResult | None:
        marker = self._manual_marker(page)
        if not marker:
            return None
        return PublishResult(
            False,
            message=f"检测到「{marker}」。请在浏览器中人工完成，PublishFlow 不会绕过验证。",
            requires_manual=True,
        )

    def get_author_profile(self, cookies: list[dict]) -> dict:
        playwright, browser, context = self._browser(cookies)
        page = context.new_page()
        try:
            page.goto(self.selectors["home_url"], wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2500)
            if "passport.bilibili.com" in page.url or "login.bilibili.com" in page.url:
                return {"login_valid": False, "nickname": "", "message": "登录态已失效，请重新导入 B 站 Cookie。"}
            manual = self._manual_result(page)
            if manual:
                return {"login_valid": False, "nickname": "", "message": manual.message}
            nickname = ""
            for selector in self.selectors["nickname_selectors"]:
                locator = page.locator(selector).first
                if locator.count() and locator.is_visible():
                    nickname = locator.inner_text().strip()
                    break
            return {"login_valid": True, "nickname": nickname or "B站账号", "message": "登录态可用。"}
        finally:
            browser.close()
            playwright.stop()

    def _wait_for_upload(self, page) -> str:
        deadline = time.monotonic() + get_settings().video_upload_timeout_seconds
        while time.monotonic() < deadline:
            manual = self._manual_result(page)
            if manual:
                return manual.message
            for key in ("upload_success_selectors", "upload_error_selectors"):
                for selector in self.selectors[key]:
                    locator = page.locator(selector).first
                    if locator.count() and locator.is_visible():
                        if key == "upload_error_selectors":
                            return locator.inner_text().strip() or "平台拒绝了视频文件。"
                        return ""
            page.wait_for_timeout(1500)
        return "视频上传等待超时，尚未提交稿件。"

    def _choose_partition(self, page, partition: str) -> bool:
        trigger = self._first(page, "partition_selectors")
        if trigger is None:
            return False
        trigger.click()
        page.wait_for_timeout(500)
        option = page.get_by_text(partition, exact=True).last
        try:
            option.wait_for(state="visible", timeout=5000)
            option.click()
            return True
        except PlaywrightTimeout:
            return False

    def _choose_collection(self, page, collection: str) -> bool:
        trigger = self._first(page, "collection_selectors", timeout=3000)
        if trigger is None:
            return False
        trigger.click()
        page.wait_for_timeout(500)
        option = page.get_by_text(collection, exact=True).last
        try:
            option.wait_for(state="visible", timeout=5000)
            option.click()
            return True
        except PlaywrightTimeout:
            return False

    def publish(self, payload, cookies: list[dict], options: dict | None = None) -> PublishResult:
        options = options or {}
        if not payload.video_path or not Path(payload.video_path).is_file():
            return PublishResult(False, message="视频文件不存在，请重新上传。")
        if payload.cover_path and not payload.cover_path.is_file():
            return PublishResult(False, message="封面文件不存在，请重新生成。")
        playwright, browser, context = self._browser(cookies)
        page = context.new_page()
        page.set_default_timeout(15000)
        submitted = False
        try:
            page.goto(self.selectors["editor_url"], wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2500)
            if "passport.bilibili.com" in page.url:
                return PublishResult(False, message="登录态已失效，请重新导入 Cookie。", retryable=True)
            manual = self._manual_result(page)
            if manual:
                return manual

            upload = self._first(page, "upload_selectors", timeout=15000)
            if upload is None:
                return PublishResult(False, message="未找到视频上传入口，平台页面可能已改版。", requires_manual=True)
            upload.set_input_files(str(payload.video_path))
            upload_error = self._wait_for_upload(page)
            if upload_error:
                retryable = "超时" in upload_error
                return PublishResult(False, message=upload_error, retryable=retryable)
            manual = self._manual_result(page)
            if manual:
                return manual

            title = self._first(page, "title_selectors")
            if title is None:
                return PublishResult(False, message="未找到标题输入框，平台页面可能已改版。", requires_manual=True)
            title.fill(payload.title)
            body = self._first(page, "body_selectors", timeout=8000)
            if body is not None and payload.body:
                body.click()
                body.fill(payload.body[:2000])

            if payload.cover_path:
                cover = self._first(page, "cover_upload_selectors", timeout=5000)
                if cover is None:
                    return PublishResult(False, message="未找到封面上传入口，请在浏览器中人工检查。", requires_manual=True)
                cover.set_input_files(str(payload.cover_path))
                page.wait_for_timeout(1500)

            for tag in payload.tags[:10]:
                tag_input = self._first(page, "tag_selectors", timeout=1500)
                if tag_input:
                    tag_input.fill(tag)
                    tag_input.press("Enter")
                    page.wait_for_timeout(150)

            partition = options.get("partition") or "知识"
            if not self._choose_partition(page, partition):
                return PublishResult(
                    False,
                    message=f"未找到分区「{partition}」，请在浏览器中人工选择后再提交。",
                    requires_manual=True,
                )
            collection = options.get("collection")
            if collection and not self._choose_collection(page, collection):
                return PublishResult(
                    False,
                    message=f"未找到合集「{collection}」，请在浏览器中人工检查合集设置。",
                    requires_manual=True,
                )
            manual = self._manual_result(page)
            if manual:
                return manual

            publish_button = self._first(page, "publish_selectors", timeout=10000)
            if publish_button is None:
                return PublishResult(False, message="未找到投稿按钮，请在浏览器中人工检查。", requires_manual=True)
            submitted = True
            publish_button.click()
            page.wait_for_timeout(1000)
            confirm = self._first(page, "confirm_selectors", timeout=2500)
            if confirm:
                confirm.click()
            manual = self._manual_result(page)
            if manual:
                manual.uncertain = submitted
                return manual

            for _ in range(60):
                page.wait_for_timeout(1000)
                for selector in self.selectors["success_selectors"]:
                    marker = page.locator(selector).first
                    if marker.count() and marker.is_visible():
                        url = page.url if "upload/video" not in page.url else "https://member.bilibili.com/platform/upload-manage/article"
                        return PublishResult(True, url=url, message="B站已接收投稿，可在稿件管理中查看审核状态。")
            return PublishResult(
                False,
                message="提交后未收到平台成功回执，结果不确定。请先在 B 站稿件管理确认，勿直接重复投稿。",
                requires_manual=True,
                uncertain=True,
            )
        except PlaywrightTimeout:
            if submitted:
                return PublishResult(
                    False,
                    message="投稿提交后平台响应超时，结果不确定。请先在 B 站稿件管理确认。",
                    requires_manual=True,
                    uncertain=True,
                )
            return PublishResult(False, message="上传准备阶段超时，尚未提交稿件。", retryable=True)
        except Exception as exc:
            if submitted:
                return PublishResult(
                    False,
                    message=f"投稿中断，结果不确定：{type(exc).__name__}。请先在 B 站稿件管理确认。",
                    requires_manual=True,
                    uncertain=True,
                )
            return PublishResult(False, message=f"上传准备失败：{type(exc).__name__}", retryable=True)
        finally:
            browser.close()
            playwright.stop()

    def schedule(self, at):
        return {"platform": self.platform, "scheduled_at": at, "status": "planned"}

    def check_status(self, task_id: str) -> dict:
        return {"platform": self.platform, "task_id": task_id, "status": "unknown"}
