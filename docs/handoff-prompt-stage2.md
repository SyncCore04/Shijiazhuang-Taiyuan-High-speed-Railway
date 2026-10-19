# 交接提示词 · 提示词2 数据清洗（复制给代码助手）

> 用法：把下面 ```text 代码块整段复制给能读写本地文件的代码助手。项目根目录：`D:\Code\Vibe coding test\石太客专列车运行图`。

```text
【角色】
你是数据工程师，负责把石太客专+阳大铁路时刻表 CSV 清洗为可验证、可追溯的 JSON，不能替真实铁路数据作猜测。只做提示词2清洗，不做前端、不改原始CSV、不重新采集。

【任务】
检查输入 CSV，编写可重复执行的清洗脚本，转换为前端将使用的 JSON，并生成数据质量报告。前端不直接解析原始 CSV。

【输入（均已存在，先读）】
- 项目目录：D:\Code\Vibe coding test\石太客专列车运行图
- 待清洗 CSV：data/raw/shita_train_timetable_2026-10-20_data-v1_draft.csv（92个物理交路/1132行，11列，已完成套跑去重）
- 来源记录：reports/sources/sources_2026-10-20_data-v1.md
- 待核/冲突清单：reports/manual_review/uncertainties_2026-10-20_data-v1.md（21车未核实、1处来源冲突、7处跨日待核、6车方向校正、线路衔接待核，全部原样保留，不要替它们下结论）
- 车站骨架：docs/stations.md
- 固定表头（顺序不得改）：train_no,direction,train_type,station_order,station,arr_time,dep_time,day_offset,km,is_stop,remark

【既有口径，必须遵守】
1. 现行图（2026-10-20第三方聚合），所有时刻"需12306官方复核"，不要声称已是官方准确数据。
2. 方向：up=进京/太原→石家庄方向，down=离京/石家庄→太原方向；unknown 保留，禁止凭车次号奇偶反推。
3. 时间绝对分钟：abs_minute = minute_of_day + day_offset*1440；次日00:10=1450，禁止用 HH:mm 字符串比较跨日。day_offset 页面未明示的保持原值并进待核，不要自动改成1。
4. 缺失留空(null/unknown)，禁止填00:00；始发无arr、终到无dep是规则留空，不是错误。
5. km 全部留空(第三方无里程)，不要用 station_order 冒充公里数。

【处理要求】
1. 先检查编码(UTF-8)、表头、行数、空值、重复行、异常格式，再定清洗步骤。
2. HH:mm→minute_of_day(0-1439)，并算 abs_minute；跨日通过 day_offset 体现。
3. 每条车次分别校验：正常停站 dep_time 不得早于 arr_time；发现疑似跨日但证据不足列待核验，不自动"修正"后静默通过。
4. 按 train_no 聚合车次，保留站序与每站到/发；区分始发/终到/停站/通过；缺失用 null/unknown 并保留异常原因。
5. 重复记录：完全重复记录后去重；同车次同站序但时刻不同=冲突，不静默选一条，写入人工复核。
6. 检查边界站、首末站缺失、station_order 重复/断号、时间倒退、车站名不一致。
7. 输出稳定可复现 JSON：同输入同规则再跑得等价结果；保留来源、remark、异常备注，不丢弃。
8. 环境支持则对输入 CSV 算 SHA-256，记录文件名/字节数/行数/校验和；不支持就明确说明。
9. 不为让图"完整"补造时刻、里程、停站。

【输出格式】
- scripts/clean_timetable.py（可按 README 命令重复运行；如改语言须说明理由）
- data/processed/shita_timetable_2026-10-20_data-v1.json
- reports/validation/validation_2026-10-20_data-v1.md
- reports/validation/cleaning_log_2026-10-20_data-v1.md
- 有冲突另出 reports/manual_review/manual_review_2026-10-20_data-v1.csv
报告至少含：输入/输出文件、总行数、有效记录数、车次数、车站数、完全重复数、冲突数、缺失字段数、无效时间数、疑似跨日项、缺失里程项、方向未知项、边界站异常、人工复核清单。

【验收标准】
- 脚本能按说明重复运行；JSON 可被标准解析器读取；
- 时间字段含义清楚，跨日不靠字符串；冲突/缺失/排除记录可追溯；
- 不静默覆盖输入 CSV；只有通过校验的数据才标记可供前端使用。

【失败/异常处理】
字段缺失、编码错误、方向未知、时间冲突、契约不匹配时，输出可定位到行号/车次/车站的报告；无法可靠修复的进待复核清单，不擅自填值；致命错误非零退出或明确标记失败。

【不要做什么】
不要让网页读CSV；不要把空值自动改0；不要把station_order当km；不要凭奇偶推方向；不要静默删冲突；不要猜跨日；不要覆盖原始文件；不要替21个未核实车补造时刻。
```

## 交接状态
- 上游提示词1 已完成并回读校验（92交路/1132行）。
- 本阶段完成后，再进入提示词3 JSON 契约（ChatGPT/DeepSeek）。
