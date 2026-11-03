---
title: Agent 会话记忆实操：SQLite 隔离与历史字符预算
description: 用一份可独立运行的 Python 脚本保存问答轮次，演示两个会话隔离、25 字符历史裁剪和过小预算错误。
pubDatetime: 2026-11-03T10:00:00+08:00
archiveDatetime: 2026-03-07T12:00:00+08:00
featured: true
draft: false
tags:
  - 上下文管理
  - memory
  - sqlite
series: AI Agent 代码实操
seriesOrder: 7
noteType: 代码实操
---

Agent 连续收到两条消息：“我用的是 v1”和“现在改成 v2”。同一时间，另一个用户正在查询退款。如果只是把所有消息塞进一个全局列表，两个问题会一起进入模型输入。这篇先完成一个可以直接运行的记忆选择器：SQLite 保存问答轮次，按会话查询，再为近期历史设置字符预算。

演示数据是自编的支持对话，不访问真实用户数据，也不请求模型。重点是亲眼看到数据库取出了哪些轮次，哪些内容被丢弃，而不是先讨论复杂的长期记忆框架。

## 目录

## 先看输入与目标

| 会话 | 按时间写入的内容 | 本次希望检查什么 |
| --- | --- | --- |
| A | 使用 v1 → 改成 v2 → 仍报 E102 | 保留近期追问，观察旧版本轮次是否被裁掉 |
| B | 查询退款 → 请给日期 | B 的内容不能出现在 A 的查询结果中 |

一问一答作为一条记录，避免裁剪后只留下半轮答案。这里的预算是 `len(question) + len(answer)`，单位为 Python 字符；没有计算角色标签、系统指令、当前问题或模型 Token，不能拿它当模型的完整输入上限。

## 运行环境与完整代码

环境：Python 3.12，Windows PowerShell 或 WSL/Linux 终端，`python` 已指向该版本。只使用标准库，数据库创建在独立临时目录中，运行完关闭并清理。下载文件后进入所在目录执行：

```bash
python --version  # 确认当前解释器是 Python 3.12。
python session_memory.py  # 运行会话隔离与字符预算演示。
```

[下载完整的 session_memory.py](/examples/agent-lab/session_memory.py)

```python
import json  # 用结构化输出观察会话内容。
import sqlite3  # 使用 Python 标准库中的 SQLite 接口。
from pathlib import Path  # 构造临时数据库路径。
from tempfile import TemporaryDirectory  # 演示结束后自动清理临时目录。

def add_turn(conn, session_id, question, answer):  # 将一问一答作为完整轮次保存。
    with conn:  # 正常退出时提交，发生异常时回滚本次写入。
        conn.execute(  # 使用参数占位符绑定内容，不拼接 SQL 字符串。
            "INSERT INTO turns(session_id, question, answer) VALUES (?, ?, ?)",  # 固定写入语句。
            (session_id, question, answer),  # 会话标识与文本分别作为参数。
        )  # 完成本轮写入。

def recent_turns(conn, session_id, char_budget):  # 按字符预算选择最近的完整轮次。
    if char_budget < 1:  # 拒绝无意义的预算配置。
        raise ValueError("char_budget 必须大于 0")  # 明确返回配置错误。
    rows = conn.execute(  # 限制读取数量，避免一次加载全部历史。
        "SELECT question, answer FROM turns WHERE session_id = ? ORDER BY id DESC LIMIT 20",  # 先按会话过滤，再倒序读取。
        (session_id,),  # 单参数也使用元组绑定。
    ).fetchall()  # 示例最多取得最近二十轮。
    selected, used = [], 0  # 初始化保留轮次和已用字符数。
    for question, answer in rows:  # 从最新一轮向较旧轮次检查。
        size = len(question) + len(answer)  # 只计算正文字符，不将其声称为 Token 数。
        if not selected and size > char_budget:  # 最新一轮也装不下时，不截断半段操作建议。
            raise ValueError("最新一轮超过历史字符预算")  # 交由上层选择摘要或调整预算。
        if used + size > char_budget:  # 继续添加将超过预算。
            break  # 保留连续的近期轮次，不跳过中间轮次寻找更短消息。
        selected.append({"question": question, "answer": answer})  # 整轮加入上下文候选。
        used += size  # 累计已使用的正文字符。
    return list(reversed(selected)), used  # 恢复由旧到新的对话顺序。

def main():  # 运行两个会话的隔离与裁剪演示。
    with TemporaryDirectory(prefix="agent-memory-") as folder:  # 仅使用独立临时目录。
        conn = sqlite3.connect(Path(folder) / "memory.db")  # 创建演示数据库，不接触用户已有数据。
        try:  # 无论演示成功与否都关闭连接。
            conn.execute("CREATE TABLE turns(id INTEGER PRIMARY KEY, session_id TEXT, question TEXT, answer TEXT)")  # 为轮次建立递增编号。
            add_turn(conn, "A", "使用 v1", "先查 v1")  # A 会话最早的旧版本条件。
            add_turn(conn, "A", "改成 v2", "使用 v2 资料")  # A 会话明确切换到新版本。
            add_turn(conn, "A", "仍报 E102", "核对必填列")  # A 会话继续追问。
            add_turn(conn, "B", "查询退款", "请给日期")  # B 会话属于另一项任务。
            for session_id in ("A", "B"):  # 分别按会话标识读取。
                turns, used = recent_turns(conn, session_id, 25)  # 为演示历史分配二十五个正文字符。
                print(json.dumps({"session": session_id, "chars": used, "turns": turns}, ensure_ascii=False))  # 展示选中轮次。
            try:  # 额外验证最新一轮装不下的错误分支。
                recent_turns(conn, "A", 1)  # 故意给出过小预算。
            except ValueError as error:  # 捕获预期的配置或预算错误。
                print("budget_error:", error)  # 展示明确失败，避免静默截断。
        finally:  # 连接必须在临时目录清理前释放。
            conn.close()  # Windows 上也能正常删除已关闭的数据库文件。

if __name__ == "__main__":  # 直接执行脚本时才运行演示。
    main()  # 入口函数不访问外网，也不调用真实模型。
```

