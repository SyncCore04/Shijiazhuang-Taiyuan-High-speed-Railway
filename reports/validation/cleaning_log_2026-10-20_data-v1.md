# 清洗日志 · 石太客专 + 阳大铁路（data-v1）

> 运行时间：2026-10-19 20:47:04　｜　脚本：`scripts/clean_timetable.py` v1.0.0　｜　Python 3.13.14
> 命令：`python scripts/clean_timetable.py --input data/raw/shita_train_timetable_2026-10-20_data-v1_draft.csv`

## 1. 输入盘点（清洗前实测）

| 检查项 | 实测值 |
|---|---|
| 文件 | `data/raw/shita_train_timetable_2026-10-20_data-v1_draft.csv` |
| 字节数 | 280,799 |
| SHA-256 | `a061ad4a36ac825ef74c6702b552501b3c3fa9f9119e3032f6269c071a9215e6` |
| 编码 | UTF-8 (no BOM) |
| 换行 | CRLF |
| 物理行数 | 1133 |
| 数据行数 | 1132 |
| 表头 | `train_no,direction,train_type,station_order,station,arr_time,dep_time,day_offset,km,is_stop,remark`（与固定表头逐字一致） |

## 2. 处理步骤（固定顺序，幂等）

| 步骤 | 做法 | 本次结果 |
|---|---|---|
| S1 读取与编码 | 以二进制读入算 SHA-256，再按 UTF-8(兼容 BOM) 严格解码；解码失败直接以退出码 1 终止，不产出 JSON。 | 未改动任何字节 |
| S2 表头与列数 | 逐字比对 11 列固定表头；任一行字段数 ≠ 11 即致命错误。 | 表头一致，0 行列数异常 |
| S3 字段校验 | 逐行校验 train_no/direction/train_type/station_order/station/HH:mm/day_offset/km/is_stop；只记录不修复。 | 非法时刻 0，非法方向 0 |
| S4 完全去重 | 11 字段全同视为完全重复，保留首次出现行，其余丢弃并记录行号。 | 重复 0 条 |
| S5 冲突识别 | 按 (train_no, station_order) 分组，签名（站名/到/发/day_offset）不一致即冲突；不选边。 | 冲突 0 条 |
| S6 按车聚合 | 按 train_no 聚合并按 station_order 升序重排；校验 1..N 连续、无重复。 | 92 车，站序全部连续 |
| S7 时间换算 | HH:mm → minute_of_day（0–1439）；abs_minute = minute_of_day + day_offset*1440。全程整数运算，无字符串比较。 | 换算 1132 行 |
| S8 时间校验 | 站内 dep≥arr；跨站 abs 单调。倒退时区分「已有 day_offset 依据」与「疑似跨日」，后者不改值。 | 倒退 7 处，全部疑似跨日 |
| S9 站型判定 | 首站=origin（无 arr）、末站=terminal（无 dep）、is_stop=false=pass、其余=stop，并算 dwell_minutes。 | origin 92 / terminal 92 / stop 948 / pass 0 |
| S10 方向与走廊 | 照抄 direction；对同时含太原/阳泉北/石家庄的车做走向一致性提示；不反推、不改值。 | unknown 0 车，走向不一致 0 车 |
| S11 缺失处理 | arr/dep/km 缺失写 null 并区分「规则留空」与「真缺失」；不填 0、不填 00:00。 | km 缺 1132，规则留空 184 |
| S12 输出与复核 | 生成确定性 JSON、校验报告、复核 CSV；内置二次构建字节比对。 | 复核项 48 条 |
| S13 契约成型 | 按 docs/data-contract.md v1.0.0 组装 meta/provenance/stations/trains/segments/warnings/stats；区间由相邻站点派生，站表并入骨架无车站。 | 区间 1988 条，站点表 308 条 |

## 3. 关键判断（为什么这么做）

1. **不自动修跨日**：7 处时间倒退的 day_offset 均为 0，页面未标次日。改成 1 会让曲线「看起来正常」，但那是猜测。脚本保留原值、标 `suspected_day_offset`、把车标为不可用，等 12306 定。
2. **不改方向**：6 车已在采集期做 down→up 校正，脚本只加 `direction_corrected` 标记；对 K1331/Z267 这类「奇数号 + 整体离京」的表象差异不另作解释。
3. **km 不补**：第三方无里程，`station_order` 是序号不是距离，冒充会让 Marey 图纵轴产生虚假精度。
4. **冲突不选边**：文件内 0 冲突，但 G2637 的跨页冲突按主录页保留并登记，不因「看起来更顺」而改站名。
5. **保留 remark 原文**：每站 remark 含来源 URL/日期/「需12306官方复核」字样，原样进 JSON，便于逐条回溯。
6. **不补 21 车**：未核实车次连站名都不写进 trains，只在 `known_gaps` 登记编号与原因。

## 4. 产物清单

| 文件 | 字节 | SHA-256 |
|---|---|---|
| `data/processed/shita_timetable_2026-10-20_data-v1.json` | 2,271,203 | `5692feb075a2a57f19a84cff5592cafaaff676e529992ecbfc6cbfa5ded0c0b4` |
| `reports/validation/validation_2026-10-20_data-v1.md` | 9,716 | `3769b4093b65fab32b8cbd53c73d67ae4b1e15912a5abeca54852a37cbdfe0d2` |
| `reports/manual_review/manual_review_2026-10-20_data-v1.csv` | 11,468 | `afe36c6fef596aa51b9fcfff57ff02dce846a47d67e070294ed80fa07dd951ea` |
| `reports/validation/cleaning_log_2026-10-20_data-v1.md` | （本文件） | — |

> 原始 CSV 只读，未修改、未覆盖、未移动；SHA-256 见第 1 节，可用于事后核对。

## 5. 复现方式

```bash
python scripts/clean_timetable.py \
  --input data/raw/shita_train_timetable_2026-10-20_data-v1_draft.csv
```

默认输出到 `data/processed/`、`reports/validation/`、`reports/manual_review/`；可用 `--output/--validation-report/--cleaning-log/--manual-review-csv` 覆盖。

## 6. 复现性自检

- 二次构建字节一致：**PASS**
- 本次 JSON SHA-256：`5692feb075a2a57f19a84cff5592cafaaff676e529992ecbfc6cbfa5ded0c0b4`
- 该 JSON 不含时间戳，重跑应得到同一哈希；若哈希变化，说明输入或规则被改动。

