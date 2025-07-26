#!/usr/bin/env python3
"""
Device‑inventory snapshot
─────────────────────────
• Reads switch_list.xlsx  (cols: switch_type, ip, username, password)
• Collects MAC table, interface status, LLDP, last traffic time
• Writes to device_inventory.db   (append‑only)
• Writes/overwrites sheet YYYY‑MM‑DD in device_inventory.xlsx
"""

import os, re, sys, datetime, logging, sqlite3, requests
import pandas as pd
from netmiko import ConnectHandler

# ─────────────────── CONFIG ───────────────────
LOCAL_OUI_CACHE_FILE = "oui_cache.csv"
DB_FILE   = "device_inventory.db"
XLSX_FILE = "device_inventory.xlsx"
LOG_FILE  = "device_inventory.log"


# ────────────────── LOGGING ────────────────────
def setup_logging():
    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


# ────────────── NORMALISERS ────────────────────
PREFIX_MAP = {
    "GigabitEthernet":  "Gi",
    "FastEthernet":     "Fa",
    "TenGigabitEthernet": "Te",
    "TwentyFiveGigE":   "Tf",
    "FortyGigabitEthernet": "Fo",
    "HundredGigE":      "Hu",
    "Ethernet":         "Et",
    "Port-channel":     "Po",
}

def normalize_mac(raw: str) -> str:
    mac = raw.replace(".", "").lower()
    return ":".join(mac[i : i + 2] for i in range(0, len(mac), 2))


def normalize_port(port: str) -> str:
    """Convert long prefixes + zero‑padding → canonical (Gi1/0/1)"""
    port = port.strip()
    for long, short in PREFIX_MAP.items():
        if port.startswith(long):
            port = short + port[len(long):]
            break

    # handle slash‑based formats
    m = re.match(r"([A-Za-z]+)(\d+)/(\d+)/(\d+)", port)
    if m:
        return f"{m[1]}{int(m[2])}/{int(m[3])}/{int(m[4])}"
    m2 = re.match(r"([A-Za-z]+)(\d+)/(\d+)", port)
    if m2:
        return f"{m2[1]}{int(m2[2])}/{int(m2[3])}"
    m3 = re.match(r"([A-Za-z]+)(\d+)", port)
    return f"{m3[1]}{int(m3[2])}" if m3 else port


# ──────────────── OUI CACHE ────────────────────
def load_oui_cache() -> dict:
    if os.path.exists(LOCAL_OUI_CACHE_FILE):
        df = pd.read_csv(LOCAL_OUI_CACHE_FILE)
        return dict(zip(df.oui, df.vendor))
    return {}


def update_oui_cache(oui: str, vendor: str):
    cols = ["oui", "vendor"]
    df = pd.read_csv(LOCAL_OUI_CACHE_FILE) if os.path.exists(LOCAL_OUI_CACHE_FILE) else pd.DataFrame(columns=cols)
    if oui not in df.oui.values:
        df = pd.concat([df, pd.DataFrame([{"oui": oui, "vendor": vendor}])], ignore_index=True)
        df.to_csv(LOCAL_OUI_CACHE_FILE, index=False)


# ───────────────── PARSERS ─────────────────────
def get_vendor(mac: str, oui_dict: dict) -> str:
    oui = ":".join(mac.split(":")[:3])
    if oui in oui_dict:
        return oui_dict[oui]
    try:
        r = requests.get(f"https://api.macvendors.com/{mac}", timeout=5)
        if r.ok:
            oui_dict[oui] = r.text
            update_oui_cache(oui, r.text)
            return r.text
    except Exception:
        pass
    oui_dict[oui] = "Unknown"
    update_oui_cache(oui, "Unknown")
    return "Unknown"


def parse_mac_table(output: str, oui_dict: dict) -> pd.DataFrame:
    patt = re.compile(
        r"(?P<vlan>\d+)\s+(?P<mac>[0-9a-f.]+)\s+(?:DYNAMIC|STATIC|SECURE)\s+(?P<port>\S+)",
        re.I,
    )
    rows = []
    for m in patt.finditer(output):
        port = normalize_port(m.group("port"))
        mac  = normalize_mac(m.group("mac"))
        rows.append({
            "port":        port,
            "mac_address": mac,
            "vendor":      get_vendor(mac, oui_dict),
        })
    return pd.DataFrame(rows).drop_duplicates("port")


