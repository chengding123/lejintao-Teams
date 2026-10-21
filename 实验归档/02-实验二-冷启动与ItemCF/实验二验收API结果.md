# 实验二本地 API 验收结果

运行日期：2026-10-21（Asia/Shanghai）  
服务：`http://127.0.0.1:8080`  
数据：`rec-course-v3-train5-1.0.0` / `temporal-v1-cold500-train5-v3`，`business` 模式

以下内容来自本机正在运行的 API 与电影目录，不是手工固定推荐清单。分数保留 API 返回值。

## Popular 全局热门 Top10

请求：`GET /api/v1/demo/history-users/14/recommendations/popular?limit=10`  
HTTP 200；模型 `popular-bayes-v1`；10 条、10 个唯一电影 ID。

| 排名 | ID | 电影 | 得分 |
|---:|---:|---|---:|
| 1 | 318 | The Shawshank Redemption (1994) | 4.417339 |
| 2 | 858 | The Godfather (1972) | 4.284944 |
| 3 | 50 | The Usual Suspects (1995) | 4.254428 |
| 4 | 1203 | 12 Angry Men (1957) | 4.244986 |
| 5 | 195159 | Spider-Man: Into the Spider-Verse (2018) | 4.243790 |
| 6 | 2019 | Seven Samurai (1954) | 4.240772 |
| 7 | 1221 | The Godfather: Part II (1974) | 4.231629 |
| 8 | 2959 | Fight Club (1999) | 4.223231 |
| 9 | 202439 | Parasite (2019) | 4.214027 |
| 10 | 904 | Rear Window (1954) | 4.207170 |

## Cold Start 零行为账号

本地新账号：`account_id=1`，登录名 `exp2_cold_98ebeda865`。登录后的 `/api/v1/me/ratings` 与 `/api/v1/me/favorites` 均返回 HTTP 200、总数 0。没有给该账号添加评分或收藏。

默认回退请求：`GET /api/v1/me/recommendations/cold_start?limit=10`，HTTP 200，模型 `cold-start-genres-v1`，10 条唯一结果，召回来源为 `popular_non_personalized`。电影 ID 顺序：

`318, 858, 50, 1203, 195159, 2019, 1221, 2959, 202439, 904`

兴趣定制请求：`GET /api/v1/me/recommendations/cold_start?limit=10&genres=Action`，HTTP 200，模型 `cold-start-genres-v1`，10 条唯一结果，召回来源为 `genre_preference`。电影 ID 顺序：

`195159, 2019, 2959, 6016, 2571, 1209, 79132, 908, 3000, 58559`

全部 10 条均含 `Action` 类型。默认与兴趣定制榜单的 ID 集合不同，证明兴趣筛选分支在此账号上生效。

## ItemCF 两位指定用户

| 用户 | 历史评分数 | HTTP / 模型 | Top10 电影 ID 顺序 |
|---|---:|---|---|
| ml14（14） | 15 | 200 / `itemcf-cosine-v1` | `3253, 2502, 4679, 2716, 1265, 2174, 1197, 3552, 3033, 1285` |
| ml55（55） | 19 | 200 / `itemcf-cosine-v1` | `457, 2000, 1608, 1101, 2194, 2797, 1610, 2268, 1500, 474` |

两榜均为 10 条唯一结果，与各自历史评分电影均无交集；两榜 Top10 交集为 0。ml14 历史评分呈喜剧偏好（其 15 条记录均为 5.0），Top10 主要为喜剧片；ml55 历史兴趣覆盖动作、惊悚、犯罪、剧情等类型，推荐也呈现相应的混合类型。

## 测试与截图状态

- 容器内执行 `tests/test_experiment_two.py` 对应的 unittest 用例：5 项通过（`Ran 5 tests ... OK`）。
- Popular、Cold Start、ml14 ItemCF 与 ml55 ItemCF 四张页面截图均由用户提供，分别保存为 `验收截图/01-Popular-Top10.png` 至 `验收截图/04-ItemCF-ml55.png`。Cold Start 图可见 `app:1`、无偏好热门回退和完整 Top10；页面未显示评分/收藏计数，0/0 状态见上文账号 API 验证。四张页面验收截图现已齐全。没有伪造截图，也没有换用其他浏览器/CDP 通道绕过。

