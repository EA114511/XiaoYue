"""
性能优化工具模块

提供通用优化基础设施：
  1. CircuitBreaker — 熔断器（防止级联故障）
  2. RetryStrategy — 指数退避重试
  3. run_concurrently — 并发任务执行
"""

import asyncio
import logging
import time
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple, TypeVar

import httpx

logger = logging.getLogger("voice-assistant.optimization")


# ============================================================
# 熔断器
# ============================================================

class CircuitState(Enum):
    CLOSED = "closed"           # 正常，请求通过
    OPEN = "open"              # 熔断，请求直接失败
    HALF_OPEN = "half_open"    # 半开，允许部分请求试探


class CircuitBreaker:
    """
    熔断器 — 防止级联故障

    状态流转:
      CLOSED ──(失败次数超阈值)──→ OPEN
      OPEN ──(超时等待)──→ HALF_OPEN
      HALF_OPEN ──(成功)──→ CLOSED
      HALF_OPEN ──(失败)──→ OPEN

    用法:
        breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=30)
        async with breaker:
            result = await risky_operation()
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_requests: int = 1,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_requests = half_open_max_requests

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.half_open_requests = 0
        self._lock = asyncio.Lock()

    async def __aenter__(self):
        await self._check()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            await self._record_failure()
        else:
            await self._record_success()
        return False  # 不抑制异常

    async def _check(self):
        """检查是否允许请求通过"""
        async with self._lock:
            if self.state == CircuitState.OPEN:
                if time.time() - self.last_failure_time >= self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_requests = 0
                    logger.info(f"[熔断器] OPEN → HALF_OPEN，允许试探请求")
                else:
                    raise CircuitBreakerOpenError(
                        f"熔断器开启，拒绝请求（{self.recovery_timeout - (time.time() - self.last_failure_time):.0f}s后重试）"
                    )

            if self.state == CircuitState.HALF_OPEN:
                if self.half_open_requests >= self.half_open_max_requests:
                    raise CircuitBreakerOpenError("熔断器半开，请求数已达上限")

    async def _record_success(self):
        async with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                logger.info(f"[熔断器] HALF_OPEN → CLOSED，服务恢复")
            elif self.state == CircuitState.CLOSED:
                self.failure_count = max(0, self.failure_count - 1)  # 缓慢衰减

    async def _record_failure(self):
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                self.half_open_requests = 0
                logger.warning(f"[熔断器] HALF_OPEN → OPEN，试探请求失败")
            elif self.state == CircuitState.CLOSED and self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                logger.warning(
                    f"[熔断器] CLOSED → OPEN，连续{self.failure_count}次失败"
                )


class CircuitBreakerOpenError(Exception):
    """熔断器开启异常"""
    pass


# ============================================================
# 指数退避重试
# ============================================================

T = TypeVar("T")


class RetryStrategy:
    """
    重试策略

    用法:
        strategy = RetryStrategy(max_retries=3, base_delay=1.0)
        result = await strategy.execute(call_api, arg1, arg2)
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        jitter: bool = True,
        retryable_exceptions: Optional[Tuple] = None,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter
        self.retryable_exceptions = retryable_exceptions or (
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.RemoteProtocolError,
            ConnectionError,
            TimeoutError,
        )

    async def execute(
        self,
        func: Callable[..., Awaitable[T]],
        *args,
        **kwargs,
    ) -> T:
        """执行函数并自动重试"""
        last_error = None

        for attempt in range(1, self.max_retries + 2):  # 第1次 + max_retries 次重试
            try:
                return await func(*args, **kwargs)
            except self.retryable_exceptions as e:
                last_error = e
                if attempt > self.max_retries:
                    break
                delay = self._get_delay(attempt)
                logger.warning(
                    f"[重试] 第{attempt}次失败（{type(e).__name__}），"
                    f"{delay:.1f}s后重试第{attempt + 1}次"
                )
                await asyncio.sleep(delay)
            except Exception:
                # 非可重试异常，直接抛出
                raise

        raise last_error  # type: ignore

    def _get_delay(self, attempt: int) -> float:
        """计算退避延迟"""
        import random
        delay = min(self.base_delay * (2 ** (attempt - 1)), self.max_delay)
        if self.jitter:
            delay = delay * (0.5 + random.random() * 0.5)  # ±50% jitter
        return delay


# ============================================================
# 并发任务执行
# ============================================================

async def run_concurrently(
    tasks: Dict[str, Callable[[], Awaitable[Any]]],
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """
    并发执行多个异步任务

    用法:
        results = await run_concurrently({
            "asr": lambda: asr_service.recognize_file(audio),
            "nlu": lambda: nlu_service.parse(text),
        })
        asr_result = results["asr"]
        nlu_result = results["nlu"]
    """
    async def run_task(name: str, coro_fn: Callable) -> Tuple[str, Any]:
        try:
            result = await asyncio.wait_for(coro_fn(), timeout=timeout)
            return name, result
        except Exception as e:
            logger.error(f"[并发] {name} 异常: {e}")
            return name, e

    coros = [run_task(name, fn) for name, fn in tasks.items()]
    completed = await asyncio.gather(*coros)

    results = {}
    for name, result in completed:
        results[name] = result

    return results