def parse_if_status(output: str) -> pd.DataFrame:
    """
    Parse 'show interfaces status' even when the Name field contains spaces.
    Columns Cisco prints (IOS/IOS-XE):
      Port  Name  Status  Vlan  Duplex  Speed  Type
    """

    # known Status keywords → build alternation once
    status_re = r"(connected|notconnect|disabled|err-disabled|inactive|monitoring|secure-shutdown|sfpAbsent)"
    patt = re.compile(
        rf"^(?P<port>\S+)\s+"             # Port (no spaces)
        rf"(?P<name>.+?)\s+"              # Name (lazy)  ← stops at status
        rf"(?P<status>{status_re})\s+"
        r"(?P<vlan>\S+)\s+"
        r"(?P<duplex>\S+)\s+"
        r"(?P<speed>\S+)\s+"
        r"(?P<type>.+)$",
        re.I,
    )

    rows = []
    for line in output.splitlines():
        if not line.strip() or line.startswith(("Port", "---")):
            continue
        m = patt.match(line.rstrip())
        if not m:
            logging.debug("Unparsed status line: %s", line)
            continue
        rows.append(
            dict(
                port=normalize_port(m.group("port")),
                status=m.group("status"),
                vlan=m.group("vlan"),
                description=m.group("name").strip(),
                duplex=m.group("duplex"),
                speed=m.group("speed"),
                type=m.group("type").strip(),
            )
        )
    return pd.DataFrame(rows)


def _age_to_timedelta(text: str):
    if text.lower() == "never":
        return None
    if ":" in text:  # hh:mm:ss
        h, m, s = map(int, text.split(":"))
        return datetime.timedelta(hours=h, minutes=m, seconds=s)
    total = 0
    for num, unit in re.findall(r"(\d+)([wdhms])", text):
        total += int(num) * dict(w=604800, d=86400, h=3600, m=60, s=1)[unit]
    return datetime.timedelta(seconds=total) if total else None


def parse_last_traffic(output: str) -> pd.DataFrame:
    rows, cur_port = [], None
    hdr  = re.compile(r"^(\S+) is .*, line protocol is")
    last = re.compile(r"Last input (\S+), output (\S+),")
    for line in output.splitlines():
        m_hdr = hdr.match(line)
        if m_hdr:
            cur_port = normalize_port(m_hdr.group(1))
            continue
        if cur_port:
            m_last = last.search(line)
            if not m_last:
                continue
            in_d  = _age_to_timedelta(m_last.group(1))
            out_d = _age_to_timedelta(m_last.group(2))
            deltas = [d for d in (in_d, out_d) if d]
            stamp = (datetime.datetime.now() - min(deltas)).isoformat(sep=" ", timespec="seconds") if deltas else "Never"
            rows.append({"port": cur_port, "last_traffic_seen": stamp})
            cur_port = None
    return pd.DataFrame(rows)


def get_lldp_neighbors(dev: dict) -> pd.DataFrame:
    cols = ["port", "neighbor_name", "neighbor_port", "neighbor_platform", "neighbor_capability", "neighbor_device_id"]
    try:
        conn = ConnectHandler(**dev); conn.enable()
        raw = conn.send_command("show lldp neighbors detail")
        conn.disconnect()
        blocks = re.split(r"(?m)^Local (?:Intf|Interface|Port id):", raw)[1:]
        rows = []
        for blk in blocks:
            port = normalize_port(re.search(r"\s*(\S+)", blk).group(1))
            def cyl(pat):
                m = re.search(pat, blk)
                return m.group(1).strip() if m else ""
            rows.append(
                dict(
                    port=port,
                    neighbor_name=cyl(r"System Name:\s*(.+)") or cyl(r"Chassis id:\s*(\S+)"),
                    neighbor_port=cyl(r"Port id:\s*(\S+)"),
                    neighbor_platform=cyl(r"System Description:\s*([\s\S]+?)(?=\n\S|\Z)"),
                    neighbor_capability=cyl(r"System Capabilities:\s*(.+)") or cyl(r"Enabled Capabilities:\s*(.+)"),
                    neighbor_device_id=cyl(r"Chassis id:\s*(\S+)"),
                )
            )
        return pd.DataFrame(rows, columns=cols)
    except Exception as e:
        logging.error("LLDP failed for %s: %s", dev["ip"], e)
        return pd.DataFrame(columns=cols)