## 实际输出怎样读

以下输出已在 Python 3.12.14 本地运行核对：

```text
{"session": "A", "chars": 25, "turns": [{"question": "改成 v2", "answer": "使用 v2 资料"}, {"question": "仍报 E102", "answer": "核对必填列"}]}
{"session": "B", "chars": 8, "turns": [{"question": "查询退款", "answer": "请给日期"}]}
budget_error: 最新一轮超过历史字符预算
```

第一行保留 A 的最近两轮，合计二十五个正文字符；最早的 v1 轮次没有进入结果。第二行只出现 B 的退款对话。第三行来自故意设置为一字符的预算，程序明确拒绝，不截断半句话后继续生成。

## 代码里的三个决定

数据库查询先执行 `WHERE session_id = ?`，再倒序取最多二十轮。参数通过占位符绑定；会话内容不会被拼进 SQL。`session_id` 在这个独立演示中是固定字符串，接入登录系统时应由可信的应用上下文绑定，而不是让模型任意选择其他会话。

倒序扫描可以先保住最近轮次，返回前再恢复正序。装不下下一条时直接停止，不跳过中间轮次去挑更短的旧消息。这样更容易解释“哪些连续历史进入了本次输入”。

数据库存储与模型输入是两件事：本例只裁剪读取结果，没有删除旧记录。真实系统的保存期限、用户删除和重启恢复需要另外设计；临时数据库也不提供跨进程持久化。

## 自己修改一次，观察结果

把主循环的二十五改成三十五，A 的最早 v1 轮次也会回来。这能直接说明：历史更多，不等于当前版本条件更准确。产品版本等关键状态如果必须保留，应单独记录并显式更新，不能只依赖它恰好留在近期历史里。

再给 B 增加一轮问答，确认 A 的输出不变。最后保留一字符预算的错误检查，核对上层收到的是明确错误，而不是一个看似完整但信息被截断的上下文。

这段代码只选择用户问答轮次。接入带工具调用的消息协议时，还应检查工具请求与返回的配对，不能直接把任意协议消息当成普通问答裁剪。

## 资料入口

- [Python 3.12：sqlite3](https://docs.python.org/3.12/library/sqlite3.html)：参数绑定、连接和事务上下文的官方说明。
- [Python 3.12：tempfile](https://docs.python.org/3.12/library/tempfile.html#tempfile.TemporaryDirectory)：独立临时目录及清理行为。

## 中文实战阅读

[张高兴：使用LangGraph为对话添加历史记录，博客园](https://www.cnblogs.com/zhanggaoxing/p/18791377)展示了thread_id与存储的连接方式。本篇的SQLite脚本用于先观察会话隔离和历史选择，接入框架检查点时仍需保留相同的隔离测试。
