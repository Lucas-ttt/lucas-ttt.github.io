---
title: "SQL Agent 怎样限制执行权限并核对查询结果？"
description: "逐段拆解 SQLite 只读授权、执行预算与纠错复验，用 350 元和 999.99 元的对照检查查询业务口径。"
pubDatetime: 2026-11-03T10:00:00+08:00
archiveDatetime: 2026-03-20T12:00:00+08:00
featured: true
draft: false
series: "AI Agent 面试十问"
seriesOrder: 6
noteType: "代码实操"
tags:
  - agent
  - nl2sql
  - 项目走读
---

运营问“十月成功退款金额是多少”，Agent 生成的 SQL 能执行，并不说明它统计了正确的月份和状态。本篇把查询工具缩到五条演示记录：先算出可手工核对的数字，再测试错误 SQL、修正后复验和写入拒绝。代码只使用 Python 标准库，可以直接运行。

## 目录

## 面试题

**允许 Agent 生成并执行 SQL 时，怎样限制权限、控制失败重试，并验证查出来的数字符合业务口径？**

本文聚焦数据库执行工具，用五条自编退款记录、一次错误注入和金额核对完成独立演示。示例中的 SQL 由代码预设，接入模型生成查询后，仍需经过相同的执行检查。

## 一分钟回答

我会把 SQL 生成、执行约束和业务核对分开。模型只提交候选 SQL，程序使用受限连接执行，限制可做的操作、查询资源和返回规模；报错后修正的语句也必须重新走同一个入口，不能绕过检查。查询成功后，再核对统计对象、时间字段、状态和金额单位。本文把十月成功退款限定为三条，结果应为三百五十元；改成未成功状态后，仍是合法只读查询，却得到九百九十九点九九元。这说明只读权限只能减少一类执行风险，不能保证用户的问题已经被正确翻译成指标。

## 先确认用户说的“退款金额”指什么

在真实需求里，十月可能指申请时间、支付时间或成功退款时间；退款金额可能是申请金额、成功实退金额或扣除手续费后的净额。本例明确使用演示列 `day` 代表状态时间，`status=success` 代表成功记录，按整数分求和。不先明确这些条件，换一个更强的模型也可能生成与业务目标不一致的 SQL。

另外，查询“各渠道退款额”属于分组统计，并不自动等于严格意义上的归因分析。若以后计算渠道贡献，还要定义订单与渠道关联、归因窗口、一笔交易多次触达的分配规则，以及重试记录去重。这里先验证最小金额查询工具，避免把一个分组求和脚本包装成完整归因方法。

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

## 代码逐段解析

### 初始化结束后，在连接上收紧动作

`create_demo` 先建表并写入自编数据，提交后再打开 `query_only` 和授权回调。顺序很关键：初始化需要写入，交给查询工具时才进入受限状态。回调只放行本例所需的 SELECT、READ 和 FUNCTION，其余动作返回拒绝；这比仅在系统提示词里告诉模型“不要删除数据”更能约束这条连接。[SQLite 官方说明](https://www.sqlite.org/c3ref/set_authorizer.html)明确了授权回调在语句编译时检查动作，以及拒绝值的行为。

这个演示回调没有检查具体表、列或函数名。因此它没有实现租户隔离、敏感列授权，也不是任意 SQL 的完整安全沙箱。参数绑定用来传日期和状态这样的值，不能自动审核模型生成的表名、列名与整条语句。真实系统还需要数据库最小权限、对象白名单和独立的业务授权；不能只因为使用了问号占位符就宣称自由生成的 SQL 都安全。

### 新 SQL 与修正 SQL 只能走同一个入口

`checked_query` 先执行 `EXPLAIN QUERY PLAN`，再执行当前 SQL，并在 `finally` 清理进度回调。它能暴露一些语法、对象和权限问题，但当前代码没有解析执行计划来拒绝特定扫描；EXPLAIN 成功也不证明筛选条件符合业务。SQLite 的 [EXPLAIN QUERY PLAN 文档](https://www.sqlite.org/eqp.html)将其定位为查看查询策略的调试工具，不能把这一步叫作语义正确性证明。

故意写错的 `SELEC` 触发数据库异常后，修正查询再次调用 `checked_query`，而非直接使用裸 `execute`。这条路径防止“第一条检查了，第二条为了纠错就跳过检查”。接入 Agent 时还应限制修正次数，记录每次候选与错误，避免在相同错误上无限重试；本文只演示一次固定修正，没有已经实现自由纠错规划。

### 时间预算与结果条数控制的是不同资源

进度回调每执行一定数量的虚拟机指令再检查时钟，所以 `0.2` 秒是本例的近似执行预算，不是一个对所有阻塞都精确生效的强制中止器。`fetchmany(20)` 限制取回行数，不代表数据库最多扫描二十行，聚合或排序仍可能需要处理更多数据。两者都需要根据数据库与连接方式另行验证。

还有一个容易漏掉的展示问题：本例只返回两个渠道，可以完整求和；若将来超过二十个分组，直接把取回的二十行再求总和就会少算。此时要显式标记截断、分页，或另跑同条件的独立总额查询，不能把局部结果当作完整报告。金额在数据库里保留整数分，只在显示时转换，便于与原始记录逐项核对。

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

## 面试追问与复核清单

**三百五十元是怎么确认的？** 三条十月成功记录分别为一百二十、八十和一百五十元，先手工相加，再核对分组结果与独立总额查询。两个 SQL 结果一致也不能单独作为证明，因为它们可能复制了同一个错误条件；五条明细提供了第三个核对依据。

**没有成功退款时能直接显示零吗？** 执行失败、没有符合条件的记录、金额列异常是不同状态。SQL 的 `SUM` 在没有输入行时可能返回空值，应根据已确定的业务规则处理；数据库异常不能转换成零元，否则运营会把系统不可用误认为业务确实没有退款。

**上线前还缺什么？** 需要补身份与数据范围授权、数据库专用只读账号、表列限制、真正的查询超时和结果截断策略，并测试大表与异常查询。高风险写操作应使用另外的工具和明确审批链路。博客园 LucaJu 的[人工介入实战](https://www.cnblogs.com/jucunqi/p/19956619)可以作为继续阅读的案例；本文没有实现其审批流程，也没有把模型生成 SQL 的质量归入已验证范围。

一次可解释的查询记录至少应包含用户问题、已确认口径、SQL、绑定参数、执行状态和结果范围。涉及业务数据时还要处理脱敏与访问控制，不能为了留痕把完整敏感结果直接写入公开日志。

## 继续阅读

- [SQLite：EXPLAIN QUERY PLAN](https://www.sqlite.org/eqp.html)：检查查询策略的用途与输出格式边界。
- [Python 3.12中文文档：sqlite3](https://docs.python.org/zh-cn/3.12/library/sqlite3.html)：参数绑定、authorizer及进度回调。
- [SQLite：授权回调](https://www.sqlite.org/c3ref/set_authorizer.html)：核对允许与拒绝动作的执行语义。
- [LangGraph：自定义SQL Agent](https://docs.langchain.com/oss/python/langgraph/sql-agent)：进一步阅读模型、检查节点与执行节点的连接。
