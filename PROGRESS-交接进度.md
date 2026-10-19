# 石太客专·阳大铁路 运行图项目 — 进度与交接文档

> 用途：跨 agent 交接的单一进度源。每个阶段完成后，由接手 agent 更新本表与时间戳。
> 最后更新：2026-10-19 ｜ 当前阶段：**数据源切换至 12306 官方前端（data-v2 / 契约 2.1.0 / web-v1.4.0）**｜ 下一步：按需调试 ｜ 备料：全部完成
> 总纲文件：`石太客专运行图可视化项目：分阶段提示词工程.md`（所有硬约束以它为准）

## 0. 项目一句话

最终交付一个**本地可打开的原生 HTML/CSS/JS/SVG 页面**（无框架、无 CDN、无构建），两个联动视图 + 统一播放器：拖动时间线，石太客专与阳大铁路上的车次同步移动。

- 视图A 线路示意：`太原/太原南 — 阳泉北 — 石家庄/石家庄北`（石太客专）＋ `阳泉北 — 阳泉东`（阳大铁路），阳泉北高亮，上下行分色+箭头/线型。
- 视图B Marey 运行图：横轴绝对分钟（当日00:00—次日06:00），纵轴车站，每车折线，当前时间竖线。
- 播放器：播放/暂停、拖时间轴、±1分钟、0.5/1/2/5x、左右键逐分钟、空格暂停；暂停即停，不回绕。

## 1. 阶段总览（对照提示词0–10）

| 阶段 | 提示词 | 状态 | 负责通道 | 产出/落点 |
|---|---|---|---|---|
| 项目总控规则 | 0 | ✅ 已采纳（无单独输出） | 主代理 | 全局约束已落实 |
| 数据采集 | 1 | ✅ 完成（92交路/1132行，已回读校验） | 采集组织代理 | `data/raw/shita_train_timetable_2026-10-20_data-v1_draft.csv`、sources、uncertainties |
| 数据清洗 | 2 | ✅ 完成（1132行→JSON；86车可绘/6车阻断；48条复核） | 代码助手 | `scripts/clean_timetable.py`、`data/processed/*.json`、validation 报告、manual_review CSV |
| JSON 契约 | 3 | ✅ 完成（v1.0.0 冻结；Schema 2020-12 + synthetic 样例 + 校验器） | 代码助手 | `docs/data-contract.md`、`docs/schema/*.json`、`data/test-fixtures/synthetic_contract_sample.json`、`scripts/validate_contract.py` |
| Marey 图 | 4 | ✅ 完成（86 车可绘；时间/站轴/事件/缩放；18 项验收） | 代码助手 | `js/marey-chart.js`、`marey-demo.html`、`css/demo.css`、`docs/modules/marey-chart.md` |
| 线路动画 | 5 | ✅ 完成（86 标记；插值/停站/终到/跨日；15 项验收） | 代码助手 | `js/line-diagram.js`、`line-demo.html`、`docs/modules/line-diagram.md` |
| 播放器 | 6 | ✅ 完成（单 rAF；0.5/1/2/5x；边界/键盘/销毁） | 代码助手 | `js/player.js` |
| 筛选交互 | 7 | ✅ 完成（方向/车型/车站；两视图同源；详情联动） | 代码助手 | `js/interactions.js`、`index.html`、`css/app.css` |
| 验收测试 | 8 | ✅ 完成（E2E 38 + 纯函数 16 + 契约；用例表/模板/报告） | 代码助手 | `scripts/test_e2e.mjs`、`scripts/test_pure.mjs`、`docs/test-plan.md`、`reports/validation/test_report_2026-10-19.md` |
| 调试审查 | 9 | 🔵 按需（开发期已修复标签重叠/命中区/共用槽位站名等问题，无独立交付） | 按需 | 缺陷报告模板 `docs/templates/` |
| 部署存档 | 10 | ✅ 完成（README/来源/版本/归档清单；明确 file:// 限制） | 代码助手 | `README.md`、`docs/data-sources.md`、`docs/version-history.md`、`docs/archive-manifest.md` |

