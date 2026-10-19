# -*- coding: utf-8 -*-
"""
从 12306 官方前端接口采集石太走廊列车时刻表（data-v2 数据源）。

通道（与浏览器 F12 看到的完全一致）：
  1) GET /otn/leftTicket/init          -> 拿 Cookie + CLeftTicketUrl（本次为 leftTicket/queryG）
  2) GET /otn/{CLeftTicketUrl}         -> 余票查询，拿到区间内车次列表（含始发/终到/历时）
  3) GET /otn/czxx/queryByTrainNo      -> 逐车拿全程经停站到发时刻
  4) GET /otn/resources/js/framework/station_name.js -> 电报码 -> 中文站名

输出：
  data/raw/shita_train_timetable_2026-10-20_data-v2_12306.csv   （11 列契约格式）
  data/raw/_12306_raw/2026-10-20/*.json                          （原始响应，只读留证）
  reports/sources/collect_2026-10-20_data-v2.json                （采集摘要）

用法：
  python scripts/collect_12306.py --limit 6      # 小样本验证
  python scripts/collect_12306.py                # 全量
"""
from __future__ import annotations

import argparse
import csv
import gzip
import http.cookiejar
import json
import random
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

BASE = "https://kyfw.12306.cn"
SERVICE_DATE = "2026-10-20"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
INIT_URL = (BASE + "/otn/leftTicket/init?linktypeid=dc"
            "&fs=%E5%A4%AA%E5%8E%9F,TYV&ts=%E7%9F%B3%E5%AE%B6%E5%BA%84,SJP"
            "&date=2026-10-20&flag=N,N,Y")

# 走廊相关 OD（覆盖全线、各子段、阳大支线、两个“太原/石家庄”双站）
OD_LIST = [
    ("TYV", "SJP", "太原", "石家庄"),
    ("SJP", "TYV", "石家庄", "太原"),
    ("TNV", "SJP", "太原南", "石家庄"),
    ("SJP", "TNV", "石家庄", "太原南"),
    ("TYV", "YPP", "太原", "阳泉北"),
    ("YPP", "TYV", "阳泉北", "太原"),
    ("YPP", "SJP", "阳泉北", "石家庄"),
    ("SJP", "YPP", "石家庄", "阳泉北"),
    ("AYP", "SJP", "阳泉东", "石家庄"),
    ("SJP", "AYP", "石家庄", "阳泉东"),
    ("YPP", "AYP", "阳泉北", "阳泉东"),
    ("AYP", "YPP", "阳泉东", "阳泉北"),
    # 长途 OD：补「走廊内通过不停」的标杆车（G379/G380 太原↔北京，石家庄通过不停）。
    # 北京西/北京丰台只能从石家庄方向接入，故这些车必然经石太客专。
    ("TYV", "BXP", "太原", "北京西"),
    ("TYV", "FTP", "太原", "北京丰台"),
    ("TNV", "BXP", "太原南", "北京西"),
    ("TNV", "FTP", "太原南", "北京丰台"),
    ("BXP", "TYV", "北京西", "太原"),
    ("FTP", "TYV", "北京丰台", "太原"),
    ("BXP", "TNV", "北京西", "太原南"),
    ("FTP", "TNV", "北京丰台", "太原南"),
]

# 京原线特征站：北京西—原平—太原，不经石太。用于排除同 OD 里的非走廊车（K603/K604）。
JINGYUAN_STATIONS = {"灵丘", "五台山北", "繁峙", "代县", "原平", "忻州", "阳曲", "涞源"}
CORRIDOR_STATIONS = {"石家庄", "石家庄北", "阳泉北", "阳泉东"}
BEIJING_STATIONS = {"北京", "北京西", "北京南", "北京北", "北京丰台", "清河"}

TYPE_MAP = {
    "高速": "高铁", "高铁": "高铁", "动车": "动车", "城际": "城际", "市郊": "市郊",
    "直特": "直达特快", "直达特快": "直达特快",
    "特快": "特快", "快速": "快速", "普快": "普快", "普慢": "普慢",
    "旅游": "旅游", "临时旅客": "临客",
}

