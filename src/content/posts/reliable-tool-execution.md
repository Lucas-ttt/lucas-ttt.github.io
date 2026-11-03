---
title: "把工具失败拆开处理：参数校验、有限重试与幂等"
description: "分别复现无效参数、临时读取失败和工单重复提交，用明确状态与业务幂等约束处理执行风险。"
pubDatetime: 2026-11-03T10:00:00+08:00
archiveDatetime: 2026-03-07T12:00:00+08:00
featured: false
draft: false
tags: ["agent", "工具调用", "幂等"]
series: "AI Agent 开发实践"
seriesOrder: 7
noteType: 代码实操
modDatetime: 2026-11-03T13:03:44+00:00
---

我在把检索函数接到工具入口时，最先整理的不是更多工具名称，而是失败之后的行为。同样表现为“这次没有拿到结果”，背后的原因可能是参数根本不合法、读取连接暂时中断，也可能是写入已经完成，只是回复没有回来。如果全部交给一个通用重试循环，错误输入会被反复发送，写入还可能重复执行。

为了把这几种情况分开观察，我做了一个完全本地的实验：只读部分查询排障资料，写入部分在临时 SQLite 数据库中创建工单。它不会发送通知、操作真实退款或连接外部系统。这个范围足够小，可以逐项核对实际执行次数，也能看清哪些约束需要放在应用与数据库里。

## 目录

## 我先明确哪些失败可以再次尝试

工具入口先检查参数集合和字段类型。查询工具只接受 `query` 与 `version`，不能少传，也不能多塞一个自由填写的权限字段。值必须是非空字符串，规范化后的参数才交给实际函数。这样空问题会直接返回校验错误，根本不进入读取循环。

读取连接的临时故障是另一种状态。我给这个只读工具最多两次总尝试，包含第一次调用；第一次故意抛出连接异常，第二次真正查询 v2 的 E102。这个实验检查的是调用控制，没有模拟真实网络的故障率，也没有处理服务商的所有异常类型。接外部服务时，还需要为认证失败、限流、超时和业务拒绝分别映射状态。

我没有把同一个循环套到创建工单上。读取失败后再次查询，通常只增加开销；写入失败后再次提交，则必须先弄清第一次是否已经产生副作用。工具的重试资格应该跟操作语义绑定，不能只看异常名字里有没有“超时”。

## 用业务操作标识约束重复写入

创建工单时，我让调用方携带稳定的 `request_key`。数据库用它作为主键，并保存规范参数的指纹与已创建的工单编号。同一业务键、相同参数再次到达时，返回原编号；同一业务键却换了标题或版本时，明确报告冲突，要求调用方核对。

这里的参数指纹不是鉴权凭证。它只用于判断两次请求是否描述同一内容，不能证明用户有权创建或查询工单。真实应用还要把业务键放进可信用户、租户与操作类型的范围中，避免不同用户恰好使用同一个字符串。当前实验没有账户系统，这些身份条件不能由模型自行提供。

我采用先插入、由唯一约束处理重复的方式，避免把“先查不存在，再插入”误当成并发安全。真正起作用的是数据库对同一键的约束，应用层查重只能改善提示。规范化、参数指纹与实际写入也使用同一份数据，否则有可能把本来等价的请求误判为不同操作。

## 完整实现

将[工具控制脚本](/examples/agent-lab/tool_safety.py)与[只读检索函数](/examples/agent-lab/knowledge_tool.py)放在同一目录。环境为 Python 3.12，仅使用标准库，所有写入发生在脚本自己建立并清理的临时数据库中。

