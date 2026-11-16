"""用自编流水复现两期成功退款金额的对账与口径差异。"""

import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory


# 时间统一为东八区的 ISO 8601 文本，字典序与时间顺序一致。
WINDOWS = {
    "previous": ("2026-09-01T00:00:00+08:00", "2026-09-08T00:00:00+08:00"),
    "current": ("2026-10-01T00:00:00+08:00", "2026-10-08T00:00:00+08:00"),
}
COLUMNS = ("refund_id", "channel", "status", "amount_cents", "applied_at", "succeeded_at")
REFUNDS = (
    ("r01", "自然流量", "succeeded", 12000, "2026-09-01T09:00:00+08:00", "2026-09-01T10:00:00+08:00"),
    ("r02", "广告", "succeeded", 8000, "2026-09-04T09:00:00+08:00", "2026-09-04T10:00:00+08:00"),
    ("r03", "合作渠道", "succeeded", 5000, "2026-09-06T10:00:00+08:00", "2026-09-06T11:00:00+08:00"),
    ("r04", "自然流量", "succeeded", 7000, "2026-09-30T22:00:00+08:00", "2026-10-01T00:00:00+08:00"),
    ("r05", "自然流量", "succeeded", 9000, "2026-10-03T08:00:00+08:00", "2026-10-03T09:00:00+08:00"),
    ("r06", "广告", "succeeded", 6000, "2026-10-05T14:00:00+08:00", "2026-10-05T15:00:00+08:00"),
    ("r07", "合作渠道", "succeeded", 8000, "2026-10-06T10:00:00+08:00", "2026-10-06T11:00:00+08:00"),
    ("r08", "自然流量", "succeeded", 4000, "2026-10-07T19:00:00+08:00", "2026-10-08T00:00:00+08:00"),
    ("r09", "广告", "failed", 15000, "2026-10-02T16:00:00+08:00", None),
)

# 时间字段只由脚本中两个固定口径决定。时间窗与状态均绑定为参数。
SUCCESS_WINDOW = "status = ? AND succeeded_at >= ? AND succeeded_at < ?"
APPLICATION_WINDOW = "status = ? AND applied_at >= ? AND applied_at < ?"


def initialize(path):
    with closing(sqlite3.connect(path)) as db:
        db.execute("""
            CREATE TABLE refunds (
                refund_id TEXT PRIMARY KEY,
                channel TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('succeeded', 'failed')),
                amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
                applied_at TEXT NOT NULL,
                succeeded_at TEXT,
                CHECK ((status = 'succeeded') = (succeeded_at IS NOT NULL))
            )
        """)
        db.executemany("INSERT INTO refunds VALUES (?, ?, ?, ?, ?, ?)", REFUNDS)
        db.commit()


def summarize(db, window, *, use_application_time=False):
    start, end = window
    where = APPLICATION_WINDOW if use_application_time else SUCCESS_WINDOW
    parameters = ("succeeded", start, end)
    # 总额直接对明细聚合。两个查询共享口径，但总额不依赖渠道汇总结果。
    count, total = db.execute(
        f"SELECT COUNT(*), COALESCE(SUM(amount_cents), 0) FROM refunds WHERE {where}",
        parameters,
    ).fetchone()
    channels = [
        {"channel": channel, "count": channel_count, "amount_cents": amount}
        for channel, channel_count, amount in db.execute(
            f"""
            SELECT channel, COUNT(*), SUM(amount_cents) FROM refunds
            WHERE {where} GROUP BY channel ORDER BY channel
            """,
            parameters,
        )
    ]
    matching_ids = [
        row[0] for row in db.execute(
            f"SELECT refund_id FROM refunds WHERE {where} ORDER BY refund_id", parameters
        )
    ]
    assert sum(row["amount_cents"] for row in channels) == total
    assert sum(row["count"] for row in channels) == count == len(matching_ids)
    return {
        "start_inclusive": start,
        "end_exclusive": end,
        "amount_cents": total,
        "count": count,
        "matching_refund_ids": matching_ids,
        "channels": channels,
    }


