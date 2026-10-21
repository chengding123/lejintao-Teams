# 实验二交付源码快照

这是实验二完成时的源码副本，保留主项目原有相对路径，后续实验不会覆盖本目录。

本快照包含实验二变更和运行所需的学生实现入口；实验一基线源码仍独立保存在 `01-实验一-系统认知与内容推荐/交付源码快照/`。课程固定数据、数据库、账号凭据、环境密钥及 Docker 数据卷不在快照中，也不要上传 GitHub。

包含：

- `backend/app/experiments.py`：接口、偏好校验和算法列表。
- `recommender/business.py`：业务历史及热门、正向交互只读适配器。
- `recommender/contracts.py`、`recommender/validation.py`：算法注册、请求和模型契约校验。
- `recommender/student/`：热门、ItemCF、冷启动算法与模型绑定。
- `frontend/src/`：实验室参数入口、结果来源说明及类型定义。
- `tests/test_experiment_two.py`：实验二行为用例。
