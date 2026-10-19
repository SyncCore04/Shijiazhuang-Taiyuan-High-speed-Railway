# 测试计划与用例 · 石太客专运行图

> 版本：v1.0（2026-10-19）｜对应数据：`data-v1` / 契约 `1.0.0` / 页面 `web-v1.0.0`
> 测试数据：真实数据 `data/processed/…json` + synthetic `data/test-fixtures/*.json`（严格分离，文件名含 synthetic）
> 结论汇总见 `reports/validation/test_report_2026-10-19.md`

---

## 1. 范围与环境

| 项 | 内容 |
|---|---|
| 被测对象 | `index.html` + `js/{marey-chart,line-diagram,player,interactions}.js` + 清洗产物 JSON |
| 环境 | Windows 11 · Edge（Chromium 内核）headless · Node 22 · Python 3.13 |
| 运行方式 | 项目根目录 `python -m http.server 8000`，访问 `http://localhost:8000/index.html` |
| 自动化 | `node scripts/test_e2e.mjs`（43 项，需 playwright-core）· `node scripts/test_pure.mjs`（22 项，无浏览器）· `python scripts/validate_contract.py --all`（Schema + 11 项不变量） |
| 前置 | 8000 端口可用；`data/processed/…json` 已生成且校验和未被改动 |
| 风险 | ① 时刻为第三方聚合，测试只证明"内部自洽"，不证明官方正确；② 6 车阻断数据不可绘制；③ 播放时序断言依赖真实时钟，极慢机器上容差可能不够 |

**测试数据分层**：`data/test-fixtures/` 下所有文件 `meta.data_kind = "synthetic"`，页面拒绝加载非 real 数据；真实数据只在 `data/processed/`。两者不混用。

---

## 2. 必测场景覆盖矩阵（对照提示词8 的 14 项）

| # | 场景 | 覆盖方式 | 结果 |
|---|---|---|---|
| 1 | 跨日 23:50 → 次日 00:10（1430 → 1450） | PURE-02/06、E2E-24、夹具 `synthetic_crossday_tiny.json` | PASS |
| 2 | 同站停留位置固定 / Marey 水平停站段 | PURE-07、E2E-23 | PASS |
| 3 | 暂停后不推进；±1 分钟精确 | E2E-09/15/16 | PASS |
| 4 | 0.5x / 1x / 2x / 5x 比例正确 | E2E-08/10/11/12 | PASS |
| 5 | 拖动时间轴同步、不跳回、松手恢复 | E2E-21/37/38 | PASS |
| 6 | 筛选后播放不重置时间 | E2E-30 | PASS |
| 7 | 边界站/首末站处理 | 数据层 `validation_…md §6`；详情显示「始发/终到」（E2E-31） | PASS |
| 8 | 缺失里程不得当 0 | 契约校验 `km 全为 null`；UI 无 km 展示 | PASS |
| 9 | 方向未知 / 类型未知 / 停站未知 | 本批 `unknown=0`、`is_stop` 全 true，无真实样本；选项按数据动态生成 | N/A（原因已说明） |
| 10 | 重复车次 / 重复站序 / 时间倒退 / 冲突 | 数据层 0 重复、0 冲突；前端只画 86 车（E2E-01） | PASS |
| 11 | 键盘：空格、←/→、输入控件不误触 | E2E-17/18/19 | PASS |
| 12 | RAF 生命周期：反复播放不叠加、销毁后停止 | E2E-13/14 | PASS |
| 13 | 空数据 / 单车次 / 大量 / 非法 JSON / 版本不匹配 | E2E-36/40/41、PURE-06~09、E2E-01 | PASS |
| 14 | 本地运行方式 | E2E-39（`file://` 提示）+ README | PASS |

> 站点拓扑与轨道专项：E2E-03（纵轴 7 行）、E2E-04（获鹿—石家庄北 石太普铁虚线，且不连石家庄）、E2E-05（一城双停）、E2E-06（轨道无斜线）、E2E-07（车底点贴轨）；
> PURE-05/06/07（坐标方位与支线挂接）、PURE-08（轨道正交）、PURE-09（阳泉北→石家庄北 经获鹿、不过石家庄）、PURE-10（0 像素偏离）。

