#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
契约校验器（提示词3 / 阶段3）

两段校验：
  A. JSON Schema（Draft 2020-12）结构校验 —— 依赖 jsonschema 包
  B. 跨字段不变量（纯标准库）—— 防止「结构合法但数据自相矛盾」

用法：
  python scripts/validate_contract.py                      # 校验真实数据
  python scripts/validate_contract.py --data <file> ...    # 校验指定文件（可多个）
  python scripts/validate_contract.py --all                # 真实数据 + synthetic 样例

退出码：0 全通过；1 有失败；2 环境缺依赖。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = ROOT / "docs/schema/shita-timetable.schema.json"
DEFAULT_DATA = sorted((ROOT / "data/processed").glob("shita_timetable_2026-10-20_data-v*.json"))
SYNTHETIC = ROOT / "data/test-fixtures/synthetic_contract_sample.json"


class Checker:
    def __init__(self, label):
        self.label = label
        self.results = []

    def add(self, name, ok, detail=""):
        self.results.append((name, bool(ok), detail))

    @property
    def failed(self):
        return [r for r in self.results if not r[1]]


def hhmm_to_minutes(value):
    h, m = value.split(":")
    return int(h) * 60 + int(m)


def check_invariants(data, source_path=""):
    """跨字段一致性检查；返回 Checker。"""
    c = Checker("invariants")

    # 1. 时间模型：abs = minute_of_day + day_offset*1440
    bad = []
    checked = 0
    for t in data["trains"]:
        for s in t["stops"]:
            for key in ("arr", "dep"):
                minute = s["minute_of_day"][key]
                absolute = s["abs_minute"][key]
                raw = s[f"{key}_time"]
                if raw is None:
                    if minute is not None or absolute is not None:
                        bad.append(f"{t['train_no']}/{s['station']}/{key}: 原始时刻为空但分钟非空")
                    continue
                checked += 1
                if minute != hhmm_to_minutes(raw):
                    bad.append(f"{t['train_no']}/{s['station']}/{key}: minute_of_day != HH:mm 换算")
                if absolute != minute + s["day_offset"] * 1440:
                    bad.append(f"{t['train_no']}/{s['station']}/{key}: abs != minute + offset*1440")
    c.add("时间模型 abs=minute+offset*1440", not bad,
          f"{len(bad)} 处不一致" if bad else f"{checked} 个时刻全部满足")

    # 2. 站序 1..N 连续且唯一
    bad = []
    for t in data["trains"]:
        orders = [s["station_order"] for s in t["stops"]]
        if orders != list(range(1, len(orders) + 1)):
            bad.append(f"{t['train_no']}: {orders[:8]}…")
        if t["station_count"] != len(t["stops"]):
            bad.append(f"{t['train_no']}: station_count 与 stops 长度不符")
    c.add("站序 1..N 连续唯一", not bad, "; ".join(bad[:3]) or "全部车次通过")

    # 3. 引用完整性：stops / segments / warnings → stations
    station_ids = {s["station_id"] for s in data["stations"]}
    train_ids = {t["train_id"] for t in data["trains"]}
    bad = []
    for t in data["trains"]:
        for s in t["stops"]:
            if s["station_id"] not in station_ids:
                bad.append(f"stop 引用未知站 {s['station_id']}")
            if s["station_id"] != "st:" + s["station"]:
                bad.append(f"station_id 与站名不一致 {s['station']}")
    for seg in data["segments"]:
        if seg["train_id"] not in train_ids:
            bad.append(f"segment 引用未知车次 {seg['train_id']}")
        for key in ("from_station_id", "to_station_id"):
            if seg[key] not in station_ids:
                bad.append(f"segment 引用未知站 {seg[key]}")
    c.add("stops/segments 引用完整", not bad, "; ".join(bad[:3]) or "全部可解析")

    # 4. segment 与 stop 的时刻必须一一对应
    stop_index = {}
    for t in data["trains"]:
        for s in t["stops"]:
            stop_index[(t["train_id"], s["station_order"])] = s
    bad = []
    for seg in data["segments"]:
        f = stop_index.get((seg["train_id"], seg["from_station_order"]))
        to = stop_index.get((seg["train_id"], seg["to_station_order"]))
        if f is None or to is None:
            bad.append(f"{seg['segment_id']}: 端点站序不存在")
            continue
        if seg["segment_type"] == "dwell":
            if seg["from_station_id"] != seg["to_station_id"]:
                bad.append(f"{seg['segment_id']}: dwell 两端站不同")
            if seg["arrival_abs_minute"] != f["abs_minute"]["arr"] or \
               seg["departure_abs_minute"] != f["abs_minute"]["dep"]:
                bad.append(f"{seg['segment_id']}: dwell 时刻与站点不一致")
        elif seg["segment_type"] == "run":
            if seg["to_station_order"] != seg["from_station_order"] + 1:
                bad.append(f"{seg['segment_id']}: run 站序不连续")
            if seg["departure_abs_minute"] != f["abs_minute"]["dep"] or \
               seg["arrival_abs_minute"] != to["abs_minute"]["arr"]:
                bad.append(f"{seg['segment_id']}: run 时刻与站点不一致")
    c.add("segment↔stop 时刻一致", not bad, "; ".join(bad[:3]) or f"{len(data['segments'])} 条区间全部对齐")

    # 5. segment 数量守恒：dwell + run = 停站数 + 有后继的站数
    expected = 0
    for t in data["trains"]:
        for i, s in enumerate(t["stops"]):
            if s["arr_time"] and s["dep_time"] and (s["dwell_minutes"] or 0) > 0:
                expected += 1
            if i < len(t["stops"]) - 1:
                expected += 1
    c.add("segment 数量守恒", len(data["segments"]) == expected,
          f"实际 {len(data['segments'])} / 期望 {expected}")

    # 6. 告警引用（excluded 允许指向未录入车次）
    bad = []
    for w in data["warnings"]:
        if w["train_id"] is not None and w["train_id"] not in train_ids and w["severity"] != "excluded":
            bad.append(f"{w['warning_id']}: 未知 train_id {w['train_id']}")
        if w["station_id"] is not None and w["station_id"] not in station_ids:
            bad.append(f"{w['warning_id']}: 未知 station_id {w['station_id']}")
    c.add("warnings 引用完整", not bad, "; ".join(bad[:3]) or f"{len(data['warnings'])} 条告警")

    # 7. stats 与数组一致
    st = data["stats"]
    meta = data["meta"]
    pairs = [
        ("trains", st["trains"], len(data["trains"])),
        ("stations", st["stations"], len(data["stations"])),
        ("segments", st["segments"], len(data["segments"])),
        ("stop_records", st["stop_records"], sum(len(t["stops"]) for t in data["trains"])),
        ("warnings.total", st["warnings"]["total"], len(data["warnings"])),
        ("usable+blocked", st["usable_trains"] + st["blocked_trains"], st["trains"]),
        ("meta.usable_trains", meta["validation_status"]["usable_trains"], st["usable_trains"]),
    ]
    bad = [f"{k}: {a} != {b}" for k, a, b in pairs if a != b]
    c.add("stats 自洽", not bad, "; ".join(bad[:3]) or "计数与数组长度一致")

    # 8. 空值不得被填 0：km 必须全为 null 且计数吻合
    km_null = sum(1 for t in data["trains"] for s in t["stops"] if s["km"] is None)
    c.add("km 全为 null 且计数吻合",
          km_null == st["km_missing_stops"] == st["stop_records"],
          f"null {km_null} / stats {st['km_missing_stops']} / 站点 {st['stop_records']}")

    # 9. 可用性门槛：有阻断告警的车不得标记可绘制
    blocked_nos = {w["train_no"] for w in data["warnings"]
                   if w["severity"] == "block" and w["train_no"] and "," not in w["train_no"]}
    bad = [t["train_no"] for t in data["trains"]
           if t["train_no"] in blocked_nos and t["validation"]["usable_for_frontend"]]
    c.add("阻断车未标记可绘制", not bad, "、".join(bad) or "全部一致")

    # 10. 真实/测试数据标识
    kind = meta["data_kind"]
    is_synth_file = "synthetic" in source_path.lower()
    c.add("data_kind 与文件性质一致", (kind == "synthetic") == is_synth_file,
          f"data_kind={kind}，文件名{'含' if is_synth_file else '不含'} synthetic")

    return c