状态图例：✅完成 🔵进行中 ⬜未开始 ⛔阻塞

### 备料进度（不依赖采集结果，提前做）
- ✅ #1 车站主数据骨架 → `docs/stations.md`
- ✅ #2 JSON 契约草稿 → `docs/data-contract.md` + Schema
- ✅ #3 验收测试清单框架 → `docs/test-plan.md`
- ✅ #4 file:// 加载方案对比 → 契约 §8 + README（结论：走本地 HTTP，离线包未实施）
- ✅ #5 线路示意布局草图 → `js/line-diagram.js` 的 `buildLayout`

### 提示词1 采集结果摘要（已回读校验通过）
- 92 个物理交路 / 1132 行；up46/down46/unknown0；车型 高铁347·动车437·快速234·直达特快72·市郊32·城际10；day_offset=1 共125行；km 全留空。
- 校验：11列一致、站序连续、无00:00填充、始发空arr/终到空dep规则正确、同车同站冲突0。
- **待12306复核**（详见 uncertainties v1）：未核实21车、停运未录5车、来源冲突1处(G2637/G2640滨海北/西)、跨日待核7处、方向校正6车、D1095/D1096与C799/C800线路衔接待核；ip.cn声称157趟仅渲染约80，可能遗漏。
- 数据为第三方现行图，**全部需12306官方复核**，未访问12306、未编造。

## 2. 已确认口径（用户拍板，勿擅自改）

1. **非历史存档**：取消"车次号更新前历史版本"，改为现行图（第三方页 2026-10-20 前后）。文档/文件不得再写"历史版本/调图前"。
2. **来源**：第三方公开平台（去哪儿 train.qunar.com、携程 trains.ctrip.com 等），每条时刻标注"需12306官方复核"；**不绕登录/验证码/反爬，不高频请求**；12306 不直接抓。
3. **车型全收，含普速 K**：K 多走石太老线（非客专），remark 标"走石太老线，非客专"。
4. **长交路录全程**：成都东/深圳坪山/上海虹桥/杭州西/乌鲁木齐等远端站也录入，供查时刻表；主图只画目标两区间。
5. **方向定义**（国铁集团）：进京/支线到干线=up（双数），离京/干线到支线=down（单数）；**奇偶仅交叉参考，禁止凭奇偶反推**，以实际去向/页面为准，存疑 unknown。石太段 石家庄→太原南=down，反向=up。
6. **时间统一绝对分钟**：`abs = minute_of_day + day_offset*1440`，次日00:10=1450，禁止 HH:mm 字符串比跨日。
7. **file:// 加载方式待阶段10定**：独立JSON需本地HTTP服务，或把数据嵌入数据脚本做双击单文件；不得谎称双击可用。

## 3. 采集期已处理事项（明细见 uncertainties v1）

- **套跑/中途换号去重**：已按物理交路合并，另一编号不进 CSV，完整换号对照见 uncertainties §7。
- **停运剔除**：G4693、D1617–D1620 未录；D917/D918 隔日开行已在 remark 标注。
- **未核实21车**：未填造，列 uncertainties §1。
- **C799/C800 现行已核**（2026-10-20 去哪儿）：
  - C800 up：阳泉东07:28—阳泉北08:03/08:05—石家庄北08:59/09:06—保定10:19/10:22—北京丰台11:39。
  - C799 down：北京丰台14:13—保定15:26/15:34—石家庄北16:59/17:05—阳泉北18:09/18:11—阳泉东18:40。

## 4. CSV 固定表头（11列，顺序不得改）

```
train_no,direction,train_type,station_order,station,arr_time,dep_time,day_offset,km,is_stop,remark
```
缺失留空，**禁止填 00:00**；始发无到达、终到无出发；km 第三方多无，留空。

## 5. 目录现状

