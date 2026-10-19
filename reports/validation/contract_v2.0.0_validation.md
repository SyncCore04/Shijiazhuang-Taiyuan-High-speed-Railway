# 契约冻结校验报告 · v2.0.0

> 日期：2026-10-19　｜　契约：`docs/data-contract.md` v2.0.0　｜　Schema：`docs/schema/shita-timetable.schema.json`
> 校验器：`scripts/validate_contract.py`（jsonschema 4.26.0，Draft 2020-12）
> 数据：`shita_timetable_2026-10-20_data-v1.json`（2,271,203 B，SHA-256 `5692feb075a2a57f19a84cff5592cafaaff676e529992ecbfc6cbfa5ded0c0b4`）
> 结论：**Schema + 11 项不变量全部通过；站点拓扑拆分符合预期。**

## 1. 本轮变更（v1.0.0 → v2.0.0）

| 项 | v1.0.0 | v2.0.0 |
|---|---|---|
| 站点布局字段 | `stations[].line_positions[]`（`order` 共享槽位） | `stations[].place`（`x/y` 示意坐标、`sequence`、`branch_of/branch_order/link`） |
| 石家庄 / 石家庄北 | 共用 order 0，图上合并为一行 | 拆为两个点；石家庄北 `link=connecting`（联络线） |
| 太原 / 太原南 | 共用 order 5，合并 | 拆为两个点；`sequence` 2 与 1 |
| 运行图纵轴 | 5 行 | 7 行（含两个同城站） |
| 线路图 | 1D 等距 + 竖向支线 | 按 `x/y` 上北下南摆放，联络线虚线 |

## 2. 站点拓扑实测

主线（`sequence` 升序，西 → 东）：`太原南 → 太原 → 东凌井(东陵井) → 阳泉北 → 井陉北 → 获鹿 → 石家庄`

支线：

| 站 | `branch_of` | `link` | 图上表现 |
|---|---|---|---|
| 石家庄北 | 获鹿 | connecting | 石太普铁（虚线）；与石家庄站无连线 |
| 盂县东 / 河底 / 荫营东 / 阳泉东 | 阳泉北 | regional | 阳大支线（细实线） |
| 平定 / 宁艾 / 大寨(昔阳) | 阳泉东 | regional | 阳大支线二级 |

运行图行序（自上而下，东 → 西 + 支线）：`石家庄、石家庄北、阳泉北、阳泉东、平定、太原、太原南`

## 3. 校验输出（原样）

```text
=== D:\Code\Vibe coding test\石太客专列车运行图\data\processed\shita_timetable_2026-10-20_data-v1.json ===
  [PASS] Schema Draft 2020-12（0 处不合法）
  [PASS] 时间模型 abs=minute+offset*1440：2080 个时刻全部满足
  [PASS] 站序 1..N 连续唯一：全部车次通过
  [PASS] stops/segments 引用完整：全部可解析
  [PASS] segment↔stop 时刻一致：1988 条区间全部对齐
  [PASS] segment 数量守恒：实际 1988 / 期望 1988
  [PASS] warnings 引用完整：48 条告警
  [PASS] stats 自洽：计数与数组长度一致
  [PASS] km 全为 null 且计数吻合：null 1132 / stats 1132 / 站点 1132
  [PASS] 阻断车未标记可绘制：全部一致
  [PASS] data_kind 与文件性质一致：data_kind=real，文件名不含 synthetic
  摘要：shita_timetable_2026-10-20_data-v1（real） trains=92 stops=1132 segments=1988 warnings=48

=== D:\Code\Vibe coding test\石太客专列车运行图\data\test-fixtures\synthetic_contract_sample.json ===
  [PASS] Schema Draft 2020-12（0 处不合法）
  [PASS] 时间模型 abs=minute+offset*1440：10 个时刻全部满足
  [PASS] 站序 1..N 连续唯一：全部车次通过
  [PASS] stops/segments 引用完整：全部可解析
  [PASS] segment↔stop 时刻一致：7 条区间全部对齐
  [PASS] segment 数量守恒：实际 7 / 期望 7
  [PASS] warnings 引用完整：1 条告警
  [PASS] stats 自洽：计数与数组长度一致
  [PASS] km 全为 null 且计数吻合：null 7 / stats 7 / 站点 7
  [PASS] 阻断车未标记可绘制：全部一致
  [PASS] data_kind 与文件性质一致：data_kind=synthetic，文件名含 synthetic
  摘要：shita_timetable_synthetic_contract-sample（synthetic） trains=2 stops=7 segments=7 warnings=1

结论：全部通过
```

## 4. 数据值回归说明

- 输入 CSV SHA-256 **未变**：`a061ad4a36ac825ef74c6702b552501b3c3fa9f9119e3032f6269c071a9215e6`。
- 清洗脚本中 `trains` / `segments` / `warnings` 的生成逻辑本轮未改，仅 `build_stations` 与站点常量表变化。
- 站记录数仍为 1132、区间 1988、告警 48、车次 92（见 `stats`）。
- **限制**：v1 JSON 未保留副本，无法做逐字段 diff；因此以「输入哈希不变 + 相关代码路径未改 + stats 一致」作为等价性依据。后续版本请用测试报告中的 train/stops 投影哈希做严格对拍。
- 投影哈希（本轮记录）：`412fc0293aa994c5…`（完整值见 `reports/validation/test_report_2026-10-19.md §7`）。

## 5. 未通过项

无。
