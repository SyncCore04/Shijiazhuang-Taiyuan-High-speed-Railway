# JSON 数据契约 · 石太客专 + 阳大铁路运行图

> 版本 **v2.1.0（2026-10-19 修订：放宽 `day_offset` / `abs_minute` 可为负，配合 12306 官方数据源）**
> 上一版 v2.0.0（站点拓扑拆分 + 示意坐标）仍适用于 `data-v1.json`。
> Schema：`docs/schema/shita-timetable.schema.json`（JSON Schema Draft 2020-12）
> 真实数据：`data/processed/shita_timetable_2026-10-20_data-v2.json`（`meta.data_kind = "real"`，12306 官方前端）
> 对照数据：`data/processed/shita_timetable_2026-10-20_data-v1.json`（去哪儿聚合，契约 2.0.0）
> 测试数据：`data/test-fixtures/synthetic_contract_sample.json`（`meta.data_kind = "synthetic"`，禁止当真）
> 校验器：`scripts/validate_contract.py`　｜　冻结后任何字段增删改都必须升版本，见 §9。

---

## 1. 契约定位

前端**只读本契约定义的 JSON**，不解析 CSV、不自行推算跨日、不自行拼装区间。

数据链只有一条：

```
data/raw/*.csv  →  scripts/clean_timetable.py  →  data/processed/*.json  →  前端
                          （清洗 + 契约成型）          （本契约）            （只读）
```

清洗脚本同时承担"清洗"和"契约成型"两件事，避免出现"清洗产物 → 另一份转换产物"的双份真相。

---

## 2. 顶层结构

```json
{
  "meta":       { ... },   // 版本、时间基准、覆盖范围、校验状态
  "provenance": { ... },   // CSV 校验和、清洗器版本、文档清单、免责声明
  "stations":   [ ... ],   // 站点主数据（含骨架里本批无车的站）
  "trains":     [ ... ],   // 车次 + 完整停站序列
  "segments":   [ ... ],   // 区间（运行 / 停站），供 Marey 图与线路动画直接消费
  "warnings":   [ ... ],   // 结构化待核/冲突（含未录入车次的登记）
  "stats":      { ... }    // 供 UI 显示与自检的计数
}
```

数组顺序是**确定性**的：`stations` 按「在库优先 → 停站数降序 → 站名」；`trains` 按车次自然序（`D15 < D1096`）；`segments` 按车次自然序 + 站序；`warnings` 按严重度 → 码 → 车次 → 站序。**前端不得依赖数组下标作为 ID**。

---

## 3. 时间模型（全局唯一口径）

| 概念 | 定义 |
|---|---|
| `arr_time` / `dep_time` | 原始 `HH:mm`（00:00–23:59），仅作展示与回溯；**禁止用于比较** |
| `minute_of_day` | `HH*60 + MM`，取值 **0–1439** |
| `day_offset` | 相对基准服务日的整天数，整数；v1 通常 0/1，**v2 可为负**（见下） |
| `abs_minute` | `minute_of_day + day_offset * 1440`，**唯一可用于排序、绘图、比较的时间** |

- 基准：`meta.time_origin = 基准服务日 2026-10-20 00:00（绝对分钟 0）`，时区 `Asia/Shanghai`。
- 次日 00:10 → `minute_of_day=10`、`day_offset=1`、`abs_minute=1450`。**不得压回 10**。
- 缺失时刻一律 `null`：`minute_of_day` 与 `abs_minute` 的对应项同时为 `null`，不得填 0。
- **v2.1.0 起 `day_offset` 与 `abs_minute` 可为负**：data-v2 录的是「服务日当天经过走廊」的列车，长途车可能在前一日就从远端始发（如 D16 成都东 10-19 15:37），其始发段 `day_offset=-1`、`abs_minute<0`。负值表示**基准服务日 00:00 之前**，前端只绘制时间域内的部分，不得裁掉或平移。
- **同一站 `arr` 与 `dep` 共用该站 `day_offset`**：停站跨午夜（如 23:57 到、00:07 开）无法用单值表达，此类车在本批标记 `usable_for_frontend=false`（K214/K546/K892/T175），不篡改时刻。
- v1 覆盖 `abs_minute` 14–2663；v2 覆盖 **-1930（10-19 15:50）– 3586（10-22 11:46）**，`meta.coverage` 按实际值输出，前端横轴按此扩展。

