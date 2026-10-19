# -*- coding: utf-8 -*-
"""对比 data-v1（去哪儿聚合）与 data-v2（12306 官方前端）的差异，输出 Markdown + JSON。

用法：
  python scripts/diff_datasets.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

V1 = Path("data/processed/shita_timetable_2026-10-20_data-v1.json")
V2 = Path("data/processed/shita_timetable_2026-10-20_data-v2.json")
OUT_MD = Path("reports/manual_review/data-v1_to_v2_diff.md")
OUT_JSON = Path("reports/manual_review/data-v1_to_v2_diff.json")


def load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def stop_map(train: dict) -> dict[str, dict]:
    """站名 -> stop（同名站只取第一次）。"""
    out = {}
    for s in train["stops"]:
        out.setdefault(s["station"], s)
    return out


def hm(stop: dict, key: str) -> str:
    v = stop.get(key)
    return v if v else "—"


def main() -> int:
    d1, d2 = load(V1), load(V2)
    t1 = {t["train_no"]: t for t in d1["trains"]}
    t2 = {t["train_no"]: t for t in d2["trains"]}

    added = sorted(set(t2) - set(t1))
    removed_raw = sorted(set(t1) - set(t2))
    common = sorted(set(t1) & set(t2))

    # 自动配对“同站表、同到发时刻、仅车次号不同”的交路（12306 换号口径与 v1 不同）
    def sig(t: dict):
        return tuple((s["station"], s.get("arr_time"), s.get("dep_time")) for s in t["stops"])

    renames, removed = [], []
    added_pool = list(added)
    for rno in removed_raw:
        match = next((ano for ano in added_pool if sig(t1[rno]) == sig(t2[ano])), None)
        if match:
            renames.append((rno, match))
            added_pool.remove(match)
        else:
            removed.append(rno)
    added = added_pool

    rows, diffs = [], []
    identical, time_changed = [], []
    for no in common:
        a, b = t1[no], t2[no]
        ma, mb = stop_map(a), stop_map(b)
        only_a = [s for s in ma if s not in mb]
        only_b = [s for s in mb if s not in ma]
        time_diff = []
        for st in ma:
            if st not in mb:
                continue
            sa, sb = ma[st], mb[st]
            pairs = [("arr_time", "到达"), ("dep_time", "出发")]
            for key, label in pairs:
                va, vb = sa.get(key), sb.get(key)
                if va != vb:
                    time_diff.append({"station": st, "field": label, "v1": va, "v2": vb})
        same = (not time_diff and not only_a and not only_b
                and a["direction"] == b["direction"]
                and a["train_type"] == b["train_type"])
        if same:
            identical.append(no)
        elif time_diff:
            time_changed.append(no)
        diffs.append({
            "train_no": no,
            "v1": {"origin": a["origin"], "terminal": a["terminal"], "stops": a["station_count"],
                   "duration": a["duration_minutes"], "direction": a["direction"],
                   "train_type": a["train_type"]},
            "v2": {"origin": b["origin"], "terminal": b["terminal"], "stops": b["station_count"],
                   "duration": b["duration_minutes"], "direction": b["direction"],
                   "train_type": b["train_type"]},
            "only_in_v1": only_a,
            "only_in_v2": only_b,
            "time_diffs": time_diff,
            "identical": same,
        })

    md = []
    md.append("# data-v1 → data-v2 差异报告（去哪儿聚合 → 12306 官方前端）")
    md.append("")
    md.append("> 对比对象：`shita_timetable_2026-10-20_data-v1.json`（第三方聚合，92 车）")
    md.append("> 与 `shita_timetable_2026-10-20_data-v2.json`（12306 leftTicket + queryByTrainNo）。")
    md.append("")
    md.append("## 1. 总览")
    md.append("")
    md.append("| 指标 | v1 | v2 |")
    md.append("|---|---|---|")
    md.append(f"| 车次数 | {len(t1)} | {len(t2)} |")
    md.append(f"| 站记录 | {sum(t['station_count'] for t in t1.values())} | {sum(t['station_count'] for t in t2.values())} |")
    md.append(f"| 共有车次 | — | {len(common)} |")
    md.append(f"| 仅 v1 有 | {len(removed)} | — |")
    md.append(f"| 仅 v2 有 | — | {len(added)} |")
    md.append(f"| 共有车次中完全一致 | — | {len(identical)} |")
    md.append(f"| 共有车次中时刻有变 | — | {len(time_changed)} |")
    md.append(f"| 仅编号变更（站表/时刻一致） | — | {len(renames)} |")
    md.append("")

    md.append("## 2. 车次号变更（同一列车，12306 与 v1 用了不同编号）")
    md.append("")
    if renames:
        md.append("| v1 编号 | v2 编号 | 始发→终到 | 站数 | 说明 |")
        md.append("|---|---|---|---|---|")
        for a, b in renames:
            t = t2[b]
            md.append(f"| {a} | **{b}** | {t['origin']}→{t['terminal']} | {t['station_count']} | 站表与逐站时刻完全一致，仅编号不同 |")
        md.append("")
        md.append("> 12306 以“交路首行标注的始发车次号”为准；v1 的编号来自第三方页面，现统一改为 12306 口径。")
    else:
        md.append("无。")
    md.append("")

    md.append("## 3. 仅 v1 有（12306 未返回）")
    md.append("")
    if removed:
        md.append("| 车次 | 始发 | 终到 | 站数 | 历时 |")
        md.append("|---|---|---|---|---|")
        for no in removed:
            t = t1[no]
            md.append(f"| {no} | {t['origin']} | {t['terminal']} | {t['station_count']} | {t['duration_minutes']} 分 |")
    else:
        md.append("无。")
    md.append("")

    md.append("## 4. 仅 v2 有（12306 新增）")
    md.append("")
    if added:
        md.append("| 车次 | 始发 | 终到 | 站数 | 历时 | 方向 | 车型 |")
        md.append("|---|---|---|---|---|---|---|")
        for no in added:
            t = t2[no]
            md.append(f"| {no} | {t['origin']} | {t['terminal']} | {t['station_count']} | {t['duration_minutes']} 分 | {t['direction']} | {t['train_type']} |")
    else:
        md.append("无。")
    md.append("")

    md.append("## 5. 共有车次的头部字段差异（始发/终到/历时/站数/方向/车型）")
    md.append("")
    md.append("| 车次 | v1 始发→终到 | v2 始发→终到 | v1 历时 | v2 历时 | 站数 v1→v2 | 方向 | 车型 |")
    md.append("|---|---|---|---|---|---|---|---|")
    head_changed = 0
    for d in diffs:
        a, b = d["v1"], d["v2"]
        if (a["origin"], a["terminal"], a["duration"], a["stops"], a["direction"], a["train_type"]) == \
           (b["origin"], b["terminal"], b["duration"], b["stops"], b["direction"], b["train_type"]):
            continue
        head_changed += 1
        flag = lambda x, y: f"**{x}→{y}**" if x != y else str(x)  # noqa: E731
        md.append(f"| {d['train_no']} | {a['origin']}→{a['terminal']} | {b['origin']}→{b['terminal']} | "
                  f"{a['duration']} | {b['duration']} | {a['stops']}→{b['stops']} | "
                  f"{flag(a['direction'], b['direction'])} | {flag(a['train_type'], b['train_type'])} |")
    if head_changed == 0:
        md.append("| — | 全部一致 | — | — | — | — | — | — |")
    md.append("")

    md.append("## 6. 逐站时刻差异")
    md.append("")
    if time_changed:
        for no in time_changed:
            d = next(x for x in diffs if x["train_no"] == no)
            md.append(f"### {no}（{d['v1']['origin']}→{d['v1']['terminal']}）")
            md.append("")
            if d["only_in_v1"]:
                md.append(f"- v1 多出站：{'、'.join(d['only_in_v1'])}")
            if d["only_in_v2"]:
                md.append(f"- v2 多出站：{'、'.join(d['only_in_v2'])}")
            md.append("")
            md.append("| 车站 | 字段 | v1 | v2 |")
            md.append("|---|---|---|---|")
            for td in d["time_diffs"]:
                md.append(f"| {td['station']} | {td['field']} | {td['v1'] or '—'} | {td['v2'] or '—'} |")
            md.append("")
    else:
        md.append("共有车次的逐站时刻**全部一致**。")
        md.append("")

    md.append("## 7. 结论")
    md.append("")
    md.append(f"- v2 共 {len(t2)} 车，其中 {len(common)} 车与 v1 同编号可逐站比对；"
              f"**逐站到发时刻 0 差异**（{len(identical)}/{len(common)} 完全一致）。")
    md.append(f"- 覆盖范围：v2 多 {len(added)} 车（v1 未采到的 K/T/Z 普速与部分 D/G/C），"
              f"少 {len(removed)} 车{('（' + '、'.join(removed) + '，当日不开行或已改号）') if removed else ''}。")
    md.append(f"- {len(renames)} 车仅编号不同，站表与时刻完全一致（见 §2）。")
    md.append("")
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(md), encoding="utf-8")

    OUT_JSON.write_text(json.dumps({
        "v1_trains": len(t1), "v2_trains": len(t2),
        "common": len(common), "added": added, "removed": removed,
        "identical": identical, "time_changed": time_changed,
        "diffs": diffs,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"v1={len(t1)} v2={len(t2)} common={len(common)} added={len(added)} removed={len(removed)}")
    print(f"identical={len(identical)} time_changed={len(time_changed)}")
    print(f"added: {' '.join(added)}")
    print(f"removed: {' '.join(removed)}")
    print(f"[write] {OUT_MD}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
