# 测试报告 · 石太客专运行图 web-v1.3.0

> 日期：2026-10-19　｜　数据：`shita_timetable_2026-10-20_data-v1.json`（2,271,203 B，SHA-256 `5692feb075a2a57f19a84cff5592cafaaff676e529992ecbfc6cbfa5ded0c0b4`）
> 契约：2.0.0　｜　页面：web-v1.3.0　｜　环境：Windows 11 · Edge headless · Node 22 · Python 3.13

## 1. 结论

| 套件 | 用例数 | 通过 | 失败 | 退出码 |
|---|---|---|---|---|
| 端到端 `scripts/test_e2e.mjs` | 43 | 43 | 0 | 0 |
| 纯函数 `scripts/test_pure.mjs` | 22 | 22 | 0 | 0 |
| 契约 `scripts/validate_contract.py --all` | 3 个文件 × (Schema + 11 不变量) | 全部 PASS | 0 | 0 |
| 手工用例 | 2 | — | — | 未执行 |

**总体：通过（自动化部分）。** 手工项（长时播放、视觉检查）未执行，不计入通过。

## 2. 本轮修正与验证

修正内容（用户指图）：站序应为 `太原 → 东凌井 → 阳泉北 → 井陉北 → 获鹿 → 石家庄`；石家庄北经**石太普铁**挂**获鹿**，不挂石家庄；石家庄—石家庄北之间不画连线。

| 用例 | 断言 |
|---|---|
| E2E-04 | 虚线联络线的端点是 `获鹿` 与 `石家庄北`（不是石家庄） |
| E2E-06 | 所有 `.ld-track` 路径的每一段都是水平或垂直 |
| E2E-07 | 当前时刻所有车底点到最近轨道的距离 < 0.5px |
| PURE-09 | 阳泉北→石家庄北 的路径经过获鹿、且不经过石家庄 |
| PURE-10 | 86 车全程采样，车底点偏离轨道最大 0.000px |

## 3. 端到端输出（原样）

```text
PASS | 两视图各渲染 86 车 | 86/86
PASS | 初始暂停且时间 10:00
PASS | 运行图纵轴分成 7 行 | 石家庄 / 石家庄北 / 阳泉北 / 阳泉东 / 平定 / 太原 / 太原南
PASS | 获鹿—石家庄北（石太普铁）为虚线联络线 | {"dash":"7 5","a":"获鹿","b":"石家庄北"}
PASS | 一城双停：G622 同时停太原南与太原 | 太原南→太原
PASS | 轨道全部横平竖直（无斜线） | {"paths":14,"segs":14,"bad":0}
PASS | 车底点严格贴在轨道上 | {"worst":{"off":2.842170943040401e-14,"train":"G3386"},"count":13}
PASS | 1x 播放约 2 分钟/秒 | Δ=2.03
PASS | 暂停后时间不推进 | 602.08 → 602.08
PASS | 5x 播放约 10 分钟/秒 | Δ=10.05
PASS | 0.5x 播放约 1 分钟/秒 | Δ=1.01
PASS | 2x 播放约 4 分钟/秒 | Δ=4.04
PASS | destroy 后停止推进并清理监听 | 62 → 62
PASS | 反复播放/暂停不产生多个 RAF 循环 | Δ=2.01
PASS | +1 分钟精确 +1 | 601
PASS | −1 分钟精确 −1 | 600
PASS | ← / → 逐分钟 | 601
PASS | 空格播放/暂停
PASS | 选择器聚焦时空格不误触 | playing=false
PASS | 到边界停止且不绕回 | 2700=2700, playing=false
PASS | 拖到末端即停 | 2700
PASS | 时间读数与 Marey 光标一致
PASS | 线路图可见标记 = 活动车次 | 12/12
PASS | 次日时刻显示正确（1450 = 次日 00:10） | 次日 00:10
PASS | 方向=上行：两视图一致 | 43/43/43
PASS | 车型=高铁筛选 | 32/32
PASS | 车站=阳泉北（停站） | 84/84
PASS | 通过模式为空状态（本批无通过站） | visible=0, banner=true
PASS | 重置筛选恢复全部 | 86/86
PASS | 筛选不重置时间、不暂停 | 600.6 → 601.3, playing=true
PASS | 点击 Marey 车次 → 详情 | S951下行 · 市郊 已校验 始发 → 终到 阳泉北 → 阳泉东 停站数 2 全程时长 28 分钟 跨日 无 数据来源
PASS | 选中同步到线路图 | 1
PASS | 选中车次被筛掉时清空并提示 | cleared=true
PASS | 点击线路图标记 → 同一份详情 | G606上行 · 高铁 已校验 始发 → 终到 太原南 → 北京丰台 停站数 5
PASS | 线路图选中同步回 Marey
PASS | 空筛选不报错
PASS | 拖动时暂停且时间跟随 | 次日 03:06, playing=false
PASS | 松手后恢复播放 | playing=true
PASS | file:// 打开给出明确提示 | 无法加载数据：Failed to fetch。浏览器在 file:// 下禁止 fetch，请用本地
PASS | 非法 JSON 显示错误而非白屏 | 无法加载数据：Expected property name or '}' in 
PASS | 契约主版本不匹配时拒绝渲染 | 数据契约版本不匹配：页面按 v2.x 读取，文件为 v3.0.0。
PASS | 窄屏（900px）切为单列 | columns=1
PASS | 页面无 console/page 错误

合计 43 项，失败 0 项
```