TYPE_BY_PREFIX = {
    "G": "高铁", "D": "动车", "C": "城际", "S": "市郊",
    "Z": "直达特快", "T": "特快", "K": "快速", "Y": "旅游",
}


def map_train_type(code: str, raw_class: str) -> str:
    """车型：优先按车次号前缀判定（与项目 v1 口径一致），前缀不明时用 12306 分类。

    12306 的 train_class_name 对 C 字头返回“动车”、对 S 字头返回“快速”，
    与项目“城际/市郊”口径不符，因此前缀优先。
    """
    prefix = code[0].upper() if code else ""
    if prefix in TYPE_BY_PREFIX:
        return TYPE_BY_PREFIX[prefix]
    if code.isdigit():
        return "普快"
    return TYPE_MAP.get(raw_class, raw_class or "未知")

HEADER = ["train_no", "direction", "train_type", "station_order", "station",
          "arr_time", "dep_time", "day_offset", "km", "is_stop", "remark"]


def log(msg: str) -> None:
    print(msg, flush=True)


class Client:
    def __init__(self, sleep: float = 1.1):
        cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        self.opener.addheaders = [
            ("User-Agent", UA),
            ("Accept-Language", "zh-CN,zh;q=0.9"),
            ("Accept-Encoding", "gzip, deflate"),
            ("Connection", "keep-alive"),
        ]
        self.sleep = sleep
        self.left_ticket_path = "leftTicket/queryZ"
        self.init_url = INIT_URL

    def _get(self, url: str, referer: str | None = None, timeout: int = 25) -> tuple[int, str]:
        req = urllib.request.Request(url)
        if referer:
            req.add_header("Referer", referer)
        r = self.opener.open(req, timeout=timeout)
        raw = r.read()
        if "gzip" in r.headers.get("Content-Encoding", ""):
            raw = gzip.decompress(raw)
        return r.status, raw.decode("utf-8", "replace")

    def get_json(self, url: str, referer: str | None = None, retries: int = 3) -> dict:
        last = None
        for attempt in range(retries):
            try:
                st, body = self._get(url, referer)
                if st != 200:
                    raise RuntimeError(f"HTTP {st}")
                return json.loads(body)
            except Exception as exc:  # noqa: BLE001
                last = exc
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"请求失败 {url}: {last}")

    def init(self) -> None:
        st, html = self._get(INIT_URL)
        m = re.search(r"CLeftTicketUrl\s*=\s*'([^']+)'", html)
        if m:
            self.left_ticket_path = m.group(1)
        log(f"[init] status={st} CLeftTicketUrl={self.left_ticket_path}")

    def query_left_ticket(self, fs: str, ts: str) -> dict:
        q = urllib.parse.urlencode({
            "leftTicketDTO.train_date": SERVICE_DATE,
            "leftTicketDTO.from_station": fs,
            "leftTicketDTO.to_station": ts,
            "purpose_codes": "ADULT",
        })
        url = f"{BASE}/otn/{self.left_ticket_path}?{q}"
        data = self.get_json(url, referer=self.init_url)
        time.sleep(self.sleep + random.random() * 0.4)
        return data

    def query_by_train_no(self, train_no: str, fs: str, ts: str, d: str) -> dict:
        q = urllib.parse.urlencode({
            "train_no": train_no,
            "from_station_telecode": fs,
            "to_station_telecode": ts,
            "depart_date": d,
        })
        url = f"{BASE}/otn/czxx/queryByTrainNo?{q}"
        data = self.get_json(url, referer=self.init_url)
        time.sleep(self.sleep + random.random() * 0.4)
        return data


def parse_hhmm(value: str) -> int | None:
    if not value or not re.fullmatch(r"\d{2}:\d{2}", value):
        return None
    h, m = value.split(":")
    return int(h) * 60 + int(m)


