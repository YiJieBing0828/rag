"""引用编号一致性检查 —— 本地探针（不依赖服务、不依赖 DB、不依赖 LLM）。

用法（在 backend 目录下）：
    .\\.venv\\Scripts\\python.exe dev\\citation_check_probe.py

它做三件事：
  1. 造 3 个假 chunk：片段 1 含「78 分钟」，片段 2、3 不含；
  2. 喂一段真实的 answer 形态：结论「78 分钟」标的是 [2]（依据其实在片段 1）；
  3. 断言你的检查函数能指出「编号 2 与片段 2 的内容不符」。

⚠ 这个探针不测你的正则写得好不好，只测「这条链走不走得通」你能不能自己看出来。
   它现在跑不通是正常的 —— 因为 app/llm/citation_checker.py 还没建。
"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

# 直接 `python dev\xxx.py` 时 sys.path[0] 是 dev\ 而不是 backend\，
# 把 backend 目录顶进去，才能 import 到 app 包
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.retrieval.vector_retriever import RetrievedChunk  # noqa: E402

# ↓↓↓ 这里就是你要补的模块。函数名/签名按契约来，实现你自己写。
from app.llm.citation_checker import check_citation_alignment

# 真实形态：第一句的结论来自片段 1，模型却标了 [2]；第二句的引用是对的。
ANSWER = """从 20% 充到 80% 约需 78 分钟；充满后自动进入浮充 [2]。
Aster-7 的固件更新只在停机状态下进行，升级期间不要断电 [1]。"""


def _chunk(content: str, name: str, score: float, page: int) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_name=name,
        content=content,
        page_no=page,
        section_path=None,
        score=score,
    )


CHUNKS = [
    # 片段 1：真有「78 分钟」，也真有「Aster-7」
    _chunk(
        "……Aster-7 电池从 20% 充到 80% 约需 78 分钟，剩余 20% 为浮充区间，避免长期满电存放……",
        "Aster-7 运维手册",
        0.71,
        3,
    ),
    # 片段 2：没有 78 分钟（这就是被错标的那一段）
    _chunk(
        "……固件更新只在停机状态下进行，升级期间不要断电，完成后重新上电自检……",
        "Aster-7 运维手册",
        0.65,
        7,
    ),
    # 片段 3：干扰项
    _chunk(
        "……首次开机与联网：长按电源键 3 秒，指示灯蓝色闪烁后松开……",
        "Aster-7 快速上手指南",
        0.52,
        1,
    ),
]


def _get(issue, key):
    """兼容你返回 dataclass 还是 dict：两种写法都认。"""
    if isinstance(issue, dict):
        return issue.get(key)
    return getattr(issue, key, None)


def main() -> int:
    issues = check_citation_alignment(ANSWER, CHUNKS)
    issues = list(issues or [])

    print("=" * 64)
    print(f"answer 共 {len(ANSWER)} 字，chunks 共 {len(CHUNKS)} 段")
    print(f"检查结果：{len(issues)} 条 issue")
    for i, it in enumerate(issues, 1):
        print(f"  [{i}] ordinal={_get(it, 'ordinal')}  "
              f"tokens={_get(it, 'tokens')}  missing={_get(it, 'missing')}")
    print("=" * 64)

    failures: list[str] = []

    # 断言 1：必须抓到「编号 2 有问题」这一条
    hit = [it for it in issues if _get(it, "ordinal") == 2]
    if not hit:
        failures.append(
            "断言1 失败：没有 ordinal==2 的 issue。"
            "说明 [2] 那一句没有被解析到，或者片段 2 被误判为「对得上」。"
        )

    # 断言 2：那条 issue 的 missing 里必须含 78（这是「依据不在这段」的硬证据）
    if hit:
        missing = _get(hit[0], "missing") or ()
        missing_str = " ".join(str(x) for x in missing)
        if "78" not in missing_str:
            failures.append(
                f"断言2 失败：ordinal==2 的 missing 里没有 78（实际={missing_str!r}）。"
                "说明硬 token 没抽到「78 分钟」这种数字+单位形态。"
            )

    # 断言 3（反向）：编号 1 的那句是真的，不该被误报
    wrong = [it for it in issues if _get(it, "ordinal") == 1]
    if wrong:
        failures.append(
            "断言3 失败：ordinal==1 被误报（那句的「固件更新…不要断电」确实在片段 1 里）。"
            "说明抽取或匹配过宽，会变成噪音。"
        )

    if failures:
        print()
        for f in failures:
            print("✗ " + f)
        print()
        print("→ 探针未通过。先看第一条失败，改一处，再跑一次。")
        return 1

    print("✓ 三条断言全过：编号错位被抓到、依据缺失被看到、正确引用没被误伤。")
    print("→ 下一步：起前端跑一次端到端，确认日志里有 warning 且回答没变。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
