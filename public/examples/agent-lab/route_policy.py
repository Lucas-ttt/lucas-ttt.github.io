import json  # 输出每种任务对应的本地路由结果。
from dataclasses import dataclass  # 显式保存选型所依赖的条件。

@dataclass(frozen=True)  # 输入条件不可在判断过程中被悄悄改写。
class Task:  # 这是一份演示决策表，不会实际调用模型或训练。
    name: str  # 任务名称用于核对结果。
    needs_documents: bool = True  # 是否需要产品资料。
    fits_context: bool = True  # 调用方已确认材料是否能装入实际剩余上下文。
    changing_knowledge: bool = False  # 资料是否频繁变化。
    multiple_versions: bool = False  # 是否需要维护版本适用条件。
    live_records: bool = False  # 是否需要当前业务记录。
    behavior_adaptation: bool = False  # 是否要改变稳定的输出行为。

def choose_route(task):  # 让每个选择都能对应输入条件。
    routes, reasons = [], []  # 同一任务允许组合多条路径。
    if task.live_records:  # 实时订单或退款状态应从有权限的业务接口读取。
        routes.append("business_api")  # 不把历史文档当成当前交易状态。
        reasons.append("实时记录先查受授权的业务接口")  # 业务权限仍由应用落实。
    if task.needs_documents:  # 产品规则与排障说明走文档路径。
        if task.fits_context and not task.changing_knowledge and not task.multiple_versions:  # 小而固定的资料可直接提供全文。
            routes.append("long_context")  # 不为单页固定材料额外维护检索链。
            reasons.append("固定短资料已确认可装入剩余上下文")  # 这个布尔量不是用中文字符估算token。
        else:  # 更新、版本或容量条件使外部证据管理更有价值。
            routes.append("rag")  # 先选择适用资料，再组装上下文。
            reasons.append("需要更新、版本筛选或按需提供证据")  # 不宣称所有场景都必需向量库。
    if task.behavior_adaptation:  # 稳定格式与领域表达属于另一种目标。
        routes.append("fine_tune_candidate")  # 只是进入对比评估，不自动启动训练。
        reasons.append("先验证提示与示例，再评估行为适配训练")  # 训练不能保证记住实时事实。
    return {"task": task.name, "routes": routes, "reasons": reasons}  # 同时保留原因便于复核。

if __name__ == "__main__":  # 五种输入不调用网络，也不需要密钥。
    tasks = [  # 通过改变条件观察路线，不用技术名称反推需求。
        Task("固定单页手册"),  # 长上下文可能已经足够。
        Task("多版本排障库", fits_context=False, changing_knowledge=True, multiple_versions=True),  # 当前原型选择的知识管理方向。
        Task("当前退款状态", needs_documents=False, live_records=True),  # 文档不能提供实时交易状态。
        Task("固定分类格式", needs_documents=False, behavior_adaptation=True),  # 训练候选只用于行为目标。
        Task("退款状态加流程说明", fits_context=False, changing_knowledge=True, live_records=True),  # 接口与RAG可以协作。
    ]  # 输入全部为自编演示场景。
    for task in tasks:  # 输出每条决策及其条件解释。
        print(json.dumps(choose_route(task), ensure_ascii=False))  # 不将本地规则称为模型评测结果。