---

## 4. ID 规则

| ID | 生成规则 | 示例 | 稳定性 |
|---|---|---|---|
| `station_id` | `st:` + 站名 | `st:阳泉北` | 站名不变则不变；**含中文，只能当 Map 键，不能直接做 CSS 选择器** |
| `train_id` | `tr:` + 车次号 | `tr:C800` | 一个物理交路一个编号；若未来出现同号不同交路，将追加后缀并升 minor 版本 |
| `segment_id` | `sg:{车次号}:{三位序号}:{run\|dwell}` | `sg:C800:003:run` | 序号为该车区间顺序（从 1 开始），站序不变则不变 |
| `warning_id` | `RV-{三位序号}` | `RV-007` | 同一批复核项排序稳定 |

`stations[].corridor_ids` 保存 `docs/stations.md` 里的短 ID（`yqbei`、`sjz` 等），供与设计稿/文档对齐；**不替代** `station_id`。

---

## 5. 字段字典

### 5.1 `meta`

| 字段 | 类型 | 必填 | 含义 / 允许值 | 缺失处理 |
|---|---|---|---|---|
| `schema_version` | string | 是 | 语义化版本，正则 `x.y.z` | 不允许缺失 |
| `dataset_id` | string | 是 | 数据集标识 | 不允许缺失 |
| `data_version` | string | 是 | 数据批次，如 `data-v1` | 不允许缺失 |
| `history_version` | string\|null | 是 | 历史存档版本；本项目为现行图，恒 `null` | 允许 null |
| `history_status` | enum | 是 | `current_timetable_not_archive` \| `archived_snapshot` | 不允许缺失 |
| `data_kind` | enum | 是 | `real` \| `synthetic` | 不允许缺失 |
| `generated_at` | string\|null | 是 | ISO 时间；**本数据集恒 `null`**，理由见 §11.1 | 允许 null |
| `generated_at_note` | string\|null | 否 | 解释为何为 null | — |
| `build_id` | string | 是 | `CSV SHA-256 前 12 位 + 清洗器版本`，替代构建时间做溯源 | 不允许缺失 |
| `time_unit` | enum | 是 | 恒 `minute` | — |
| `timezone` | enum | 是 | 恒 `Asia/Shanghai` | — |
| `time_origin` | string | 是 | 绝对分钟 0 点的定义 | — |
| `source_summary` | object | 是 | `primary` / `access_date` / `query_date` / `official_verification` / `cross_check` | 不允许缺失 |
| `coverage` | object | 是 | `service_date`、`abs_minute_min/max`、`trains_total`、`stations_total`、`lines` | 不允许缺失 |
| `validation_status` | object | 是 | `state`(`pass`\|`pass_with_open_reviews`\|`fail`)、`usable_trains`、`blocked_trains`、`open_warnings` | 不允许缺失 |

### 5.2 `provenance`

| 字段 | 类型 | 含义 |
|---|---|---|
| `csv.file / sha256 / bytes / rows / encoding / line_endings / header` | — | 输入 CSV 的只读身份信息，用于事后核对是否换了源 |
| `cleaner.script / version` | string | 生成该 JSON 的脚本与版本 |
| `documents[]` | array | `{path, role}`，列出与本数据相关的来源/复核/骨架/契约文档 |
| `caveats[]` | array | 必须在 UI 图注中体现的免责声明（第三方聚合、需 12306 复核、km 全空等） |

### 5.3 `stations[]`

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `station_id` | string | 是 | 见 §4 |
| `name` | string | 是 | CSV 站名（未做归一，`昔阳`≠`大寨(昔阳)`） |
| `in_dataset` | bool | 是 | 本批 CSV 是否出现该站（骨架站可能为 false） |
| `is_corridor` | bool | 是 | 是否属于石太/阳大目标通道（有 `place` 即为 true） |
| `is_highlighted` | bool | 是 | 图上高亮，仅阳泉北为 true |
| `km` | number\|null | 是 | **恒 null**（第三方无里程），禁止用站序代替 |
| `station_order` | integer\|null | 是 | **全局站序无定义，恒 null**；逐车站序见 `trains[].stops[].station_order` |
| `place` | object\|null | 是 | 示意坐标与线路挂接：`{line, sequence, x, y, role, branch_of, branch_order, link, label}`；通道外站点为 `null` |
| `corridor_ids[]` | array | 是 | `docs/stations.md` 的短 ID |
| `source` | enum | 是 | `docs/stations.md` \| `csv` |
| `notes` | string\|null | 是 | 办客/可信度/待核说明，原文摘要 |
| `stats.stop_records / train_types` | int / array | 是 | 本批停站记录数、涉及车型 |

