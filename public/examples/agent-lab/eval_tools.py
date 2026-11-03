from knowledge_tool import search_knowledge  # 本例只测工具契约，不调用LLM。

CASES = [  # 每条样例明确输入和预期证据ID或异常类型。
    {"name": "v1 的 E102", "params": {"query": "E102", "version": "v1"}, "ids": ["csv-v1"]},  # 旧版字段说明。
    {"name": "v2 的 E102", "params": {"query": "E102", "version": "v2"}, "ids": ["csv-v2"]},  # 新版字段说明。
    {"name": "v2 的 E201", "params": {"query": "E201", "version": "v2"}, "ids": ["encoding-v2"]},  # 编码错误说明。
    {"name": "未知版本", "params": {"query": "E102", "version": "v9"}, "ids": []},  # 没有适用资料属于正常空结果。
    {"name": "空问题", "params": {"query": "", "version": "v2"}, "error": "ValueError"},  # 不接受空输入。
    {"name": "空版本", "params": {"query": "E102", "version": ""}, "error": "ValueError"},  # 不能猜测用户版本。
    {"name": "零条候选", "params": {"query": "E102", "version": "v2", "top_k": 0}, "error": "ValueError"},  # 检查数量下界。
    {"name": "文本数量", "params": {"query": "E102", "version": "v2", "top_k": "3"}, "error": "ValueError"},  # 不默默接受错误类型。
]  # 结束八条固定回归用例。

def run_case(case: dict) -> tuple[bool, str]:  # 每个用例返回通过状态与实际结果。
    try:  # 参数错误是本例需要观察的正常检查分支。
        documents = search_knowledge(**case["params"])  # 原样传入用例中的参数。
    except ValueError as error:  # 只捕获工具契约声明的异常。
        expected = case.get("error") == "ValueError"  # 不把所有异常都当作通过。
        return expected, f"ValueError: {error}"  # 保留真实异常信息供排错。
    actual = [document["id"] for document in documents]  # 只比较明确定义的证据标识。
    passed = "error" not in case and actual == case["ids"]  # 若预期异常却正常返回，也判失败。
    return passed, str(actual)  # 回传实际值，而非只打印一个汇总分数。

def main() -> None:  # 固定顺序执行并报告结果。
    passed_count = 0  # 通过数量从零累计。
    for case in CASES:  # 每条用例独立验证，不依赖前面的结果。
        passed, actual = run_case(case)  # 调用工具并对比预期。
        passed_count += int(passed)  # 将布尔结果转换为通过数量。
        status = "PASS" if passed else "FAIL"  # 用简短状态标记方便查找失败行。
        print(f"{status} {case['name']}: {actual}")  # 同时显示问题和实际输出。
    print(f"工具回归通过: {passed_count}/{len(CASES)}")  # 分母是这八个固定用例。
    raise SystemExit(0 if passed_count == len(CASES) else 1)  # 任一失败都会返回非零退出码。

if __name__ == "__main__":  # 仅直接运行时执行回归。
    main()  # 该结果不是LLM回答准确率或生产质量结论。