def fmt_hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def load_station_map() -> dict[str, str]:
    """电报码 -> 中文站名（从 station_name.js 解析）。"""
    req = urllib.request.Request(BASE + "/otn/resources/js/framework/station_name.js")
    req.add_header("User-Agent", UA)
    r = urllib.request.urlopen(req, timeout=25)
    raw = r.read()
    if "gzip" in r.headers.get("Content-Encoding", ""):
        raw = gzip.decompress(raw)
    js = raw.decode("utf-8", "replace")
    m = re.search(r"var station_names\s*=\s*'([^']+)'", js)
    out = {}
    if m:
        for item in m.group(1).split("@")[1:]:
            p = item.split("|")
            if len(p) >= 3:
                out[p[2]] = p[1]
    log(f"[stations] 电报码映射 {len(out)} 条")
    return out


def collect_left_ticket(client: Client, raw_dir: Path, station_map: dict[str, str],
                        reuse: bool = False) -> tuple[dict, list[dict]]:
    """跑全部 OD，返回 (train_no -> 交路命中信息, 原始查询清单)。

    12306 的 train_no 是**物理交路号**：一趟车在途中换车次号时，leftTicket 会
    按区段返回多个车次号，但共用同一个 train_no；queryByTrainNo 用该号查到的是
    交路全程，且只在首行标注**始发车次号**。因此这里按 train_no 归并，同时登记
    该交路出现过的全部车次号，供后续选择展示编号。
    """
    hits: dict[str, dict] = {}
    od_report = []
    for fs, ts, fname, tname in OD_LIST:
        cache_file = raw_dir / f"leftTicket_{fs}_{ts}.json"
        if reuse and cache_file.exists():
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            log(f"[leftTicket] {fname}->{tname}: 复用缓存")
        else:
            try:
                data = client.query_left_ticket(fs, ts)
            except Exception as exc:  # noqa: BLE001
                log(f"[leftTicket] {fname}->{tname} 失败：{exc}")
                od_report.append({"from": fs, "to": ts, "from_name": fname, "to_name": tname,
                                  "error": str(exc), "count": 0})
                continue
            cache_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        rows = ((data.get("data") or {}).get("result") or [])
        od_report.append({"from": fs, "to": ts, "from_name": fname, "to_name": tname,
                          "count": len(rows), "httpstatus": data.get("httpstatus")})
        log(f"[leftTicket] {fname}->{tname}: {len(rows)} 条")
        for row in rows:
            f = row.split("|")
            if len(f) < 20:
                continue
            # 12306 会把“北京西/北京丰台”按“北京”城市聚合，连带返回到北京北/清河的车
            # （那些走大西+京张，不经石太）。这里按实际上下车站电报码严格卡死。
            if ts in ("BXP", "FTP") and f[7] not in ("BXP", "FTP"):
                continue
            if fs in ("BXP", "FTP") and f[6] not in ("BXP", "FTP"):
                continue
            tn, code = f[2], f[3]
            item = {
                "train_no_internal": tn,
                "code": code,
                "from_tele": f[6],
                "to_tele": f[7],
                "from_name": station_map.get(f[6], ""),
                "to_name": station_map.get(f[7], ""),
                "from_dep": f[8],
                "to_arr": f[9],
                "lishi": f[10],
                "start_train_date": f[13],
                "query_from": fs,
                "query_to": ts,
            }
            prev = hits.get(tn)
            if prev is None:
                item["codes"] = [code]
                hits[tn] = item
            else:
                if code not in prev["codes"]:
                    prev["codes"].append(code)
                a, b = parse_hhmm(item["lishi"]), parse_hhmm(prev["lishi"])
                if a is not None and (b is None or a > b):
                    item["codes"] = prev["codes"]
                    hits[tn] = item
    return hits, od_report


