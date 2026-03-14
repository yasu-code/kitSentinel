import json
import logging
import os
import traceback
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import boto3
import requests
from playwright.sync_api import sync_playwright

logger = logging.getLogger()
logger.setLevel(logging.INFO)

JST = ZoneInfo("Asia/Tokyo")

def get_secrets() -> dict:

    secrets_name = os.environ["SECRETS_NAME"]
    region_name = "ap-northeast-1"

    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    response = client.get_secret_value(
        SecretId=secrets_name
    )
    return json.loads(response["SecretString"])


def get_target_week(event: dict) -> tuple[list[datetime], list[str]]:
    """日付リストを返す。
    - date指定あり: 指定日が含まれる週（月〜日）
    - date指定なし: 今日を基準とした再来週（月〜日）
    """
    if event and "date" in event:
        base_date = datetime.strptime(event["date"], "%Y-%m-%d").replace(tzinfo=JST)
        monday = base_date - timedelta(days=base_date.weekday())
    else:
        base_date = datetime.now(JST)
        days_until_monday = 14 - base_date.weekday()
        monday = base_date + timedelta(days=days_until_monday)

    dates = [monday + timedelta(days=i) for i in range(7)]
    day_numbers = [d.strftime("%-d") for d in dates]

    print("test2", day_numbers)
    return dates, day_numbers


def send_line_message(token: str, user_id: str, message: str) -> None:
    resp = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        json={
            "to": user_id,
            "messages": [{"type": "text", "text": message}],
        },
        timeout=10,
    )
    resp.raise_for_status()
    logger.info("LINE通知送信完了: %s", resp.status_code)


def send_line_alert(token: str, user_id: str, dates: list[datetime], site_url: str) -> None:
    start = dates[0].strftime("%m/%d")
    end = dates[-1].strftime("%m/%d")
    message = (
        f"【警告】ミールキット未予約\n"
        f"再来週（{start}〜{end}）の予約が1件もありません。\n"
        f"至急確認してください。\n"
        f"{site_url}"
    )
    send_line_message(token, user_id, message)


def send_line_error_alert(token: str, user_id: str, reason: str, site_url: str) -> None:
    message = (
        f"【エラー】kitSentinel処理失敗\n"
        f"{reason}\n"
        f"ログを確認してください。\n"
        f"{site_url}"
    )
    try:
        send_line_message(token, user_id, message)
    except Exception:
        logger.error("エラー通知のLINE送信失敗\n%s", traceback.format_exc())


def check_reservations(page, day_numbers: list[str]) -> list[str]:
    """カレンダーDOMを解析し、予約済みの日（数字文字列）リストを返す。"""
    reserved_days = []
    day_elements = page.query_selector_all(".day")

    if not day_elements:
        raise RuntimeError("カレンダー要素 (.day) が見つかりません")

    for el in day_elements:
        # 日付数字を取得
        day_text_el = el.query_selector(".day-num, .date, span")
        if day_text_el is None:
            day_text_el = el
        day_text = (day_text_el.inner_text() or "").strip()
        # "3/16" のような月/日形式の場合、日部分のみを抽出
        if "/" in day_text:
            day_text = day_text.split("/")[-1].lstrip("0") or day_text.split("/")[-1]

        if day_text not in day_numbers:
            continue

        has_cart = (
            el.query_selector(".cart") is not None
            or el.query_selector("img[src*='ico-deliver_truck']") is not None
        )
        if has_cart:
            reserved_days.append(day_text)

    return reserved_days


def navigate_to_month(page, target_month: int, target_year: int) -> None:
    """必要に応じて翌月ボタンをクリックして対象月へ遷移する。"""
    for _ in range(2):  # 最大2ヶ月先まで
        current_text = page.inner_text(".calendar-header, .month-header, h2") or ""
        # 月が一致していれば終了（簡易判定）
        if str(target_month) in current_text:
            return
        next_btn = page.query_selector(".next-month, .btn-next, [aria-label='次の月']")
        if next_btn:
            next_btn.click()
            page.wait_for_load_state("load")


