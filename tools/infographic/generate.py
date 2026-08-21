#!/usr/bin/env python3
"""gpt-image-2 で 16:9 インフォグラフィックを生成する最小 CLI。"""
import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

API = "https://api.openai.com/v1/images/generations"
# 単価は OpenAI の画像モデル料金表（gpt-image-2）に基づく。
# 画像入力は本 CLI では発生しない（テキストプロンプトのみ）ため計上しない。
PRICE_OUT_PER_TOKEN = 30.0 / 1_000_000
PRICE_TXT_IN_PER_TOKEN = 5.0 / 1_000_000


def estimate_cost(usage: dict) -> float:
    """usage から概算コストを出す。input_tokens の内訳が返る場合はテキスト分だけ数える。"""
    details = usage.get("input_tokens_details") or {}
    text_in = details.get("text_tokens", usage.get("input_tokens", 0))
    return usage.get("output_tokens", 0) * PRICE_OUT_PER_TOKEN + text_in * PRICE_TXT_IN_PER_TOKEN


def generate(prompt: str, out_path: str, size: str, quality: str, api_key: str,
             timeout: int = 900) -> dict:
    body = json.dumps({
        "model": "gpt-image-2",
        "prompt": prompt,
        "size": size,
        "quality": quality,
        "n": 1,
    }).encode("utf-8")
    req = urllib.request.Request(
        API, data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    started = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as res:
        payload = json.load(res)
    elapsed = time.time() - started
    with open(out_path, "wb") as fh:
        fh.write(base64.b64decode(payload["data"][0]["b64_json"]))
    usage = payload.get("usage", {})
    return {"path": out_path, "elapsed_sec": round(elapsed, 1),
            "output_tokens": usage.get("output_tokens"),
            "cost_usd": round(estimate_cost(usage), 4)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--prompt-file", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--size", default="1536x864",
                    help="幅・高さとも 16 の倍数であること（16:9 なら 1536x864 / 1792x1008 / 2048x1152）")
    ap.add_argument("--quality", default="medium", choices=["low", "medium", "high"])
    ap.add_argument("--timeout", type=int, default=900,
                    help="1 枚あたりの応答待ち上限（秒）。既定 900")
    args = ap.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("環境変数 OPENAI_API_KEY が設定されていない", file=sys.stderr)
        return 1

    try:
        with open(args.prompt_file, encoding="utf-8") as fh:
            prompt = fh.read()
        print(json.dumps(
            generate(prompt, args.out, args.size, args.quality, api_key, args.timeout),
            ensure_ascii=False))
    except urllib.error.HTTPError as exc:
        print(f"HTTPError {exc.code}: {exc.read().decode('utf-8')[:500]}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"接続に失敗した: {exc.reason}", file=sys.stderr)
        return 1
    except TimeoutError:
        print(f"応答が {args.timeout} 秒以内に返らなかった", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"API のレスポンスが JSON として読めない: {exc}", file=sys.stderr)
        return 1
    except (KeyError, IndexError) as exc:
        print(f"API のレスポンスに想定したキーがない: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"ファイル入出力に失敗した: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