def extract_stops(resp: dict) -> list[dict]:
    rows = ((resp.get("data") or {}).get("data") or [])
    out = []
    for r in rows:
        out.append({
            "station_no": r.get("station_no"),
            "station_name": (r.get("station_name") or "").strip(),
            "arrive_time": r.get("arrive_time"),
            "start_time": r.get("start_time"),
            "stopover_time": r.get("stopover_time"),
            "station_train_code": (r.get("station_train_code") or "").strip(),
            "train_class_name": (r.get("train_class_name") or "").strip(),
            "start_station_name": r.get("start_station_name"),
            "end_station_name": r.get("end_station_name"),
        })
    return out


def infer_day_offsets(stops: list[dict]) -> tuple[list[int], list[str]]:
    """按站序推断每站相对始发日的天数偏移。

    规则：
      - 上一站出发 -> 本站到达，若时刻回落，且回落后“跨日运行时长”<= 20h，判为跨日；
      - 同站 dep < arr 视为停站跨午夜，偏移 +1。
    """
    offsets: list[int] = []
    notes: list[str] = []
    off = 0
    prev_dep_abs: int | None = None
    for i, s in enumerate(stops):
        arr = parse_hhmm(s["arrive_time"])
        dep = parse_hhmm(s["start_time"])
        arr_abs = arr + off * 1440 if arr is not None else None
        if arr is not None and prev_dep_abs is not None and arr_abs is not None and arr_abs < prev_dep_abs:
            back = prev_dep_abs - arr_abs
            advance = 1440 - back  # 跨日后实际运行时长
            if 0 < advance <= 1200:
                off += 1
                arr_abs = arr + off * 1440
                notes.append(f"{s['station_name']} 跨日 +1（区段 {advance} 分钟）")
            # advance > 1200：判为时刻回落异常，不跨日
        if dep is not None:
            dep_abs = dep + off * 1440
            if arr_abs is not None and dep_abs < arr_abs:
                advance = 1440 - (arr_abs - dep_abs)
                if 0 < advance <= 1200:
                    off += 1
                    dep_abs = dep + off * 1440
                    notes.append(f"{s['station_name']} 停站跨午夜 +1（arr {s['arrive_time']} dep {s['start_time']}）")
                else:
                    dep_abs = arr_abs  # 异常回落，按到达时刻处理
            prev_dep_abs = dep_abs
        else:
            prev_dep_abs = arr_abs if arr_abs is not None else prev_dep_abs
        offsets.append(off)
    return offsets, notes


def infer_direction(stops: list[dict]) -> tuple[str, str]:
    names = [s["station_name"] for s in stops]
    idx = {n: i for i, n in enumerate(names)}
    ty = min([idx[n] for n in ("太原", "太原南") if n in idx], default=None)
    sj = min([idx[n] for n in ("石家庄", "石家庄北") if n in idx], default=None)
    yq = idx.get("阳泉北")
    if ty is not None and sj is not None:
        return ("up", "太原侧在前→石家庄侧在后") if ty < sj else ("down", "石家庄侧在前→太原侧在后")
    if yq is not None and "阳泉东" in idx:
        return ("up", "阳泉东→阳泉北（支线进干线）") if idx["阳泉东"] < yq else ("down", "阳泉北→阳泉东（干线进支线）")
    # 兜底：走廊内无停站的标杆车（G379/G380），按国铁“进京=上行、离京=下行”
    if names and names[-1] in BEIJING_STATIONS:
        return "up", "终到北京，按进京=上行兜底"
    if names and names[0] in BEIJING_STATIONS:
        return "down", "北京始发，按离京=下行兜底"
    return "unknown", "无法从站序判定"


def load_direction_ref(path: Path) -> dict[str, str]:
    """v1 中已由人工核定的车次方向，作为同车次的方向基准（不擅自改口径）。"""
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return {t["train_no"]: t["direction"] for t in d.get("trains", [])}
    except Exception:  # noqa: BLE001
        return {}


