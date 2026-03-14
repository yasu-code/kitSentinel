"""ローカル実行用エントリポイント。"""
import json
import sys
from dotenv import load_dotenv

load_dotenv()

import lambda_function  # noqa: E402 (must load .env before importing)


def main() -> None:
    # コマンドライン引数で基準日を指定可能（例: python run_local.py 2026-03-17）
    event: dict = {}
    if len(sys.argv) > 1:
        event["date"] = sys.argv[1]

    result = lambda_function.handler(event, None)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
