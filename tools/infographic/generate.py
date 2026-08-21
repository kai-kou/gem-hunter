#!/usr/bin/env python3
"""gpt-image-2 で 16:9 インフォグラフィックを生成する最小 CLI。"""
import argparse, base64, json, os, sys, time, urllib.request

API = "https://api.openai.com/v1/images/generations"
PRICE_OUT_PER_TOKEN = 30.0 / 1_000_000
PRICE_TXT_IN_PER_TOKEN = 5.0 / 1_000_000


def generate(prompt: str, out_path: str, size: str, quality: str, timeout: int = 900) -> dict:
    body = json.dumps({
        "model": "gpt-image-2",
        "prompt": prompt,
        "size": size,
        "quality": quality,
        "n": 1,
    }).encode("utf-8")
    req = urllib.request.Request(
        API, data=body,
        headers={
            "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
            "Content-Type": "application/json",
        },
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as res:
        payload = json.load(res)
    elapsed = time.time() - t0
    with open(out_path, "wb") as fh:
        fh.write(base64.b64decode(payload["data"][0]["b64_json"]))
    usage = payload.get("usage", {})
    cost = (usage.get("output_tokens", 0) * PRICE_OUT_PER_TOKEN
            + usage.get("input_tokens", 0) * PRICE_TXT_IN_PER_TOKEN)
    return {"path": out_path, "elapsed_sec": round(elapsed, 1),
            "output_tokens": usage.get("output_tokens"), "cost_usd": round(cost, 4)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt-file", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--size", default="1536x864")
    ap.add_argument("--quality", default="medium", choices=["low", "medium", "high"])
    args = ap.parse_args()
    with open(args.prompt_file, encoding="utf-8") as fh:
        prompt = fh.read()
    try:
        print(json.dumps(generate(prompt, args.out, args.size, args.quality), ensure_ascii=False))
    except urllib.error.HTTPError as exc:
        print(f"HTTPError {exc.code}: {exc.read().decode('utf-8')[:500]}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