```python
import hashlib  # 为规范化业务参数生成稳定指纹。
import json  # 序列化参数与演示结果。
import sqlite3  # 用唯一约束保护本地工单的重复提交。
from pathlib import Path  # 定位独立临时数据库。
from tempfile import TemporaryDirectory  # 演示不接触已有业务文件。
from knowledge_tool import search_knowledge  # 复用已经验证的只读检索函数。

class IdempotencyConflict(ValueError):  # 同一业务键不能绑定两份不同内容。
    pass  # 错误类型让调用方停止自动重试。

class ReplyLost(TimeoutError):  # 模拟写入完成后没有收到回复。
    pass  # 此异常不能证明服务端没有执行。

def checked_payload(payload, fields):  # 在执行之前校验明确的字段集合。
    if not isinstance(payload, dict) or set(payload) != set(fields):  # 拒绝缺少字段和多余字段。
        raise ValueError("参数字段不符合约定")  # 不把错误输入交给工具猜测。
    if any(not isinstance(value, str) or not value.strip() for value in payload.values()):  # 这里只接收非空字符串。
        raise ValueError("参数必须为非空字符串")  # 统一在调用前失败。
    return {key: value.strip() for key, value in payload.items()}  # 指纹与执行使用相同规范值。

def lookup_with_retry(payload, fail_first=False):  # 只对这个只读工具允许有限重试。
    params = checked_payload(payload, ("query", "version"))  # 参数错误发生在尝试计数之前。
    for attempt in range(1, 3):  # 总尝试最多两次，包含第一次。
        try:  # 临时连接故障与输入错误分开处理。
            if fail_first and attempt == 1:  # 用确定性故障替身验证一次恢复。
                raise ConnectionError("模拟读取连接中断")  # 不调用外部服务。
            hits = search_knowledge(**params)  # 真正执行本地只读查询。
            return {"status": "ok", "attempts": attempt, "ids": [row["id"] for row in hits]}  # 空列表也是正常查询结果。
        except ConnectionError:  # 本例仅把连接异常列入可重试集合。
            if attempt == 2:  # 第二次失败后明确退出。
                return {"status": "unavailable", "attempts": attempt, "ids": []}  # 不伪造证据。

def create_ticket(db, request_key, payload, lose_reply=False):  # 创建本地演示工单，不发送通知。
    params = checked_payload(payload, ("title", "version"))  # 写操作也必须先校验。
    if not isinstance(request_key, str) or not request_key.strip() or len(request_key) > 80:  # 业务键来自受信任应用上下文。
        raise ValueError("业务操作标识不合法")  # 不用随机新键掩盖同一次操作。
    fingerprint = hashlib.sha256(json.dumps(params, sort_keys=True, ensure_ascii=False).encode()).hexdigest()  # 同一规范参数得到同一指纹。
    ticket_id = "TK-" + hashlib.sha256(request_key.encode()).hexdigest()[:8]  # 生成稳定的演示编号。
    with db:  # 唯一约束与插入位于同一事务中。
        try:  # 直接尝试插入，由数据库处理重复键竞争。
            db.execute("INSERT INTO tickets VALUES (?, ?, ?, ?)", (request_key, fingerprint, ticket_id, params["title"]))  # 参数不拼接进SQL。
            state = "created"  # 本次实际新增记录。
        except sqlite3.IntegrityError:  # 只在数据库拒绝重复键后读取原操作。
            previous = db.execute("SELECT fingerprint, ticket_id FROM tickets WHERE request_key = ?", (request_key,)).fetchone()  # 按业务键查询已保存状态。
            if previous is None or previous[0] != fingerprint:  # 同键不同内容属于冲突。
                raise IdempotencyConflict("同一业务操作标识对应不同参数")  # 要求调用方核对，不重新创建。
            ticket_id, state = previous[1], "reused"  # 相同内容复用既有结果。
    if lose_reply:  # 此处写入事务已经提交。
        raise ReplyLost("写入后回复丢失，请先查询业务状态")  # 本地超时不能等同于执行失败。
    return {"status": state, "ticket_id": ticket_id}  # 返回明确的业务状态。

def main():  # 依次验证三类不同故障。
    try:  # 错误参数应在读取之前停止。
        lookup_with_retry({"query": "", "version": "v2"})  # 注入空问题。
    except ValueError as error:  # 不把校验错误送进重试循环。
        print("参数错误", str(error))  # 显示真实错误分支。
    print("只读恢复", json.dumps(lookup_with_retry({"query": "E102", "version": "v2"}, fail_first=True), ensure_ascii=False))  # 第一轮失败、第二轮成功。
    with TemporaryDirectory(prefix="lucas-tools-") as folder:  # 创建本次独立数据库。
        db = sqlite3.connect(Path(folder) / "tickets.db")  # 不使用用户已有数据库。
        try:  # 所有退出路径都释放连接。
            db.execute("CREATE TABLE tickets(request_key TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, ticket_id TEXT NOT NULL, title TEXT NOT NULL)")  # 业务键由唯一约束保护。
            payload = {"title": "v2 导入报 E102", "version": "v2"}  # 自编工单内容。
            for _ in range(2):  # 用同一业务键重复提交相同内容。
                print("工单结果", json.dumps(create_ticket(db, "operation-001", payload), ensure_ascii=False))  # 第二次应复用第一次结果。
            try:  # 验证相同键不能偷偷改成另一项操作。
                create_ticket(db, "operation-001", {"title": "另一项故障", "version": "v2"})  # 参数指纹与原记录不同。
            except IdempotencyConflict as error:  # 冲突停止，不重试写入。
                print("重复冲突", str(error))  # 保留可诊断原因。
            try:  # 模拟第二项操作已经成功但回复丢失。
                create_ticket(db, "operation-002", payload, lose_reply=True)  # 写入完成后抛出异常。
            except ReplyLost:  # 先查询原业务键对应的状态。
                row = db.execute("SELECT ticket_id FROM tickets WHERE request_key = ?", ("operation-002",)).fetchone()  # 读取操作是否已存在。
                print("回复丢失后核对", "已找到工单" if row else "状态待确认")  # 不盲目提交第三次写入。
            print("实际工单数", db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0])  # 总共只产生两项业务操作。
        finally:  # Windows下也要先释放数据库再清理目录。
            db.close()  # 关闭本次连接。

if __name__ == "__main__":  # 导入模块不触发演示写入。
    main()  # 仅操作临时数据库和自编资料。
```

