# 归档清单（web-v1.3.0 / data-v1 / contract 2.0.0）

> 归档日期：2026-10-19　｜　目标环境：本地 Windows，通过 `python -m http.server` 访问
> 标记：✅ 完成　🟡 有条件（见备注）　⬜ 未完成

## 1. 交付文件

| 类别 | 文件 | 状态 |
|---|---|---|
| 页面 | `index.html` | ✅ |
| 样式 | `css/demo.css`、`css/app.css` | ✅ |
| 模块 | `js/marey-chart.js`、`js/line-diagram.js`、`js/player.js`、`js/interactions.js` | ✅ |
| 数据 | `data/processed/shita_timetable_2026-10-20_data-v1.json` | ✅ |
| 测试数据 | `data/test-fixtures/synthetic_contract_sample.json`、`synthetic_crossday_tiny.json` | ✅（synthetic 标记） |
| 清洗 | `scripts/clean_timetable.py` | ✅ |
| 校验/测试 | `scripts/validate_contract.py`、`test_pure.mjs`、`test_e2e.mjs` | ✅ |
| 契约 | `docs/data-contract.md`、`docs/schema/shita-timetable.schema.json` | ✅ |
| 文档 | `README.md`、`docs/data-sources.md`、`docs/version-history.md`、`docs/test-plan.md`、`docs/modules/*` | ✅ |
| 报告 | `reports/sources/*`、`reports/validation/*`、`reports/manual_review/*` | ✅ |
| 演示页（阶段4/5） | `marey-demo.html`、`line-demo.html` | 🟡 保留备查，非最终页 |

## 2. 不进入公开分发的文件

| 文件 | 原因 |
|---|---|
| `data/raw/**` | 原始采集数据，第三方聚合，未确认可再分发 |
| `data/raw/shards/**` | 分片采集记录，含逐页 URL |

个人本地归档保留；对外只发布清洗后的 JSON 与页面。

## 3. 验收状态

| 项 | 状态 |
|---|---|
| 页面可在本地 HTTP 下打开并交互 | ✅（E2E-01/38） |
| 两视图同屏联动 | ✅（E2E-17/20/27/30） |
| 播放器时序/倍速/边界/键盘 | ✅（E2E-03~16） |
| 筛选语义与空状态 | ✅（E2E-20~25/31） |
| 跨日不靠字符串 | ✅（E2E-19、PURE-02/06） |
| 6 车阻断有明确说明 | ✅（页面脚注 + 图例） |
| 长时播放稳定性 | ⬜ 未执行（MANUAL-01） |
| 人工视觉检查 | ⬜ 未执行（MANUAL-02） |
| 双击 `file://` 离线包 | ⬜ 未实施（当前明确不支持，页面有提示） |

## 4. 待核实（数据层，非页面缺陷）

1. 6 车 `day_offset`（K373/K374/K565/K609/K730/K866）需 12306 核定。
2. 21 个未核实车次、5 个停运车次是否现行开行。
3. G2637 第 8 站（滨海北/西）。
4. 昔阳 ↔ 大寨(昔阳) 站名归一、平定/昔阳办客状态。
5. 两线逐站里程（当前全 null）。
6. ip.cn 声称 157 趟与实际 92 交路的差异。

## 5. 版本映射

| 交付物 | 版本 | 校验和 |
|---|---|---|
| 数据 JSON | data-v1（2026-10-19 再生） | `5692feb075a2a57f19a84cff5592cafaaff676e529992ecbfc6cbfa5ded0c0b4` |
| 原始 CSV | data-v1 | `a061ad4a36ac825ef74c6702b552501b3c3fa9f9119e3032f6269c071a9215e6` |
| 契约 | 2.0.0 | 见 `docs/schema/shita-timetable.schema.json` |
| 页面 | web-v1.3.0 | marey 1.1.0 / line 1.2.0 / player 1.0.0 / interactions 1.0.0 |