**`place` 是示意图坐标，不是经纬度**：

- `x`：0 = 最西，1 = 最东；`y`：0 = 最北，1 = 最南（上北下南、左西右东）。数值由 `docs/stations.md` 的人工示意图给出，仅保证相对方位，不保证比例。
- `sequence`：沿线顺序（西 → 东），运行图纵轴用它排序（**东在上、西在下**）。支线站为 `null`。
- `branch_of` / `branch_order`：支线接轨站与支线内顺序。`link` 区分 `main` 正线、`connecting` 联络线（虚线）、`regional` 支线。
- `label`：站名放置方向（`above/below/left/right`），供绘图避让。

本批取值（摘要）：`太原南(0.10, 0.62) → 太原(0.10, 0.36) → 东凌井(0.26, 0.36) → 阳泉北(0.44, 0.36) → 井陉北(0.58, 0.36) → 获鹿(0.72, 0.36) → 石家庄(0.86, 0.36)`；
`石家庄北(0.72, 0.14)` 经**石太普铁**在获鹿接轨（`branch_of=获鹿`，`link=connecting`）；`阳泉东(0.44, 0.68)` 等阳大支线站挂阳泉北。

> 石家庄站与石家庄北之间**没有连线**：两站无同车双停，进石家庄北的车走石太普铁（获鹿—石家庄北）。

> 坐标按**横平竖直**取值：主线站共用 `y=0.36`，支线站共用 `x=0.52`，保证轨道只有水平/垂直段。

> v1.0.0 曾把石家庄/石家庄北、太原/太原南合并为同一槽位。v2.0.0 拆开：两站是不同车站、不同里程点，且存在 5 车「一城双停」（太原南 → 太原），合并会丢失停站信息。

### 5.4 `trains[]`

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `train_id` | string | 是 | 见 §4 |
| `train_no` | string | 是 | 展示用车次号 |
| `direction` | enum | 是 | `up`(进京/太原→石家庄) \| `down`(离京/石家庄→太原) \| `unknown` |
| `train_type` | string | 是 | 高铁/动车/城际/市郊/快速/直达特快 |
| `service_status` | object | 是 | `{code: normal\|alternate_day\|unknown, basis}`；**仅从 remark 原文提取**，不做外部判断 |
| `origin` / `terminal` | string | 是 | 首站 / 末站站名 |
| `station_count` | int | 是 | 停站序列长度，必须等于 `stops.length` |
| `first_dep_abs_minute` / `last_arr_abs_minute` | int\|null | 是 | 首站发车、末站到达的绝对分钟 |
| `duration_minutes` | int\|null | 是 | 末到 − 首发；**≤0 时为 null**（跨日未定的车不输出负时长） |
| `has_day_offset` | bool | 是 | 是否存在 `day_offset≠0` 的站（v2 含负值） |
| `validation.status` | enum | 是 | `validated` \| `validated_with_notes` \| `needs_review` |
| `validation.usable_for_frontend` | bool | 是 | **前端绘制闸门**：存在阻断级矛盾时为 false |
| `validation.blocking_issue_count` / `warning_count` | int | 是 | 阻断/提示计数 |
| `validation.flags[]` | array | 是 | 见 §6 标志表 |
| `remarks[]` | array | 是 | 车次级备注；**本批不做二次归纳，恒空数组**，原文见 `stops[].remark` |
| `source_refs[]` | array | 是 | `{url, accessed}`；仅采集时记录了 URL 的车次非空（36/92），其余见 `provenance` |
| `stops[]` | array | 是 | 见 §5.5 |