```
石太客专列车运行图/
├─ 石太客专运行图可视化项目：分阶段提示词工程.md   # 总纲
├─ PROGRESS-交接进度.md                            # 本文件
├─ data/raw/            # 原始/草稿CSV（只读，禁止覆盖）
├─ data/processed/      # 契约化 JSON（前端唯一数据源）
├─ data/test-fixtures/  # synthetic 测试数据（data_kind=synthetic，禁与真实混）
├─ scripts/             # clean_timetable.py（清洗+契约成型）、validate_contract.py（校验）
├─ index.html           # 最终页面（两视图 + 播放器 + 筛选 + 详情）
├─ js/                  # marey-chart / line-diagram / player / interactions（均 1.0.0）
├─ css/                 # demo.css（两个演示页共用）
├─ marey-demo.html      # 阶段4 最小接入示例（非最终页面）
├─ line-demo.html       # 阶段5 最小接入示例（非最终页面）
├─ reports/sources/     # 来源记录
├─ reports/validation/  # 清洗校验报告 + 契约冻结校验报告
├─ reports/manual_review/ # 待核实/冲突（含 uncertainties v1）
└─ docs/                # data-contract.md、schema/、stations.md
```

## 6. 提示词2 数据清洗：已完成（2026-10-19）

产物：
- `scripts/clean_timetable.py`（可重复执行，UTF-8 严格校验、固定表头校验、退出码 0/1/2）
- `data/processed/shita_timetable_2026-10-20_data-v1.json`（契约化后 2,271,579 B，SHA-256 `b22925a3…`，无时间戳、排序显式，重跑字节一致）
- `reports/validation/validation_2026-10-20_data-v1.md`、`reports/validation/cleaning_log_2026-10-20_data-v1.md`
- `reports/manual_review/manual_review_2026-10-20_data-v1.csv`（48 条，含行号/车次/车站/证据/出处）

结果要点（口径见 validation §3）：
- 结构全通过：1132 行、92 车、300 站名、0 重复、0 文件内冲突、0 非法时刻、0 个 00:00 填充、0 边界/站序异常。
- 疑似跨日 7 处 / 6 车（K373/K374/K565/K609/K730/K866），与 uncertainties §4 逐条一致；保留 day_offset=0 原值，**未自动改 1**，该 6 车 `usable_for_frontend=false`。
- 可用 86 车：77 车零标注、9 车带待核标注（6 方向校正中未阻断的 4 车 + D1095/D1096 衔接 + K585/K587 站名 + G2637 来源冲突）。
- 21 个未核实车 + 5 个停运车只在 `known_gaps` 登记编号，**未生成任何时刻**。
- 原始 CSV 未改动（SHA-256 `a061ad4a…`）；JSON 已用 Python `json` 与 Node `JSON.parse` 双解析通过。

## 7. 提示词3 JSON 契约：已完成（v1.0.0 冻结）

产物：
- `docs/data-contract.md`（字段字典、时间模型、ID 规则、版本规则、加载方案、设计取舍）
- `docs/schema/shita-timetable.schema.json`（JSON Schema Draft 2020-12）
- `data/test-fixtures/synthetic_contract_sample.json`（上下行各一车、阳泉北、停站、通过站、跨日、km 缺失；`data_kind=synthetic`）
- `scripts/validate_contract.py`（Schema + 11 项语义不变量）
- `reports/validation/contract_v1.0.0_validation.md`（校验输出 + 契约化前后回归）

契约要点：
- 顶层 7 段：`meta / provenance / stations / trains / segments / warnings / stats`；前端只读此文件，不解析 CSV。
- 时间只用 `abs_minute`；`minute_of_day` 仅供展示；缺失一律 null。
- `segments` 1988 条（run 1040 + dwell 948），与 stops 时刻逐条校验一致。
- `stations` 308 条（本批出现 300 + 骨架无车 8）；`line_positions.order` 是示意槽位，**不是公里数**。
- `generated_at` 恒 null（保证字节级可复现），溯源用 `build_id`。
- 验收：真实数据与 synthetic 样例均 Schema 0 错、11 项不变量全 PASS；契约化前后 1132 站记录 **0 字段差异**。

## 8. 提示词4 Marey 运行图：已完成（模块 v1.0.0）

产物：
- `js/marey-chart.js`（无依赖，UMD 双导出，Node 可直接 require 单测）
- `marey-demo.html` + `css/demo.css`（最小接入示例，**非最终页面**）
- `docs/modules/marey-chart.md`（接口、轴算法、断线规则、验收记录、已知限制）

