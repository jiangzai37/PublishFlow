import json
import os
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
_smoke_data = os.environ.get("PUBLISHFLOW_SMOKE_DATA_DIR")
if not _smoke_data:
    raise SystemExit(
        "请设置 PUBLISHFLOW_SMOKE_DATA_DIR 为独立临时数据目录；禁止使用项目真实数据目录。"
    )
DATA_ROOT = Path(_smoke_data).resolve()
if DATA_ROOT in {ROOT, ROOT / "data"} or ROOT in DATA_ROOT.parents:
    raise SystemExit("PUBLISHFLOW_SMOKE_DATA_DIR 必须位于项目目录之外的独立临时目录。")
ARTIFACTS = ROOT / "artifacts"
ARTIFACTS.mkdir(exist_ok=True)
BASE = os.environ.get("SMOKE_WEB_URL", "http://127.0.0.1:5173").rstrip("/")
API_URL = os.environ.get("SMOKE_API_URL", "http://127.0.0.1:8765").rstrip("/")
VIDEO_DIR = DATA_ROOT / "videos"
COVER_DIR = DATA_ROOT / "covers"
ASSET_DIR = DATA_ROOT / "assets"
SAMPLE_IMAGE = ARTIFACTS / "stage4-sample.png"
INITIAL_VIDEO_FILES = set(VIDEO_DIR.glob("*")) if VIDEO_DIR.exists() else set()
INITIAL_COVER_FILES = set(COVER_DIR.glob("*")) if COVER_DIR.exists() else set()
INITIAL_ASSET_FILES = set(ASSET_DIR.glob("*")) if ASSET_DIR.exists() else set()
STAGE5_DRAFT_TITLE = "UI 阶段5看板验收"
STAGE5_ACCOUNT_NAME = "UI 阶段5验收账号"


def initial_audit_id() -> int:
    database = DATA_ROOT / "publishflow.db"
    if not database.exists():
        return 0
    with sqlite3.connect(database) as db:
        return db.execute("SELECT COALESCE(MAX(id), 0) FROM audit_events").fetchone()[0]


INITIAL_AUDIT_ID = initial_audit_id()

sample = Image.new("RGB", (960, 540), "#e8e1d5")
sample_draw = ImageDraw.Draw(sample)
sample_draw.rectangle((70, 70, 890, 470), outline="#a44732", width=5)
sample_draw.text((125, 235), "PUBLISHFLOW / STAGE 04", fill="#292923")
sample.save(SAMPLE_IMAGE)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def cleanup_test_data() -> None:
    database = DATA_ROOT / "publishflow.db"
    if not database.exists():
        return
    with sqlite3.connect(database) as db:
        draft_rows = db.execute(
            "SELECT id, cover_image, video_path FROM drafts WHERE title IN (?, ?, ?)",
            ("UI 自动化验收草稿", "UI 视频自动化验收", STAGE5_DRAFT_TITLE),
        ).fetchall()
        draft_ids = [row[0] for row in draft_rows]
        test_media_files = set()
        for row in draft_rows:
            for value in row[1:]:
                if not value:
                    continue
                relative = value.removeprefix("/media/").removeprefix("/videos/")
                candidate = DATA_ROOT / relative
                if candidate.parent in (COVER_DIR, VIDEO_DIR):
                    test_media_files.add(candidate)
    with httpx.Client(base_url=API_URL, trust_env=False, timeout=10) as client:
        for plan in client.get("/api/schedules").json():
            if plan["name"] == "UI 自动化验收计划" or plan["draft_id"] in draft_ids:
                client.delete(f"/api/schedules/{plan['id']}")
    with sqlite3.connect(database) as db:
        account_ids = [
            row[0]
            for row in db.execute(
                "SELECT id FROM accounts WHERE nickname IN (?, ?, ?)",
                ("UI 验收账号", "UI B站验收账号", STAGE5_ACCOUNT_NAME),
            )
        ]
        if draft_ids:
            placeholders = ",".join("?" for _ in draft_ids)
            task_ids = [
                row[0]
                for row in db.execute(
                    f"SELECT id FROM publish_tasks WHERE draft_id IN ({placeholders})",
                    draft_ids,
                )
            ]
            if task_ids:
                task_placeholders = ",".join("?" for _ in task_ids)
                db.execute(
                    f"DELETE FROM metric_snapshots WHERE task_id IN ({task_placeholders})",
                    task_ids,
                )
                db.execute(
                    f"DELETE FROM compliance_decisions WHERE task_id IN ({task_placeholders})",
                    task_ids,
                )
                db.execute(
                    f"DELETE FROM publish_logs WHERE task_id IN ({task_placeholders})",
                    task_ids,
                )
                db.execute(
                    f"DELETE FROM publish_tasks WHERE id IN ({task_placeholders})",
                    task_ids,
                )
            db.execute(
                f"DELETE FROM schedule_plans WHERE draft_id IN ({placeholders})",
                draft_ids,
            )
            db.execute(f"DELETE FROM drafts WHERE id IN ({placeholders})", draft_ids)
        if account_ids:
            placeholders = ",".join("?" for _ in account_ids)
            db.execute(
                f"DELETE FROM accounts WHERE id IN ({placeholders})", account_ids
            )
        db.execute("DELETE FROM schedule_plans WHERE name = ?", ("UI 自动化验收计划",))
        db.execute("DELETE FROM presets WHERE name = ?", ("UI 自动化模板",))
        db.execute("DELETE FROM audit_events WHERE id > ?", (INITIAL_AUDIT_ID,))
        new_asset_files = set(ASSET_DIR.glob("*")) - INITIAL_ASSET_FILES
        new_media_files = (
            new_asset_files
            | (set(VIDEO_DIR.glob("*")) - INITIAL_VIDEO_FILES)
            | (set(COVER_DIR.glob("*")) - INITIAL_COVER_FILES)
        )
        asset_ids = []
        legacy_test_asset_files = set()
        for asset_id, original_name, stored_path in db.execute(
            "SELECT id, original_name, stored_path FROM media_assets"
        ).fetchall():
            path = DATA_ROOT / stored_path
            legacy_test = original_name in {
                "接口封面测试.png",
                "把复杂的事，交给清晰的系统.png",
                "stage3-sample.mp4",
            } or original_name.startswith(("test-video-", "UI 视频自动化验收"))
            if path in new_media_files or legacy_test:
                asset_ids.append(asset_id)
            if legacy_test:
                legacy_test_asset_files.add(path)
        if asset_ids:
            placeholders = ",".join("?" for _ in asset_ids)
            db.execute(
                f"DELETE FROM media_assets WHERE id IN ({placeholders})", asset_ids
            )
        db.commit()
    for path in test_media_files:
        path.unlink(missing_ok=True)
    for path in legacy_test_asset_files:
        path.unlink(missing_ok=True)
    for path in set(VIDEO_DIR.glob("*")) - INITIAL_VIDEO_FILES:
        path.unlink(missing_ok=True)
    for path in set(COVER_DIR.glob("*")) - INITIAL_COVER_FILES:
        path.unlink(missing_ok=True)
    for path in set(ASSET_DIR.glob("*")) - INITIAL_ASSET_FILES:
        path.unlink(missing_ok=True)
    SAMPLE_IMAGE.unlink(missing_ok=True)


try:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 1440, "height": 1000}, device_scale_factor=1
        )
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "console",
            lambda message: (
                errors.append(message.text) if message.type == "error" else None
            ),
        )
        page.on(
            "response",
            lambda response: (
                errors.append(f"HTTP {response.status} {response.url}")
                if response.status >= 400
                else None
            ),
        )

        page.goto(BASE, wait_until="networkidle")
        check(
            page.get_by_role("heading", name="让内容，准确抵达。").is_visible(),
            "工作台首页未显示",
        )
        check(page.get_by_text("本地服务已连接").is_visible(), "本地服务未连接")

        page.locator(".title-field input").fill("未保存文章保护验收")
        page.once("dialog", lambda dialog: dialog.dismiss())
        page.get_by_role("button", name="填入示例").first.click()
        check(
            page.locator(".title-field input").input_value() == "未保存文章保护验收",
            "取消未保存文章覆盖后内容发生变化",
        )

        page.once("dialog", lambda dialog: dialog.accept())
        page.get_by_role("button", name="填入示例").first.click()
        page.locator(".article-preview h1").wait_for(state="visible")
        check(
            "把复杂的事" in page.locator(".article-preview h1").inner_text(),
            "实时预览未更新",
        )

        page.get_by_role("button", name="知乎思辨", exact=True).click()
        page.wait_for_timeout(700)
        check(
            page.locator(".preview-preset").inner_text() == "知乎思辨",
            "排版预设切换失败",
        )
        page.locator(".article-preview h2").first.wait_for(state="visible")
        check(
            page.locator(".article-preview blockquote").count() >= 1,
            "Markdown 标题或引用未渲染",
        )
        page.locator(".preview-head .spin").wait_for(state="detached", timeout=15000)
        check(
            "##" not in page.locator(".article-preview").inner_text(),
            "预览中残留未渲染的 Markdown 标题",
        )

        page.get_by_role("button", name="重新生成").click()
        page.locator(".cover-box img").wait_for(state="visible", timeout=15000)
        check(
            page.locator(".cover-box img").get_attribute("src").startswith("/media/"),
            "封面未生成",
        )

        page.locator(".title-field input").fill("UI 自动化验收草稿")
        page.get_by_label("文章正文").fill("这是行业第一的本地发布工作台。")
        page.locator(".ad-ack input").wait_for(state="visible", timeout=15000)
        page.locator(".ad-ack input").check()
        page.get_by_label("文章正文").fill("这是行业第一的本地发布工作台，正文已更新。")
        page.wait_for_function("!document.querySelector('.ad-ack input')?.checked")
        page.locator(".ad-ack input").check()
        page.locator(".preset-pills button:not(.active)").first.click()
        page.wait_for_function("!document.querySelector('.ad-ack input')?.checked")
        page.get_by_label("文章正文").fill("用于验证本地发布工作台的完整流程。")
        page.get_by_role("button", name="保存草稿").click()
        page.get_by_text("草稿已安全保存到本机", exact=True).wait_for(state="visible")

        def delay_draft_save(route):
            if route.request.method == "PUT":
                time.sleep(0.8)
            route.continue_()

        page.route("**/api/drafts/*", delay_draft_save)
        page.get_by_role("button", name="保存草稿").click()
        page.get_by_label("文章正文").fill(
            "保存请求期间继续编辑的内容不会被旧响应覆盖。"
        )
        page.get_by_text("草稿已安全保存到本机", exact=True).wait_for(state="visible")
        check(
            page.get_by_label("文章正文").input_value()
            == "保存请求期间继续编辑的内容不会被旧响应覆盖。",
            "保存期间的新编辑被旧响应覆盖",
        )
        page.unroute("**/api/drafts/*", delay_draft_save)
        page.get_by_role("button", name="保存草稿").click()
        page.get_by_text("草稿已安全保存到本机", exact=True).wait_for(state="visible")
        page.screenshot(path=ARTIFACTS / "desktop-editor.png", full_page=True)

        page.locator(".main-nav").get_by_role("button", name="素材库").click()
        page.get_by_role("heading", name="让每一份素材，都有去处。").wait_for(
            state="visible"
        )
        registered_assets = page.request.get(f"{BASE}/api/assets").json()
        check(
            any(asset["source"] == "cover" for asset in registered_assets),
            "生成封面未自动进入素材库",
        )
        page.locator('.import-section input[type="file"]').first.set_input_files(
            SAMPLE_IMAGE
        )
        uploaded_row = page.locator(".asset-row").filter(has_text="stage4-sample.png")
        uploaded_row.wait_for(state="visible")
        uploaded_row.get_by_role("button", name="编辑 stage4-sample.png 的标签").click()
        uploaded_row.locator(".inline-tag-editor input").fill("验收，封面")
        uploaded_row.locator(".inline-tag-editor").get_by_role(
            "button", name="保存", exact=True
        ).click()
        page.get_by_text("素材标签已更新。", exact=True).wait_for(state="visible")
        page.screenshot(path=ARTIFACTS / "desktop-media.png", full_page=True)
        uploaded_row.get_by_role("button", name="使用图片", exact=True).click()
        check(
            page.locator(".cover-box img").get_attribute("src").startswith("/assets/"),
            "素材库图片未回填文章封面",
        )
        saved_draft = next(
            item
            for item in page.request.get(f"{BASE}/api/drafts").json()
            if item["title"] == "UI 自动化验收草稿"
        )
        with page.expect_response(
            lambda response: (
                response.request.method == "PUT"
                and response.url.endswith(f"/api/drafts/{saved_draft['id']}")
            )
        ) as save_response:
            page.get_by_role("button", name="保存草稿").click()
        check(save_response.value.ok, "素材封面写入草稿失败")
        uploaded_asset = next(
            asset
            for asset in page.request.get(f"{BASE}/api/assets").json()
            if asset["original_name"] == "stage4-sample.png"
        )
        protected_delete = page.request.delete(
            f"{BASE}/api/assets/{uploaded_asset['id']}"
        )
        check(protected_delete.status == 409, "被草稿引用的素材未被阻止删除")

        page.get_by_role("button", name="一稿多发", exact=True).click()
        page.get_by_role("heading", name="让一份原稿，有多种表达。").wait_for(
            state="visible"
        )
        reuse_modal = page.locator(".reuse-modal")
        check(
            reuse_modal.locator(".modal-close").evaluate(
                "element => element === document.activeElement"
            ),
            "复用弹窗未将焦点移到关闭按钮",
        )
        page.keyboard.press("Shift+Tab")
        check(
            reuse_modal.get_by_role("button", name="创建独立版本", exact=True).evaluate(
                "element => element === document.activeElement"
            ),
            "复用弹窗 Shift+Tab 未循环到末尾按钮",
        )
        page.keyboard.press("Tab")
        check(
            reuse_modal.locator(".modal-close").evaluate(
                "element => element === document.activeElement"
            ),
            "复用弹窗 Tab 未循环到首个按钮",
        )
        page.locator(".reuse-modal").get_by_role(
            "button", name="知乎知识社区", exact=True
        ).click()
        page.get_by_role("button", name="创建独立版本", exact=True).click()
        page.get_by_text("独立复用版本已创建，原稿保持不变", exact=True).wait_for(
            state="visible"
        )
        reused_drafts = [
            item
            for item in page.request.get(f"{BASE}/api/drafts").json()
            if item["title"] == "UI 自动化验收草稿"
        ]
        check(
            len(reused_drafts) >= 2
            and len({item["id"] for item in reused_drafts}) >= 2,
            "一稿多发未创建独立草稿",
        )
        check(
            any(item["source"] == "reuse" for item in reused_drafts),
            "复用草稿来源标记异常",
        )

        page.locator(".main-nav").get_by_role("button", name="模板工坊").click()
        page.get_by_role("heading", name="模板工坊", exact=True).wait_for(
            state="visible"
        )
        page.get_by_role("button", name="新建模板", exact=True).click()
        page.locator("#template-name").fill("UI 自动化模板")
        page.locator("#template-description").fill("阶段 4 自定义模板验收")
        page.locator("#template-heading-style").select_option("numbered")
        preview_frame = page.frame_locator(".te-preview-stage iframe")
        preview_frame.locator("h1").wait_for(state="visible", timeout=15000)
        with page.expect_response(
            lambda response: (
                response.request.method == "POST"
                and response.url.endswith("/api/presets")
            )
        ) as preset_response:
            page.get_by_role("button", name="创建模板", exact=True).click()
        check(
            preset_response.value.ok,
            f"自定义模板保存失败：{preset_response.value.text()}",
        )
        page.get_by_text("模板已保存到本机。", exact=True).wait_for(state="visible")
        saved_presets = page.request.get(f"{BASE}/api/presets").json()
        check(
            any(
                preset["name"] == "UI 自动化模板" and not preset["is_builtin"]
                for preset in saved_presets
            ),
            "自定义模板未保存",
        )
        page.screenshot(path=ARTIFACTS / "desktop-template-editor.png", full_page=True)
        page.locator("#template-name").fill("UI 自动化模板 未保存")
        page.once("dialog", lambda dialog: dialog.dismiss())
        page.get_by_role("button", name="内容编辑台", exact=True).click()
        check(
            page.get_by_role("heading", name="模板工坊", exact=True).is_visible(),
            "模板未保存修改离开保护未生效",
        )
        page.locator("#template-name").fill("UI 自动化模板")
        page.get_by_role("button", name="应用", exact=True).click()
        check(
            page.get_by_role("heading", name="让内容，准确抵达。").is_visible(),
            "模板应用后未返回编辑台",
        )
        check(
            page.locator(".preview-preset").inner_text() == "UI 自动化模板",
            "自定义模板未应用到编辑器",
        )

        page.get_by_role("button", name="账号与授权").click()
        check(
            page.get_by_role("button", name="知乎", exact=True).is_visible(),
            "知乎导入入口未显示",
        )
        page.locator(".form-label input").fill("UI 验收账号")
        page.locator(".form-label textarea").fill(
            '[{"name":"session","value":"ui-test","domain":".csdn.net"}]'
        )
        page.get_by_role("button", name="加密保存账号").click()
        page.locator(".account-item").wait_for(state="visible")
        check(page.locator(".account-item").count() >= 1, "Cookie 导入失败")
        page.get_by_role("button", name="哔哩哔哩", exact=True).click()
        page.locator(".form-label input").fill("UI B站验收账号")
        page.locator(".form-label textarea").fill(
            '[{"name":"SESSDATA","value":"ui-test","domain":".bilibili.com"}]'
        )
        page.get_by_role("button", name="加密保存账号").click()
        page.locator(".account-item").filter(has_text="UI B站验收账号").wait_for(
            state="visible"
        )

        page.get_by_role("button", name="定时与队列").click()
        page.get_by_role("button", name="新建调度计划").click()
        form = page.locator(".schedule-form-panel")
        form.locator("input").first.fill("UI 自动化验收计划")
        form.locator(".account-checkboxes input").check()
        form.locator(".schedule-authorization input").check()
        page.screenshot(path=ARTIFACTS / "desktop-schedule-form.png", full_page=True)
        form.locator('input[type="datetime-local"]').fill("")
        form.get_by_role("button", name="创建调度计划").click()
        page.get_by_text("请选择一次性计划的执行时间", exact=True).wait_for(
            state="visible"
        )
        form.locator('input[type="datetime-local"]').fill(
            (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
        )
        form.get_by_role("button", name="创建调度计划").click()
        page.locator(".schedule-item").filter(has_text="UI 自动化验收计划").wait_for(
            state="visible"
        )
        page.screenshot(path=ARTIFACTS / "desktop-schedules.png", full_page=True)

        page.get_by_role("button", name="内容编辑台").click()
        page.locator("#scheduled-at").fill(
            (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
        )
        page.locator(".authorization input").check()
        publish_trigger = page.locator(".publish-button")
        publish_trigger.click()
        publish_modal = page.locator(".publish-modal")
        publish_modal.wait_for(state="visible")
        check(
            publish_modal.locator(".modal-close").evaluate(
                "element => element === document.activeElement"
            ),
            "发布弹窗未将焦点移到关闭按钮",
        )
        page.keyboard.press("Shift+Tab")
        check(
            publish_modal.get_by_role(
                "button", name="确认创建任务", exact=True
            ).evaluate("element => element === document.activeElement"),
            "发布弹窗 Shift+Tab 未循环到末尾按钮",
        )
        page.keyboard.press("Tab")
        check(
            publish_modal.locator(".modal-close").evaluate(
                "element => element === document.activeElement"
            ),
            "发布弹窗 Tab 未循环到首个按钮",
        )
        page.keyboard.press("Escape")
        publish_modal.wait_for(state="detached")
        check(
            publish_trigger.evaluate("element => element === document.activeElement"),
            "发布弹窗关闭后未恢复触发按钮焦点",
        )

        drafts = page.request.get(f"{BASE}/api/drafts").json()
        accounts = page.request.get(f"{BASE}/api/accounts").json()
        draft = next(item for item in drafts if item["title"] == "UI 自动化验收草稿")
        account = next(item for item in accounts if item["nickname"] == "UI 验收账号")
        task_response = page.request.post(
            f"{BASE}/api/publish",
            data={
                "draft_id": draft["id"],
                "account_id": account["id"],
                "preset_id": "fresh",
                "authorized": True,
                "scheduled_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                "max_retries": 1,
            },
        )
        check(task_response.ok, f"定时任务创建失败：{task_response.text()}")

        page.get_by_role("button", name="发布记录").click()
        task_item = (
            page.locator(".task-item").filter(has_text="UI 自动化验收草稿").first
        )
        task_item.get_by_role("button", name="暂停", exact=True).click()
        task_item.get_by_text("已暂停", exact=True).wait_for(state="visible")
        task_item.get_by_role("button", name="恢复", exact=True).click()
        task_item.get_by_text("等待中", exact=True).wait_for(state="visible")
        task_item.get_by_role("button", name="跳过", exact=True).click()
        task_item.get_by_text("已跳过", exact=True).wait_for(state="visible")

        stage5_draft_response = page.request.post(
            f"{BASE}/api/drafts",
            data={
                "title": STAGE5_DRAFT_TITLE,
                "body": "用于验证本地数据看板与合规指标回采，不会调用真实平台。",
                "tags": ["阶段5", "验收"],
            },
        )
        check(
            stage5_draft_response.ok,
            f"阶段5验收草稿创建失败：{stage5_draft_response.text()}",
        )
        stage5_account_response = page.request.post(
            f"{BASE}/api/accounts/cookies",
            data={
                "platform": "csdn",
                "nickname": STAGE5_ACCOUNT_NAME,
                "cookie_json": '[{"name":"session","value":"stage5-ui-test","domain":".csdn.net"}]',
            },
        )
        check(
            stage5_account_response.ok,
            f"阶段5验收账号创建失败：{stage5_account_response.text()}",
        )
        with sqlite3.connect(DATA_ROOT / "publishflow.db") as db:
            cursor = db.execute(
                "INSERT INTO publish_tasks "
                "(draft_id, account_id, platform, content_type, preset_id, status, retry_count, max_retries, "
                "created_at, updated_at) "
                "VALUES (?, ?, 'csdn', 'article', 'fresh', 'success', 0, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                (
                    stage5_draft_response.json()["id"],
                    stage5_account_response.json()["id"],
                ),
            )
            stage5_task_id = cursor.lastrowid
            db.commit()

        page.locator(".main-nav").get_by_role("button", name="数据看板").click()
        page.get_by_role("heading", name="看见每一次发布的回响。").wait_for(
            state="visible"
        )
        page.locator(".kpi-grid").wait_for(state="visible")
        page.screenshot(path=ARTIFACTS / "desktop-dashboard.png", full_page=True)
        page.evaluate("""() => {
          const originalFetch = window.fetch.bind(window)
          let releaseAnalytics
          window.__analyticsGate = new Promise(resolve => { releaseAnalytics = resolve })
          window.__releaseAnalytics = releaseAnalytics
          window.__originalFetch = originalFetch
          window.fetch = (input, init) => originalFetch(input, init).then(response => {
            if (String(input).includes('/api/analytics?days=7')) {
              return window.__analyticsGate.then(() => response)
            }
            return response
          })
        }""")
        with page.expect_request(
            lambda request: request.url.endswith("/api/analytics?days=7")
        ):
            page.get_by_role("button", name="近 7 天", exact=True).click()
        with page.expect_response(
            lambda response: response.url.endswith("/api/analytics?days=30")
        ):
            page.get_by_role("button", name="近 30 天", exact=True).click()
        page.wait_for_function(
            "!document.querySelector('.dashboard-toolbar .button')?.disabled"
        )
        page.evaluate("""() => {
          window.__releaseAnalytics()
          return new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))
        }""")
        check(
            page.get_by_role("button", name="近 30 天", exact=True).get_attribute(
                "aria-pressed"
            )
            == "true",
            "看板快速切换后被旧周期响应覆盖",
        )
        check(
            "近 30 天" in page.locator(".trend-chart").get_attribute("aria-label"),
            "看板图表周期与当前选择不一致",
        )
        page.evaluate("window.fetch = window.__originalFetch")
        page.get_by_role("button", name="录入指标", exact=True).click()
        metric_form = page.locator(".metric-form-panel")
        metric_form.locator(".metric-task-field select").select_option(
            str(stage5_task_id)
        )
        metric_form.get_by_label("浏览量", exact=True).fill("120")
        metric_form.get_by_label("阅读量", exact=True).fill("30")
        metric_form.get_by_label("点赞", exact=True).fill("5")
        metric_form.get_by_label("评论", exact=True).fill("2")
        metric_form.get_by_label("分享", exact=True).fill("1")
        metric_form.get_by_label("收藏", exact=True).fill("3")
        metric_form.get_by_label("备注", exact=True).fill("阶段5浏览器验收数据")
        page.screenshot(path=ARTIFACTS / "desktop-metric-form.png", full_page=True)
        metric_form.get_by_role("button", name="保存指标", exact=True).click()
        metric_form.wait_for(state="detached")
        page.locator(".snapshot-list").get_by_text(
            STAGE5_DRAFT_TITLE, exact=True
        ).wait_for(state="visible")
        analytics = page.request.get(f"{BASE}/api/analytics?days=30").json()
        check(
            analytics["metrics"]["views"] >= 120
            and analytics["metrics"]["reads"] >= 30,
            "指标未进入统计聚合",
        )
        check(analytics["metrics"]["engagement"] >= 11, "互动指标聚合异常")
        page.screenshot(path=ARTIFACTS / "desktop-dashboard-filled.png", full_page=True)

        page.locator(".main-nav").get_by_role("button", name="发布记录").click()
        audit_row = (
            page.locator(".audit-row").filter(has_text="POST /api/metrics").first
        )
        audit_row.wait_for(state="visible")
        audit_row.locator(".audit-row-main").click()
        check(
            audit_row.locator(".audit-detail code").first.inner_text() != "",
            "审计请求标识为空",
        )
        audit_metadata = audit_row.locator(".audit-metadata pre").inner_text()
        check(
            '"path"' in audit_metadata and "metadata_json" not in audit_metadata,
            "审计详情未使用后端 metadata 对象",
        )
        check(
            "cookie" not in audit_metadata.lower()
            and "authorization" not in audit_metadata.lower(),
            "审计详情暴露了凭证字段",
        )
        page.screenshot(path=ARTIFACTS / "desktop-audit.png", full_page=True)

        page.get_by_role("button", name="内容编辑台", exact=True).click()
        page.get_by_label("文章正文").fill("本地发布工作台行业第一。")
        page.locator(".editor-view .ad-ack input").wait_for(
            state="visible", timeout=15000
        )
        page.locator(".editor-view .ad-ack input").check()
        page.get_by_role("button", name="保存草稿").click()
        page.get_by_text("草稿已安全保存到本机", exact=True).wait_for(state="visible")
        page.locator(".editor-view .ad-ack input").check()

        page.get_by_role("button", name="视频发布").click()
        check(
            page.get_by_role("heading", name="让画面，也准确抵达。").is_visible(),
            "视频工作台未显示",
        )
        page.get_by_role("button", name="新建视频", exact=True).click()
        check(
            page.locator(".video-copy-fields .title-field input").input_value() == "",
            "确认覆盖后未创建空白视频草稿",
        )
        page.locator(".video-copy-fields .title-field input").fill("视频独立预览验收")
        page.locator(".video-copy-fields textarea").fill("这里包含破解内容，行业第一。")
        page.locator(".video-publish-panel .compliance-box").get_by_text(
            "包含禁止发布内容，已拦截。"
        ).wait_for(state="visible", timeout=15000)
        check(
            not page.locator(".video-publish-panel .ad-ack input").is_checked(),
            "文章广告确认污染了视频广告确认",
        )
        page.locator(".video-publish-panel .ad-ack input").check()
        page.get_by_role("button", name="内容编辑台").click()
        check(
            page.locator(".editor-view .ad-ack input").is_checked(),
            "视频广告确认污染了文章广告确认",
        )
        page.get_by_label("文章正文").fill("文章预览与视频合规检查互不影响。")
        page.locator(".article-preview").get_by_text(
            "文章预览与视频合规检查互不影响。"
        ).wait_for(state="visible", timeout=15000)
        check(
            "破解" not in page.locator(".compliance-box").inner_text(),
            "视频合规结果污染了文章预览",
        )
        page.get_by_role("button", name="保存草稿", exact=True).click()
        page.get_by_text("草稿已安全保存到本机", exact=True).wait_for(state="visible")
        page.get_by_role("button", name="视频发布").click()
        page.locator(".video-publish-panel .compliance-box").get_by_text(
            "包含禁止发布内容，已拦截。"
        ).wait_for(state="visible", timeout=15000)
        page.locator('.video-upload-zone input[type="file"]').set_input_files(
            ARTIFACTS / "stage3-sample.mp4"
        )
        page.locator(".video-preview-block video").wait_for(
            state="visible", timeout=30000
        )
        check(
            "640 × 360" in page.locator(".video-filebar").inner_text(),
            "视频元数据未显示",
        )
        page.locator(".video-copy-fields .title-field input").fill("UI 视频自动化验收")
        page.locator(".video-copy-fields textarea").fill(
            "用于验证本地视频上传、抽帧、转码与定时投稿队列。"
        )
        page.locator(".video-copy-fields .tags-field input").fill("测试，视频工作流")
        page.get_by_role("button", name="抽帧并生成封面").click()
        page.locator(".video-cover-preview img").wait_for(
            state="visible", timeout=30000
        )
        page.get_by_role("button", name="转为发布兼容格式").click()
        page.get_by_text("已转为 H.264 / AAC MP4，并启用快速播放", exact=True).wait_for(
            state="visible", timeout=60000
        )
        page.get_by_role("button", name="保存草稿", exact=True).click()
        page.get_by_text("视频草稿已保存到本机", exact=True).wait_for(state="visible")
        page.locator(".video-copy-fields .title-field input").fill("未保存视频保护验收")
        page.once("dialog", lambda dialog: dialog.dismiss())
        page.get_by_role("button", name="新建视频", exact=True).click()
        check(
            page.locator(".video-copy-fields .title-field input").input_value()
            == "未保存视频保护验收",
            "取消新建视频后未保存内容丢失",
        )
        page.locator(".video-copy-fields .title-field input").fill("UI 视频自动化验收")
        page.locator("#video-account-select").select_option(label="UI B站验收账号")
        page.locator(".video-publish-panel .authorization input").check()
        page.get_by_role("button", name="内容编辑台", exact=True).click()
        check(
            not page.locator(".editor-view .authorization input").is_checked(),
            "视频授权污染了文章授权状态",
        )
        page.get_by_role("button", name="视频发布", exact=True).click()
        check(
            page.locator(".video-publish-panel .authorization input").is_checked(),
            "切换视图丢失了视频授权状态",
        )
        page.screenshot(path=ARTIFACTS / "desktop-video.png", full_page=True)
        page.locator("#video-scheduled-at").fill(
            (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
        )
        page.get_by_role("button", name="创建定时投稿任务").click()
        page.get_by_role("heading", name="确认创建定时任务？").wait_for(state="visible")
        check(
            "知识" in page.locator(".modal-summary").inner_text(),
            "视频分区未进入确认摘要",
        )
        with page.expect_response(
            lambda response: (
                response.request.method == "POST"
                and response.url.endswith("/api/publish")
            )
        ) as publish_response:
            page.get_by_role("button", name="确认创建任务", exact=True).click()
        check(
            publish_response.value.ok,
            f"视频定时任务创建失败：{publish_response.value.text()}",
        )
        page.get_by_text("已创建 B 站定时投稿任务", exact=True).wait_for(
            state="visible"
        )
        page.get_by_role("button", name="发布记录").click()
        page.locator(".task-item").filter(has_text="UI 视频自动化验收").wait_for(
            state="visible"
        )
        check(
            "视频"
            in page.locator(".task-item")
            .filter(has_text="UI 视频自动化验收")
            .first.inner_text(),
            "视频任务类型未显示",
        )

        for width in (901, 1000, 1100):
            page.set_viewport_size({"width": width, "height": 900})
            page.get_by_role("button", name="账号与授权").click()
            page.wait_for_timeout(350)
            overflow = page.evaluate(
                "document.documentElement.scrollWidth > document.documentElement.clientWidth"
            )
            check(not overflow, f"{width}px 账号页存在横向溢出")
            page.get_by_role("button", name="定时与队列").click()
            page.wait_for_timeout(350)
            overflow = page.evaluate(
                "document.documentElement.scrollWidth > document.documentElement.clientWidth"
            )
            check(not overflow, f"{width}px 调度页存在横向溢出")
        page.set_viewport_size({"width": 1000, "height": 900})
        page.screenshot(path=ARTIFACTS / "tablet-schedules.png", full_page=True)
        page.get_by_role("button", name="账号与授权").click()
        page.screenshot(path=ARTIFACTS / "tablet-accounts.png", full_page=True)

        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(BASE, wait_until="networkidle")
        check(
            page.locator(".sidebar").evaluate("element => element.inert"),
            "移动端关闭导航仍可被键盘聚焦",
        )
        page.get_by_role("button", name="打开导航").click()
        check(page.locator(".sidebar.is-open").is_visible(), "移动端导航未打开")
        check(
            not page.locator(".sidebar").evaluate("element => element.inert"),
            "移动端打开导航后仍被 inert 屏蔽",
        )
        page.get_by_role("button", name="内容编辑台").click()
        check(
            page.locator(".sidebar").evaluate("element => element.inert"),
            "移动端导航关闭后未恢复 inert",
        )
        page.locator(".article-preview h1").wait_for(state="visible")
        page.wait_for_timeout(350)
        overflow = page.evaluate(
            "document.documentElement.scrollWidth > document.documentElement.clientWidth"
        )
        check(not overflow, "移动端编辑台存在横向溢出")
        page.screenshot(path=ARTIFACTS / "mobile-editor.png", full_page=True)
        page.get_by_role("button", name="一稿多发", exact=True).click()
        page.get_by_role("heading", name="让一份原稿，有多种表达。").wait_for(
            state="visible"
        )
        overflow = page.evaluate(
            "document.documentElement.scrollWidth > document.documentElement.clientWidth"
        )
        check(not overflow, "移动端复用弹窗存在横向溢出")
        page.screenshot(path=ARTIFACTS / "mobile-reuse.png", full_page=True)
        page.locator(".reuse-modal").get_by_role(
            "button", name="取消", exact=True
        ).click()
        check(
            page.get_by_role("button", name="一稿多发", exact=True).evaluate(
                "element => element === document.activeElement"
            ),
            "复用弹窗关闭后未恢复触发按钮焦点",
        )

        page.get_by_role("button", name="打开导航").click()
        page.locator(".main-nav").get_by_role("button", name="素材库").click()
        page.locator(".asset-row").first.wait_for(state="visible")
        page.wait_for_timeout(350)
        overflow = page.evaluate(
            "document.documentElement.scrollWidth > document.documentElement.clientWidth"
        )
        check(not overflow, "移动端素材库存在横向溢出")
        page.screenshot(path=ARTIFACTS / "mobile-media.png", full_page=True)

        page.get_by_role("button", name="打开导航").click()
        page.locator(".main-nav").get_by_role("button", name="模板工坊").click()
        preview_frame = page.frame_locator(".te-preview-stage iframe")
        preview_frame.locator("h1").wait_for(state="visible", timeout=15000)
        page.locator(".te-preview-stage").scroll_into_view_if_needed()
        page.wait_for_timeout(350)
        overflow = page.evaluate(
            "document.documentElement.scrollWidth > document.documentElement.clientWidth"
        )
        check(not overflow, "移动端模板工坊存在横向溢出")
        page.screenshot(path=ARTIFACTS / "mobile-template-editor.png", full_page=True)

        page.get_by_role("button", name="打开导航").click()
        page.get_by_role("button", name="定时与队列").click()
        page.wait_for_timeout(350)
        overflow = page.evaluate(
            "document.documentElement.scrollWidth > document.documentElement.clientWidth"
        )
        check(not overflow, "移动端调度页存在横向溢出")
        page.screenshot(path=ARTIFACTS / "mobile-schedules.png", full_page=True)

        page.get_by_role("button", name="打开导航").click()
        page.locator(".main-nav").get_by_role("button", name="数据看板").click()
        page.locator(".kpi-grid").wait_for(state="visible")
        page.wait_for_timeout(350)
        overflow = page.evaluate(
            "document.documentElement.scrollWidth > document.documentElement.clientWidth"
        )
        check(not overflow, "移动端数据看板存在横向溢出")
        page.screenshot(path=ARTIFACTS / "mobile-dashboard.png", full_page=True)
        page.get_by_role("button", name="录入指标", exact=True).click()
        page.locator(".metric-form-panel").wait_for(state="visible")
        overflow = page.evaluate(
            "document.documentElement.scrollWidth > document.documentElement.clientWidth"
        )
        check(not overflow, "移动端指标录入存在横向溢出")
        page.screenshot(path=ARTIFACTS / "mobile-metric-form.png", full_page=True)
        page.get_by_role("button", name="关闭指标录入").click()

        page.get_by_role("button", name="打开导航").click()
        page.locator(".main-nav").get_by_role("button", name="发布记录").click()
        page.locator(".audit-trail").wait_for(state="visible")
        page.wait_for_timeout(350)
        overflow = page.evaluate(
            "document.documentElement.scrollWidth > document.documentElement.clientWidth"
        )
        check(not overflow, "移动端审计日志存在横向溢出")
        page.screenshot(path=ARTIFACTS / "mobile-audit.png", full_page=True)

        page.get_by_role("button", name="打开导航").click()
        page.get_by_role("button", name="视频发布").click()
        page.locator(".video-preview-block video").wait_for(state="visible")
        page.wait_for_timeout(350)
        overflow = page.evaluate(
            "document.documentElement.scrollWidth > document.documentElement.clientWidth"
        )
        check(not overflow, "移动端视频页存在横向溢出")
        page.screenshot(path=ARTIFACTS / "mobile-video.png", full_page=True)

        page.route(
            "**/api/health",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "status": "ok",
                        "version": "0.5.0",
                        "mode": "local",
                        "publishing_enabled": False,
                    }
                ),
            ),
        )
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.goto(BASE, wait_until="networkidle")
        check(page.locator(".publishing-disabled").is_visible(), "禁用发布状态未显示")
        check(
            page.locator(".editor-view .publish-button").is_disabled(),
            "禁用发布后文章投稿按钮仍可点击",
        )
        page.get_by_role("button", name="视频发布", exact=True).click()
        check(
            page.locator(".video-view .publish-button").is_disabled(),
            "禁用发布后视频投稿按钮仍可点击",
        )
        page.get_by_role("button", name="定时与队列", exact=True).click()
        check(
            page.get_by_role("button", name="新建调度计划", exact=True).is_disabled(),
            "禁用发布后新建计划按钮仍可点击",
        )
        page.unroute("**/api/health")

        check(not errors, f"浏览器控制台错误：{errors}")
        browser.close()
