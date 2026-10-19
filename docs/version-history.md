# 版本记录

## 1. 版本三元组

| 维度 | 当前版本 | 载体 |
|---|---|---|
| 数据 | `data-v2`（服务日 2026-10-20，12306 官方前端） | `data/processed/shita_timetable_2026-10-20_data-v2.json` |
| 契约 | `2.1.0` | `docs/data-contract.md` + `docs/schema/shita-timetable.schema.json` |
| 页面 | `web-v1.4.0` | `index.html` + `js/*.js` + `css/*.css` |
| 对照数据 | `data-v1`（去哪儿聚合，92 车） | `data/processed/shita_timetable_2026-10-20_data-v1.json`（契约 2.0.0，保留） |

三者独立演进：换数据不改页面、加字段升契约 MINOR、页面改版不动数据文件。

## 2. 数据版本

| 版本 | 服务日 | 行数 | CSV SHA-256 | JSON SHA-256 | 说明 |
|---|---|---|---|---|---|
| `data-v0-draft` | 2026-10-19 | — | — | — | 采集草稿，已被 v1 取代，仅保留 uncertainties/sources |
| `data-v1` | 2026-10-20 | 1132 | `a061ad4a36ac825ef74c6702b552501b3c3fa9f9119e3032f6269c071a9215e6` | `5692feb075a2a57f19a84cff5592cafaaff676e529992ecbfc6cbfa5ded0c0b4` | 92 车；86 可绘 / 6 阻断；48 条待核。2026-10-19 按契约 v2.0.0 重新生成（时刻未变，站点顺序与石家庄北接轨点修正） |
| `data-v2` | 2026-10-20 | 2125 | `7abfc727dd33b7c9a57374fb75bd02f0bf7957524ba2c8bc72fe6d1e6cd1a88e` | `2449cea12494315ec6175530fd10409afafe4b2be30a229945008cb31d44f0d0` | **159 车；155 可绘 / 4 阻断**；12306 官方前端直采，2 跳过（K603/K604 京原线）、7 条告警。与 v1 同编号的 88 车逐站时刻 100% 一致，多出 98 车（含 G379/G380 走廊内通过不停车） |

重建命令：`python scripts/clean_timetable.py`（v1，确定性输出，重跑哈希不变）；`SHITA_PROFILE=v2 python scripts/clean_timetable.py`（v2）。

## 3. 契约版本

| 版本 | 日期 | 变更 |
|---|---|---|
| `1.0.0` | 2026-10-19 | 首次冻结：7 段式结构（meta/provenance/stations/trains/segments/warnings/stats）、`abs_minute` 时间模型、稳定 ID、`usable_for_frontend` 闸门、`warnings` 码表 |
| `2.0.0` | 2026-10-19 | **破坏性**：`line_positions` → `place`（示意坐标 x/y、沿线 sequence、支线 branch_of/branch_order/link）；石家庄/石家庄北、太原/太原南 拆为独立站；新增联络线/支线链接类型 |
| `2.1.0` | 2026-10-19 | **MINOR（放宽约束）**：`day_offset` 与 `abs_minute` 允许为负，表示服务日 00:00 之前；`coverage.abs_minute_min` 同步放宽。用于 data-v2 中「前一日始发、当日经过走廊」的长途车 |

兼容规则见 `docs/data-contract.md §9`。

## 4. 页面版本与模块

| 模块 | 版本 | 文件 | 说明 |
|---|---|---|---|
| 运行图 | 1.1.0 | `js/marey-chart.js` | 阶段4；纵轴按 place 拆分同城车站 |
| 线路示意 | 1.2.0 | `js/line-diagram.js` | 阶段5；横平竖直轨道 + 沿轨寻路插值 |
| 播放器 | 1.0.0 | `js/player.js` | 阶段6；单 rAF，1x = 2 分钟/秒 |
| 筛选/详情 | 1.0.0 | `js/interactions.js` | 阶段7；纯函数 + 详情渲染 |
| 页面 | web-v1.3.0 | `index.html` | 阶段7 组装；43 项端到端验收 |

## 5. 报告索引

| 报告 | 路径 |
|---|---|
| 清洗校验 | `reports/validation/validation_2026-10-20_data-v1.md` |
| 清洗日志 | `reports/validation/cleaning_log_2026-10-20_data-v1.md` |
| 契约冻结校验 | `reports/validation/contract_v1.0.0_validation.md` |
| 测试报告 | `reports/validation/test_report_2026-10-19.md` |
| 待核清单 | `reports/manual_review/manual_review_2026-10-20_data-v1.csv` |
| 来源记录 | `reports/sources/sources_2026-10-20_data-v1.md` |