接口（后续阶段按此对接，勿改名）：
`initMareyChart(container, data, options)` / `setCurrentTime(absMinute)` / `setVisibleTrains(ids|null)` /
`setDomain(min,max)` / `setOption` / `resize` / `destroy` / `getLayout`；事件 `trainselect`（detail 含 trainId/trainNo/direction）。
**播放器只调 `setCurrentTime`，不要碰 DOM。**

关键实现：
- 纵轴由 `line_positions` 生成 5 行：`石家庄/石家庄北 → 阳泉北 → 阳泉东(支线) → 平定(支线) → 太原南/太原`；共用槽位合并、支线插在阳泉北之后。
- 默认时间域 `[0,2700]`（不用总纲的"次日06:00"，会截掉 166 个时刻）；提供 6h/3h/1.5h 窗口缩放，刻度按像素自适应。
- 未映射站/缺时刻 → **断线**，不跨缺口连线；通过站 arr==dep 只产生一个点。
- `setCurrentTime` 只改光标图层 transform，实测 `<path d>` 与 SVG 子节点数不变。
- 每条折线有 10px 透明命中区（1px 细线点不中）+ `tabindex` 键盘可选。

验收：Playwright(headless Edge) 18 项全 PASS（含真实鼠标点击、键盘、筛选计数、窄屏重绘）。

## 9. 提示词5 线路动画：已完成（模块 v1.0.0）

产物：
- `js/line-diagram.js`（无依赖，UMD 双导出）
- `line-demo.html`（最小接入示例，复用 `css/demo.css`）
- `docs/modules/line-diagram.md`（坐标算法、七状态机、接口、15 项验收）

接口：`initLineDiagram(container, data, options)` / `setLineTime(absMinute)` / `setVisibleTrains(ids|null)` /
`setSelectedTrain(trainId|null)` / `resize` / `destroy` / `getLayout` / `getActiveTrains` / `getTrainStates`；
事件与 Marey 一致：`trainselect`（detail 含 trainId/trainNo/direction）。

关键实现：
- 坐标由 `line_positions` 生成：主轴 6 槽位等分；阳大支线从阳泉北斜下后**竖向**按 order 展开；共用槽位合并（石家庄/石家庄北、太原/太原南）。
- 只画"相邻且两端都在图上"的 segment；通道外站点整段跳过，不跨缺口连线。
- 七状态：`off_corridor / pending / between / moving / stopped / terminal / left`；`terminal` 半透明停在终点，`left` 消失。
- `setLineTime` 只改 transform/opacity/display；标签同层错位 3 级，终到车不常驻标签。
- 上下行用圆点/菱形 + 颜色双编码。

验收：Playwright 15 项全 PASS（含跨日 1450、K1331 停在石家庄、真实鼠标点击、方向筛选、在线计数一致）。

## 10. 提示词6 播放器：已完成（v1.0.0）

`js/player.js`：
- 单一 rAF 循环；1x = **2 模拟分钟/秒**（`minutesPerSecond` 常量，唯一来源）；0.5/2/5x 同比例。
- 首帧只记时间戳不推进；`maxFrameSeconds=0.25` 防切标签页跳变；到边界停在 max 不回绕。
- `seek` 即时生效；`step(±1)` 精确 1 分钟；键盘空格/←/→，焦点在 input/select/button 时让行。
- `destroy()` 取消 rAF 并移除监听。
- 验收：E2E-03~16（含 4 档倍速、边界、destroy、反复播放不叠加）。

## 11. 提示词7 统一页面：已完成（web-v1.0.0，2026-10-19 改版为 web-v1.1.0）

