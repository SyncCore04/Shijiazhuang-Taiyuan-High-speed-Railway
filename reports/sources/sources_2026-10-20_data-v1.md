# 来源清单（2026-10-20 现行图 · data-v1）

- 采集基准日：2026-10-20 现行图；实际访问日期：2026-10-19（本地），页面 queryDate=2026-10-20。
- **所有时刻均为第三方平台聚合数据，一律需12306官方复核**；本次未访问12306、未绕验证码/反爬、未高频请求。
- 产物：`data/raw/shita_train_timetable_2026-10-20_data-v1_draft.csv`（92 个物理交路 / 1132 行）。

## 一、主来源：去哪儿单车现行页

- URL 模板：`https://train.qunar.com/train/timetable/{车次}`
- 访问日期：2026-10-19；页面 queryDate=2026-10-20，含 14 天运行图开/停芯片与内嵌绝对时刻（ld+json / page-data-json）。
- 支持范围：本批 92 个入 CSV 物理交路的全程经停站、到发时刻、车型、换号节点；跨日（day_offset=1）依据页面绝对到达时间判定。
- 可信度：中。第三方聚合，时刻与停站需12306复核；运行图芯片可判断近14天开/停，但不替代官方图。
- 分片覆盖：

| 分片 | 文件 | 入CSV车次（物理交路） | 行数 |
|---|---|---|---|
| 种子（已核实样板） | shard_00_seed.csv | C800, C799, S951, D1095 | 14 |
| A 阳大/市郊/城际 | shard_A_yangda.csv | D1096, S952–S966（15趟市郊） | 33 |
| B G 短线（北京↔太原/晋内） | shard_B_gshort.csv | G601,G602,G606,G607,G608,G610,G611,G620,G621,G622,G623,G624,G626,G627,G628,G629,G683,G684,G791,G792 | 158 |
| C G 跨局长线 | shard_C_glong.csv | G1861,G1862,G1955,G1956,G2605,G2606,G2609,G2610,G2620,G2637,G3385,G3386 | 189 |
| D D 跨局长线 | shard_D_dlong.csv | D15,D16,D69,D70,D918,D917,D1630,D1629 | 106 |
| E1 D 山东/西北群1 | shard_E1_dgroup1.csv | D1634,D1638,D1637,D1642,D1641,D1646,D1645,D1650,D1649,D1657,D1665,D1670 | 229 |
| E2 D 山东群2/内蒙 | shard_E2_dgroup2.csv | D1671,D1672,D1675,D1676 | 97 |
| F1 普速K已知清单 | shard_F1_kknown.csv | K374,K373,K565,K585,K587,K730,K866,K609 | 150 |
| F2 普速KTZ额外候选 | shard_F2_ktzextra.csv | K1117,K1331,K1572,K213,Z198,Z267,Z268,Z55 | 156 |
| H 额外候选核验 | shard_H_candidates.csv | 0（全部排除/未核实，仅表头） | 0 |

## 二、交叉来源：携程单车页

- URL 模板：`https://trains.ctrip.com/TrainSchedule/{车次}/`
- 访问日期：2026-10-19。
- 实际作用：仅用于去哪儿缺页或抽查交叉（D1096、D1634、D1637 等时刻/经停一致）；多数页面为 JS 壳，静态 HTML 无停站时刻（trainStopList=[]），不能作为时刻来源。
- 可信度：中低（静态可取数据少）；未采用其任何独立时刻。

## 三、候选线索来源（时刻不采信）

- ip.cn 车站清单页：
  - 阳泉北 `https://www.ip.cn:8443/train/shanxi/yangquanbei.html`（声称157趟，渲染约80条，含套跑重复编号、可能过时）
  - 阳泉东 `https://www.ip.cn:8443/train/shanxi/yangquandong.html`（28趟）
  - 石家庄北 `https://www.ip.cn:8443/train/hebei/shijiazhuangbei.html`（声称121趟）
  - 太原南 `https://www.ip.cn:8443/train/shanxi/taiyuannan.html`（大西/太焦省内车居多，多数不经石太通道）
- 用途：仅用于找候选车次号；**其到发时刻一律未采信**，每个车次均回到去哪儿现行页核验。
- 可信度：低（过时、重复、列错站），仅作线索。

## 四、未采用通道

- 携程区间列表页（`/TrainBooking/{from}-to-{to}.html`）：JS 渲染无静态数据，未取得车次列表，未采用。
- 12306：按要求未访问、未绕过登录/验证码。

## 五、逐车来源与去重/冲突明细

见各分片 notes：`data/raw/shards/shard_{A,B,C,D,E1,E2,F1,F2,H}_notes.md`，含每车 URL、访问日期、方向依据、换号去重、停运/未能核实记录。
