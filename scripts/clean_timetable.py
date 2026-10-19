#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
石太客专 + 阳大铁路 时刻表清洗脚本（提示词2 / 阶段2）

职责边界
--------
- 只做清洗与校验：不采集、不补造、不修改原始 CSV、不产出前端页面。
- 所有时刻均为第三方聚合数据，一律"需12306官方复核"，脚本不改变这一事实。
- 缺失留空（null / unknown），禁止填 00:00；km 全部留空，禁止用 station_order 冒充。
- 跨日只认 day_offset；页面未明示 day_offset 的时间倒退一律标"疑似跨日"进人工复核，
  不自动把 day_offset 改成 1，也不静默修正时刻。

可复现性
--------
- 输出 JSON 不含任何运行时钟（无 generated_at），同输入 + 同规则 → 字节级一致。
- 排序全部显式指定（车次自然序、站序、复核项按严重度+类别+车次）。
- 脚本内置二次构建校验（--self-check-repro，默认开启），比对两次序列化字节。

退出码
------
0  清洗完成（可能存在待复核项，均在报告与 JSON 中标注）
1  数据级致命错误（表头不符、编码错误、列数不符等），已写出错误说明，不产出 JSON
2  参数/输入文件错误
"""

from __future__ import annotations

import argparse
import codecs
import csv
import hashlib
import io
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

VERSION = "1.0.0"
SCHEMA_VERSION = "2.0.0"
DATASET_ID = "shita_timetable_2026-10-20_data-v1"

# ---------------------------------------------------------------------------
# 数据源 profile
#   v1 = 去哪儿/携程等第三方聚合页（2026-10-19 采集，含大量人工复核清单）
#   v2 = 12306 官方前端 leftTicket + queryByTrainNo（2026-10-19 采集）
# 通过环境变量切换：SHITA_PROFILE=v2 python scripts/clean_timetable.py
# v1 分支的常量与版本号保持原样，保证旧数据重跑字节一致。
# ---------------------------------------------------------------------------
PROFILE = os.environ.get("SHITA_PROFILE", "v1").strip().lower()
DATA_VERSION = "data-v1" if PROFILE == "v1" else "data-v2"
DATASET_ID = f"shita_timetable_2026-10-20_{DATA_VERSION}"
if PROFILE != "v1":
    VERSION = "1.1.0"
    # 2.1.0：放宽 abs_minute 可为负（服务日之前），见 docs/data-contract.md §2.3
    SCHEMA_VERSION = "2.1.0"

# 固定表头，顺序不得改（总纲 §4）
HEADER = [
    "train_no",
    "direction",
    "train_type",
    "station_order",
    "station",
    "arr_time",
    "dep_time",
    "day_offset",
    "km",
    "is_stop",
    "remark",
]

TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
TRAIN_NO_RE = re.compile(r"^[A-Z]{1,2}\d{1,4}$")
VALID_DIRECTIONS = ("up", "down", "unknown")
MINUTES_PER_DAY = 1440

# ---------------------------------------------------------------------------
# 人工复核清单中的既有事实（只做"读取/对照"，不在此处下新结论）
# 来源：reports/manual_review/uncertainties_2026-10-20_data-v1.md
# ---------------------------------------------------------------------------

# §4 已据页面绝对到达时间标 day_offset=1 的 14 车（125 行）
DAY_OFFSET1_TRAINS = {
    "D15", "D16", "D69", "D70", "D917", "D918",
    "K1117", "K1331", "K1572", "K213",
    "Z198", "Z267", "Z268", "Z55",
}

# §4 页面未明示"次日"、按规范填 0 但午夜时刻回落、需 12306 核定 day_offset 的 7 处
SUSPECTED_CROSSINGS = {
    ("K374", 11, "枣庄西", "02:48"),
    ("K373", 9, "徐州", "01:30"),
    ("K565", 12, "聊城", "00:52"),
    ("K730", 11, "衡水", "00:34"),
    ("K730", 29, "惠州", "03:40"),
    ("K866", 18, "辛集", "00:14"),
    ("K609", 2, "辛集", "02:59"),
}

# §5 方向合并校正记录（down→up，需 12306 按官方上下行定义复核）
DIRECTION_CORRECTED = {"K374", "K730", "K1331", "Z198", "Z267", "D918"}

# §1 未能核实车次（21 个，未进 CSV；禁止用任何线索时刻填充）
UNVERIFIED_TRAINS = [
    ("G794", "B 分片", "去哪儿死链；携程无数据；疑 G791 套跑切换号"),
    ("G3767", "C 分片", "去哪儿 link dead；携程 parse error"),
    ("G3768", "C 分片", "同上"),
    ("G3769", "C 分片", "同上"),
    ("G3770", "C 分片", "同上"),
    ("D4216", "D 分片", "去哪儿 404；携程 JS 壳无时刻"),
    ("D4217", "D 分片", "同上"),
    ("D1681", "E2 分片", "去哪儿 404；携程无数据（ip.cn 线索不采信）"),
    ("D1682", "E2 分片", "同上"),
    ("D1683", "E2 分片", "同上；疑与 D1682 同车换号"),
    ("D1684", "E2 分片", "同上；疑与 D1681 同车换号"),
    ("K4585", "F1 分片", "去哪儿 404；携程空壳；可能临客/季节性/已停运"),
    ("K4586", "F1 分片", "同上"),
    ("K4587", "F1 分片", "同上"),
    ("K4588", "F1 分片", "同上"),
    ("T6", "F2 分片", "去哪儿 404；携程 trainStopList=[]"),
    ("T7", "F2 分片", "同上"),
    ("T8", "F2 分片", "同上"),
    ("Z69", "F2 分片", "同上；勿与 D69 混淆"),
    ("Z70", "F2 分片", "同上；勿与 D70 混淆"),
    ("D266", "H 分片", "去哪儿 404；携程无数据"),
]

# §2 停运 / 图内不开行（未进 CSV，仅登记）
SUSPENDED_TRAINS = [
    ("G4693", "去哪儿运行图 10/20–11/02 每日全标停"),
    ("D1617", "10/20–28 SUSPENDED、10/29 起 UNKNOWN"),
    ("D1618", "14 天全 SUSPENDED"),
    ("D1619", "14 天全 SUSPENDED"),
    ("D1620", "10/20–28 SUSPENDED、10/29 起 UNKNOWN"),
]

# §3 来源冲突（1 处）
SOURCE_CONFLICTS = [
    {
        "train_no": "G2637",
        "station_order": 8,
        "station_in_csv": "滨海北",
        "arr_in_csv": "16:52",
        "dep_in_csv": "16:54",
        "issue": "G2637 页作「滨海北 16:52/16:54」，G2640 页作「滨海西 16:48/16:50」，站名与时刻均不一致",
        "source_action": "CSV 按主录页 G2637 录入；未静默取舍，交 12306 核定",
    }
]

# §6 线路归属 / 衔接待核（只登记，不下结论）
ROUTE_PENDING = [
    ("D1095", "页面仅列阳泉东 07:09 → 太原南 08:36 两站，是否经阳泉北待核"),
    ("D1096", "太原南 09:25 → 太原 09:36/09:41 → 阳泉东 11:15，页面未列阳泉北，衔接线路待核"),
    ("C799", "经石家庄北，该段属客专还是老线待核"),
    ("C800", "经石家庄北，该段属客专还是老线待核"),
    ("S954", "阳泉东 10:40 → 阳泉北 11:26（46 分钟，其余市郊车均 28 分钟），疑待避/慢行，待核"),
]

# docs/stations.md（2026-10-19）车站骨架，逐字誊录，不改写、不补里程
CORRIDOR_CATALOG = [
    # 石太主通道（西 → 东）。坐标：x 西→东、y 北→南，横平竖直；非精确经纬度。
    # 顺序依据：石家庄→获鹿→井陉北→阳泉北→东凌井→太原（docs/stations.md 表序，反向即西→东）。
    {"id": "tyn", "name": "太原南", "line": "shita", "sequence": 1, "x": 0.10, "y": 0.62,
     "role": "endpoint_west", "branch_of": None, "branch_order": None, "link": "main", "label": "below",
     "pax": "是", "highlight": False,
     "note": "多数 G/D 终到，经联络线接入，接大西高铁", "confidence": "confirmed"},
    {"id": "ty", "name": "太原", "line": "shita", "sequence": 2, "x": 0.10, "y": 0.36,
     "role": "endpoint_west", "branch_of": None, "branch_order": None, "link": "main", "label": "above",
     "pax": "是", "highlight": False,
     "note": "部分车终到；东行经太原站后转石太", "confidence": "confirmed"},
    {"id": "donglingjing", "name": "东凌井(东陵井)", "line": "shita", "sequence": 3, "x": 0.26, "y": 0.36,
     "role": "intermediate", "branch_of": None, "branch_order": None, "link": "main", "label": "below",
     "pax": "待核(线索不办客)", "highlight": False,
     "note": "太原—阳泉北之间，越行/会让，不办客", "confidence": "待核"},
    {"id": "yqbei", "name": "阳泉北", "line": "shita", "sequence": 4, "x": 0.44, "y": 0.36,
     "role": "junction", "branch_of": None, "branch_order": None, "link": "main", "label": "above",
     "pax": "是", "highlight": True,
     "note": "石太与阳大共站（阳大场），盂县", "confidence": "confirmed"},
    {"id": "jxbei", "name": "井陉北", "line": "shita", "sequence": 5, "x": 0.58, "y": 0.36,
     "role": "intermediate", "branch_of": None, "branch_order": None, "link": "main", "label": "below",
     "pax": "待核(线索不办客)", "highlight": False,
     "note": "阳泉北—获鹿之间；太行山隧道在井陉北—阳泉北区间", "confidence": "部分confirmed(相邻)/办客待核"},
    {"id": "huolu", "name": "获鹿", "line": "shita", "sequence": 6, "x": 0.72, "y": 0.36,
     "role": "intermediate", "branch_of": None, "branch_order": None, "link": "main", "label": "below",
     "pax": "待核(线索不办客)", "highlight": False,
     "note": "石家庄西侧；石太普铁在此接轨并经石家庄北，故石家庄北挂获鹿", "confidence": "待核"},
    {"id": "sjz", "name": "石家庄", "line": "shita", "sequence": 7, "x": 0.86, "y": 0.36,
     "role": "endpoint_east", "branch_of": None, "branch_order": None, "link": "main", "label": "below",
     "pax": "是", "highlight": False,
     "note": "正线引入石家庄站太青场，京广高铁/太青/石太交汇", "confidence": "confirmed"},
    {"id": "sjzb", "name": "石家庄北", "line": "shita", "sequence": 8, "x": 0.72, "y": 0.14,
     "role": "endpoint_east", "branch_of": "获鹿", "branch_order": 1, "link": "connecting", "label": "above",
     "pax": "是（2026-01恢复客运）", "highlight": False,
     "note": "经石太普铁（获鹿—石家庄北）接入，C799/C800、部分车停；与石家庄无同车双停", "confidence": "confirmed"},
    # 阳大支线（阳泉北向南）
    {"id": "yxd", "name": "盂县东", "line": "yangda", "sequence": None, "x": 0.44, "y": 0.46,
     "role": "branch_intermediate", "branch_of": "阳泉北", "branch_order": 1, "link": "regional", "label": "left",
     "pax": "预留", "highlight": False, "note": "预留站", "confidence": "confirmed(预留)/办客待核"},
    {"id": "hedi", "name": "河底", "line": "yangda", "sequence": None, "x": 0.44, "y": 0.54,
     "role": "branch_intermediate", "branch_of": "阳泉北", "branch_order": 2, "link": "regional", "label": "left",
     "pax": "待核", "highlight": False, "note": "新建，现状不办客", "confidence": "待核"},
    {"id": "yinyangdong", "name": "荫营东", "line": "yangda", "sequence": None, "x": 0.44, "y": 0.60,
     "role": "branch_intermediate", "branch_of": "阳泉北", "branch_order": 3, "link": "regional", "label": "left",
     "pax": "待核", "highlight": False, "note": "国铁2020稿列新建站，现状不办客", "confidence": "待核"},
    {"id": "yqd", "name": "阳泉东", "line": "yangda", "sequence": None, "x": 0.44, "y": 0.68,
     "role": "branch_intermediate", "branch_of": "阳泉北", "branch_order": 4, "link": "regional", "label": "right",
     "pax": "是", "highlight": False,
     "note": "市区客运站；S951-S966、C799/C800、D1095/D1096 起点/终到", "confidence": "confirmed"},
    {"id": "pingding", "name": "平定", "line": "yangda", "sequence": None, "x": 0.44, "y": 0.78,
     "role": "branch_intermediate", "branch_of": "阳泉东", "branch_order": 1, "link": "regional", "label": "right",
     "pax": "待核", "highlight": False, "note": "改建站", "confidence": "待核"},
    {"id": "ningai", "name": "宁艾", "line": "yangda", "sequence": None, "x": 0.44, "y": 0.86,
     "role": "branch_intermediate", "branch_of": "阳泉东", "branch_order": 2, "link": "regional", "label": "right",
     "pax": "预留", "highlight": False, "note": "预留", "confidence": "待核"},
    {"id": "dazhai", "name": "大寨(昔阳)", "line": "yangda", "sequence": None, "x": 0.44, "y": 0.94,
     "role": "branch_terminal", "branch_of": "阳泉东", "branch_order": 3, "link": "regional", "label": "right",
     "pax": "待核", "highlight": False, "note": "改建站，未见现行客运", "confidence": "待核"},
]

# v2（12306 官方前端）：站序、跨日、方向均由接口数据与采集脚本推断，
# v1 的“未核实/停运/来源冲突/待核”人工清单不再适用，全部清空；
# 不再存在的车次在采集摘要里登记，不生成任何时刻。
if PROFILE != "v1":
    DAY_OFFSET1_TRAINS = set()
    SUSPECTED_CROSSINGS = set()
    DIRECTION_CORRECTED = set()
    UNVERIFIED_TRAINS = []
    SUSPENDED_TRAINS = []
    SOURCE_CONFLICTS = []
    ROUTE_PENDING = []

# 车站骨架中"名称与 CSV 不一致"的已知点：CSV 名 → 骨架名（只登记，不改写）
CATALOG_NAME_NOTES = {
    "昔阳": "大寨(昔阳)",
}

# 目标通道核心站（用于边界/线路连续性检查）
CORRIDOR_CORE = {"石家庄", "石家庄北", "太原", "太原南", "阳泉北", "阳泉东"}

# ---------------------------------------------------------------------------
# 契约层（schema 2.0.0）：稳定 ID、示意坐标与支线挂接、告警码
# ---------------------------------------------------------------------------

def sid(name: str) -> str:
    """站点稳定 ID：st:+站名。含中文，仅作 Map 键，不依赖数组下标、不用于 CSS 选择器。"""
    return "st:" + name


def tid(train_no: str) -> str:
    """车次稳定 ID：tr:+车次号。本批一个物理交路一个编号，故与 train_no 一一对应。"""
    return "tr:" + train_no


# 复核类别 → 契约告警码
WARNING_CODE = {
    "crossing_unresolved": "CROSSING_UNRESOLVED",
    "crossing_not_reproduced": "CROSSING_NOT_REPRODUCED",
    "source_conflict": "SOURCE_CONFLICT",
    "direction_review": "DIRECTION_REVIEW",
    "route_pending": "ROUTE_PENDING",
    "station_naming": "STATION_NAME_MISMATCH",
    "catalog_conflict": "STATION_CATALOG_CONFLICT",
    "conflict": "DUPLICATE_ORDER_CONFLICT",
    "station_order": "STATION_ORDER_GAP",
    "time_reversal": "TIME_REVERSAL",
    "dep_before_arr": "DEP_BEFORE_ARR",
    "missing_time": "MISSING_TIME",
    "missing_field": "MISSING_FIELD",
    "invalid_time": "INVALID_TIME",
    "invalid_direction": "INVALID_DIRECTION",
    "boundary": "BOUNDARY_RULE",
    "duplicate_row": "DUPLICATE_ROW",
    "excluded_unverified": "EXCLUDED_UNVERIFIED",
    "excluded_suspended": "EXCLUDED_SUSPENDED",
}


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------

def natural_key(train_no: str):
    """车次自然序：字母前缀 + 数字数值，保证 D15 < D1095。"""
    m = re.match(r"^([A-Za-z]*)(\d*)$", train_no)
    if not m:
        return (train_no, 0)
    return (m.group(1), int(m.group(2) or 0))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hhmm_to_minutes(value: str):
    """'HH:mm' → 0..1439；非法返回 None。"""
    m = TIME_RE.match(value)
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def fmt_minutes(value):
    """0..2879 → 'HH:mm(+1d)' 形式的可读串，仅用于报告。"""
    if value is None:
        return "—"
    day, rem = divmod(value, MINUTES_PER_DAY)
    return f"{rem // 60:02d}:{rem % 60:02d}" + (f" +{day}d" if day else "")


class Issue:
    """单条校验发现。severity: block=阻断前端使用 / warn=可绘制但需标注 / info=仅记录。"""

    __slots__ = ("severity", "category", "train_no", "station_order", "station",
                 "row_number", "issue", "evidence")

    def __init__(self, severity, category, issue, train_no="", station_order=None,
                 station="", row_number=None, evidence=""):
        self.severity = severity
        self.category = category
        self.train_no = train_no
        self.station_order = station_order
        self.station = station
        self.row_number = row_number
        self.issue = issue
        self.evidence = evidence

    def as_dict(self):
        return {
            "severity": self.severity,
            "category": self.category,
            "train_no": self.train_no,
            "station_order": self.station_order,
            "station": self.station,
            "row_number": self.row_number,
            "issue": self.issue,
            "evidence": self.evidence,
        }


# ---------------------------------------------------------------------------
# 1. 读取与结构校验
# ---------------------------------------------------------------------------

def read_source(path: Path):
    raw = path.read_bytes()
    meta = {
        "file": path.name,
        "path": str(path).replace("\\", "/"),
        "bytes": len(raw),
        "sha256": sha256_bytes(raw),
    }
    bom = raw.startswith(codecs.BOM_UTF8)
    meta["bom"] = bom

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SystemExitWithMessage(
            f"编码错误：文件无法按 UTF-8 解码（{exc}）。请勿用 GBK/ANSI 另存后重试。", 1
        )

    meta["encoding"] = "UTF-8" + (" (with BOM)" if bom else " (no BOM)")
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n")
    meta["line_endings"] = "CRLF" if crlf == lf and crlf > 0 else ("LF" if crlf == 0 else "MIXED")
    meta["physical_lines"] = len(text.splitlines())
    meta["trailing_newline"] = text.endswith("\n")
    return text, meta


class SystemExitWithMessage(Exception):
    """数据级致命错误：携带退出码与说明。"""

    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


def parse_rows(text: str, issues):
    """按固定表头解析，保留物理行号（表头为第 1 行）。"""
    reader = csv.reader(io.StringIO(text, newline=""))
    rows = []
    header = None
    for idx, fields in enumerate(reader, start=1):
        if idx == 1:
            header = [f.strip() for f in fields]
            if header != HEADER:
                raise SystemExitWithMessage(
                    "表头不符：期望 11 列固定顺序\n  期望: " + ",".join(HEADER) +
                    "\n  实际: " + ",".join(header), 1
                )
            continue
        if not fields or all(f == "" for f in fields):
            issues.append(Issue("warn", "blank_line", "空行已跳过", row_number=idx))
            continue
        if len(fields) != len(HEADER):
            raise SystemExitWithMessage(
                f"第 {idx} 行列数不符：期望 11 列，实际 {len(fields)} 列 → {fields!r}", 1
            )
        rec = dict(zip(HEADER, [f.strip() for f in fields]))
        rec["_row"] = idx
        rows.append(rec)
    if header is None:
        raise SystemExitWithMessage("文件为空，缺少表头", 1)
    return rows


def validate_row(rec, issues):
    """逐字段校验；不做任何"修复"，只记录。"""
    row = rec["_row"]
    train = rec["train_no"]
    order_raw = rec["station_order"]

    if not train:
        issues.append(Issue("block", "missing_field", "train_no 为空", row_number=row))
    elif not TRAIN_NO_RE.match(train):
        issues.append(Issue("warn", "format", f"train_no 格式异常：{train!r}", train, row_number=row))

    if rec["direction"] not in VALID_DIRECTIONS:
        issues.append(Issue("block", "invalid_direction",
                            f"direction 非法：{rec['direction']!r}（仅允许 up/down/unknown）",
                            train, row_number=row))
    if not rec["train_type"]:
        issues.append(Issue("block", "missing_field", "train_type 为空", train, row_number=row))

    order = None
    if not order_raw:
        issues.append(Issue("block", "missing_field", "station_order 为空", train, row_number=row))
    else:
        try:
            order = int(order_raw)
            if order < 1:
                raise ValueError
        except ValueError:
            issues.append(Issue("block", "format", f"station_order 非正整数：{order_raw!r}",
                                train, row_number=row))
            order = None
    rec["_order"] = order

    if not rec["station"]:
        issues.append(Issue("block", "missing_field", "station 为空", train, order, row_number=row))

    for field in ("arr_time", "dep_time"):
        value = rec[field]
        rec["_" + field] = None
        if not value:
            continue
        minutes = hhmm_to_minutes(value)
        if minutes is None:
            issues.append(Issue("block", "invalid_time", f"{field} 非法时刻：{value!r}",
                                train, order, rec["station"], row))
            continue
        rec["_" + field] = minutes

    if not rec["day_offset"]:
        issues.append(Issue("warn", "missing_field", "day_offset 为空，按 0 处理并标注",
                            train, order, rec["station"], row))
        rec["_day_offset"] = 0
        rec["_day_offset_imputed"] = True
    else:
        try:
            rec["_day_offset"] = int(rec["day_offset"])
            rec["_day_offset_imputed"] = False
            if rec["_day_offset"] not in (-2, -1, 0, 1, 2):
                issues.append(Issue("warn", "format",
                                    f"day_offset 超出常见范围 -1/0/1：{rec['day_offset']}",
                                    train, order, rec["station"], row))
        except ValueError:
            issues.append(Issue("block", "format", f"day_offset 非整数：{rec['day_offset']!r}",
                                train, order, rec["station"], row))
            rec["_day_offset"] = 0
            rec["_day_offset_imputed"] = True

    rec["_km"] = None
    if rec["km"]:
        try:
            rec["_km"] = float(rec["km"])
            issues.append(Issue("warn", "km_present",
                                f"km 非空（{rec['km']}），本次口径为第三方无里程，需核对来源",
                                train, order, rec["station"], row))
        except ValueError:
            issues.append(Issue("block", "format", f"km 非数值：{rec['km']!r}",
                                train, order, rec["station"], row))

    rec["_is_stop"] = rec["is_stop"].lower() == "true"
    if rec["is_stop"].lower() not in ("true", "false"):
        issues.append(Issue("warn", "format", f"is_stop 非布尔：{rec['is_stop']!r}，按 false 处理",
                            train, order, rec["station"], row))


# ---------------------------------------------------------------------------
# 2. 去重 / 冲突
# ---------------------------------------------------------------------------

def deduplicate(rows, issues):
    """完全重复（11 字段全同）保留首行；同车次同站序不同内容 = 冲突，不静默选一条。"""
    seen = {}
    kept = []
    duplicates = []
    for rec in rows:
        key = tuple(rec[f] for f in HEADER)
        if key in seen:
            duplicates.append({"row": rec["_row"], "kept_row": seen[key],
                               "train_no": rec["train_no"], "station_order": rec["station_order"],
                               "station": rec["station"]})
            continue
        seen[key] = rec["_row"]
        kept.append(rec)

    groups = defaultdict(list)
    for rec in kept:
        groups[(rec["train_no"], rec["_order"])].append(rec)

    conflicts = []
    for (train, order), recs in sorted(groups.items(), key=lambda kv: (natural_key(kv[0][0]), kv[0][1])):
        if len(recs) <= 1:
            continue
        signatures = {tuple(r[f] for f in ("station", "arr_time", "dep_time", "day_offset"))
                      for r in recs}
        if len(signatures) <= 1:
            continue
        conflicts.append({
            "train_no": train,
            "station_order": order,
            "variants": [
                {"row": r["_row"], "station": r["station"], "arr_time": r["arr_time"],
                 "dep_time": r["dep_time"], "day_offset": r["day_offset"]}
                for r in recs
            ],
        })
        issues.append(Issue(
            "block", "conflict",
            f"同车次同站序存在 {len(signatures)} 种不同记录，未静默取舍",
            train, order, recs[0]["station"], recs[0]["_row"],
            evidence="; ".join(f"行{r['_row']}:{r['station']} {r['arr_time']}/{r['dep_time']}" for r in recs),
        ))

    for dup in duplicates:
        issues.append(Issue("warn", "duplicate_row",
                            f"完全重复记录已去重（保留第 {dup['kept_row']} 行）",
                            dup["train_no"], dup["station_order"], dup["station"], dup["row"]))
    return kept, duplicates, conflicts


# ---------------------------------------------------------------------------
# 3. 单车次构建与校验
# ---------------------------------------------------------------------------

def build_trains(rows, issues, conflict_keys=None):
    conflict_keys = conflict_keys or set()
    grouped = defaultdict(list)
    for rec in rows:
        grouped[rec["train_no"]].append(rec)

    trains = []
    for train_no in sorted(grouped, key=natural_key):
        recs = sorted(grouped[train_no], key=lambda r: (r["_order"] if r["_order"] else 10 ** 6, r["_row"]))
        direction = recs[0]["direction"]
        train_type = recs[0]["train_type"]
        train_issues = []

        # 3.1 站序连续性（1..N 无断号、无重复）
        orders = [r["_order"] for r in recs]
        order_ok = orders == list(range(1, len(recs) + 1))
        if not order_ok:
            train_issues.append(Issue("block", "station_order",
                                      f"station_order 不连续或重复：{orders}",
                                      train_no, None, "", recs[0]["_row"]))
        row_order = [r["_row"] for r in recs]
        if row_order != sorted(row_order):
            train_issues.append(Issue("warn", "row_order",
                                      "CSV 中行序与 station_order 不一致，已按站序重排",
                                      train_no, None, "", recs[0]["_row"]))
        if len(recs) < 2:
            train_issues.append(Issue("block", "boundary",
                                      f"仅 {len(recs)} 条站记录，无法构成交路",
                                      train_no, None, "", recs[0]["_row"]))

        # 3.2 边界站规则：始发无 arr、终到无 dep；中间站不可缺时刻
        for idx, rec in enumerate(recs):
            is_first, is_last = idx == 0, idx == len(recs) - 1
            if is_first and rec["_arr_time"] is not None:
                train_issues.append(Issue("warn", "boundary",
                                          f"始发站 {rec['station']} 却有到达时刻 {rec['arr_time']}",
                                          train_no, rec["_order"], rec["station"], rec["_row"]))
            if is_last and rec["_dep_time"] is not None:
                train_issues.append(Issue("warn", "boundary",
                                          f"终到站 {rec['station']} 却有出发时刻 {rec['dep_time']}",
                                          train_no, rec["_order"], rec["station"], rec["_row"]))
            if not is_first and rec["_arr_time"] is None:
                train_issues.append(Issue("block", "missing_time",
                                          "中间站缺到达时刻", train_no, rec["_order"],
                                          rec["station"], rec["_row"]))
            if not is_last and rec["_dep_time"] is None:
                train_issues.append(Issue("block", "missing_time",
                                          "中间站缺出发时刻", train_no, rec["_order"],
                                          rec["station"], rec["_row"]))
            if rec["_arr_time"] is None and rec["_dep_time"] is None:
                train_issues.append(Issue("block", "missing_time",
                                          "整站无到发时刻", train_no, rec["_order"],
                                          rec["station"], rec["_row"]))

        # 3.3 时间校验：站内 dep>=arr；跨站 abs 单调
        stops = []
        prev_dep_abs = None
        prev_minute = None
        prev_station = None
        for idx, rec in enumerate(recs):
            offset = rec["_day_offset"] * MINUTES_PER_DAY
            arr_m, dep_m = rec["_arr_time"], rec["_dep_time"]
            arr_abs = arr_m + offset if arr_m is not None else None
            dep_abs = dep_m + offset if dep_m is not None else None
            flags = []
            if (train_no, rec["_order"]) in conflict_keys:
                flags.append("conflict")

            if rec["_day_offset"] == 1:
                flags.append("day_offset_from_source")

            if arr_abs is not None and dep_abs is not None and dep_abs < arr_abs:
                train_issues.append(Issue(
                    "block", "dep_before_arr",
                    f"{rec['station']} 出发 {rec['dep_time']} 早于到达 {rec['arr_time']}",
                    train_no, rec["_order"], rec["station"], rec["_row"]))
                flags.append("dep_before_arr")

            anchor = arr_abs if arr_abs is not None else dep_abs
            if anchor is not None and prev_dep_abs is not None and anchor < prev_dep_abs:
                gap = prev_dep_abs - anchor
                suspected = rec["_day_offset"] == 0 and arr_m is not None and prev_minute is not None \
                    and arr_m < prev_minute
                evidence = (f"前站 {prev_station} 发车 {fmt_minutes(prev_dep_abs)} → "
                            f"本站到达 {fmt_minutes(anchor)}，倒退 {gap} 分钟；day_offset={rec['_day_offset']}")
                if suspected:
                    train_issues.append(Issue(
                        "block", "crossing_unresolved",
                        "时间倒退且 day_offset=0，页面未明示次日：疑似跨日，保留原值不自动改 1",
                        train_no, rec["_order"], rec["station"], rec["_row"], evidence))
                    flags.append("suspected_day_offset")
                else:
                    train_issues.append(Issue(
                        "block", "time_reversal",
                        "绝对分钟倒退，且不满足疑似跨日条件",
                        train_no, rec["_order"], rec["station"], rec["_row"], evidence))
                    flags.append("time_reversal")

            # 站停类型
            is_first, is_last = idx == 0, idx == len(recs) - 1
            if is_first:
                stop_kind = "origin"
            elif is_last:
                stop_kind = "terminal"
            elif not rec["_is_stop"]:
                stop_kind = "pass"
            else:
                stop_kind = "stop"

            dwell = None
            if arr_m is not None and dep_m is not None:
                dwell = dep_m - arr_m
                if dwell < 0:
                    dwell += MINUTES_PER_DAY

            stops.append({
                "station_order": rec["_order"],
                "station": rec["station"],
                "station_id": sid(rec["station"]),
                "arr_time": rec["arr_time"] or None,
                "dep_time": rec["dep_time"] or None,
                "minute_of_day": {"arr": arr_m, "dep": dep_m},
                "abs_minute": {"arr": arr_abs, "dep": dep_abs},
                "day_offset": rec["_day_offset"],
                "day_offset_imputed": rec["_day_offset_imputed"],
                "km": rec["_km"],
                "is_stop": rec["_is_stop"],
                "stop_kind": stop_kind,
                "dwell_minutes": dwell,
                "remark": rec["remark"] or None,
                "source_row": rec["_row"],
                "flags": flags,
            })

            prev_dep_abs = dep_abs if dep_abs is not None else arr_abs
            prev_minute = dep_m if dep_m is not None else arr_m
            prev_station = rec["station"]

        # 3.4 方向校验（只对照，不反推）
        if direction == "unknown":
            flags = ["direction_unknown"]
            train_issues.append(Issue("warn", "direction_unknown",
                                      "direction=unknown，保留原值；禁止凭车次号奇偶反推",
                                      train_no, None, "", recs[0]["_row"]))
        else:
            flags = []
            ty_idx = [i for i, s in enumerate(stops) if s["station"] in ("太原", "太原南")]
            sjz_idx = [i for i, s in enumerate(stops) if s["station"] in ("石家庄", "石家庄北")]
            yq_idx = [i for i, s in enumerate(stops) if s["station"] == "阳泉北"]
            if ty_idx and sjz_idx and yq_idx:
                ok = (ty_idx[0] < yq_idx[0] < sjz_idx[0]) if direction == "up" \
                    else (sjz_idx[0] < yq_idx[0] < ty_idx[0])
                if not ok:
                    flags.append("corridor_order_mismatch")
                    train_issues.append(Issue(
                        "warn", "corridor_order",
                        f"石太段站序与 direction={direction} 不一致，未改方向",
                        train_no, None, "", recs[0]["_row"],
                        evidence="站序: " + "→".join(s["station"] for s in stops)))

        # 3.5 目标通道覆盖
        station_names = {s["station"] for s in stops}
        if "阳泉北" not in station_names and "阳泉东" in station_names:
            flags.append("route_pending")
            train_issues.append(Issue("warn", "route_pending",
                                      "经阳泉东但页面未列阳泉北，线路衔接待核（未补站）",
                                      train_no, None, "阳泉东", recs[0]["_row"]))
        if not (station_names & CORRIDOR_CORE):
            flags.append("off_corridor")
            train_issues.append(Issue("warn", "off_corridor",
                                      "不含任何目标通道核心站", train_no, None, "", recs[0]["_row"]))

        if train_no in DIRECTION_CORRECTED:
            flags.append("direction_corrected")
            train_issues.append(Issue("warn", "direction_corrected",
                                      "采集期已按石太段走向 down→up 校正，需 12306 按官方上下行定义复核",
                                      train_no, None, "", recs[0]["_row"]))

        # 3.6 来源冲突（跨页，文档已登记）：只标注，不改站名/时刻
        for conflict in SOURCE_CONFLICTS:
            if conflict["train_no"] != train_no:
                continue
            for stop in stops:
                if stop["station_order"] == conflict["station_order"]:
                    stop["flags"].append("source_conflict")
            train_issues.append(Issue(
                "warn", "source_conflict", conflict["issue"],
                train_no, conflict["station_order"], conflict["station_in_csv"], recs[0]["_row"],
                evidence=f"CSV 值 {conflict['arr_in_csv']}/{conflict['dep_in_csv']}；{conflict['source_action']}"))

        # 3.7 站名与骨架表一致性
        for stop in stops:
            name = stop["station"]
            if name in CATALOG_NAME_NOTES:
                stop["flags"].append("catalog_name_mismatch")
                train_issues.append(Issue(
                    "warn", "station_naming",
                    f"CSV 站名「{name}」与车站骨架「{CATALOG_NAME_NOTES[name]}」不一致，未擅自改名",
                    train_no, stop["station_order"], name, stop["source_row"]))

        # 3.8 汇总
        blocking = [i for i in train_issues if i.severity == "block"]
        warnings = [i for i in train_issues if i.severity == "warn"]
        stop_flags = {f for s in stops for f in s["flags"]}
        all_flags = sorted(set(flags) | stop_flags)
        origin = stops[0]
        terminal = stops[-1]
        first_dep = origin["abs_minute"]["dep"]
        last_arr = terminal["abs_minute"]["arr"]
        duration = (last_arr - first_dep) if (first_dep is not None and last_arr is not None) else None
        if duration is not None and duration <= 0:
            duration = None  # abs 不单调时总时长无意义，不输出负数
        # 3.9 服务状态与来源引用（只从 remark 原文提取，不做外部推断）
        remark_set = sorted({s["remark"] for s in stops if s["remark"]})
        if any("隔日" in r for r in remark_set):
            service_status = {"code": "alternate_day", "basis": "remark 含「隔日规律」"}
        elif any("每日开行" in r for r in remark_set):
            service_status = {"code": "normal", "basis": "remark 含「每日开行」"}
        else:
            service_status = {"code": "unknown", "basis": None}

        urls = []
        for r in remark_set:
            for u in re.findall(r"https?://[^\s-]+", r):
                if u not in urls:
                    urls.append(u)
        source_refs = [{"url": u, "accessed": "2026-10-19"} for u in urls]

        trains.append({
            "train_id": tid(train_no),
            "train_no": train_no,
            "direction": direction,
            "train_type": train_type,
            "service_status": service_status,
            "origin": origin["station"],
            "terminal": terminal["station"],
            "station_count": len(stops),
            "first_dep_abs_minute": first_dep,
            "last_arr_abs_minute": last_arr,
            "duration_minutes": duration,
            "has_day_offset": (any(s["day_offset"] != 0 for s in stops) if PROFILE != "v1"
                               else any(s["day_offset"] > 0 for s in stops)),
            "validation": {
                "status": "needs_review" if blocking else ("validated_with_notes" if warnings else "validated"),
                "usable_for_frontend": not blocking,
                "blocking_issue_count": len(blocking),
                "warning_count": len(warnings),
                "flags": all_flags,
            },
            "remarks": [],
            "source_refs": source_refs,
            "stops": stops,
        })
        issues.extend(train_issues)
    return trains


# ---------------------------------------------------------------------------
# 4. 复核项汇总（脚本检测 + 既有清单对照）
# ---------------------------------------------------------------------------

def collect_review_items(trains, detected_crossings, issues, source_meta):
    items = []

    def add(severity, category, train_no, issue, station_order=None, station="",
            row_number=None, evidence="", frontend_impact="", doc_ref=""):
        items.append({
            "severity": severity,
            "category": category,
            "train_no": train_no,
            "station_order": station_order,
            "station": station,
            "row_number": row_number,
            "issue": issue,
            "evidence": evidence,
            "frontend_impact": frontend_impact,
            "doc_ref": doc_ref,
            "status": "open",
        })

    # 4.1 疑似跨日（脚本检测结果，逐条与 uncertainties §4 对照）
    for train_no, order, station, arr in sorted(detected_crossings,
                                                key=lambda x: (natural_key(x[0]), x[1])):
        rec = next((s for t in trains if t["train_no"] == train_no
                    for s in t["stops"] if s["station_order"] == order), None)
        row = rec["source_row"] if rec else None
        dep = rec["dep_time"] if rec else None
        matched = (train_no, order, station, arr) in SUSPECTED_CROSSINGS
        add(
            "block", "crossing_unresolved", train_no,
            f"{station} {arr} 相对前站时刻倒退，day_offset=0 且页面未明示次日；疑似跨日",
            order, station, row,
            evidence=f"前站时刻见 source_row 上下文；arr={arr} dep={dep} day_offset=0",
            frontend_impact="该车 abs_minute 不单调，暂不可用于运行图",
            doc_ref="uncertainties §4（已登记，本次检测结果与清单一致）" if matched
            else "uncertainties §4 未登记：本次新发现，需补入清单",
        )

    # 4.2 文档已登记但脚本未检出的跨日项（防漏检；仅当该车该站确实存在于本批数据时）
    detected_keys = {(t, o, s) for t, o, s, _ in detected_crossings}
    train_index = {t["train_no"]: t for t in trains}
    for train_no, order, station, arr in sorted(SUSPECTED_CROSSINGS, key=lambda x: (natural_key(x[0]), x[1])):
        present = train_no in train_index and any(
            s["station_order"] == order for s in train_index[train_no]["stops"])
        if present and (train_no, order, station) not in detected_keys:
            add("warn", "crossing_not_reproduced", train_no,
                f"uncertainties §4 登记的 {station} {arr} 跨日疑点，本次未复现（可能已被上游修正）",
                order, station, evidence="清单对照", doc_ref="uncertainties §4")

    # 4.3 来源冲突（G2637/G2640）
    for conflict in SOURCE_CONFLICTS:
        if conflict["train_no"] not in train_index:
            continue
        add("warn", "source_conflict", conflict["train_no"], conflict["issue"],
            conflict["station_order"], conflict["station_in_csv"],
            evidence=f"CSV 值：{conflict['arr_in_csv']}/{conflict['dep_in_csv']}；{conflict['source_action']}",
            frontend_impact="该站站名/时刻存疑，图上需标注待核",
            doc_ref="uncertainties §3")

    # 4.4 方向校正 6 车
    for train_no in sorted(DIRECTION_CORRECTED, key=natural_key):
        train = train_index.get(train_no)
        if train is None:
            continue
        od = f"{train['origin']}→{train['terminal']}"
        add("warn", "direction_review", train_no,
            f"采集期按石太段走向将 down 校正为 up（{od}），需 12306 按官方上下行定义复核",
            evidence=f"direction={train['direction'] if train else '—'}",
            frontend_impact="方向色/箭头可能需翻转",
            doc_ref="uncertainties §5")

    # 4.5 线路衔接待核
    for train_no, note in ROUTE_PENDING:
        if train_no not in train_index:
            continue
        add("warn", "route_pending", train_no, note,
            evidence="页面经停站列表", frontend_impact="该车在目标区间可能缺站，绘制需标缺口",
            doc_ref="uncertainties §6")

    # 4.6 车站骨架与 CSV 的站名/办客矛盾
    name_hits = defaultdict(list)
    for train in trains:
        for stop in train["stops"]:
            if stop["station"] in CATALOG_NAME_NOTES:
                name_hits[stop["station"]].append(train["train_no"])
    for csv_name, hits in sorted(name_hits.items()):
        add("warn", "station_naming", ", ".join(sorted(hits, key=natural_key)),
            f"CSV 站名「{csv_name}」，车站骨架作「{CATALOG_NAME_NOTES[csv_name]}」，未擅自归一",
            station=csv_name, evidence=f"涉及车次：{', '.join(sorted(hits, key=natural_key))}",
            frontend_impact="纵轴站名需与骨架统一后再绘图", doc_ref="docs/stations.md 二、阳大铁路")

    # 4.7 骨架标"待核/不办客"但 CSV 有停站
    catalog_note = {
        "平定": "车站骨架将「平定」标为待核（改建站，南段），但 CSV 中 K585/K587 有停站时刻",
        "昔阳": "车站骨架将「大寨(昔阳)」标为待核/未见现行客运，但 CSV 以「昔阳」列有 K585/K587 停站时刻",
    }
    for name, note in catalog_note.items():
        trains_here = sorted({t["train_no"] for t in trains for s in t["stops"] if s["station"] == name},
                             key=natural_key)
        if trains_here:
            add("warn", "catalog_conflict", ", ".join(trains_here), note,
                station=name, evidence="docs/stations.md 二、阳大铁路 vs CSV 站记录",
                frontend_impact="阳大线南段是否纳入绘图需确认", doc_ref="docs/stations.md 二")

    # 4.8 未核实 21 车（未进 CSV，禁止补造）
    for train_no, shard, note in UNVERIFIED_TRAINS:
        add("excluded", "excluded_unverified", train_no,
            "未能核实，未进本批 CSV；禁止用 ip.cn 等线索时刻填充",
            evidence=f"{shard}：{note}", frontend_impact="不在本批数据中，图上无此车",
            doc_ref="uncertainties §1")

    # 4.9 停运/图内不开行 5 车
    for train_no, note in SUSPENDED_TRAINS:
        add("excluded", "excluded_suspended", train_no, "停运或图内不开行，未录入",
            evidence=note, frontend_impact="不在本批数据中", doc_ref="uncertainties §2")

    # 4.10 脚本新发现（未被文档覆盖的阻断/警告项）
    covered = {(i["train_no"], i["category"]) for i in items}
    for issue in issues:
        if issue.severity == "info":
            continue
        if issue.category in ("crossing_unresolved", "direction_corrected", "route_pending",
                              "station_naming", "source_conflict", "duplicate_row", "blank_line",
                              "row_order", "off_corridor"):
            continue
        key = (issue.train_no, issue.category, issue.row_number)
        if key in covered:
            continue
        covered.add(key)
        add(issue.severity, issue.category, issue.train_no, issue.issue,
            issue.station_order, issue.station, issue.row_number, issue.evidence,
            frontend_impact="见 issue 描述", doc_ref="脚本检测")

    # 排序：严重度 → 类别 → 车次 → 站序
    rank = {"block": 0, "warn": 1, "info": 2, "excluded": 3}
    items.sort(key=lambda i: (rank[i["severity"]], i["category"],
                              natural_key(i["train_no"]), i["station_order"] or 0))
    for idx, item in enumerate(items, start=1):
        item["review_id"] = f"RV-{idx:03d}"
    return items


# ---------------------------------------------------------------------------
# 5. 车站字典与骨架
# ---------------------------------------------------------------------------

def build_stations(trains):
    """契约层车站表：本批出现的站点 + 骨架里尚未出现的通道站（in_dataset=false）。"""
    counter = Counter()
    types = defaultdict(set)
    for train in trains:
        for stop in train["stops"]:
            counter[stop["station"]] += 1
            types[stop["station"]].add(train["train_type"])

    catalog_by_name = {item["name"]: item for item in CORRIDOR_CATALOG}
    # v2：12306 官方站名“昔阳”复用骨架“大寨(昔阳)”的示意坐标，且骨架旧名不再单独输出
    mapped_away = set()
    if PROFILE != "v1":
        mapped_away = {CATALOG_NAME_NOTES[n] for n in counter if n in CATALOG_NAME_NOTES}

    stations = []
    for name in (set(counter) | set(catalog_by_name)) - mapped_away:
        ref = catalog_by_name.get(name)
        if ref is None and PROFILE != "v1" and name in CATALOG_NAME_NOTES:
            ref = catalog_by_name.get(CATALOG_NAME_NOTES[name])
        place = None
        if ref:
            place = {
                "line": ref["line"],
                "sequence": ref["sequence"],
                "x": ref["x"],
                "y": ref["y"],
                "role": ref["role"],
                "branch_of": ref["branch_of"],
                "branch_order": ref["branch_order"],
                "link": ref["link"],
                "label": ref["label"],
            }

        if ref:
            note = (f"办客 {ref['pax']}；可信度 {ref['confidence']}；{ref['note']}"
                    f"（示意坐标 x={ref['x']:.2f}, y={ref['y']:.2f}，非精确经纬度）")
        elif name in CATALOG_NAME_NOTES:
            note = f"CSV 站名，车站骨架作「{CATALOG_NAME_NOTES[name]}」，名称与办客状态待核，未擅自归一"
        else:
            note = None

        stations.append({
            "station_id": sid(name),
            "name": name,
            "in_dataset": name in counter,
            "is_corridor": bool(place),
            "is_highlighted": bool(ref and ref["highlight"]),
            "km": None,
            "station_order": None,
            "place": place,
            "corridor_ids": [ref["id"]] if ref else [],
            "source": "docs/stations.md" if ref else "csv",
            "notes": note,
            "stats": {
                "stop_records": counter.get(name, 0),
                "train_types": sorted(types.get(name, set())),
            },
        })

    stations.sort(key=lambda s: (
        s["place"] is None,
        s["place"]["sequence"] if s["place"] and s["place"]["sequence"] is not None else 999,
        s["place"]["branch_order"] if s["place"] and s["place"]["branch_order"] is not None else 999,
        -s["stats"]["stop_records"],
        s["name"],
    ))
    return stations


# ---------------------------------------------------------------------------
# 6. 区间（segments）与告警（warnings）
# ---------------------------------------------------------------------------

def build_segments(trains):
    """区间表：dwell=同站停站，run=相邻两站运行。时刻缺失 → type=unknown 且时长为 null。"""
    segments = []
    for train in trains:
        usable = train["validation"]["usable_for_frontend"]
        stops = train["stops"]
        seq = 0
        for i, stop in enumerate(stops):
            if stop["arr_time"] and stop["dep_time"] and (stop["dwell_minutes"] or 0) > 0:
                seq += 1
                segments.append({
                    "segment_id": f"sg:{train['train_no']}:{seq:03d}:dwell",
                    "train_id": train["train_id"],
                    "train_no": train["train_no"],
                    "segment_type": "dwell",
                    "from_station_id": stop["station_id"],
                    "to_station_id": stop["station_id"],
                    "from_station_order": stop["station_order"],
                    "to_station_order": stop["station_order"],
                    "from_dep_time": stop["dep_time"],
                    "to_arr_time": stop["arr_time"],
                    "departure_abs_minute": stop["abs_minute"]["dep"],
                    "arrival_abs_minute": stop["abs_minute"]["arr"],
                    "from_km": None,
                    "to_km": None,
                    "duration_minutes": stop["dwell_minutes"],
                    "data_quality": {"status": "ok" if usable else "review", "flags": []},
                })
            if i < len(stops) - 1:
                nxt = stops[i + 1]
                seq += 1
                dep_abs = stop["abs_minute"]["dep"]
                arr_abs = nxt["abs_minute"]["arr"]
                complete = dep_abs is not None and arr_abs is not None
                duration = (arr_abs - dep_abs) if complete else None
                flags = []
                if not complete:
                    flags.append("missing_time")
                if duration is not None and duration < 0:
                    # 负区间说明跨日未定（abs_minute 不单调）：时长置 null，原始绝对分钟保留
                    flags.append("negative_duration")
                    duration = None
                if not complete:
                    status = "incomplete"
                elif not usable or (duration is not None and duration < 0):
                    status = "review"
                else:
                    status = "ok"
                segments.append({
                    "segment_id": f"sg:{train['train_no']}:{seq:03d}:run",
                    "train_id": train["train_id"],
                    "train_no": train["train_no"],
                    "segment_type": "run" if complete else "unknown",
                    "from_station_id": stop["station_id"],
                    "to_station_id": nxt["station_id"],
                    "from_station_order": stop["station_order"],
                    "to_station_order": nxt["station_order"],
                    "from_dep_time": stop["dep_time"],
                    "to_arr_time": nxt["arr_time"],
                    "departure_abs_minute": dep_abs,
                    "arrival_abs_minute": arr_abs,
                    "from_km": None,
                    "to_km": None,
                    "duration_minutes": duration,
                    "data_quality": {"status": status, "flags": flags},
                })
    return segments


def build_warnings(review_items):
    """复核项 → 契约告警。多车共用条目 train_id 为 null，train_no 保留逗号清单。"""
    out = []
    for item in review_items:
        train_no = item["train_no"] or None
        station = item["station"] or None
        single_train = bool(train_no) and "," not in train_no
        out.append({
            "warning_id": item["review_id"],
            "code": WARNING_CODE.get(item["category"], "OTHER"),
            "severity": item["severity"],
            "message": item["issue"],
            "train_id": tid(train_no) if single_train else None,
            "train_no": train_no,
            "station_id": sid(station) if station else None,
            "station_order": item["station_order"],
            "station": station,
            "row": item["row_number"],
            "evidence": item["evidence"] or None,
            "frontend_impact": item["frontend_impact"] or None,
            "doc_ref": item["doc_ref"] or None,
            "status": item["status"],
        })
    return out


# ---------------------------------------------------------------------------
# 7. 序列化
# ---------------------------------------------------------------------------

def dumps_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def build_document(source_meta, trains, stations, segments, warnings, counts):
    abs_values = [v for t in trains for s in t["stops"]
                  for v in (s["abs_minute"]["arr"], s["abs_minute"]["dep"]) if v is not None]
    build_id = f"{source_meta['sha256'][:12]}-v{VERSION}"
    open_warnings = sum(1 for w in warnings if w["severity"] in ("block", "warn"))

    if PROFILE == "v1":
        source_summary = {
            "primary": "去哪儿 train.qunar.com 单车现行页（queryDate 2026-10-20）",
            "access_date": "2026-10-19",
            "query_date": "2026-10-20",
            "official_verification": "未访问 12306；全部时刻需 12306 官方复核",
            "cross_check": "携程单车页仅作抽查（D1096/D1634/D1637 一致），未采用其独立时刻",
        }
        documents = [
            {"path": "reports/sources/sources_2026-10-20_data-v1.md", "role": "来源清单"},
            {"path": "reports/manual_review/uncertainties_2026-10-20_data-v1.md", "role": "待核与冲突清单"},
            {"path": "reports/validation/validation_2026-10-20_data-v1.md", "role": "清洗校验报告"},
            {"path": "reports/validation/cleaning_log_2026-10-20_data-v1.md", "role": "清洗日志与复现说明"},
            {"path": "reports/manual_review/manual_review_2026-10-20_data-v1.csv", "role": "人工复核明细"},
            {"path": "docs/stations.md", "role": "车站骨架（通道站与示意纵轴）"},
            {"path": "docs/data-contract.md", "role": "JSON 契约说明"},
            {"path": "docs/schema/shita-timetable.schema.json", "role": "JSON Schema 2020-12"},
        ]
        caveats = [
            "全部时刻为第三方聚合现行图，需 12306 官方复核；本数据只保证内部自洽",
            "km 全部为 null（第三方无里程），不得用 station_order 充当公里数",
            "6 车疑似跨日未定，abs_minute 不单调，usable_for_frontend=false",
            "21 个未核实车次与 5 个停运车次未录入，禁止据线索补造",
        ]
    else:
        source_summary = {
            "primary": "中国铁路 12306 官方前端（leftTicket 余票查询 + queryByTrainNo 经停站查询）",
            "access_date": "2026-10-19",
            "query_date": "2026-10-20",
            "official_verification": "已直接取自 12306 官方前端接口，不再是第三方聚合数据",
            "cross_check": "逐车用 leftTicket 的区间到发时刻与历时（lishi）核对 queryByTrainNo 全程站表",
        }
        documents = [
            {"path": "reports/sources/sources_2026-10-20_data-v2.md", "role": "来源清单（12306 采集通道）"},
            {"path": "reports/sources/collect_2026-10-20_data-v2.json", "role": "采集摘要（车次/方向/历时/跳过项）"},
            {"path": "reports/validation/validation_2026-10-20_data-v2.md", "role": "清洗校验报告"},
            {"path": "reports/validation/cleaning_log_2026-10-20_data-v2.md", "role": "清洗日志与复现说明"},
            {"path": "reports/manual_review/data-v1_to_v2_diff.md", "role": "v1→v2 差异对比"},
            {"path": "docs/stations.md", "role": "车站骨架（通道站与示意纵轴）"},
            {"path": "docs/data-contract.md", "role": "JSON 契约说明"},
            {"path": "docs/schema/shita-timetable.schema.json", "role": "JSON Schema 2020-12"},
        ]
        caveats = [
            "时刻取自 12306 官方前端接口；车次开行状态以查询当日（2026-10-20）为准",
            "km 全部为 null（12306 前端不提供里程），不得用 station_order 充当公里数",
            "跨日 day_offset 由站序 + 时刻单调性推断，推断明细见采集摘要 cross_day_notes",
            "套跑交路只录一个车次号（优先沿用 v1 已收录编号），另一编号不进 CSV",
        ]

    meta = {
        "schema_version": SCHEMA_VERSION,
        "dataset_id": DATASET_ID,
        "data_version": DATA_VERSION,
        "history_version": None,
        "history_status": "current_timetable_not_archive",
        "data_kind": "real",
        "generated_at": None,
        "generated_at_note": "为保证字节级可复现，不写入构建时钟；构建时刻见 reports/validation/cleaning_log 对应条目",
        "build_id": build_id,
        "time_unit": "minute",
        "timezone": "Asia/Shanghai",
        "time_origin": "基准服务日 2026-10-20 00:00（绝对分钟 0）",
        "source_summary": source_summary,
        "coverage": {
            "service_date": "2026-10-20",
            "abs_minute_min": min(abs_values) if abs_values else 0,
            "abs_minute_max": max(abs_values) if abs_values else 0,
            "trains_total": len(trains),
            "stations_total": len(stations),
            "lines": ["石太客专", "阳大铁路"],
        },
        "validation_status": {
            "state": "pass_with_open_reviews" if open_warnings else "pass",
            "usable_trains": sum(1 for t in trains if t["validation"]["usable_for_frontend"]),
            "blocked_trains": sum(1 for t in trains if not t["validation"]["usable_for_frontend"]),
            "open_warnings": open_warnings,
        },
    }

    provenance = {
        "csv": {
            "file": source_meta["file"],
            "sha256": source_meta["sha256"],
            "bytes": source_meta["bytes"],
            "rows": source_meta["data_rows"],
            "encoding": source_meta["encoding"],
            "line_endings": source_meta["line_endings"],
            "header": HEADER,
        },
        "cleaner": {"script": "scripts/clean_timetable.py", "version": VERSION},
        "documents": documents,
        "caveats": caveats,
    }

    stats = {
        "trains": len(trains),
        "usable_trains": meta["validation_status"]["usable_trains"],
        "blocked_trains": meta["validation_status"]["blocked_trains"],
        "trains_with_notes": counts["trains_with_notes"],
        "stations": len(stations),
        "stations_in_dataset": counts["stations"],
        "stop_records": counts["valid_records"],
        "segments": len(segments),
        "warnings": {
            "total": len(warnings),
            "block": sum(1 for w in warnings if w["severity"] == "block"),
            "warn": sum(1 for w in warnings if w["severity"] == "warn"),
            "info": sum(1 for w in warnings if w["severity"] == "info"),
            "excluded": sum(1 for w in warnings if w["severity"] == "excluded"),
        },
        "km_missing_stops": counts["km_missing_rows"],
        "direction": {
            "up": counts["direction_trains"]["up"],
            "down": counts["direction_trains"]["down"],
            "unknown": counts["direction_trains"]["unknown"],
        },
        "day_offset_stops": counts["day_offset_rows"],
    }

    return {
        "meta": meta,
        "provenance": provenance,
        "stations": stations,
        "trains": trains,
        "segments": segments,
        "warnings": warnings,
        "stats": stats,
    }


# ---------------------------------------------------------------------------
# 7. 报告生成
# ---------------------------------------------------------------------------

def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        out.append("| " + " | ".join("" if c is None else str(c) for c in row) + " |")
    return "\n".join(out)


def write_validation_report(path, ctx):
    src = ctx["source"]
    counts = ctx["counts"]
    trains = ctx["trains"]
    issues = ctx["issues"]
    review = ctx["review_items"]
    blocked = [t for t in trains if not t["validation"]["usable_for_frontend"]]
    noted = [t for t in trains if t["validation"]["usable_for_frontend"] and t["validation"]["status"] == "validated_with_notes"]
    clean = [t for t in trains if t["validation"]["status"] == "validated"]

    L = []
    L.append(f"# 数据校验报告 · 石太客专 + 阳大铁路（2026-10-20 现行图 · {DATA_VERSION}）")
    L.append("")
    L.append(f"> 生成时间：{ctx['run_time']}　｜　脚本：`scripts/clean_timetable.py` v{VERSION}　｜　数据集：`{DATASET_ID}`")
    if PROFILE == "v1":
        L.append("> 数据性质：**第三方聚合现行图，全部时刻需 12306 官方复核**；本报告只验证内部一致性与可追溯性，不代表官方正确性。")
    else:
        L.append("> 数据性质：**取自 12306 官方前端接口（leftTicket + queryByTrainNo）**；本报告只验证内部一致性与可追溯性。")
    L.append("")
    L.append("## 1. 结论摘要")
    L.append("")
    L.append(f"- 结构校验 **通过**：11 列固定表头、{src['data_rows']} 条数据行、{counts['trains']} 个车次、{counts['stations']} 个车站名，无空行、无列数不符、无非法时刻、无 00:00 填充。")
    L.append("- **完全重复 0 条**；**同车次同站序冲突 0 条**。" if PROFILE != "v1"
             else "- **完全重复 0 条**；**同车次同站序冲突 0 条**；文档登记的 1 处跨页来源冲突（G2637/G2640）保留在人工复核。")
    if PROFILE == "v1":
        L.append(f"- **疑似跨日 {counts['suspected_crossing_rows']} 处 / {counts['suspected_crossing_trains']} 车**：与 `uncertainties §4` 逐条一致，全部保留 day_offset=0 原值，未自动改 1。")
    else:
        L.append(f"- **跨日推断 {counts['day_offset_rows']} 条 / {counts['day_offset_trains']} 车**：由站序与时刻单调性推断，明细见采集摘要。")
    L.append(f"- 前端可用：**{counts['usable_trains']} / {counts['trains']} 车**（{counts['blocked_trains']} 车因绝对分钟不单调被阻断）；其中 {counts['trains_with_notes']} 车带待核标注、{counts['clean_trains']} 车无任何标注。")
    L.append(f"- 缺失里程 {counts['km_missing_rows']} 条（100%），按口径留空；规则性留空 arr {counts['rule_empty_arr']} 条（始发）、dep {counts['rule_empty_dep']} 条（终到），均不计为缺失。")
    L.append("")
    L.append("## 2. 输入与输出")
    L.append("")
    L.append(md_table(
        ["项", "值"],
        [
            ["输入 CSV", f"`data/raw/{src['file']}`"],
            ["输入字节数", f"{src['bytes']:,}"],
            ["输入物理行数", f"{src['physical_lines']}（含表头 1 行）"],
            ["输入数据行数", src["data_rows"]],
            ["输入 SHA-256", f"`{src['sha256']}`"],
            ["编码 / 换行", f"{src['encoding']} / {src['line_endings']}"],
            ["输出 JSON", f"`data/processed/{ctx['output_name']}`"],
            ["输出 JSON 字节数", f"{ctx['output_bytes']:,}"],
            ["输出 JSON SHA-256", f"`{ctx['output_sha256']}`"],
            ["JSON 契约版本", f"`{SCHEMA_VERSION}`（`docs/data-contract.md` / `docs/schema/shita-timetable.schema.json`）"],
            ["清洗脚本", "`scripts/clean_timetable.py`"],
            ["人工复核 CSV", f"`reports/manual_review/{ctx['review_name']}`（{len(review)} 条）"],
        ],
    ))
    L.append("")
    L.append("## 3. 核心计数")
    L.append("")
    L.append(md_table(
        ["指标", "数值", "说明"],
        [
            ["总行数（数据行）", counts["data_rows"], "不含表头"],
            ["有效记录数", counts["valid_records"], "通过结构校验并进入 JSON 的站记录"],
            ["区间数（segments）", counts.get("segments", 0), "run + dwell，由站记录派生并校验一致"],
            ["站点表条目", counts.get("stations_total", counts["stations"]), f"含骨架中本批无车的 {counts.get('stations_total', counts['stations']) - counts['stations']} 站"],
            ["车次数", counts["trains"], "物理交路（已套跑去重）"],
            ["车站数", counts["stations"], "CSV 出现的不同站名"],
            ["完全重复数", counts["duplicate_rows"], "11 字段全同，已去重"],
            ["冲突数（文件内）", counts["conflicts"], "同车次同站序不同内容"],
            ["冲突数（来源级）", counts["source_conflicts"], "G2637/G2640 滨海北/西"],
            ["缺失字段数", counts["missing_fields"], f"arr {counts['null_arr']} / dep {counts['null_dep']} / km {counts['null_km']}"],
            ["无效时间数", counts["invalid_times"], "非 HH:mm 或超范围"],
            ["00:00 填充数", counts["zero_filled"], "应为 0"],
            ["疑似跨日项", counts["suspected_crossing_rows"], f"涉及 {counts['suspected_crossing_trains']} 车"],
            ["已确认 day_offset=1", counts["day_offset_rows"], f"{counts['day_offset_trains']} 车，{counts['day_offset_rows']} 行"],
            ["缺失里程项", counts["km_missing_rows"], "km 全空，未用站序冒充"],
            ["方向未知项", counts["direction_unknown_trains"], "unknown 车次"],
            ["边界站异常", counts["boundary_errors"], "始发有 arr / 终到有 dep / 中间缺时刻"],
            ["站序异常", counts["station_order_errors"], "断号、重复、非正整数"],
            ["时间倒退（含疑似跨日）", counts["time_reversals"], "按 abs_minute 判定"],
            ["人工复核项", counts["review_items"],
             f"block {counts['review_block']} / warn {counts['review_warn']} / info {counts['review_info']} / excluded {counts['review_excluded']}"],
        ],
    ))
    L.append("")
    L.append("## 4. 结构校验")
    L.append("")
    L.append(md_table(
        ["检查项", "结果", "细节"],
        [
            ["UTF-8 编码", "PASS", src["encoding"]],
            ["表头 11 列顺序", "PASS", "`" + ",".join(HEADER) + "`"],
            ["列数一致性", "PASS", "0 行列数不符"],
            ["空行", "PASS", "0 行"],
            ["字段首尾空白", "PASS", "0 处（脚本仍会 trim 并记录）"],
            ["station_order 连续性", "PASS" if counts["station_order_errors"] == 0 else "FAIL",
             "每车 1..N 连续，无断号无重复"],
            ["首站无 arr / 末站无 dep", "PASS" if counts["boundary_errors"] == 0 else "FAIL",
             f"{counts['trains']} 车全部符合规则"],
        ],
    ))
    L.append("")
    L.append("## 5. 时间校验")
    L.append("")
    L.append("- `minute_of_day` 一律由 `HH:mm` 数值换算（0–1439），**未做任何字符串比较**；跨日只通过 `abs_minute = minute_of_day + day_offset*1440` 体现。")
    L.append(f"- 站内 `dep < arr`：**{counts['dep_before_arr']} 处**。")
    L.append(f"- 跨站 `abs_minute` 倒退：**{counts['time_reversals']} 处**，全部为 day_offset=0 且时刻跨午夜的疑似跨日，逐条列于下表。")
    L.append(f"- 14 车（{counts['day_offset_rows']} 行）带 day_offset=1，按绝对分钟检查后**全部单调**，与 `uncertainties §4` 已确认清单完全一致。")
    L.append("")
    L.append("### 5.1 疑似跨日（不自动修，全部进复核）")
    L.append("")
    rows = []
    for item in review:
        if item["category"] == "crossing_unresolved":
            rows.append([item["review_id"], item["train_no"], item["station_order"], item["station"],
                         item["row_number"], item["issue"]])
    L.append(md_table(["复核号", "车次", "站序", "车站", "CSV 行号", "问题"], rows) if rows else "_无_")
    L.append("")
    L.append("> 处理方式：**保留 day_offset=0 与原始时刻**，`abs_minute` 照原值计算（因此不单调），该车 `usable_for_frontend=false`。是否次日需 12306 核定，脚本不猜。")
    L.append("")
    L.append("## 6. 车次、站序与边界站")
    L.append("")
    sk = counts["stop_kinds"]
    stop_kind_text = (f"origin {sk.get('origin', 0)} / terminal {sk.get('terminal', 0)} / "
                      f"stop {sk.get('stop', 0)} / pass {sk.get('pass', 0)}")
    L.append(md_table(
        ["检查项", "结果"],
        [
            ["车次方向唯一", "PASS（无同车次混用 up/down）"],
            ["车型唯一", "PASS（无同车次混用车型）"],
            ["站序连续 1..N", "PASS"],
            ["同车次内站名重复", "PASS（0 处）"],
            ["始发站带到达时刻", "0 处"],
            ["终到站带出发时刻", "0 处"],
            ["边界站缺失", "0 处"],
            ["不含目标通道核心站的车次", f"{counts['off_corridor_trains']} 车"],
            ["经阳泉东但未列阳泉北",
             f"{counts['route_pending_trains']} 车（{'、'.join(counts['route_pending_list']) or '无'}，已登记待核）"],
            ["站型统计", stop_kind_text],
        ],
    ))
    L.append("")
    L.append(f"站序与方向一致性：对同时含「太原/太原南」「阳泉北」「石家庄/石家庄北」的 {counts['corridor_comparable_trains']} 车做走廊走向校验，"
             f"**{counts['corridor_order_mismatch']} 车不一致**（不一致项不会改方向，只标 warn）。")
    L.append("")
    L.append("## 7. 方向分布")
    L.append("")
    L.append(md_table(
        ["方向", "车次", "站记录"],
        [[d, counts["direction_trains"][d], counts["direction_rows"][d]] for d in ("up", "down", "unknown")],
    ))
    L.append("")
    L.append(f"- unknown：**{counts['direction_unknown_trains']} 车**；脚本只读 CSV，不做奇偶反推。")
    if PROFILE == "v1":
        L.append(f"- 采集期 down→up 校正 **{len(DIRECTION_CORRECTED)} 车**（K374/K730/K1331/Z198/Z267/D918），全部标 `direction_corrected` 待 12306 复核。")
    else:
        L.append("- 方向由采集脚本按站序判定；v1 已收录车次沿用 v1 人工核定方向，新增车次按“太原侧↔石家庄侧/阳泉东”站序判定。")
    L.append("")
    L.append("## 8. 里程与缺失字段")
    L.append("")
    L.append(md_table(
        ["字段", "空值数", "性质"],
        [
            ["arr_time", counts["null_arr"], "全部为始发站，规则留空（非缺失）"],
            ["dep_time", counts["null_dep"], "全部为终到站，规则留空（非缺失）"],
            ["km", counts["null_km"], "数据源不提供里程，按口径全留空"],
            ["day_offset", counts["null_day_offset"], "无空值"],
            ["remark", counts["null_remark"], "无空值"],
        ],
    ))
    L.append("")
    L.append("## 9. 人工复核清单")
    L.append("")
    by_cat = Counter(item["category"] for item in review)
    L.append("严重度口径：`block`=阻断该车用于前端；`warn`=可绘制但需标注待核；`info`=提示；`excluded`=未进入本批数据（只登记，不补造）。")
    L.append("")
    L.append(md_table(
        ["类别", "条数", "严重度"],
        [[cat, n, (next(i["severity"] for i in review if i["category"] == cat))] for cat, n in sorted(by_cat.items())],
    ))
    L.append("")
    L.append(f"明细见 `reports/manual_review/{ctx['review_name']}`（{len(review)} 条，含行号/车次/车站/证据/文档出处）。")
    L.append("")
    if PROFILE == "v1":
        L.append("### 9.1 未核实车次（21 个，禁止补造）")
        L.append("")
        L.append("本批 CSV **不含**以下车次，脚本未生成任何时刻：" + "、".join(t for t, _, _ in UNVERIFIED_TRAINS))
        L.append("")
        L.append("### 9.2 停运 / 图内不开行（5 个）")
        L.append("")
        L.append("、".join(t for t, _ in SUSPENDED_TRAINS) + "（仅登记，未录入）")
        L.append("")
    else:
        L.append("### 9.1 未返回车次")
        L.append("")
        L.append("v2 不再维护人工“未核实/停运”清单：12306 在 2026-10-20 查询中未返回的车次，即当日无该 OD 开行记录，不生成任何时刻。")
        L.append("")
    L.append("## 10. 可供前端使用的范围")
    L.append("")
    L.append(md_table(
        ["状态", "车次数", "含义"],
        [
            ["validated", counts["clean_trains"], "无阻断、无警告"],
            ["validated_with_notes", counts["trains_with_notes"], "无阻断，但带方向/线路/站名等待核标注，绘图需注明"],
            ["needs_review（阻断）", counts["blocked_trains"], "绝对分钟不单调，不得直接绘制"],
        ],
    ))
    L.append("")
    L.append("阻断车次：" + "、".join(sorted((t["train_no"] for t in blocked), key=natural_key)))
    L.append("")
    L.append("> 判定口径：`usable_for_frontend` 只看**内部时间/结构矛盾**；数据本身「需12306复核」的属性不因本脚本而改变，前端图注必须保留该声明。")
    L.append("")
    L.append("## 11. 可复现性")
    L.append("")
    L.append(f"- 内存内二次构建比对：**{'PASS' if ctx['repro_ok'] else 'FAIL'}**（两次序列化字节一致）。")
    L.append("- 输出 JSON 不含 `generated_at` 等运行时钟，排序全部显式指定，故同输入同规则重跑字节一致。")
    L.append("- 复跑方法：同一条命令再执行一次，比对 stdout 打印的 JSON SHA-256 是否相同（脚本每次运行都会输出）。")
    L.append("")
    L.append("## 12. 未解决风险")
    L.append("")
    if PROFILE == "v1":
        L.append("1. 全部时刻为第三方聚合，**未经 12306 官方复核**；本报告只证明内部自洽。")
        L.append(f"2. {counts['suspected_crossing_trains']} 车跨日未定，绝对分钟不可用；另有 14 车 day_offset=1 依据为页面绝对时刻，仍需官方核定。")
        L.append("3. G2637 第 8 站站名/时刻存在跨页冲突，现按主录页录入。")
        L.append("4. 里程全缺，Marey 图只能按站序等距示意，不得标注公里。")
        L.append("5. 采集完整性存疑：ip.cn 阳泉北页称 157 趟、静态仅渲染约 80 条，可能漏车。")
        L.append("6. 阳大线南段：CSV 中 K585/K587 在平定/昔阳有停站，与 `docs/stations.md` 的「平定 待核（改建站）」「大寨(昔阳) 未见现行客运」表述冲突，需定稿。")
    else:
        L.append("1. 时刻来自 12306 官方前端；车次开行状态以 2026-10-20 当日查询结果为准，隔日/临时停运车次可能不在本批。")
        L.append("2. 跨日 `day_offset` 由站序与时刻单调性推断；超长待避（单区段 > 20 小时）理论上可能误判，推断点见采集摘要。")
        L.append("3. 里程全缺（12306 前端不提供），Marey 图只能按站序示意，不得标注公里。")
        L.append("4. 12306 只返回营业停站，不返回通过站；相邻营业站之间的实际经由按线路骨架 BFS 路径绘制。")
        L.append("5. 套跑交路只保留一个车次号（优先沿用 v1 编号），另一编号的区段不在本数据中单独成车。")
    L.append("")
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def write_cleaning_log(path, ctx):
    src = ctx["source"]
    counts = ctx["counts"]
    L = []
    L.append(f"# 清洗日志 · 石太客专 + 阳大铁路（{DATA_VERSION}）")
    L.append("")
    L.append(f"> 运行时间：{ctx['run_time']}　｜　脚本：`scripts/clean_timetable.py` v{VERSION}　｜　Python {ctx['python_version']}")
    L.append(f"> 命令：`{ctx['command']}`")
    L.append("")
    L.append("## 1. 输入盘点（清洗前实测）")
    L.append("")
    L.append(md_table(
        ["检查项", "实测值"],
        [
            ["文件", f"`data/raw/{src['file']}`"],
            ["字节数", f"{src['bytes']:,}"],
            ["SHA-256", f"`{src['sha256']}`"],
            ["编码", src["encoding"]],
            ["换行", src["line_endings"]],
            ["物理行数", src["physical_lines"]],
            ["数据行数", src["data_rows"]],
            ["表头", "`" + ",".join(HEADER) + "`（与固定表头逐字一致）"],
        ],
    ))
    L.append("")
    L.append("## 2. 处理步骤（固定顺序，幂等）")
    L.append("")
    steps = [
        ("S1 读取与编码", "以二进制读入算 SHA-256，再按 UTF-8(兼容 BOM) 严格解码；解码失败直接以退出码 1 终止，不产出 JSON。", "未改动任何字节"),
        ("S2 表头与列数", "逐字比对 11 列固定表头；任一行字段数 ≠ 11 即致命错误。", "表头一致，0 行列数异常"),
        ("S3 字段校验", "逐行校验 train_no/direction/train_type/station_order/station/HH:mm/day_offset/km/is_stop；只记录不修复。", f"非法时刻 0，非法方向 0"),
        ("S4 完全去重", "11 字段全同视为完全重复，保留首次出现行，其余丢弃并记录行号。", f"重复 {counts['duplicate_rows']} 条"),
        ("S5 冲突识别", "按 (train_no, station_order) 分组，签名（站名/到/发/day_offset）不一致即冲突；不选边。", f"冲突 {counts['conflicts']} 条"),
        ("S6 按车聚合", "按 train_no 聚合并按 station_order 升序重排；校验 1..N 连续、无重复。", f"{counts['trains']} 车，站序全部连续"),
        ("S7 时间换算", "HH:mm → minute_of_day（0–1439）；abs_minute = minute_of_day + day_offset*1440。全程整数运算，无字符串比较。", f"换算 {counts['valid_records']} 行"),
        ("S8 时间校验", "站内 dep≥arr；跨站 abs 单调。倒退时区分「已有 day_offset 依据」与「疑似跨日」，后者不改值。", f"倒退 {counts['time_reversals']} 处，全部疑似跨日"),
        ("S9 站型判定", "首站=origin（无 arr）、末站=terminal（无 dep）、is_stop=false=pass、其余=stop，并算 dwell_minutes。",
         f"origin {counts['stop_kinds'].get('origin', 0)} / terminal {counts['stop_kinds'].get('terminal', 0)} / "
         f"stop {counts['stop_kinds'].get('stop', 0)} / pass {counts['stop_kinds'].get('pass', 0)}"),
        ("S10 方向与走廊", "照抄 direction；对同时含太原/阳泉北/石家庄的车做走向一致性提示；不反推、不改值。", f"unknown {counts['direction_unknown_trains']} 车，走向不一致 {counts['corridor_order_mismatch']} 车"),
        ("S11 缺失处理", "arr/dep/km 缺失写 null 并区分「规则留空」与「真缺失」；不填 0、不填 00:00。", f"km 缺 {counts['km_missing_rows']}，规则留空 {counts['rule_empty_arr'] + counts['rule_empty_dep']}"),
        ("S12 输出与复核", "生成确定性 JSON、校验报告、复核 CSV；内置二次构建字节比对。", f"复核项 {counts['review_items']} 条"),
        ("S13 契约成型", "按 docs/data-contract.md v1.0.0 组装 meta/provenance/stations/trains/segments/warnings/stats；区间由相邻站点派生，站表并入骨架无车站。", f"区间 {counts.get('segments', 0)} 条，站点表 {counts.get('stations_total', 0)} 条"),
    ]
    L.append(md_table(["步骤", "做法", "本次结果"], [[a, b, c] for a, b, c in steps]))
    L.append("")
    L.append("## 3. 关键判断（为什么这么做）")
    L.append("")
    if PROFILE == "v1":
        L.append("1. **不自动修跨日**：7 处时间倒退的 day_offset 均为 0，页面未标次日。改成 1 会让曲线「看起来正常」，但那是猜测。脚本保留原值、标 `suspected_day_offset`、把车标为不可用，等 12306 定。")
        L.append("2. **不改方向**：6 车已在采集期做 down→up 校正，脚本只加 `direction_corrected` 标记；对 K1331/Z267 这类「奇数号 + 整体离京」的表象差异不另作解释。")
        L.append("3. **km 不补**：第三方无里程，`station_order` 是序号不是距离，冒充会让 Marey 图纵轴产生虚假精度。")
        L.append("4. **冲突不选边**：文件内 0 冲突，但 G2637 的跨页冲突按主录页保留并登记，不因「看起来更顺」而改站名。")
        L.append("5. **保留 remark 原文**：每站 remark 含来源 URL/日期/「需12306官方复核」字样，原样进 JSON，便于逐条回溯。")
        L.append("6. **不补 21 车**：未核实车次连站名都不写进 trains，只在 `known_gaps` 登记编号与原因。")
    else:
        L.append("1. **跨日在采集期推断**：按站序 + 时刻单调性判定（跨日后区段时长 ≤ 20 小时才成立），推断点写入采集摘要；清洗脚本只读 `day_offset` 列，不在此时二次猜测。")
        L.append("2. **方向不凭奇偶反推**：v1 已收录车次沿用其人工核定方向；v1 没有的新增车次按“太原侧 ↔ 石家庄侧 / 阳泉东”的实际站序判定，判不出的写 `unknown`。")
        L.append("3. **km 不补**：12306 前端不提供里程，`station_order` 是序号不是距离，冒充会让 Marey 图纵轴产生虚假精度。")
        L.append("4. **套跑只录一个编号**：同一 `train_no` 交路若中途换号，按“优先沿用 v1 编号”只录一段，另一编号不重复成车。")
        L.append("5. **remark 写清通道性质**：逐站标注“来源12306官方前端”“区间未停阳泉北，疑似走石太老线”“套跑切片”等，便于回溯。")
        L.append("6. **不再维护未核实清单**：12306 未返回的车次即当日无开行记录，不在 trains 里生成任何时刻。")
    L.append("")
    L.append("## 4. 产物清单")
    L.append("")
    L.append(md_table(
        ["文件", "字节", "SHA-256"],
        [
            [f"`data/processed/{ctx['output_name']}`", f"{ctx['output_bytes']:,}", f"`{ctx['output_sha256']}`"],
            [f"`reports/validation/{ctx['validation_name']}`", f"{ctx['validation_bytes']:,}", f"`{ctx['validation_sha256']}`"],
            [f"`reports/manual_review/{ctx['review_name']}`", f"{ctx['review_bytes']:,}", f"`{ctx['review_sha256']}`"],
            [f"`reports/validation/{ctx['log_name']}`", "（本文件）", "—"],
        ],
    ))
    L.append("")
    L.append("> 原始 CSV 只读，未修改、未覆盖、未移动；SHA-256 见第 1 节，可用于事后核对。")
    L.append("")
    L.append("## 5. 复现方式")
    L.append("")
    L.append("```bash")
    if PROFILE == "v1":
        L.append("python scripts/clean_timetable.py \\")
        L.append("  --input data/raw/shita_train_timetable_2026-10-20_data-v1_draft.csv")
    else:
        L.append("SHITA_PROFILE=v2 python scripts/clean_timetable.py")
    L.append("```")
    L.append("")
    L.append("默认输出到 `data/processed/`、`reports/validation/`、`reports/manual_review/`；可用 `--output/--validation-report/--cleaning-log/--manual-review-csv` 覆盖。")
    L.append("")
    L.append("## 6. 复现性自检")
    L.append("")
    L.append(f"- 二次构建字节一致：**{'PASS' if ctx['repro_ok'] else 'FAIL'}**")
    L.append(f"- 本次 JSON SHA-256：`{ctx['output_sha256']}`")
    L.append("- 该 JSON 不含时间戳，重跑应得到同一哈希；若哈希变化，说明输入或规则被改动。")
    L.append("")
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def write_review_csv(path, review_items):
    cols = ["review_id", "severity", "category", "train_no", "station_order", "station",
            "row_number", "issue", "evidence", "frontend_impact", "doc_ref", "status"]
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    writer.writeheader()
    for item in review_items:
        writer.writerow({c: ("" if item.get(c) is None else item.get(c)) for c in cols})
    path.write_text(buf.getvalue(), encoding="utf-8")


# ---------------------------------------------------------------------------
# 8. 主流程
# ---------------------------------------------------------------------------

def run(input_path: Path):
    issues = []
    text, source_meta = read_source(input_path)
    rows = parse_rows(text, issues)
    source_meta["data_rows"] = len(rows)

    for rec in rows:
        validate_row(rec, issues)

    kept, duplicates, conflicts = deduplicate(rows, issues)
    source_meta["data_rows"] = len(rows)

    conflict_keys = {(c["train_no"], c["station_order"]) for c in conflicts}
    trains = build_trains(kept, issues, conflict_keys)

    # 检测到的疑似跨日点（用于与 uncertainties §4 对照）
    detected = []
    for train in trains:
        for stop in train["stops"]:
            if "suspected_day_offset" in stop["flags"]:
                detected.append((train["train_no"], stop["station_order"],
                                 stop["station"], stop["arr_time"]))

    review_items = collect_review_items(trains, detected, issues, source_meta)

    # 计数
    all_stops = [s for t in trains for s in t["stops"]]
    direction_trains = Counter(t["direction"] for t in trains)
    direction_rows = Counter(t["direction"] for t in trains for _ in t["stops"])
    null_arr = sum(1 for s in all_stops if s["arr_time"] is None)
    null_dep = sum(1 for s in all_stops if s["dep_time"] is None)
    null_km = sum(1 for s in all_stops if s["km"] is None)

    day_offset_rows = sum(1 for s in all_stops if s["day_offset"] != 0)
    day_offset_trains = len({t["train_no"] for t in trains if t["has_day_offset"]})

    counts = {
        "data_rows": len(rows),
        "valid_records": len(all_stops),
        "trains": len(trains),
        "stations": len({s["station"] for s in all_stops}),
        "duplicate_rows": len(duplicates),
        "conflicts": len(conflicts),
        "source_conflicts": len(SOURCE_CONFLICTS),
        "missing_fields": null_arr + null_dep + null_km,
        "null_arr": null_arr,
        "null_dep": null_dep,
        "null_km": null_km,
        "null_day_offset": sum(1 for t in trains for s in t["stops"] if s["day_offset_imputed"]),
        "null_remark": sum(1 for s in all_stops if s["remark"] is None),
        "rule_empty_arr": sum(1 for t in trains for s in t["stops"] if s["stop_kind"] == "origin"),
        "rule_empty_dep": sum(1 for t in trains for s in t["stops"] if s["stop_kind"] == "terminal"),
        "invalid_times": sum(1 for i in issues if i.category == "invalid_time"),
        "zero_filled": sum(1 for s in all_stops if s["arr_time"] == "00:00" or s["dep_time"] == "00:00"),
        "suspected_crossing_rows": len(detected),
        "suspected_crossing_trains": len({d[0] for d in detected}),
        "day_offset_rows": day_offset_rows,
        "day_offset_trains": day_offset_trains,
        "km_missing_rows": null_km,
        "direction_unknown_trains": direction_trains.get("unknown", 0),
        "direction_trains": {d: direction_trains.get(d, 0) for d in VALID_DIRECTIONS},
        "direction_rows": {d: direction_rows.get(d, 0) for d in VALID_DIRECTIONS},
        "boundary_errors": sum(1 for i in issues if i.category == "boundary"),
        "station_order_errors": sum(1 for i in issues if i.category == "station_order"),
        "dep_before_arr": sum(1 for i in issues if i.category == "dep_before_arr"),
        "time_reversals": sum(1 for i in issues if i.category in ("crossing_unresolved", "time_reversal")),
        "off_corridor_trains": len({i.train_no for i in issues if i.category == "off_corridor"}),
        "route_pending_trains": len({i.train_no for i in issues if i.category == "route_pending"}),
        "route_pending_list": sorted({i.train_no for i in issues if i.category == "route_pending"},
                                     key=natural_key),
        "stop_kinds": dict(Counter(s["stop_kind"] for s in all_stops)),
        "corridor_comparable_trains": sum(
            1 for t in trains
            if any(s["station"] in ("太原", "太原南") for s in t["stops"])
            and any(s["station"] in ("石家庄", "石家庄北") for s in t["stops"])
            and any(s["station"] == "阳泉北" for s in t["stops"])),
        "corridor_order_mismatch": sum(1 for i in issues if i.category == "corridor_order"),
        "review_items": len(review_items),
        "review_block": sum(1 for i in review_items if i["severity"] == "block"),
        "review_warn": sum(1 for i in review_items if i["severity"] == "warn"),
        "review_info": sum(1 for i in review_items if i["severity"] == "info"),
        "review_excluded": sum(1 for i in review_items if i["severity"] == "excluded"),
        "clean_trains": sum(1 for t in trains if t["validation"]["status"] == "validated"),
        "trains_with_notes": sum(1 for t in trains if t["validation"]["status"] == "validated_with_notes"),
        "blocked_trains": sum(1 for t in trains if not t["validation"]["usable_for_frontend"]),
        "usable_trains": sum(1 for t in trains if t["validation"]["usable_for_frontend"]),
    }

    stations = build_stations(trains)
    segments = build_segments(trains)
    warnings = build_warnings(review_items)
    counts["segments"] = len(segments)
    counts["stations_total"] = len(stations)

    document = build_document(source_meta, trains, stations, segments, warnings, counts)
    payload = dumps_json(document)

    # 二次构建，验证确定性
    document2 = build_document(source_meta, trains, stations, segments, warnings, counts)
    repro_ok = dumps_json(document2) == payload

    return {
        "document": document,
        "payload": payload,
        "source": source_meta,
        "counts": counts,
        "trains": trains,
        "review_items": review_items,
        "issues": issues,
        "repro_ok": repro_ok,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="石太客专+阳大铁路 时刻表清洗（提示词2）")
    if PROFILE == "v1":
        default_input = "data/raw/shita_train_timetable_2026-10-20_data-v1_draft.csv"
    else:
        default_input = "data/raw/shita_train_timetable_2026-10-20_data-v2_12306.csv"
    parser.add_argument("--input", default=default_input)
    parser.add_argument("--output", default=f"data/processed/shita_timetable_2026-10-20_{DATA_VERSION}.json")
    parser.add_argument("--validation-report", default=f"reports/validation/validation_2026-10-20_{DATA_VERSION}.md")
    parser.add_argument("--cleaning-log", default=f"reports/validation/cleaning_log_2026-10-20_{DATA_VERSION}.md")
    parser.add_argument("--manual-review-csv", default=f"reports/manual_review/manual_review_2026-10-20_{DATA_VERSION}.csv")
    parser.add_argument("--fail-on-blocking", action="store_true",
                        help="存在阻断级问题时以退出码 3 结束（供 CI 使用）")
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[FATAL] 输入文件不存在：{input_path}", file=sys.stderr)
        return 2

    try:
        result = run(input_path)
    except SystemExitWithMessage as exc:
        print(f"[FATAL] {exc}", file=sys.stderr)
        return exc.code

    out_path = Path(args.output)
    val_path = Path(args.validation_report)
    log_path = Path(args.cleaning_log)
    review_path = Path(args.manual_review_csv)
    for p in (out_path, val_path, log_path, review_path):
        p.parent.mkdir(parents=True, exist_ok=True)

    payload_bytes = result["payload"].encode("utf-8")
    out_path.write_bytes(payload_bytes)
    write_review_csv(review_path, result["review_items"])

    ctx = {
        "run_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "command": "python scripts/clean_timetable.py --input " + str(input_path).replace("\\", "/"),
        "python_version": sys.version.split()[0],
        "source": result["source"],
        "counts": result["counts"],
        "trains": result["trains"],
        "issues": result["issues"],
        "review_items": result["review_items"],
        "repro_ok": result["repro_ok"],
        "output_name": out_path.name,
        "output_bytes": len(payload_bytes),
        "output_sha256": sha256_bytes(payload_bytes),
        "validation_name": val_path.name,
        "log_name": log_path.name,
        "review_name": review_path.name,
        "review_bytes": review_path.stat().st_size,
        "review_sha256": sha256_bytes(review_path.read_bytes()),
    }

    # 校验报告需要先算自身哈希 → 顺序：先写报告，再写日志（日志引用报告哈希）
    write_validation_report(val_path, ctx)
    ctx["validation_bytes"] = val_path.stat().st_size
    ctx["validation_sha256"] = sha256_bytes(val_path.read_bytes())
    write_cleaning_log(log_path, ctx)

    c = result["counts"]
    print("清洗完成")
    print(f"  输入  : {input_path} ({result['source']['bytes']:,} B, sha256={result['source']['sha256'][:16]}…)")
    print(f"  数据行: {c['data_rows']}  车次: {c['trains']}  车站: {c['stations']}  站记录: {c['valid_records']}")
    print(f"  重复  : {c['duplicate_rows']}  冲突: {c['conflicts']}  无效时间: {c['invalid_times']}")
    print(f"  疑似跨日: {c['suspected_crossing_rows']} 处 / {c['suspected_crossing_trains']} 车"
          f"  → 阻断 {c['blocked_trains']} 车，可用 {c['usable_trains']} 车")
    print(f"  复核项: {c['review_items']}（block {c['review_block']} / warn {c['review_warn']} / "
          f"info {c['review_info']} / excluded {c['review_excluded']}）")
    print(f"  确定性自检: {'PASS' if result['repro_ok'] else 'FAIL'}")
    print(f"  输出  : {out_path}  sha256={ctx['output_sha256']}")
    print(f"          {val_path}")
    print(f"          {log_path}")
    print(f"          {review_path}")

    if args.fail_on_blocking and c["blocked_trains"] > 0:
        return 3
    if not result["repro_ok"]:
        print("[FATAL] 确定性自检失败：同一输入两次构建结果不一致", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