# ───────────── ARP (Layer‑3) ─────────────
def get_arp_table(layer3: dict) -> dict:
    try:
        conn = ConnectHandler(**layer3); conn.enable()
        out = conn.send_command("show ip arp"); conn.disconnect()
        return {normalize_mac(mac): ip for ip, mac in re.findall(r"(\d+\.\d+\.\d+\.\d+)\s+\S+\s+([0-9a-f.]+)", out)}
    except Exception as e:
        logging.error("ARP error on %s: %s", layer3["ip"], e)
        return {}


# ─────────────── SWITCH LIST ──────────────
def load_switch_info(sheet="switch_list.xlsx"):
    df = pd.read_excel(sheet)
    acc = [
        dict(device_type="cisco_ios", ip=r.ip, username=r.username, password=r.password)
        for _, r in df[df.switch_type == "access_switch"].iterrows()
    ]
    l3 = df[df.switch_type == "layer3_switch"].iloc[0]
    return acc, dict(device_type="cisco_ios", ip=l3.ip, username=l3.username, password=l3.password)


# ────────────── COLLECTOR ────────────────
def collect_switch_data(dev: dict, oui: dict, arp_map: dict) -> pd.DataFrame:
    conn = ConnectHandler(**dev); conn.enable()
    hostname = conn.send_command("show run | inc ^hostname").split()[-1]
    df_if   = parse_if_status(conn.send_command("show interfaces status"))
    df_mac  = parse_mac_table(conn.send_command("show mac address-table"), oui)
    df_lldp = get_lldp_neighbors(dev)
    df_last = parse_last_traffic(conn.send_command("show interfaces"))
    conn.disconnect()

    # normalise & merge
    for f in (df_if, df_mac, df_lldp, df_last):
        if not f.empty:
            f["port"] = f["port"].apply(normalize_port)

    df = (
        df_if.merge(df_mac,  on="port", how="left")
             .merge(df_lldp, on="port", how="left")
             .merge(df_last, on="port", how="left")
    )

    # fill blanks (leave last_traffic_seen as‑is)
    text_cols = ["mac_address","vendor","neighbor_name","neighbor_port",
                 "neighbor_platform","neighbor_capability","neighbor_device_id"]
    df[text_cols] = df[text_cols].fillna("")
    df["vendor"] = df["vendor"].replace("", "Unknown")
    df["ip_address"] = df["mac_address"].map(arp_map).fillna("Unknown")

    # metadata
    df.insert(0, "switch_name", hostname)
    df.insert(1, "switch_ip", dev["ip"])
    df["snapshot_date"] = datetime.date.today().isoformat()

    return df


# ─────────────── STORAGE ──────────────────
def store_sqlite(df: pd.DataFrame, db: str = DB_FILE):
    with sqlite3.connect(db) as conn:
        df.to_sql("device_inventory", conn, if_exists="append", index=False)
    logging.info("SQLite: %d rows committed", len(df))


def store_excel(df: pd.DataFrame, xlsx: str = XLSX_FILE):
    sheet = datetime.date.today().isoformat()
    if os.path.exists(xlsx):
        with pd.ExcelWriter(xlsx, engine="openpyxl", mode="a", if_sheet_exists="replace") as w:
            df.to_excel(w, sheet_name=sheet, index=False)
    else:
        df.to_excel(xlsx, sheet_name=sheet, index=False)
    logging.info("Excel: wrote %d rows to sheet '%s' in %s", len(df), sheet, xlsx)


# ───────────────── MAIN ───────────────────
def main():
    setup_logging()
    oui_cache = load_oui_cache()
    access, layer3 = load_switch_info()

    arp_map = get_arp_table(layer3)
    frames  = []
    for dev in access:
        try:
            frames.append(collect_switch_data(dev, oui_cache, arp_map))
        except Exception as e:
            logging.error("Collection failed for %s: %s", dev["ip"], e)

    if not frames:
        logging.error("No data collected — exiting")
        sys.exit(1)

    df_all = pd.concat(frames, ignore_index=True)
    df_all = df_all.drop_duplicates(subset=["switch_name","port","snapshot_date"])

    store_sqlite(df_all)
    store_excel(df_all)


if __name__ == "__main__":
    main()
