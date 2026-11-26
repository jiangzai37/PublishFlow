from pathlib import Path

import yaml
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

from app.core.typesetting.engine import plain_text_from_html
from publishers.base import Adapter, PublishResult

SELECTORS_PATH = Path(__file__).resolve().parents[1] / "selectors" / "zhihu.yaml"


class ZhihuAdapter(Adapter):
    platform = "zhihu"
    display_name = "知乎"

    def __init__(self) -> None:
        self.selectors = yaml.safe_load(SELECTORS_PATH.read_text(encoding="utf-8"))

    def login(self, cookie_json: str) -> dict:
        import json

        return {"platform": self.platform, "cookies": json.loads(cookie_json)}

    def _browser(self, cookies: list[dict]):
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1440, "height": 960}, locale="zh-CN")
        context.add_cookies(cookies)
        return playwright, browser, context

    def _first(self, page, key: str, timeout: int = 10000):
        for selector in self.selectors[key]:
            locator = page.locator(selector).first
            try:
                locator.wait_for(state="visible", timeout=timeout if selector == self.selectors[key][0] else 1800)
                return locator
            except PlaywrightTimeout:
                continue
        return None

    def get_author_profile(self, cookies: list[dict]) -> dict:
        playwright, browser, context = self._browser(cookies)
        page = context.new_page()
        try:
            page.goto("https://www.zhihu.com/", wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(2200)
            if "/signin" in page.url or page.locator(".Modal-visible").count():
                return {"login_valid": False, "nickname": "", "message": "登录态已失效，请重新导入 Cookie。"}
            nickname = ""
            for selector in (".AppHeader-profileEntry .UserName", "a.AppHeader-profileEntry img[alt]", ".UserName"):
                locator = page.locator(selector).first
                if locator.count() and locator.is_visible():
                    nickname = locator.get_attribute("alt") or locator.inner_text().strip()
                    break
            return {"login_valid": True, "nickname": nickname or page.title(), "message": "登录态可用。"}
        finally:
            browser.close()
            playwright.stop()

    def publish(self, payload, cookies: list[dict], options: dict | None = None) -> PublishResult:
        playwright, browser, context = self._browser(cookies)
        page = context.new_page()
        page.set_default_timeout(15000)
        submitted = False
        try:
            page.goto(self.selectors["editor_url"], wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2500)
            if "/signin" in page.url or page.locator(".Modal-visible").count():
                return PublishResult(False, message="登录态已失效，请重新导入 Cookie。", retryable=True)
            title = self._first(page, "title_selectors")
            if title is None:
                return PublishResult(False, message="未找到标题输入框，知乎页面可能已改版。", requires_manual=True)
            title.fill(payload.title)
            body = self._first(page, "body_selectors", timeout=15000)
            if body is None:
                return PublishResult(False, message="未找到正文编辑区，知乎页面可能已改版。", requires_manual=True)
            body.click()
            body.fill(plain_text_from_html(payload.rendered_html))

            if payload.cover_path and payload.cover_path.exists():
                cover = page.locator(self.selectors["cover_selectors"][0]).first
                if cover.count():
                    cover.set_input_files(str(payload.cover_path))

            if payload.tags:
                topic_button = self._first(page, "topic_selectors", timeout=3000)
                if topic_button:
                    topic_button.click()
                    page.wait_for_timeout(500)
                    topic_input = page.locator("input[placeholder*='话题'], input[placeholder*='搜索']").first
                    if topic_input.count():
                        topic_input.fill(payload.tags[0].lstrip("#"))
                        topic_input.press("Enter")

            publish_button = self._first(page, "publish_selectors", timeout=10000)
            if publish_button is None:
                return PublishResult(False, message="未找到发布按钮，请检查知乎页面。", requires_manual=True)
            submitted = True
            publish_button.click()
            page.wait_for_timeout(1800)
            confirm = self._first(page, "confirm_selectors", timeout=2500)
            if confirm:
                confirm.click()
            page.wait_for_timeout(1800)

            for marker in self.selectors["manual_markers"]:
                locator = page.locator(f"text={marker}").first
                if locator.count() and locator.is_visible():
                    return PublishResult(
                        False,
                        message=f"检测到「{marker}」。请在打开的浏览器中人工完成，PublishFlow 不会自动处理验证。",
                        requires_manual=True,
                        uncertain=submitted,
                    )

            for _ in range(45):
                page.wait_for_timeout(1000)
                if "zhuanlan.zhihu.com/p/" in page.url:
                    return PublishResult(True, url=page.url, message="文章已发布。")
                success = self._first(page, "success_selectors", timeout=300)
                if success:
                    return PublishResult(True, url=page.url, message="平台已确认发布成功。")
            return PublishResult(
                False,
                message="提交后未收到平台成功回执。请检查浏览器中的状态，再决定是否重试，避免重复发布。",
                requires_manual=True,
                uncertain=True,
            )
        except PlaywrightTimeout:
            if submitted:
                return PublishResult(
                    False,
                    message="提交后平台响应超时，结果不确定。请先检查浏览器中的文章状态。",
                    requires_manual=True,
                    uncertain=True,
                )
            return PublishResult(False, message="平台响应超时，尚未提交文章。", retryable=True)
        except Exception as exc:
            return PublishResult(
                False,
                message=f"发布中断，结果不确定：{type(exc).__name__}。请检查浏览器中的文章状态，避免重复发布。",
                requires_manual=True,
                uncertain=submitted,
                retryable=not submitted,
            )
        finally:
            browser.close()
            playwright.stop()

    def schedule(self, at):
        return {"platform": self.platform, "scheduled_at": at, "status": "planned"}

    def check_status(self, task_id: str) -> dict:
        return {"platform": self.platform, "task_id": task_id, "status": "unknown"}