### 5.5 `trains[].stops[]`

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `station_order` | int | 是 | 该车次内的站序，从 1 连续递增 |
| `station` / `station_id` | string | 是 | 站名 / 站点 ID |
| `arr_time` / `dep_time` | string\|null | 是 | 原始 HH:mm；始发无 `arr`、终到无 `dep` 属**规则留空** |
| `minute_of_day` | object | 是 | `{arr, dep}`，0–1439 或 null |
| `abs_minute` | object | 是 | `{arr, dep}`，绝对分钟或 null |
| `day_offset` | int | 是 | CSV 原值，脚本不推断 |
| `day_offset_imputed` | bool | 是 | `day_offset` 是否为空被按 0 处理（本批全 false） |
| `km` | number\|null | 是 | 恒 null |
| `is_stop` | bool | 是 | CSV 原值；false 表示通过/不办客 |
| `stop_kind` | enum | 是 | `origin`(首站) \| `terminal`(末站) \| `stop`(办客停站) \| `pass`(通过) |
| `dwell_minutes` | int\|null | 是 | 停站分钟；到发缺一为 null；通过站为 0 |
| `remark` | string\|null | 是 | 采集原文（含来源 URL/日期/"需12306官方复核"），**逐字保留** |
| `source_row` | int | 是 | CSV 物理行号（表头为 1），用于定位回溯 |
| `flags[]` | array | 是 | 见 §6 |

### 5.6 `segments[]`

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `segment_id` | string | 是 | 见 §4 |
| `train_id` / `train_no` | string | 是 | 所属车次 |
| `segment_type` | enum | 是 | `run` 相邻两站运行 \| `dwell` 同站停站 \| `unknown` 时刻不足 |
| `from_station_id` / `to_station_id` | string | 是 | 起终站；dwell 时两者相同 |
| `from_station_order` / `to_station_order` | int | 是 | 起终站序；dwell 相同，run 相差 1 |
| `from_dep_time` / `to_arr_time` | string\|null | 是 | 原始时刻 |
| `departure_abs_minute` / `arrival_abs_minute` | int\|null | 是 | 绝对分钟，与对应 stop 严格一致 |
| `from_km` / `to_km` | number\|null | 是 | 恒 null |
| `duration_minutes` | int\|null | 是 | 区间时长；**为负（跨日未定）时置 null**，原始绝对分钟仍保留 |
| `data_quality.status` | enum | 是 | `ok` \| `review`（所在车被阻断或区间为负） \| `incomplete`（时刻缺失） |
| `data_quality.flags[]` | array | 是 | `missing_time`、`negative_duration` |

区间是**冗余存储**（可由 stops 推导），目的是让 Marey 图与线路动画用同一份区间语义，避免两个模块各推一遍导致不一致。校验器强制 `segment ↔ stop` 时刻一一对应、数量守恒（`dwell(停留>0) + run = 1988`）。

### 5.7 `warnings[]`

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `warning_id` | string | 是 | `RV-###` |
| `code` | enum | 是 | 见下表 |
| `severity` | enum | 是 | `block` 阻断该车绘制 \| `warn` 可绘但需标注 \| `info` 提示 \| `excluded` 未进入本批数据 |
| `message` | string | 是 | 人读说明 |
| `train_id` / `train_no` | string\|null | 是 | 多车共用条目 `train_id=null`，`train_no` 为逗号清单 |
| `station_id` / `station_order` / `station` | — \| null | 是 | 定位到站 |
| `row` | int\|null | 是 | CSV 行号 |
| `evidence` / `frontend_impact` / `doc_ref` | string\|null | 是 | 证据、对前端的影响、文档出处（如 `uncertainties §4`） |
| `status` | enum | 是 | `open` \| `resolved` \| `waived` |

`code` 允许值：`CROSSING_UNRESOLVED`、`CROSSING_NOT_REPRODUCED`、`SOURCE_CONFLICT`、`DIRECTION_REVIEW`、`ROUTE_PENDING`、`STATION_NAME_MISMATCH`、`STATION_CATALOG_CONFLICT`、`DUPLICATE_ORDER_CONFLICT`、`STATION_ORDER_GAP`、`TIME_REVERSAL`、`DEP_BEFORE_ARR`、`MISSING_TIME`、`MISSING_FIELD`、`INVALID_TIME`、`INVALID_DIRECTION`、`BOUNDARY_RULE`、`DUPLICATE_ROW`、`EXCLUDED_UNVERIFIED`、`EXCLUDED_SUSPENDED`、`OTHER`。

### 5.8 `stats`