## 4. 纯函数输出（原样）

```text
PASS | Marey：夹具轴只有 3 站
PASS | Marey：跨日 00:10 = 1450，不回绕
PASS | Marey：未映射站断线
PASS | Marey：真实数据 7 行，太原/太原南、石家庄/石家庄北分开
PASS | Line：石家庄北为联络线、阳泉东为阳大支线
PASS | Line：上北下南（太原在太原南上方、石家庄北在石家庄上方）
PASS | Line：所有轨道边横平竖直（无斜线）
PASS | Line：阳泉北→石家庄北 经获鹿走石太普铁，不经过石家庄站
PASS | Line：运行中的车底点严格落在轨道上（0 像素偏差）
PASS | Marey：时间域按 coverage 取整
PASS | Line：区间腿 3 段（run/dwell/run）
PASS | Line：跨日 00:00 位于区间中点
PASS | Line：停站固定
PASS | Line：终到停在终点
PASS | Line：未发车隐藏
PASS | Line：真实数据 86 车都有区间腿
PASS | 筛选：夹具方向 down
PASS | 筛选：真实数据 上行 46 / 下行 46 / 高铁 32（含阻断车）
PASS | 筛选：阳泉北停站 90 车（含阻断），通过 0 车
PASS | 筛选：不改动源数组
PASS | 车型选项来自数据且含 6 类
PASS | 时刻格式化：1450 → 次日 00:10

合计 22 项，失败 0 项
```

## 5. 契约校验输出（原样）

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

## 6. 未覆盖项（如实记录）

1. MANUAL-01 长时播放（10 分钟）稳定性 —— 未执行。
2. MANUAL-02 视觉检查 —— 未做系统性人工检查。
3. 方向未知 / 通过站 / 停运车 —— 本批无样本。
4. 极慢设备上的时序容差 —— 未验证。
5. 时刻数据本身仍需 12306 复核；本报告只证明页面按契约正确消费数据。

## 7. 数据一致性锚点

train/stops 投影（车次、方向、逐站站名与到发、day_offset）SHA-256：

`412fc0293aa994c58794d3ad2343047232af8967e1fb0c14ed8845857ca9b81b`

本轮只改站点顺序、坐标与接轨点，`trains` / `segments` / `warnings` 与输入 CSV（`a061ad4a…`）均未变。

## 8. 复现

```bash
python -m http.server 8000
node scripts/test_pure.mjs
node scripts/test_e2e.mjs
python scripts/validate_contract.py --all
```
