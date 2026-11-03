---
title: "给 SQL Agent 加执行边界：只读查询、纠错复验与金额核对"
description: "运行五条演示退款数据，核对350元结果，拒绝写入，并实际改变状态条件观察999.99元的错误口径。"
pubDatetime: 2026-11-03T10:00:00+08:00
archiveDatetime: 2026-03-20T12:00:00+08:00
featured: true
draft: false
series: "AI Agent 代码实操"
seriesOrder: 6
noteType: "代码实操"
tags:
  - agent
  - nl2sql
  - 项目走读
---

运营问“十月成功退款金额是多少”，Agent 生成的 SQL 能执行，并不说明它统计了正确的月份和状态。本篇把查询工具缩到五条演示记录：先算出可手工核对的数字，再测试错误 SQL、修正后复验和写入拒绝。代码只使用 Python 标准库，可以直接运行。

## 目录

## 五条资料先把口径摆出来

三条十月成功退款分别为120元、80元和150元；另外两条是十月未成功记录999.99元，以及十一月成功记录50元。正确目标为350元。表中日期表示本例定义的状态时间，金额按整数分保存；这些都是自编演示资料。

SQL 的日期条件使用左闭右开区间，状态必须为success。参数绑定传递日期和状态，金额只在显示时从分转成元。这能把“查询执行正确”和“业务条件选对”分开检查。[Python中文SQLite文档](https://docs.python.org/zh-cn/3.12/library/sqlite3.html)可对照参数绑定及连接回调；[LangGraph SQL Agent官方教程](https://docs.langchain.com/oss/python/langgraph/sql-agent)提供完整框架链路的阅读入口。

## 完整代码

环境：Python 3.12，Windows PowerShell、WSL或其他已配置Python的终端。先解压[全部示例](/examples/agent-lab.zip)，进入agent-lab目录；本篇不需要安装第三方依赖。[下载sql_readonly.py](/examples/agent-lab/sql_readonly.py)。

```python
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
```

`checked_query`是唯一执行入口：新查询和修正查询都先重新检查，再实际执行。只读PRAGMA和authorizer放在连接层，不能仅在Prompt里写“不要删除”。进度回调限制本次演示的查询执行时间，fetchmany只约束取回条数，两者作用不同。

## 运行及实际输出

```powershell
python sql_readonly.py # 运行内存数据库中的查询、纠错与写入拒绝。
```

本次Python 3.12.14运行输出：

```text
推荐 150.00 元
搜索 200.00 元
合计 350.00 元
修正后复验 35000 分
写入请求被拒绝
```

两条搜索渠道记录合计200元，推荐渠道为150元；独立总额查询返回35000分。未成功记录和十一月记录均未进入本次统计。

## 改错实验：只读仍可能算错

将main中的parameters最后一项由success改为pending，其余代码和数据保持不变。这个变体已经实际执行：

```text
推荐 999.99 元
合计 999.99 元
修正后复验 99999 分
写入请求被拒绝
```

SQL仍然合法、只读、能够执行，但统计目标已经变成未成功记录。这个实验说明权限校验不能替代指标核查。先核对状态、日期和单位，再把数字交给报告生成环节。

## 迁移到真实归因系统要补什么

此处演示的是SQLite连接边界，不是生产数据库权限方案。迁移到MySQL等数据库时，要使用该数据库的只读账号、表列授权与查询超时；修正后的SQL仍须重新走实际检查。授权回调也不是完整的资源隔离系统，不应据此声称所有任意SQL都已安全。

建议保留问题、指标定义、当前SQL、参数和结果，让报告中的350元能回到具体记录。出现SQL错误时返回错误状态，不把执行失败解释成“金额为零”。

## 继续阅读

- [Python 3.12中文文档：sqlite3](https://docs.python.org/zh-cn/3.12/library/sqlite3.html)：参数绑定、authorizer及进度回调。
- [SQLite：授权回调](https://www.sqlite.org/c3ref/set_authorizer.html)：核对允许与拒绝动作的执行语义。
- [LangGraph：自定义SQL Agent](https://docs.langchain.com/oss/python/langgraph/sql-agent)：进一步阅读模型、检查节点与执行节点的连接。
