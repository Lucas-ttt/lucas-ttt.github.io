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
