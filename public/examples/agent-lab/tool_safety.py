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
