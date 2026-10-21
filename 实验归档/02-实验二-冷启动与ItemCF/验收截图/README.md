# 实验二验收截图

此目录预留四张课程验收截图：

1. `01-Popular-Top10.png`
2. `02-ColdStart-零行为账号.png`
3. `03-ItemCF-ml14.png`
4. `04-ItemCF-ml55.png`

已收到第 1 张：`01-Popular-Top10.png`。图中可见 Popular 算法、历史用户 ml14 和完整 10 条结果。

`诊断-冷启动未登录.png` 为登录提示诊断图，不是验收截图，也不计入 4 张要求。

`诊断-测试账号已登录-首页.png` 显示测试账号已登录，但页面仍是首页、没有 Cold Start Top10，因此也不计入验收截图。

`诊断-ColdStart前仍为ml14-Content.png` 显示当前选择仍是 MovieLens 用户 ml:14 和 content 算法，因此也不计入验收截图。

已收到第 2 张：`02-ColdStart-零行为账号.png`。图中可见 `app:1`、`cold_start`、无偏好热门回退说明和完整 Top10；评分/收藏 0/0 由 API 验证记录支持，页面没有直接展示计数。

已收到第 3 张：`03-ItemCF-ml14.png`。图中可见 `ml:14`、`itemcf-cosine-v1` 和完整 Top10。

已收到第 4 张：`04-ItemCF-ml55.png`。图中可见 `ml:55`、ItemCF 算法和完整 Top10。四张课程要求的页面验收截图均已齐全。Cold Start 页面未直接显示评分/收藏数量，零行为状态由上一级 `实验二验收API结果.md` 中的 API 记录佐证。