| 字段 | 含义 |
|---|---|
| `trains` / `usable_trains` / `blocked_trains` / `trains_with_notes` | 车次计数（须满足 usable+blocked = trains） |
| `stations` / `stations_in_dataset` | 站点表长度 / 其中本批出现的站数（308 / 300） |
| `stop_records` | 停站记录总数（1132） |
| `segments` | 区间总数（1988） |
| `warnings.{total,block,warn,info,excluded}` | 告警分严重度计数 |
| `km_missing_stops` | km 为 null 的站记录数（= `stop_records`） |
| `direction.{up,down,unknown}` | 方向车次计数 |
| `day_offset_stops` | `day_offset≠0` 的站记录数（v1 125 / v2 441） |

---

## 6. 标志（flags）表

| 取值 | 出现位置 | 含义 |
|---|---|---|
| `day_offset_from_source` | stop | 该站 `day_offset=1`，依据为来源页绝对时刻 |
| `suspected_day_offset` | stop | 时间倒退且 `day_offset=0`，**疑似跨日未定**，值未被修改 |
| `time_reversal` | stop | 绝对分钟倒退且不满足疑似跨日条件 |
| `dep_before_arr` | stop | 同站出发早于到达 |
| `conflict` | stop | 同车次同站序存在多版本记录 |
| `source_conflict` | stop | 该站存在跨页来源冲突（G2637） |
| `catalog_name_mismatch` | stop | CSV 站名与车站骨架不一致（昔阳） |
| `direction_corrected` | train | 采集期做过 down→up 校正 |
| `route_pending` | train | 线路衔接待核（D1095/D1096） |
| `corridor_order_mismatch` | train | 石太段站序与 direction 相反（本批 0） |
| `off_corridor` | train | 不含任何目标通道核心站（本批 0） |
| `direction_unknown` | train | 方向未知（本批 0） |

---

## 7. 前端如何使用（最小读取规则）

1. **可用性闸门**：只绘制 `trains[].validation.usable_for_frontend === true` 的车次；其余在列表中标灰并显示对应 `warnings`。
2. **画线**：优先直接用 `segments`——`run` 画斜线（`departure_abs_minute` → `arrival_abs_minute`），`dwell` 画同站水平线；`data_quality.status !== "ok"` 的区间按虚线/不画处理，并在图注标"数据待核"。
3. **纵轴**：用 `stations[].place.sequence`（主线）与 `branch_of/branch_order`（支线）排序，**轴标题必须写"示意站序，非公里数"**；`km` 全为 null，不得换算成距离。
4. **高亮**：`stations[].is_highlighted === true`（阳泉北）。
5. **详情面板**：`stops[]` 提供完整到发、原始 HH:mm、`day_offset`、`remark` 与 `source_row`，点击车次即可逐站展示并回溯到 CSV 行。
6. **待核提示**：`warnings` 里 `train_id` 命中当前车次、或 `station_id` 命中当前车站的条目，直接显示在详情里；`severity=excluded` 的条目只用于"本批未收录"说明。
7. **横轴范围**：以 `meta.coverage.abs_minute_min/max` 为准（本批 14–2663），不得硬编码次日 06:00 截断。
8. **禁止**：自行用 HH:mm 比较大小、自行把 `minute_of_day` 加 1440、自行给 km 补值、自行改 `direction`。

---

## 8. 数据如何被本地页面加载

| 方案 | 可行性 | 说明 |
|---|---|---|
| `fetch('data/processed/xxx.json')` + `file://` 双击 | **不可行** | 浏览器对 `file://` 的 fetch 受同源策略限制（Chrome/Edge 会报 CORS） |
| 本地 HTTP 服务（`python -m http.server`） | **可行（当前推荐）** | 阶段 4–7 开发与验收均按此方式 |
| 把 JSON 包成 `data/timetable-data.js`（`window.__TIMETABLE__ = {...}`）+ `<script>` | 可行（离线单文件方案） | 阶段 10 定稿时若要求"双击即用"再启用；届时同一份 JSON 内容转写为 JS 变量，`data_kind` 等字段保持不变 |

**现阶段结论**：不谎称双击可用；开发与验收走本地 HTTP。若最终交付要求双击打开，采用第三种方案并在 README 写明生成步骤。

---

## 9. 版本与兼容规则

1. **语义化版本**：`MAJOR.MINOR.PATCH`。
   - `PATCH`：只改文案/注释/排序稳定性修复，字段与语义不变 → 前端无需改动。
   - `MINOR`：**新增可选字段**或新增枚举值 → 前端忽略未知字段即可兼容；旧代码不得因新字段崩溃。
   - `MAJOR`：删字段、改字段含义/类型、改 ID 规则、改时间基准 → 必须同步改前端并保留旧文件。