finally:
    cleanup_test_data()

print(
    json.dumps(
        {
            "status": "passed",
            "screenshots": [
                str(ARTIFACTS / "desktop-editor.png"),
                str(ARTIFACTS / "desktop-media.png"),
                str(ARTIFACTS / "desktop-template-editor.png"),
                str(ARTIFACTS / "desktop-schedule-form.png"),
                str(ARTIFACTS / "desktop-schedules.png"),
                str(ARTIFACTS / "desktop-dashboard.png"),
                str(ARTIFACTS / "desktop-metric-form.png"),
                str(ARTIFACTS / "desktop-dashboard-filled.png"),
                str(ARTIFACTS / "desktop-audit.png"),
                str(ARTIFACTS / "tablet-accounts.png"),
                str(ARTIFACTS / "tablet-schedules.png"),
                str(ARTIFACTS / "mobile-dashboard.png"),
                str(ARTIFACTS / "mobile-metric-form.png"),
                str(ARTIFACTS / "mobile-audit.png"),
                str(ARTIFACTS / "mobile-editor.png"),
                str(ARTIFACTS / "mobile-reuse.png"),
                str(ARTIFACTS / "mobile-media.png"),
                str(ARTIFACTS / "mobile-template-editor.png"),
                str(ARTIFACTS / "mobile-schedules.png"),
                str(ARTIFACTS / "desktop-video.png"),
                str(ARTIFACTS / "mobile-video.png"),
            ],
        },
        ensure_ascii=False,
    )
)