## 代码逐段解析

`checked_payload` 同时校验字段集合与值类型。返回值经过两端空白清理，随后既参与指纹计算，也参与工具执行。额外字段会被拒绝，可以尽早发现模型或调用方偏离约定；但这份简化校验没有长度上限、枚举约束和内容策略，不能直接当作所有工具的通用输入模型。

`lookup_with_retry` 把参数检查放在循环之外，只捕获允许重试的连接异常。第一次故障是明确注入的，第二次才执行真实的本地检索。返回值中保留实际尝试次数与证据标识，空列表仍是合法查询结果。上层可以据此区分暂不可用和没有适用资料。

`create_ticket` 在事务里尝试插入，捕获重复键后读取原记录。指纹相同才复用原编号，指纹不同立即结束。这里保护的是同一个数据库事务中的工单记录；如果工具还调用了事务之外的支付、邮件或第三方接口，需要进一步设计对方幂等接口、待处理状态与对账，不能把一次 SQLite 插入扩展成跨系统保证。

最需要留意的是 `lose_reply` 的位置：它在事务提交之后抛出异常。因此捕获这个异常时，数据已经存在。这个故障点让我可以直接验证“没收到回复”与“没有执行”之间的区别。

## 一次实际运行的结果

```powershell
python tool_safety.py # 运行参数错误、只读恢复、重复提交和回复丢失实验。
```

```text
参数错误 参数必须为非空字符串
只读恢复 {"status": "ok", "attempts": 2, "ids": ["csv-v2"]}
工单结果 {"status": "created", "ticket_id": "TK-6dfd819d"}
工单结果 {"status": "reused", "ticket_id": "TK-6dfd819d"}
重复冲突 同一业务操作标识对应不同参数
回复丢失后核对 已找到工单
实际工单数 2
```

第一项写操作虽然被提交了两次，但编号没有变化，数据库里也没有多一条记录。第二项写操作在提交后丢失回复，我按原业务键查到它已经存在，因此没有另发一项创建请求。最后的两条记录对应两项不同业务操作，而不是终端里出现过几次调用。

## 状态未知时，先核对而不是换一个新键

这个实验让我把“执行失败”和“结果未知”单独记录。写入前校验失败可以直接修正输入；明确拒绝执行时可以解释原因；提交后连接中断则要先查询原操作的状态。如果换一个随机新键立即重发，就主动绕过了原本的去重条件。

查询没有发现记录，也不总能证明远端没有执行。真实系统还可能存在读写延迟、异步任务或回复先于最终落库的情况，需要结合服务的状态接口与一致性约定处理。我的本地实验能立即读到同一数据库的提交结果，这个条件必须与跨系统调用区分开。

后续我会把工具名、参数摘要、业务键、尝试次数和最终状态放进同一条操作轨迹，敏感正文则按需要脱敏。这样出现重复请求时，能够回到一次具体操作核对。工具增加之前先补齐这些边界，比在失败以后只返回一段自然语言解释更便于维护。