2. **冻结含义**：v2.0.0 起，`meta` / `stations` / `trains` / `segments` / `warnings` / `stats` 的必填字段与语义不得在 MINOR 内变更。
3. **Schema 与实现同步**：任何一次数据重生成，都必须通过 `scripts/validate_contract.py`；Schema 与 JSON 互为约束（结构靠 Schema，语义靠不变量检查）。
4. **数据批次与契约版本正交**：`data_version`（data-v1/data-v2…）表示采集批次，`schema_version` 表示结构；同一 Schema 可承载多批数据。
5. **废弃流程**：字段先标 `deprecated`（PATCH 文档说明）→ 至少保留一个 MINOR → 下一个 MAJOR 删除。

**变更记录**

| 版本 | 日期 | 变更 |
|---|---|---|
| 1.0.0 | 2026-10-19 | 首次冻结。此前阶段2 输出的扁平结构（`source/rules/counts/trains[].status`）为 pre-contract 形态，已由同一清洗脚本升级为本契约；数据值未变，逐字段回归见 `reports/validation/contract_v1.0.0_validation.md` |
| 2.0.0 | 2026-10-19 | **破坏性**：`stations[].line_positions` 改为 `stations[].place`；石家庄/石家庄北、太原/太原南不再共用槽位；新增示意坐标（x/y）、沿线 `sequence`、支线 `branch_of/branch_order/link`。时刻数据逐字段未变 |

---

## 10. 清洗器输出 → 前端读取的映射

| CSV 列 | 契约字段 | 变换 |
|---|---|---|
| `train_no` | `trains[].train_no` / `train_id` | `train_id = "tr:" + train_no` |
| `direction` | `trains[].direction` | 原样（`unknown` 保留） |
| `train_type` | `trains[].train_type` | 原样 |
| `station_order` | `trains[].stops[].station_order` | 原样；另生成 `segments[].from/to_station_order` |
| `station` | `stops[].station` / `stations[].name` | 原样；另生成 `station_id = "st:" + station` |
| `arr_time` | `stops[].arr_time` / `minute_of_day.arr` / `abs_minute.arr` | `HH:mm → 分钟 → +day_offset*1440` |
| `dep_time` | `stops[].dep_time` / `minute_of_day.dep` / `abs_minute.dep` | 同上 |
| `day_offset` | `stops[].day_offset` | 原值，不推断 |
| `km` | `stops[].km` / `segments[].from_km/to_km` | 恒 null |
| `is_stop` | `stops[].is_stop` / `stop_kind` | 结合位置推导 `origin/terminal/stop/pass` |
| `remark` | `stops[].remark` | 逐字保留；另从中提取 `service_status`、`source_refs` |

派生（不来自 CSV 单列）：

| 产物 | 来源 |
|---|---|
| `segments[]` | 由相邻 stops 生成：相邻两站 → `run`；同站 arr/dep 且停留>0 → `dwell` |
| `duration_minutes` | `abs` 差值；≤0 或缺失 → null |
| `stations[]` | CSV 站名 ∪ `docs/stations.md` 骨架；`place` 由骨架表的示意坐标与线路挂接生成 |
| `warnings[]` | 脚本校验结果 + `reports/manual_review/uncertainties_*.md` 既定清单 |
| `meta.build_id` | `CSV SHA-256[:12] + "-v" + 清洗器版本` |

---

## 11. 设计取舍（含争议项，均已定案并记录影响）

### 11.1 `generated_at` 为 null
- 取舍：**可复现性 > 构建时间戳**。若写入时钟，每次重跑字节不同，无法用 SHA-256 证明"数据没被改"。
- 替代：`build_id`（输入哈希+脚本版本）承担溯源，构建时刻写在 `reports/validation/cleaning_log_*.md`。
- 影响：前端不能显示"数据生成时间"，只能显示 `build_id` 与 `query_date`（2026-10-20）。若以后需要时间戳，须升 MINOR 并接受失去字节级可复现。