def build_remark(stops: list[dict], meta: dict, extra: str = "") -> str:
    parts = ["来源12306官方前端leftTicket+queryByTrainNo", f"查询服务日{SERVICE_DATE}"]
    names = [s["station_name"] for s in stops]
    if "阳泉北" not in names and any(n in names for n in ("太原", "太原南")) \
            and any(n in names for n in ("石家庄", "石家庄北")):
        parts.append("区间未停阳泉北，疑似走石太老线")
    if meta.get("aliases"):
        parts.append(f"同一物理交路另含车次号{'/'.join(meta['aliases'])}")
    if extra:
        parts.append(extra)
    return "-".join(parts)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="12306 官方前端采集石太走廊时刻表")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 个车次（验证用）")
    ap.add_argument("--sleep", type=float, default=1.1)
    ap.add_argument("--output", default=f"data/raw/shita_train_timetable_{SERVICE_DATE}_data-v2_12306.csv")
    ap.add_argument("--summary", default=f"reports/sources/collect_{SERVICE_DATE}_data-v2.json")
    ap.add_argument("--direction-ref",
                    default=f"data/processed/shita_timetable_{SERVICE_DATE}_data-v1.json")
    ap.add_argument("--reuse-raw", action="store_true",
                    help="复用 data/raw/_12306_raw 下已缓存响应，不发网络请求（改后处理逻辑时用）")
    args = ap.parse_args(argv)

    out_path = Path(args.output)
    raw_dir = Path(f"data/raw/_12306_raw/{SERVICE_DATE}")
    raw_dir.mkdir(parents=True, exist_ok=True)

    client = Client(sleep=args.sleep)
    client.init()
    station_map = load_station_map()
    direction_ref = load_direction_ref(Path(args.direction_ref))
    log(f"[ref] v1 方向基准 {len(direction_ref)} 车")
    hits, od_report = collect_left_ticket(client, raw_dir, station_map, reuse=args.reuse_raw)

    log(f"[collect] 物理交路 {len(hits)} 个")
    items = sorted(hits.values(), key=lambda x: (x["code"][0], x["code"]))
    if args.limit:
        items = items[:args.limit]

    trains, skipped = [], []
    for i, meta in enumerate(items, 1):
        tn = meta["train_no_internal"]
        cache_file = raw_dir / f"circuit_{tn}.json"
        try:
            if args.reuse_raw and cache_file.exists():
                resp = json.loads(cache_file.read_text(encoding="utf-8"))
            else:
                resp = client.query_by_train_no(tn, meta["query_from"], meta["query_to"], SERVICE_DATE)
        except Exception as exc:  # noqa: BLE001
            skipped.append({"code": meta["code"], "train_no": tn, "reason": f"请求失败 {exc}"})
            log(f"[{i}/{len(items)}] {meta['code']} 请求失败：{exc}")
            continue
        cache_file.write_text(
            json.dumps(resp, ensure_ascii=False, indent=1), encoding="utf-8")
        if not resp.get("status"):
            skipped.append({"code": meta["code"], "train_no": tn,
                            "reason": f"status=false {resp.get('messages') or resp.get('c_url') or ''}"})
            log(f"[{i}/{len(items)}] {meta['code']} status=false")
            continue

        all_stops = extract_stops(resp)
        if len(all_stops) < 2:
            skipped.append({"code": meta["code"], "train_no": tn, "reason": "站数 < 2"})
            continue

        # 长途 OD 会带出京原线普速（K603/K604：北京西—灵丘—原平—太原），不经石太，剔除
        stop_names = {s["station_name"] for s in all_stops}
        if stop_names & JINGYUAN_STATIONS and not stop_names & CORRIDOR_STATIONS:
            skipped.append({"code": meta["code"], "train_no": tn,
                            "reason": "京原线车次（含灵丘/原平/忻州等），不经石太走廊"})
            log(f"[{i}/{len(items)}] {meta['code']} 跳过：京原线车次")
            continue

        # 车次号：优先沿用 v1 已收录编号，否则用交路首行的始发车次号
        actual_code = next((s["station_train_code"] for s in all_stops if s["station_train_code"]), "")
        v1_code = next((c for c in meta["codes"] if c in direction_ref), None)
        code = v1_code or actual_code or meta["codes"][0]
        aliases = [c for c in meta["codes"] if c != code]

        offsets, cross_notes = infer_day_offsets(all_stops)
        direction, dir_basis = infer_direction(all_stops)
        if code in direction_ref:
            direction, dir_basis = direction_ref[code], "沿用 v1 已核定方向"
        raw_type = next((s["train_class_name"] for s in all_stops if s["train_class_name"]), "")
        train_type = map_train_type(code, raw_type)

        # 始发日期 -> 相对服务日的平移
        std = meta.get("start_train_date") or ""
        shift = 0
        if re.fullmatch(r"\d{8}", std):
            shift = (date.fromisoformat(SERVICE_DATE) - date(int(std[:4]), int(std[4:6]), int(std[6:]))).days

        train = {
            "code": code, "train_no_internal": tn, "direction": direction,
            "direction_basis": dir_basis, "train_type": train_type, "raw_class": raw_type,
            "stops": all_stops, "offsets": offsets, "shift": shift,
            "aliases": aliases, "all_stop_count": len(all_stops),
            "lishi": meta["lishi"], "from_dep": meta["from_dep"], "to_arr": meta["to_arr"],
            "start_train_date": std, "cross_notes": cross_notes,
        }
        trains.append(train)
        first_dep = parse_hhmm(all_stops[0]["start_time"])
        last_arr = parse_hhmm(all_stops[-1]["arrive_time"])
        calc = None
        if first_dep is not None and last_arr is not None:
            calc = last_arr - first_dep + offsets[-1] * 1440
        log(f"[{i}/{len(items)}] {code:6s} {direction:5s} {train_type:4s} "
            f"{all_stops[0]['station_name']}->{all_stops[-1]['station_name']} 站{len(all_stops):2d} "
            f"全程{calc if calc is not None else '?'}分 区间历时{meta['lishi']}"
            + (f"  别名{'/'.join(aliases)}" if aliases else ""))

    # 写 CSV
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(HEADER)
        for t in sorted(trains, key=lambda x: (x["code"][0], x["code"])):
            last = len(t["stops"]) - 1
            for idx, s in enumerate(t["stops"]):
                arr = s["arrive_time"] if parse_hhmm(s["arrive_time"]) is not None else ""
                dep = s["start_time"] if parse_hhmm(s["start_time"]) is not None else ""
                # 12306 对终到站也填 start_time（等于到达时刻），按契约为终到站留空
                if idx == last:
                    dep = ""
                do = t["offsets"][idx] - t["shift"]
                w.writerow([
                    t["code"], t["direction"], t["train_type"], idx + 1,
                    s["station_name"], arr, dep, do, "", "true",
                    build_remark(t["stops"], t),
                ])
    log(f"[write] {out_path} 车次 {len(trains)} 行 {sum(len(t['stops']) for t in trains)}")

    summary = {
        "service_date": SERVICE_DATE,
        "access_date": time.strftime("%Y-%m-%d"),
        "channel": {
            "init": INIT_URL,
            "left_ticket_path": client.left_ticket_path,
            "query_by_train_no": f"{BASE}/otn/czxx/queryByTrainNo",
        },
        "od_queries": od_report,
        "hits_total": len(hits),
        "trains_written": len(trains),
        "stops_written": sum(len(t["stops"]) for t in trains),
        "skipped": skipped,
        "trains": [
            {
                "code": t["code"], "train_no_internal": t["train_no_internal"],
                "direction": t["direction"], "direction_basis": t["direction_basis"],
                "train_type": t["train_type"], "raw_class": t["raw_class"],
                "origin": t["stops"][0]["station_name"], "terminal": t["stops"][-1]["station_name"],
                "station_count": len(t["stops"]),
                "first_dep": t["stops"][0]["start_time"], "last_arr": t["stops"][-1]["arrive_time"],
                "lishi_12306": t["lishi"], "start_train_date": t["start_train_date"],
                "aliases": t["aliases"], "circuit_stop_count": t["all_stop_count"],
                "cross_day_notes": t["cross_notes"],
            } for t in trains
        ],
    }
    sp = Path(args.summary)
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"[write] {sp}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
