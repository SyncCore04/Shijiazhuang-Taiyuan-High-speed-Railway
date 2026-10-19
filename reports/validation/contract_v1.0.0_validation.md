# 契约冻结校验报告 · v1.0.0

> 日期：2026-10-19　｜　契约：`docs/data-contract.md` v1.0.0　｜　Schema：`docs/schema/shita-timetable.schema.json`
> 校验器：`scripts/validate_contract.py`（jsonschema 4.26.0，Draft 2020-12）　｜　命令：`python scripts/validate_contract.py --all`
> 结论：**真实数据与 synthetic 样例均通过 Schema + 11 项语义不变量；契约冻结为 v1.0.0。**

## 1. 校验对象

| 对象 | 路径 | data_kind | 字节数 | SHA-256 |
|---|---|---|---|---|
| 真实数据 | `data/processed/shita_timetable_2026-10-20_data-v1.json` | real | 2,271,579 | `b22925a3080ca402ca0b1294f28a3c8b83eb3d53cb27fefa3f84dad65131f418` |
| 测试样例 | `data/test-fixtures/synthetic_contract_sample.json` | synthetic | 15,119 | `a17b2d019c9313e391f9f5df738a198447838adcd722e6b0e15fea3bad7589e9` |

真实数据规模：92 车 / 1132 站记录 / 1988 区间 / 308 站点条目（本批出现 300）/ 48 条告警。
测试样例规模：2 车（up+down）/ 7 站（含通过站与跨日）/ 7 区间。

## 2. 校验输出（原样）

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

## 3. 契约化前后数据值回归

把 v1.0.0 之前（阶段2 pre-contract 结构）的输出与当前输出逐字段比对，确认"只改形状、不改数据"：

| 比对项 | 结果 |
|---|---|
| 站记录键集合 (train_no, station_order) | 一致（1132 vs 1132） |
| 站记录字段差异（站名/到/发/day_offset/km/is_stop/stop_kind/dwell/remark/source_row/flags/minute_of_day/abs_minute） | **0 处** |
| 车次字段差异（方向/车型/站数/首末站/首末绝对分钟/时长/has_day_offset/validation.*） | **0 处** |
| 告警条数与文本（severity/train_no/station/message） | 48 条全一致，**0 处差异**（仅空串 `""` 归一为 `null`） |

结论：契约化未改动任何时刻、站序、方向、备注或判定结果。

## 4. 结构性变化（形状，非数据）

| 变化 | 说明 |
|---|---|
| 顶层由扁平字段改为 7 段式 | `meta / provenance / stations / trains / segments / warnings / stats` |
| 新增 `segments` | 1988 条（run 1040 + dwell 948），与站记录时刻逐一校验一致 |
| 新增 `train_id` / `station_id` | `tr:C799` / `st:北京丰台` 形式，稳定且不依赖下标 |
| `manual_review` → `warnings` | 字段改名为契约字段，新增 `code`（8 类实际用到） |
| 车次状态收进 `validation` | `status / usable_for_frontend / blocking_issue_count / warning_count / flags` |
| 站表并入骨架站 | `stations` 由 300 → 308，新增 8 个 `in_dataset=false` 的通道站 |
| 体积 | 1,073,167 B → 2,271,579 B（segments 冗余存储所致，见契约 §11.3） |

## 5. 未通过项

无。

## 6. 复现

```bash
python scripts/clean_timetable.py                 # 由 CSV 重建 JSON（确定性，SHA-256 固定）
pip install jsonschema                            # 仅校验器需要
python scripts/validate_contract.py --all         # 结构 + 语义校验
```

> 若 `clean_timetable.py` 重跑后 JSON 的 SHA-256 变化，说明输入 CSV 或清洗规则被改动；此时需重新执行本报告的全部校验。