## 3. 用例表（自动化）

### 3.1 端到端 `scripts/test_e2e.mjs`（43 项）

| 编号 | 用例 | 实测 | 结果 |
|---|---|---|---|
| E2E-01 | 两视图各渲染 86 车 | 86/86 | PASS |
| E2E-02 | 初始暂停且时间 10:00 |  | PASS |
| E2E-03 | 运行图纵轴分成 7 行 | 石家庄 / 石家庄北 / 阳泉北 / 阳泉东 / 平定 / 太原 / 太原南 | PASS |
| E2E-04 | 获鹿—石家庄北（石太普铁）为虚线联络线 | {"dash":"7 5","a":"获鹿","b":"石家庄北"} | PASS |
| E2E-05 | 一城双停：G622 同时停太原南与太原 | 太原南→太原 | PASS |
| E2E-06 | 轨道全部横平竖直（无斜线） | {"paths":14,"segs":14,"bad":0} | PASS |
| E2E-07 | 车底点严格贴在轨道上 | {"worst":{"off":2.842170943040401e-14,"train":… | PASS |
| E2E-08 | 1x 播放约 2 分钟/秒 | Δ=2.03 | PASS |
| E2E-09 | 暂停后时间不推进 | 602.08 → 602.08 | PASS |
| E2E-10 | 5x 播放约 10 分钟/秒 | Δ=10.05 | PASS |
| E2E-11 | 0.5x 播放约 1 分钟/秒 | Δ=1.01 | PASS |
| E2E-12 | 2x 播放约 4 分钟/秒 | Δ=4.04 | PASS |
| E2E-13 | destroy 后停止推进并清理监听 | 62 → 62 | PASS |
| E2E-14 | 反复播放/暂停不产生多个 RAF 循环 | Δ=2.01 | PASS |
| E2E-15 | +1 分钟精确 +1 | 601 | PASS |
| E2E-16 | −1 分钟精确 −1 | 600 | PASS |
| E2E-17 | ← / → 逐分钟 | 601 | PASS |
| E2E-18 | 空格播放/暂停 |  | PASS |
| E2E-19 | 选择器聚焦时空格不误触 | playing=false | PASS |
| E2E-20 | 到边界停止且不绕回 | 2700=2700, playing=false | PASS |
| E2E-21 | 拖到末端即停 | 2700 | PASS |
| E2E-22 | 时间读数与 Marey 光标一致 |  | PASS |
| E2E-23 | 线路图可见标记 = 活动车次 | 12/12 | PASS |
| E2E-24 | 次日时刻显示正确（1450 = 次日 00:10） | 次日 00:10 | PASS |
| E2E-25 | 方向=上行：两视图一致 | 43/43/43 | PASS |
| E2E-26 | 车型=高铁筛选 | 32/32 | PASS |
| E2E-27 | 车站=阳泉北（停站） | 84/84 | PASS |
| E2E-28 | 通过模式为空状态（本批无通过站） | visible=0, banner=true | PASS |
| E2E-29 | 重置筛选恢复全部 | 86/86 | PASS |
| E2E-30 | 筛选不重置时间、不暂停 | 600.6 → 601.3, playing=true | PASS |
| E2E-31 | 点击 Marey 车次 → 详情 | S951下行 · 市郊 已校验 始发 → 终到 阳泉北 → 阳泉东 停站数 2 全程时长 2… | PASS |
| E2E-32 | 选中同步到线路图 | 1 | PASS |
| E2E-33 | 选中车次被筛掉时清空并提示 | cleared=true | PASS |
| E2E-34 | 点击线路图标记 → 同一份详情 | G606上行 · 高铁 已校验 始发 → 终到 太原南 → 北京丰台 停站数 5 | PASS |
| E2E-35 | 线路图选中同步回 Marey |  | PASS |
| E2E-36 | 空筛选不报错 |  | PASS |
| E2E-37 | 拖动时暂停且时间跟随 | 次日 03:06, playing=false | PASS |
| E2E-38 | 松手后恢复播放 | playing=true | PASS |
| E2E-39 | file:// 打开给出明确提示 | 无法加载数据：Failed to fetch。浏览器在 file:// 下禁止 fetch，… | PASS |
| E2E-40 | 非法 JSON 显示错误而非白屏 | 无法加载数据：Expected property name or '}' in  | PASS |
| E2E-41 | 契约主版本不匹配时拒绝渲染 | 数据契约版本不匹配：页面按 v2.x 读取，文件为 v3.0.0。 | PASS |
| E2E-42 | 窄屏（900px）切为单列 | columns=1 | PASS |
| E2E-43 | 页面无 console/page 错误 |  | PASS |

### 3.2 纯函数 `scripts/test_pure.mjs`（22 项）

| 编号 | 用例 | 实测 | 结果 |
|---|---|---|---|
| PURE-01 | Marey：夹具轴只有 3 站 |  | PASS |
| PURE-02 | Marey：跨日 00:10 = 1450，不回绕 |  | PASS |
| PURE-03 | Marey：未映射站断线 |  | PASS |
| PURE-04 | Marey：真实数据 7 行，太原/太原南、石家庄/石家庄北分开 |  | PASS |
| PURE-05 | Line：石家庄北为联络线、阳泉东为阳大支线 |  | PASS |
| PURE-06 | Line：上北下南（太原在太原南上方、石家庄北在石家庄上方） |  | PASS |
| PURE-07 | Line：所有轨道边横平竖直（无斜线） |  | PASS |
| PURE-08 | Line：阳泉北→石家庄北 经获鹿走石太普铁，不经过石家庄站 |  | PASS |
| PURE-09 | Line：运行中的车底点严格落在轨道上（0 像素偏差） |  | PASS |
| PURE-10 | Marey：时间域按 coverage 取整 |  | PASS |
| PURE-11 | Line：区间腿 3 段（run/dwell/run） |  | PASS |
| PURE-12 | Line：跨日 00:00 位于区间中点 |  | PASS |
| PURE-13 | Line：停站固定 |  | PASS |
| PURE-14 | Line：终到停在终点 |  | PASS |
| PURE-15 | Line：未发车隐藏 |  | PASS |
| PURE-16 | Line：真实数据 86 车都有区间腿 |  | PASS |
| PURE-17 | 筛选：夹具方向 down |  | PASS |
| PURE-18 | 筛选：真实数据 上行 46 / 下行 46 / 高铁 32（含阻断车） |  | PASS |
| PURE-19 | 筛选：阳泉北停站 90 车（含阻断），通过 0 车 |  | PASS |
| PURE-20 | 筛选：不改动源数组 |  | PASS |
| PURE-21 | 车型选项来自数据且含 6 类 |  | PASS |
| PURE-22 | 时刻格式化：1450 → 次日 00:10 |  | PASS |

### 3.3 契约校验 `scripts/validate_contract.py`

真实数据与两个 synthetic 夹具均通过 Schema（Draft 2020-12）+ 11 项不变量（时间模型、站序、引用完整性、区间与站点一致、数量守恒、告警引用、stats 自洽、km 全 null、阻断车不标记可绘制、data_kind 与文件性质一致）。

---

## 4. 手工用例（未自动化）

| 编号 | 场景 | 步骤 | 预期 | 状态 |
|---|---|---|---|---|
| MANUAL-01 | 长时间播放 | 5x 连播 10 分钟 | 无内存增长/卡顿，时间不跳变，暂停后立即停 | 待执行 |
| MANUAL-02 | 视觉检查 | 人工看两视图重叠、标签可读性、颜色对比 | 无遮挡致命、图例可辨 | 待执行 |

> `file://` 提示、非法 JSON、契约版本不匹配、窄屏、连续拖动已转为自动化（E2E-32～E2E-37），不再列手工。

## 5. 缺陷与验收模板

- 缺陷报告：`docs/templates/defect-report.md`
- 验收报告：`docs/templates/acceptance-report.md`

---

## 6. 复现命令

```bash
# 1) 起服务
python -m http.server 8000

# 2) 纯函数回归（无需浏览器）
node scripts/test_pure.mjs

# 3) 端到端（需 playwright-core + Edge）
node scripts/test_e2e.mjs

# 4) 契约校验（需 jsonschema）
python scripts/validate_contract.py --all
```
