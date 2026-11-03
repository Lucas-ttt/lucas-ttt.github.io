import sqlite3  # 用标准库 SQLite 演示只读查询，不连接真实业务数据库。
from decimal import Decimal  # 用十进制定点转换分与元。
from time import monotonic  # 为每条查询设置执行时间边界。

def create_demo():  # 创建仅存在内存中的自编退款资料。
    db = sqlite3.connect(":memory:")  # 进程结束后演示库自动消失。
    db.execute("CREATE TABLE refunds(day TEXT, cents INTEGER, status TEXT, channel TEXT)")  # 金额始终存整数分。
    rows = [("2026-10-02", 12000, "success", "搜索"), ("2026-10-15", 8000, "success", "搜索"), ("2026-10-23", 15000, "success", "推荐"), ("2026-10-26", 99999, "pending", "推荐"), ("2026-11-01", 5000, "success", "搜索")]  # 五行资料覆盖状态与跨月边界。
    db.executemany("INSERT INTO refunds VALUES (?, ?, ?, ?)", rows)  # 初始化使用参数绑定。
    db.commit()  # 初始化结束后再收紧查询连接。
    db.execute("PRAGMA query_only = ON")  # 在该连接上开启只读模式。
    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}  # 此演示只允许查询所需动作。
    db.set_authorizer(lambda action, *args: sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY)  # 在数据库执行层拒绝写入和其他动作。
    return db  # 返回受到约束的演示连接。

def checked_query(db, sql, parameters=()):  # 新查询和修正后的查询使用同一个入口。
    deadline = monotonic() + 0.2  # 每次入口建立独立的查询预算。
    db.set_progress_handler(lambda: int(monotonic() > deadline), 1000)  # 周期性检查执行预算。
    try:  # 执行前校验与真正查询均在同一权限连接上完成。
        db.execute("EXPLAIN QUERY PLAN " + sql, parameters).fetchall()  # 每次都重新检查当前 SQL。
        return db.execute(sql, parameters).fetchmany(20)  # 控制返回条数，避免把无限结果交给模型。
    finally:  # 无论成功失败均清理本次预算回调。
        db.set_progress_handler(None, 0)  # 不把上一次截止时间带入下一次查询。

if __name__ == "__main__":  # 直接运行即可观察正常、修正与拒绝分支。
    db = create_demo()  # 所有演示数据在本次运行内创建。
    parameters = ("2026-10-01", "2026-11-01", "success")  # 日期采用左闭右开范围。
    sql = "SELECT channel, SUM(cents) FROM refunds WHERE day >= ? AND day < ? AND status = ? GROUP BY channel ORDER BY channel"  # 分组与总额使用相同条件。
    try:  # 主查询只统计已成功的十月退款。
        result = checked_query(db, sql, parameters)  # 实际执行受约束的查询。
        for channel, cents in result:  # 按渠道显示查询结果。
            print(channel, f"{Decimal(cents) / 100:.2f} 元")  # 只在显示边界把分转换成元。
        print("合计", f"{Decimal(sum(row[1] for row in result)) / 100:.2f} 元")  # 核对分组加总。
        try:  # 人为制造一次语法错误。
            checked_query(db, "SELEC SUM(cents) FROM refunds")  # 错误不会被当作金额为零。
        except sqlite3.DatabaseError:  # 记录失败后提交另一条查询。
            total = checked_query(db, "SELECT SUM(cents) FROM refunds WHERE day >= ? AND day < ? AND status = ?", parameters)  # 修正查询重新走校验。
            print("修正后复验", total[0][0], "分")  # 输出与分组结果相互核对。
        try:  # 验证数据库层面的写入约束。
            checked_query(db, "DELETE FROM refunds")  # 此语句应被数据库拒绝。
        except sqlite3.DatabaseError:  # 捕获拒绝，不尝试其他路径执行。
            print("写入请求被拒绝")  # 只输出状态，不隐藏失败原因。
    finally:  # 演示结束时释放内存连接。
        db.close()  # 不在用户磁盘创建业务数据。