`index.html` + `js/interactions.js` + `css/app.css`：
- 两视图同屏：Marey（560px）+ 线路示意（360px），共用播放器时间。
- 筛选：方向 / 车型（按数据生成）/ 车站在该站停站、通过；一次计算 ids，两个视图同源，保证可见集合一致。
- 选中联动：任一视图点击 → 两图同时高亮 + 详情；被筛掉时清空并提示。
- 详情：逐站到发、`day_offset`、站型、备注、待核告警；缺失显示「未知/始发/终到」。
- 空结果横幅；`file://`、非法 JSON、契约主版本不匹配都有明确 fatal 提示。
- 验收：E2E-01/17~31（同屏联动、筛选、空状态）。

## 12. 提示词8 测试与提示词10 存档：已完成

- 测试：`scripts/test_e2e.mjs`（38 项）+ `scripts/test_pure.mjs`（16 项）+ 契约校验；用例表 `docs/test-plan.md`，报告 `reports/validation/test_report_2026-10-19.md`；缺陷/验收模板在 `docs/templates/`。
- 新增 synthetic 夹具：`synthetic_crossday_tiny.json`（23:50→次日 00:10），与真实数据严格分离。
- 存档：`README.md`、`docs/data-sources.md`、`docs/version-history.md`、`docs/archive-manifest.md`；明确 `file://` 不可用，原始 CSV 不公开分发。
- 未执行：MANUAL-01 长时播放、MANUAL-02 人工视觉检查（已在报告中标注）。

## 13. 站点拓扑改版（2026-10-19，契约 v2.0.0）

用户要求：线路图按真实方位（上北下南、左西右东）排布；太原/太原南、石家庄/石家庄北分开；石家庄—石家庄北用虚线表示联络线；运行图也能区分不同到站。

- **数据模型**：`stations[].line_positions` → `stations[].place`（`x/y` 归一化示意坐标、`sequence` 沿线顺序、`branch_of/branch_order/link`）。石家庄/石家庄北、太原/太原南不再共用槽位。
- **顺序依据**：数据里东行是 `太原南 → 太原 → 阳泉北`（G622/D1096 等 5 车双停可证），西行反之。
- **线路图**：主线折线 `太原南 → 太原 → 获鹿 → 井陉北 → 阳泉北 → 东凌井 → 石家庄`；石家庄北经虚线联络线挂石家庄；阳泉东等阳大支线挂阳泉北。
- **运行图**：7 行（石家庄北、石家庄、阳泉北、阳泉东、平定、太原、太原南）；双停车次在太原南/太原两行间画竖段（糖葫芦）。
- **版本**：契约 2.0.0（破坏性）、web-v1.1.0、marey/line 模块 1.1.0；data-v1 重新生成（时刻未变，JSON hash 变更）。
- **验收**：E2E 41 项（新增纵轴 7 行、联络线虚线、一城双停）、纯函数 19 项（新增坐标方位与支线挂接）全 PASS。报告：`reports/validation/contract_v2.0.0_validation.md`、`test_report_2026-10-19.md`。

### 13.1 横平竖直轨道改版（web-v1.2.0 / line 1.2.0）

- 站点坐标改为网格对齐：主线共 `y=0.36`、支线共 `x=0.52`，太原南在太原正南、石家庄北在石家庄正北。
- `line-diagram` 增加**轨道图**：`edges` + 邻接表 + `route(from,to)`（BFS 唯一路径）；区间位置改为**沿折线按弧长取点**，不再两站直线插值。
- 例：C800 阳泉北→石家庄北 走 阳泉北→东凌井→石家庄→石家庄北，不再斜穿。
- 坐标未对齐时 `orthoGeometry` 兜底成「先横后竖」，杜绝斜轨。
- 小站补灰字标签；车次标签错层 4 级。
- 验收：E2E 43 项（+轨道无斜线、+车底贴轨）、纯函数 22 项（+轨道正交、+沿轨经获鹿、+0 像素偏离）全 PASS。

### 13.2 站序与石家庄北接轨修正（web-v1.3.0）