def handler(event: dict, context) -> dict:
    logger.info("実行開始 event=%s", event)

    site_url = os.environ.get("SITE_URL", "")

    try:
        secrets = get_secrets()
    except Exception:
        logger.error("Secrets取得失敗\n%s", traceback.format_exc())
        return {"status": "ERROR", "reason": "secrets_fetch_failed"}

    site_login_id = secrets["SITE_LOGIN_ID"]
    site_login_pw = secrets["SITE_LOGIN_PW"]
    line_token = secrets["LINE_CHANNEL_ACCESS_TOKEN"]
    line_user_id = secrets["LINE_USER_ID"]

    try:
        dates, day_numbers = get_target_week(event)
    except Exception:
        logger.error("日付計算失敗\n%s", traceback.format_exc())
        send_line_error_alert(line_token, line_user_id, "日付計算に失敗しました。", site_url)
        return {"status": "ERROR", "reason": "date_calc_failed"}

    logger.info(
        "監視対象週: %s〜%s  day_numbers=%s",
        dates[0].strftime("%Y-%m-%d"),
        dates[-1].strftime("%Y-%m-%d"),
        day_numbers,
    )

    reserved_days: list[str] = []
    screenshot_path = "/tmp/calendar.png"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--single-process",
                    "--no-zygote",
                ],
            )
            page = browser.new_page()
            page.set_default_timeout(30_000)

            # ログイン
            page.goto(site_url)
            page.wait_for_load_state("load")

            # ログインID / メールアドレス
            page.fill("#txtWeb_Login_Id", site_login_id)
            # パスワード
            page.fill("#pwdPassword", site_login_pw)
            # ログインボタン
            page.click("button.btnLogin")

            page.wait_for_load_state("load")
            page.wait_for_timeout(5_000)

            # ログイン失敗チェック
            if "ログアウト" not in page.content() and "logout" not in page.url:
                logger.warning("ログイン後のページにログアウトリンクが見つかりません（要確認）")

            logger.info("step1")

            # 月跨ぎ対応
            target_year = dates[0].year
            target_month = dates[0].month
            navigate_to_month(page, target_month, target_year)

            logger.info("step2")
            # 月末〜月初を跨ぐ場合、翌月分も確認
            if dates[-1].month != target_month:
                reserved_days += check_reservations(page, day_numbers[:dates[-1].day])
                next_btn = page.query_selector(".next-month, .btn-next, [aria-label='次の月']")
                if next_btn:
                    next_btn.click()
                    page.wait_for_load_state("load")
                remaining = [d for d in day_numbers if d not in reserved_days]
                reserved_days += check_reservations(page, remaining)
            else:
                reserved_days = check_reservations(page, day_numbers)

            browser.close()

    except Exception:
        logger.error("ブラウザ操作中にエラー\n%s", traceback.format_exc())
        # スクリーンショット試行（best effort）
        try:
            page.screenshot(path=screenshot_path)
            logger.info("スクリーンショット保存: %s", screenshot_path)
        except Exception:
            pass
        send_line_error_alert(line_token, line_user_id, "ブラウザ操作中にエラーが発生しました。", site_url)
        return {"status": "ERROR", "reason": "browser_error"}

    if reserved_days:
        logger.info("SAFE: 予約あり %s", reserved_days)
        return {"status": "SAFE", "reserved_days": reserved_days}

    # ALERT: 対象週の予約が1件もない
    logger.warning(
        "ALERT: %s〜%s の予約が0件",
        dates[0].strftime("%Y-%m-%d"),
        dates[-1].strftime("%Y-%m-%d"),
    )
    try:
        send_line_alert(line_token, line_user_id, dates, site_url)
    except Exception:
        logger.error("LINE通知失敗\n%s", traceback.format_exc())
        return {"status": "ALERT", "line_notify": "failed"}

    return {"status": "ALERT", "line_notify": "sent"}
