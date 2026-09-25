"""Create a small snapshot from the Freeway Bureau's public VD feeds."""
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

BASE = "https://tisvcloud.freeway.gov.tw/history/motc20/"
SITE = "https://william12304.github.io/stock-dashboard/traffic.json"


def children(node, path):
    return node.findall(path) if node is not None else []


def value(node, key):
    return (node.findtext(key) or "").strip() if node is not None else ""


def number(raw):
    try:
        result = float(raw)
        return result if result >= 0 else None
    except (TypeError, ValueError):
        return None


def get_xml(name):
    request = Request(BASE + name, headers={"User-Agent": "Mozilla/5.0 (public road data dashboard)"})
    with urlopen(request, timeout=25) as response:
        root = ET.fromstring(response.read())
    for element in root.iter():
        element.tag = element.tag.rsplit("}", 1)[-1]
    return root


def tdx_fallback():
    """Read the alternate official TDX feed using cached static detector metadata."""
    cached = Path("traffic.json")
    if not cached.exists():
        return False
    reference = json.loads(cached.read_text(encoding="utf-8"))
    known = {row["id"]: row for row in reference.get("rows", [])}
    request = Request(
        "https://tdx.transportdata.tw/api/basic/v2/Road/Traffic/Live/VD/Freeway?%24top=3000&%24format=JSON",
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
    )
    with urlopen(request, timeout=18) as response:
        result = json.load(response)
    source_time = result.get("SrcUpdateTime") or result.get("UpdateTime")
    if not source_time or datetime.now(timezone.utc) - datetime.fromisoformat(source_time.replace("Z", "+00:00")) > timedelta(minutes=15):
        raise ValueError("TDX data is older than 15 minutes")
    rows = []
    for vd in result.get("VDLives", []):
        if vd.get("Status") != 0:
            continue
        for flow in vd.get("LinkFlows", []):
            old = known.get(f'{vd.get("VDID")}:{flow.get("LinkID")}')
            if not old:
                continue
            lanes = []
            for lane in flow.get("Lanes", []):
                speed = number(lane.get("Speed"))
                volumes = [number(vehicle.get("Volume")) for vehicle in lane.get("Vehicles", [])]
                if speed is not None and volumes and all(v is not None for v in volumes):
                    lanes.append({"speed": speed, "volume": int(sum(volumes))})
            if lanes:
                rows.append({**old, "time": vd.get("DataCollectTime"), "lanes": lanes})
    if len(rows) < 100:
        raise ValueError("TDX returned too few matching detectors")
    cached.write_text(json.dumps({"generatedAt": datetime.now(timezone.utc).isoformat(),
                                  "sourceTime": source_time, "rows": rows},
                                 ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Updated {len(rows)} detector rows through TDX")
    return True


def main():
    try:
        static = get_xml("VD.xml")
        live = get_xml("VDLive.xml")
        meta = {}
        for vd in children(static, "./VDs/VD"):
            ident = value(vd, "VDID")
            if not ident:
                continue
            links = {value(link, "LinkID"): value(link, "RoadDirection")
                     for link in children(vd, "./DetectionLinks/DetectionLink")}
            road = value(vd, "RoadName")
            match = re.search(r"VD-N(\d+)", ident, re.I)
            if match:
                road = f"國道{int(match.group(1))}號"
            meta[ident] = {"road": road, "mile": value(vd, "LocationMile"),
                           "links": links, "type": value(vd, "DetectionType")}

        rows = []
        for vd in children(live, "./VDLives/VDLive"):
            info = meta.get(value(vd, "VDID"))
            if not info or (info["type"] and info["type"] != "1") or not info["road"].startswith("國道"):
                continue
            if value(vd, "Status") != "0":
                continue
            for flow in children(vd, "./LinkFlows/LinkFlow"):
                link_id = value(flow, "LinkID")
                direction = info["links"].get(link_id, "")
                if not direction:
                    continue
                lanes = []
                for lane in children(flow, "./Lanes/Lane"):
                    volumes = [number(value(vehicle, "Volume"))
                               for vehicle in children(lane, "./Vehicles/Vehicle")]
                    if any(v is None for v in volumes):
                        volume = None
                    else:
                        volume = int(sum(volumes))
                    lanes.append({"id": value(lane, "LaneID"), "type": value(lane, "LaneType"),
                                  "speed": number(value(lane, "Speed")), "volume": volume,
                                  "occupancy": number(value(lane, "Occupancy"))})
                if lanes:
                    rows.append({"id": value(vd, "VDID") + ":" + link_id,
                                 "road": info["road"], "mile": info["mile"],
                                 "direction": direction, "time": value(vd, "DataCollectTime"),
                                 "lanes": lanes})
        if not rows:
            raise ValueError("No valid freeway detector rows")
        payload = {"generatedAt": datetime.now(timezone.utc).isoformat(),
                   "sourceTime": value(live, "UpdateTime"), "rows": rows}
        Path("traffic.json").write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"Updated {len(rows)} traffic detector rows")
    except Exception as error:
        print(f"Traffic source unavailable: {error}")
        try:
            if tdx_fallback():
                return
        except Exception as fallback_error:
            print(f"TDX unavailable: {fallback_error}")
        cached = Path("traffic.json")
        if cached.exists():
            try:
                if json.loads(cached.read_text(encoding="utf-8")).get("rows"):
                    print("Preserving repository snapshot")
                    return
            except (ValueError, OSError):
                pass
        try:
            request = Request(SITE, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(request, timeout=15) as response:
                old = json.load(response)
            if old.get("rows"):
                Path("traffic.json").write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
                return
        except Exception:
            pass
        Path("traffic.json").write_text(json.dumps({"sourceTime": None, "rows": []}), encoding="utf-8")


if __name__ == "__main__":
    main()