### 11.2 `stations[].station_order` 恒 null
- 取舍：**拒绝发明全局站序**。石家庄/石家庄北、太原/太原南是并列端点，强行线性编号会制造"相邻"假象。
- 替代：逐车站序放 `stops[].station_order`；运行图纵轴用 `place.sequence`，线路图用 `place.x/y`。
- 影响：前端不能对 `stations` 直接排序画轴；未映射站（如昔阳）`place` 为 null，需单独处理。

### 11.3 `segments` 冗余存储
- 取舍：宁可多存 1988 条区间，也不让两个模块各自推导。代价是 JSON 体积翻倍（约 1.0MB → 1.9MB）。
- 保障：校验器强制区间与站点时刻一一对应、数量守恒。

### 11.4 `km` 全 null
- 第三方无里程，`docs/stations.md` 亦明确"里程留空待核"。任何用 `station_order` 冒充公里的做法都会给图制造虚假精度。
- 影响：Marey 图纵轴只能等距示意，轴标题必须写明。

### 11.5 通过站（`pass`）的表达
- 契约允许 `stop_kind=pass` + `is_stop=false`，时刻用 `arr=dep` 表示通过瞬间（不产生 `dwell` 区间）。
- 本批真实数据 `is_stop` 全为 true，**没有通过站**；该分支仅在 synthetic 样例中验证。

### 11.6 6 车跨日未定
- K373/K374/K565/K609/K730/K866 的 `usable_for_frontend=false`，但数据仍完整保留（含 `abs_minute` 原值）。
- 前端应：不绘制这 6 车，或在列表中灰显 + 显示 `CROSSING_UNRESOLVED` 告警；**不得自行把 `day_offset` 改成 1**。

### 11.7 站点拓扑拆分（v2.0.0）

- 问题：v1 把「太原 / 太原南」「石家庄 / 石家庄北」合并成同一纵轴槽位，图上只显示一个点，无法表达「到太原」与「到太原南」的区别，也丢掉 5 车（D1096/D1638/G622/G624/G2620）在太原南与太原的连续停站。
- 选择：拆成独立站点，新增 `place` 坐标与 `sequence`；石家庄北作**联络线支站**（`link=connecting`，图上虚线），阳泉东作**阳大支线**（`link=regional`，实线细线）。
- 代价：运行图出现 7 行；走石家庄北的 20 车会跨过石家庄行（1 次跨越），支线车会跨过主线行。1D 纵轴无法完全避免交叉，已用「联络线 / 阳大支线」标签标明支线属性。
- 顺序依据：数据里东行实际是 `太原南 → 太原 → 阳泉北`（5 车双停可证），所以纵轴自上而下为 `石家庄北、石家庄、阳泉北、阳泉东、平定、太原、太原南`。

### 11.8 多车共用告警
- `STATION_NAME_MISMATCH`（K585/K587 的昔阳）等条目 `train_id=null`、`train_no="K585, K587"`；前端按 `train_no` 拆分匹配，不要假定 `train_id` 非空。

---

## 12. 校验方式与当前结果

```bash
# 结构 + 语义双校验（需 jsonschema）
pip install jsonschema
python scripts/validate_contract.py --all
```

2026-10-19 实测：

| 对象 | Schema | 不变量 | 结论 |
|---|---|---|---|
| 真实数据（92 车 / 1132 站 / 1988 区间 / 48 告警） | PASS | 11/11 PASS | 通过 |
| synthetic 样例（2 车 / 7 站 / 7 区间 / 1 告警） | PASS | 11/11 PASS | 通过 |

不变量覆盖：`abs = minute + day_offset*1440`、站序 1..N、引用完整性、`segment↔stop` 时刻一致、区间数量守恒、告警引用、stats 自洽、km 全 null、阻断车不得标记可绘制、`data_kind` 与文件性质一致。

---

## 13. 已知缺口（不在本契约内解决）

1. 全部时刻为第三方聚合，**需 12306 官方复核**；契约只保证结构自洽，不保证数值正确。
2. 21 个未核实车次、5 个停运车次未录入；`warnings` 中以 `EXCLUDED_*` 登记，**无任何时刻**。
3. `昔阳` 未映射到骨架 `大寨(昔阳)`，`place` 为 null；平定/昔阳办客状态与骨架冲突，待定稿。
4. G2637 第 8 站（滨海北/滨海西）跨页冲突未定，现按主录页录入。
5. 里程、坐标全缺；如需真实纵轴距离，须补官方里程来源后再升 MINOR。
