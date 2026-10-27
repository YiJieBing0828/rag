"""语义缓存探针：不开服务、不提问，直接看 Redis 里到底有没有缓存条目。

用法（在 backend 目录下）：
    .\\.venv\\Scripts\\python.exe dev\\semantic_cache_probe.py

它回答三个问题：
  1. 缓存开关是不是真开着（读的是 settings，不是 .env 原文）
  2. Redis 里那个索引建了没有、里面现在有几条
  3. 最新几条缓存的问题原文是什么（判断"我要问的那句在不在里面"）

为什么需要它：命中缓存要同时满足「开关开 / 有条目 / 相似度 ≥ 阈值」，
只看日志「没有 cache hit」分不清是哪一条不满足，会白试好几轮。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import redis  # noqa: E402

from app.core.config import settings  # noqa: E402

INDEX = "rag_semantic_cache"


def main() -> int:
    print("=" * 68)
    print(f"semantic_cache_enabled     = {settings.semantic_cache_enabled}")
    print(f"semantic_cache_ttl_seconds = {settings.semantic_cache_ttl_seconds}")
    print(f"semantic_cache_min_similar = {settings.semantic_cache_min_similarity}")
    print(f"redis_url                  = {settings.redis_url}")
    print("=" * 68)

    r = redis.from_url(settings.redis_url, decode_responses=True)

    try:
        r.execute_command("FT.INFO", INDEX)
    except Exception as exc:  # noqa: BLE001
        print(f"✗ 索引 {INDEX} 不存在或不可用：{exc}")
        print("  ⇒ 缓存从没被写入过，问多少次都不会命中。")
        return 1

    total = r.execute_command("FT.SEARCH", INDEX, "*", "LIMIT", 0, 0)[0]
    print(f"索引 {INDEX} 存在，当前条目数：{total}")

    if total == 0:
        print("⇒ 条目为 0：说明写回没发生过（答案被拒答 / 校验没过 / 当时开关是关的）。")
        return 1

    # 看最新的几条：确认"我要问的那句"在不在里面
    rows = r.execute_command(
        "FT.SEARCH", INDEX, "*", "RETURN", "1", "prompt", "LIMIT", 0, 10
    )
    print("\n最近 10 条缓存的问题原文：")
    for i in range(1, len(rows), 2):
        fields = rows[i + 1]
        # fields 形如 ['prompt', '...', ...]
        prompt = ""
        for j in range(0, len(fields) - 1, 2):
            if fields[j] == "prompt":
                prompt = fields[j + 1]
                break
        print(f"  - {prompt!r}")

    print("\n⇒ 你要问的那句如果不在上面，就先问一次（冷路径会写回），再问第二次。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
