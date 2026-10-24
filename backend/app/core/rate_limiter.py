"""滑动窗口限流。

算法：Redis Sorted Set + Lua 脚本（判定与写入同一次往返、原子）
- 每个 key 一份用户的请求时间戳集合（score=now，member=uuid 保证不重复）
- 脚本内先 zremrangebyscore 清掉过期时间戳
- zcard 拿到当前窗口内请求数
- 只有 count < limit 才 zadd + expire —— **被拒的请求不落窗口**
- expire 给 key 续 window 秒 TTL，避免冷用户的 key 永驻 Redis

为什么必须用 Lua：早期实现把 zremrangebyscore / zcard / zadd / expire 四条命令
塞进同一个 pipeline（transaction=True），pipeline 保证"一次往返、顺序执行"，
但**不保证"判不过就不写"** —— zadd 在拿到 count 之前已经排进队列。后果是
被拒的请求给自己续了 60 秒：客户端越重试，窗口越满，稳态 60/重试间隔 ≥ 配额
时**永久锁死**（配额 3、每 5 s 重试 ⇒ 稳态 12 ⟹ 120 秒一次不放行，实测
流水 `2026-10-23-020-G`）。Lua 脚本在服务端"读—判—写"一气呵成，才有
"判不过就不留痕"这个语义。

不引入 slowapi / fastapi-limiter 等装饰器库：滑动窗口逻辑在模块内自包含，
基于 redis-py 实现，便于阅读与调试。
"""

import time
from functools import lru_cache
from uuid import uuid4

from app.core.config import settings
from app.core.exceptions import RateLimitedError
from app.core.logging import get_logger
from app.core.redis import get_redis

logger = get_logger(__name__)

# 限流窗口固定 60 秒，配合 RATE_LIMIT_PER_MINUTE 形成"每分钟 N 次"语义
_WINDOW_SECONDS = 60

# KEYS[1] 限流键；ARGV[1] now / ARGV[2] window / ARGV[3] limit / ARGV[4] member
# 返回：本次判定时窗口内的条数（< limit 表示放行且已写入）
_SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])

redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)

-- 超限就直接返回，不 zadd：被拒的请求不能占用窗口配额
if count >= limit then
    return count
end

redis.call('ZADD', key, now, ARGV[4])
redis.call('EXPIRE', key, window)
return count
"""


class RateLimiter:
    """滑动窗口限流器（每 identity 维度独立）。"""

    def __init__(self) -> None:
        self._redis = get_redis()
        # register_script 只在首次调用时 SCRIPT LOAD，之后走 EVALSHA
        self._script = self._redis.register_script(_SLIDING_WINDOW_LUA)

    async def check(self, identity: str) -> None:
        """命中阈值时抛 RateLimitedError；未命中静默返回。"""
        now = time.time()
        key = f"rag:rate_limit:{identity}"
        limit = settings.rate_limit_per_minute

        count = await self._script(
            keys=[key],
            args=[now, _WINDOW_SECONDS, limit, str(uuid4())],
        )

        if int(count) >= limit:
            logger.warning(
                "rate limit exceeded: identity=%s count=%s limit=%s",
                identity,
                count,
                limit,
            )
            raise RateLimitedError(
                f"请求过于频繁，每分钟最多 {limit} 次，请稍后再试"
            )


@lru_cache(maxsize=1)
def get_rate_limiter() -> RateLimiter:
    return RateLimiter()