def compare_channels(previous, current):
    before = {row["channel"]: row["amount_cents"] for row in previous["channels"]}
    after = {row["channel"]: row["amount_cents"] for row in current["channels"]}
    return [
        {
            "channel": channel,
            "previous_cents": before.get(channel, 0),
            "current_cents": after.get(channel, 0),
            "change_cents": after.get(channel, 0) - before.get(channel, 0),
        }
        for channel in sorted(before.keys() | after.keys())
    ]


def verify_read_only(db):
    # 只验证当前连接对这条 UPDATE 的实际行为。
    before = db.execute("SELECT amount_cents FROM refunds WHERE refund_id = ?", ("r01",)).fetchone()
    try:
        db.execute("UPDATE refunds SET amount_cents = ? WHERE refund_id = ?", (1, "r01"))
    except sqlite3.OperationalError as error:
        if error.sqlite_errorcode != sqlite3.SQLITE_READONLY:
            raise
        assert db.execute("SELECT amount_cents FROM refunds WHERE refund_id = ?", ("r01",)).fetchone() == before
        return error.sqlite_errorname
    raise AssertionError("只读连接未拒绝写入")


def run():
    durations = [datetime.fromisoformat(end) - datetime.fromisoformat(start) for start, end in WINDOWS.values()]
    assert durations[0] == durations[1] and durations[0].days == 7
    with TemporaryDirectory(prefix="lucas-refunds-") as folder:
        path = (Path(folder) / "refunds.db").resolve()
        initialize(path)
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
            periods = {label: summarize(db, window) for label, window in WINDOWS.items()}
            wrong = {label: summarize(db, window, use_application_time=True) for label, window in WINDOWS.items()}
            write_rejected = verify_read_only(db)

    previous, current = periods["previous"], periods["current"]
    assert previous["matching_refund_ids"] == ["r01", "r02", "r03"]
    assert current["matching_refund_ids"] == ["r04", "r05", "r06", "r07"]
    assert (previous["amount_cents"], current["amount_cents"]) == (25000, 30000)
    assert wrong["current"]["matching_refund_ids"] == ["r05", "r06", "r07", "r08"]
    assert (wrong["previous"]["amount_cents"], wrong["current"]["amount_cents"]) == (25000, 27000)

    channel_changes = compare_channels(previous, current)
    change = current["amount_cents"] - previous["amount_cents"]
    assert sum(row["change_cents"] for row in channel_changes) == change
    wrong_change = wrong["current"]["amount_cents"] - wrong["previous"]["amount_cents"]
    correct_ids = set(current["matching_refund_ids"])
    wrong_ids = set(wrong["current"]["matching_refund_ids"])

    return {
        "dataset": "9 条自编退款流水",
        "metric": {
            "timestamp": "succeeded_at",
            "status": "succeeded",
            "amount_unit": "分",
            "timezone": "Asia/Shanghai (UTC+08:00)",
            "window_rule": "[start, end)",
            "window_days": 7,
        },
        "input_records": [dict(zip(COLUMNS, row)) for row in REFUNDS],
        "periods": periods,
        "change_cents": change,
        "channel_changes": channel_changes,
        "counterexample": {
            "timestamp": "applied_at",
            "periods": wrong,
            "change_cents": wrong_change,
            "change_error_cents": wrong_change - change,
            "omitted_current_ids": sorted(correct_ids - wrong_ids),
            "extra_current_ids": sorted(wrong_ids - correct_ids),
        },
        "checks": {
            "group_totals_match": True,
            "change_matches": True,
            "write_rejected": write_rejected,
        },
        "interpretation": "各渠道金额变动用于核对总额差值，业务原因需要结合其他数据验证。",
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the refund reconciliation on synthetic data.")
    parser.add_argument("--check", action="store_true", help="Check the published result against a fresh run")
    args = parser.parse_args()
    report = run()
    if args.check:
        saved = Path(__file__).with_name("refund_reconciliation_results.json")
        if json.loads(saved.read_text(encoding="utf-8")) != report:
            parser.exit(1, "Saved reconciliation results do not match the current experiment.\n")
        print("PASS refund totals, date boundary, channel deltas, and read-only write rejection")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