用户指图纠正：
- 正确站序为 `太原 → 东凌井 → 阳泉北 → 井陉北 → 获鹿 → 石家庄`（此前把获鹿/井陉北放到了阳泉北西侧、东凌井放到了东侧，反了）。
- 石家庄北不在客专正线，经**石太普铁**在**获鹿**接轨：`branch_of` 由「石家庄」改为「获鹿」，图上虚线画在获鹿—石家庄北之间。
- 石家庄站与石家庄北之间不再画任何连线（两站无同车双停）。
- 运行图纵轴相应变为：石家庄、石家庄北、阳泉北、阳泉东、平定、太原、太原南（获鹿无停站不单独成行，但支线子站仍按位置插入）。
- 验收：E2E 43、纯函数 22 全 PASS；新增「联络线端点为获鹿/石家庄北」「阳泉北→石家庄北 经获鹿且不过石家庄」断言。


## 14. 数据源切换：12306 官方前端（2026-10-19，data-v2 / 契约 2.1.0）

用户反馈「数据不精准」，要求从前端页面（`kyfw.12306.cn/otn/leftTicket/init`）爬取并更新。

### 14.1 采集通道（与浏览器 F12 完全一致）
- `GET /otn/leftTicket/init` → Cookie + 动态 `CLeftTicketUrl`（本次 `leftTicket/queryG`）
- `GET /otn/{CLeftTicketUrl}` → 区间车次、始发/终到、到发时刻、历时
- `GET /otn/czxx/queryByTrainNo` → 按物理交路取**全程经停站**
- `GET /otn/resources/js/framework/station_name.js` → 电报码→站名（3404 站）
- 20 组 OD（太原/太原南/阳泉北/阳泉东 ↔ 石家庄/石家庄北，另加太原 ↔ 北京西/北京丰台补「通过不停」标杆车）取并集 → 159 个物理交路 → 逐车查全程，2 跳过（K603/K604 走京原线）
- 不绕验证码、不登录、每请求间隔 1.1–1.5s；原始响应留证 `data/raw/_12306_raw/2026-10-20/`

### 14.2 关键发现
- **`train_no` 是物理交路号**：一趟车中途换号时，leftTicket 按区段返回多个车次号但共用 `train_no`；`queryByTrainNo` 只返回全程一次，且只在首行标注始发车次号 → 本批按交路录一条，别名写 remark。
- **`day_offset` 出现负值**：v2 录的是「10-20 经过走廊」的车，长途车前一日始发（D16 成都东 10-19 15:37），故 199 条为负。契约 2.1.0 放宽 `day_offset`/`abs_minute` 可为负。
- **车型不能直接用 `train_class_name`**：12306 对 C 字头返回「动车」、S 字头返回「快速」，改按车次号前缀判定（G/D/C/S/Z/T/K）。
- **停站跨午夜无法用单值 `day_offset` 表达**：K214/K546/K892/T175 共 4 车阻断（v1 是 6 车跨日未定）。

### 14.3 结果
| 项 | v1 | v2 |
|---|---|---|
| 车次 | 92 | **159** |
| 站记录 | 1132 | **2125** |
| 可绘制 | 86 | **155** |
| 阻断 | 6 | 4 |
| 来源 | 去哪儿聚合 | 12306 官方前端 |

- **88 个同编号车次逐站到发时刻 100% 一致**（0 差异）；v2 多 98 车（含补采的 G379/G380 走廊通过不停车）（v1 漏采的 K/T/Z 与部分 D/G/C）；v1 独有仅 D918（12306 显示 10-20 当日不开行）。
- 3 处仅编号不同：G1861→G1864、G1955→G1958、G2637→G2640（站表与时刻完全一致）。
- 昔阳已映射到骨架「大寨(昔阳)」坐标，K585/K586 南段可完整绘制。

### 14.4 产物
- `scripts/collect_12306.py`（采集，支持 `--reuse-raw` 复用缓存）
- `data/raw/shita_train_timetable_2026-10-20_data-v2_12306.csv`（SHA-256 `7abfc727…`）
- `data/processed/shita_timetable_2026-10-20_data-v2.json`（SHA-256 `2449cea1…`）
- `reports/sources/sources_2026-10-20_data-v2.md`、`reports/sources/collect_2026-10-20_data-v2.json`
- `reports/manual_review/data-v1_to_v2_diff.md`（含编号变更自动配对）
- `scripts/clean_timetable.py` 增加 `SHITA_PROFILE` 切换：v1 常量与版本号原样保留，v1 重跑仍字节一致
- 测试：纯函数 22 项、E2E 43 项、契约校验全部 PASS（断言改为从数据动态取车数，避免换数据就红）

