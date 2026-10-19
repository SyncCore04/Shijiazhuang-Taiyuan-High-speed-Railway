# 清洗日志 · 石太客专 + 阳大铁路（data-v2）

> 运行时间：2026-10-19 20:57:54　｜　脚本：`scripts/clean_timetable.py` v1.1.0　｜　Python 3.13.14
> 命令：`python scripts/clean_timetable.py --input data/raw/shita_train_timetable_2026-10-20_data-v2_12306.csv`

## 1. 输入盘点（清洗前实测）

| 检查项 | 实测值 |
|---|---|
| 文件 | `data/raw/shita_train_timetable_2026-10-20_data-v2_12306.csv` |
| 字节数 | 335,707 |
| SHA-256 | `7abfc727dd33b7c9a57374fb75bd02f0bf7957524ba2c8bc72fe6d1e6cd1a88e` |
| 编码 | UTF-8 (no BOM) |
| 换行 | LF |
| 物理行数 | 2126 |
| 数据行数 | 2125 |
| 表头 | `train_no,direction,train_type,station_order,station,arr_time,dep_time,day_offset,km,is_stop,remark`（与固定表头逐字一致） |

## 2. 处理步骤（固定顺序，幂等）

| 步骤 | 做法 | 本次结果 |
|---|---|---|
| S1 读取与编码 | 以二进制读入算 SHA-256，再按 UTF-8(兼容 BOM) 严格解码；解码失败直接以退出码 1 终止，不产出 JSON。 | 未改动任何字节 |
| S2 表头与列数 | 逐字比对 11 列固定表头；任一行字段数 ≠ 11 即致命错误。 | 表头一致，0 行列数异常 |
| S3 字段校验 | 逐行校验 train_no/direction/train_type/station_order/station/HH:mm/day_offset/km/is_stop；只记录不修复。 | 非法时刻 0，非法方向 0 |
| S4 完全去重 | 11 字段全同视为完全重复，保留首次出现行，其余丢弃并记录行号。 | 重复 0 条 |
| S5 冲突识别 | 按 (train_no, station_order) 分组，签名（站名/到/发/day_offset）不一致即冲突；不选边。 | 冲突 0 条 |
| S6 按车聚合 | 按 train_no 聚合并按 station_order 升序重排；校验 1..N 连续、无重复。 | 159 车，站序全部连续 |
| S7 时间换算 | HH:mm → minute_of_day（0–1439）；abs_minute = minute_of_day + day_offset*1440。全程整数运算，无字符串比较。 | 换算 2125 行 |
| S8 时间校验 | 站内 dep≥arr；跨站 abs 单调。倒退时区分「已有 day_offset 依据」与「疑似跨日」，后者不改值。 | 倒退 0 处，全部疑似跨日 |
| S9 站型判定 | 首站=origin（无 arr）、末站=terminal（无 dep）、is_stop=false=pass、其余=stop，并算 dwell_minutes。 | origin 159 / terminal 159 / stop 1807 / pass 0 |
| S10 方向与走廊 | 照抄 direction；对同时含太原/阳泉北/石家庄的车做走向一致性提示；不反推、不改值。 | unknown 0 车，走向不一致 0 车 |
| S11 缺失处理 | arr/dep/km 缺失写 null 并区分「规则留空」与「真缺失」；不填 0、不填 00:00。 | km 缺 2125，规则留空 318 |
| S12 输出与复核 | 生成确定性 JSON、校验报告、复核 CSV；内置二次构建字节比对。 | 复核项 7 条 |
| S13 契约成型 | 按 docs/data-contract.md v1.0.0 组装 meta/provenance/stations/trains/segments/warnings/stats；区间由相邻站点派生，站表并入骨架无车站。 | 区间 3773 条，站点表 446 条 |

## 3. 关键判断（为什么这么做）

1. **跨日在采集期推断**：按站序 + 时刻单调性判定（跨日后区段时长 ≤ 20 小时才成立），推断点写入采集摘要；清洗脚本只读 `day_offset` 列，不在此时二次猜测。
2. **方向不凭奇偶反推**：v1 已收录车次沿用其人工核定方向；v1 没有的新增车次按“太原侧 ↔ 石家庄侧 / 阳泉东”的实际站序判定，判不出的写 `unknown`。
3. **km 不补**：12306 前端不提供里程，`station_order` 是序号不是距离，冒充会让 Marey 图纵轴产生虚假精度。
4. **套跑只录一个编号**：同一 `train_no` 交路若中途换号，按“优先沿用 v1 编号”只录一段，另一编号不重复成车。
5. **remark 写清通道性质**：逐站标注“来源12306官方前端”“区间未停阳泉北，疑似走石太老线”“套跑切片”等，便于回溯。
6. **不再维护未核实清单**：12306 未返回的车次即当日无开行记录，不在 trains 里生成任何时刻。

## 4. 产物清单

| 文件 | 字节 | SHA-256 |
|---|---|---|
| `data/processed/shita_timetable_2026-10-20_data-v2.json` | 3,964,620 | `2449cea12494315ec6175530fd10409afafe4b2be30a229945008cb31d44f0d0` |
| `reports/validation/validation_2026-10-20_data-v2.md` | 8,173 | `80bed8139ee8ab3060486f55c7875f0b638c2c86eb051295db2c03590e47bfc3` |
| `reports/manual_review/manual_review_2026-10-20_data-v2.csv` | 1,439 | `776fc257df218d51b5ede6bc37c0998b95fb87191dc0a39971ecc96ae034cbec` |
| `reports/validation/cleaning_log_2026-10-20_data-v2.md` | （本文件） | — |

> 原始 CSV 只读，未修改、未覆盖、未移动；SHA-256 见第 1 节，可用于事后核对。

## 5. 复现方式

```bash
SHITA_PROFILE=v2 python scripts/clean_timetable.py
```

默认输出到 `data/processed/`、`reports/validation/`、`reports/manual_review/`；可用 `--output/--validation-report/--cleaning-log/--manual-review-csv` 覆盖。

## 6. 复现性自检

- 二次构建字节一致：**PASS**
- 本次 JSON SHA-256：`2449cea12494315ec6175530fd10409afafe4b2be30a229945008cb31d44f0d0`
- 该 JSON 不含时间戳，重跑应得到同一哈希；若哈希变化，说明输入或规则被改动。