def main(argv=None):
    parser = argparse.ArgumentParser(description="校验契约 JSON")
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    parser.add_argument("--data", nargs="*", default=None)
    parser.add_argument("--all", action="store_true", help="真实数据 + synthetic 样例")
    parser.add_argument("--allow-synthetic", action="store_true",
                        help="允许通过校验的文件带 data_kind=synthetic（--all 时自动开启）")
    args = parser.parse_args(argv)

    try:
        import jsonschema
    except ImportError:
        print("[FATAL] 缺少 jsonschema。安装：pip install jsonschema", file=sys.stderr)
        return 2

    schema = json.loads(Path(args.schema).read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)

    files = []
    if args.all:
        files.extend(DEFAULT_DATA)
        if SYNTHETIC.exists():
            files.append(SYNTHETIC)
    elif args.data:
        files.extend(Path(p) for p in args.data)
    else:
        files.extend(DEFAULT_DATA)

    ok_all = True
    for path in files:
        path = Path(path)
        print(f"\n=== {path} ===")
        if not path.exists():
            print("  [FAIL] 文件不存在")
            ok_all = False
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"  [FAIL] JSON 解析失败：{exc}")
            ok_all = False
            continue
        errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
        if errors:
            ok_all = False
            print(f"  [FAIL] Schema：{len(errors)} 处不合法")
            for e in errors[:10]:
                loc = " / ".join(str(p) for p in e.path) or "<root>"
                print(f"    - {loc}: {e.message[:180]}")
        else:
            print(f"  [PASS] Schema Draft 2020-12（0 处不合法）")

        checker = check_invariants(data, str(path))
        for name, ok, detail in checker.results:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}：{detail}")
        ok_all = ok_all and not checker.failed

        if not args.all and not args.allow_synthetic and data["meta"]["data_kind"] == "synthetic":
            print("  [WARN] 该文件为 synthetic 测试数据，未被当作真实数据使用")

        print(f"  摘要：{data['meta']['dataset_id']}（{data['meta']['data_kind']}）"
              f" trains={data['stats']['trains']} stops={data['stats']['stop_records']} "
              f"segments={data['stats']['segments']} warnings={data['stats']['warnings']['total']}")

    print("\n结论：" + ("全部通过" if ok_all else "存在失败项"))
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