## 15. 录制页 record.html（2026-10-19，web 同批）

用户要求"全屏布置运行线路图，可以控制播放、进度条、倍速，类似视频播放器"，方便录屏。（第一版误以 Marey 为主视图，用户纠正"不是时刻表图，是那个可视化图"后改为**线路动画为主**。）

- **布局**：图铺满视口。Marey 用实际像素 1:1；**线路用「逻辑 viewBox ÷ zoom（默认 2）+ CSS 拉伸回容器」**，车底/轨道/站名等全部元素等比放大且矢量无损（`#viewLine svg{width/height:100%}` 覆盖内联尺寸，SVG2 geometry property）。底部悬浮胶囊控制条（播放/进度/时间/倍速/视图切换/全屏）。
- **录制友好**：鼠标静止 2.6s → 控制条与光标一起隐去；`H` 键锁定纯画面（再按恢复）；`F` 全屏；右下水印可用 `?corner=0` 关闭。
- **视图切换**：`line`（默认）/ `marey` / `both`（Marey 62% + 线路 38%），非 Marey 模式为 HUD 预留 64px 高度避免遮挡"昔阳"。`line-diagram.js` 新增 `showCaption` 选项（录制时关掉底部操作说明）。
- **URL 参数**：`view` / `t`（初始时刻）/ `from`+`to`（时间域，默认 180–1920 覆盖全部走廊时刻）/ `autoplay` / `speed` / `fs`+`fl`（字号倍率，默认 1.35/1.25）/ `corner`。
- **模块改动**：`marey-chart.js` 与 `line-diagram.js` 新增 `fontScale` 选项（默认 1，向后兼容，index.html 无感）。
- **播放边界**：进度拖到终点自动停、播完再按播放从头开始，沿用 `player.js` 既有语义；按任意键会唤醒控制条。
- **录制可读性二调**（用户反馈"线条太细、站名太小"）：`zoom` 默认 2→3（车底 30px / 轨道 27px / 站名 36px），CSS 再加粗轨道（main 9 / branch 7 / connecting 5 逻辑宽度）；左上角常驻 72px 大号当前时刻（`bigtime=0` 可关，跨日自动标「次日」，不随控件隐去）。
- **防重叠**：Marey 加 `showLegend` 选项（录制页关图例，`margin.top` 加到 100 让位）；CSS 隐藏线路内建图例 `.ld-legend` 与 Marey 光标小时刻（`.mc-cursor rect/text`，只留竖线）——时间信息统一由左上角大时刻承担。
- **枢纽站主题化**（用户指定）：CSS 按 `.ld-station[data-station=…]` 覆盖六站站名——字号 ×2（逻辑 24px→显示 72px）+ 白描边防压线；配色 太原/太原南=#1e3a8a 深蓝、石家庄/石家庄北=#14532d 深绿、阳泉北/阳泉东=#c2410c 深红（沿用阳泉北高亮色）。纯 CSS 实现（SVG presentation attribute 可被 CSS 覆盖），index.html 不受影响。
- **验收**：`scripts/test_record.mjs`（playwright 截图 + 行为断言：155 车渲染、双图尺寸、播放推进、边界停、H 键锁定、自动隐藏）全部通过；index 43 项 E2E 无回归。
- **一键启动**：根目录 `start.bat`（**GBK 编码保存**，UTF-8 中文 bat 在 cmd 下会解析错乱）。自动找可用 Python（绕开 Store 占位程序）、检测端口占用（已占用则只开浏览器）、`record`/端口参数。实测 8010 端口 200。

## 16. 交接检查点（新 agent 先读）

- 先读本文件 §2 口径、§4 表头、总纲对应阶段提示词；再读 `reports/manual_review/` 未决项。
- 未核实项不得补造；缺依据就留空并进 uncertainties。
- 每次只做当前阶段，最小改动，不覆盖无关文件。
