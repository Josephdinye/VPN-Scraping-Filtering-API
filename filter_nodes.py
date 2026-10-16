import json
import os
import subprocess
import time
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

FEED_URLS = [
    "https://raw.githubusercontent.com/Josephdinye/Joseph-fastVPN/refs/heads/main/config1.txt",
    "https://raw.githubusercontent.com/Josephdinye/Joseph-fastVPN/refs/heads/main/configs.txt"
]

TEST_URL = "https://gstatic.com"
DOWNLOAD_URL = "https://cloudflare.com" # 1MB real file chunk

COUNTRY_MAP = {
    "germany": "🇩🇪", "usa": "🇺🇸", "america": "🇺🇸", "singapore": "🇸🇬", "japan": "🇯🇵",
    "netherlands": "🇳🇱", "united kingdom": "🇬🇧", "uk": "🇬🇧", "france": "🇫🇷", "canada": "🇨🇦",
    "russia": "🇷🇺", "brazil": "🇧🇷", "italy": "🇮🇹", "spain": "🇪🇸", "sweden": "🇸🇪"
}

def download_xray():
    if os.path.exists("./xray"):
        return
    print("Downloading Xray-core binary...")
    url = "https://github.com"
    urllib.request.urlretrieve(url, "xray.zip")
    subprocess.run(["unzip", "-q", "xray.zip", "xray"], check=True)
    subprocess.run(["chmod", "+x", "./xray"], check=True)
    if os.path.exists("xray.zip"):
        os.remove("xray.zip")
    print("Xray core ready.")

def parse_vless(vless_link):
    try:
        if not vless_link.startswith("vless://"):
            return None
        parts = vless_link.split("#", 1)
        raw_uri = parts[0]
        label = urllib.parse.unquote(parts[1]).split("#")[0].strip() if len(parts) > 1 else "Premium Server"
        
        parsed = urllib.parse.urlparse(raw_uri)
        # Handle cases where query params or comments contain clean up targets
        query = parsed.query.split(" #")[0].strip() if parsed.query else ""
        
        return {
            "uuid": parsed.username,
            "address": parsed.hostname,
            "port": int(parsed.port),
            "label": label,
            "params": urllib.parse.parse_qs(query),
            "raw": vless_link
        }
    except Exception:
        return None

def build_xray_config(parsed_node, listen_port):
    p = parsed_node["params"]
    
    # Helper to pull flat queries from list maps safely
    def get_param(key, default=None):
        val = p.get(key)
        return val[0] if val else default

    vnext_user = {
        "id": parsed_node["uuid"],
        "encryption": get_param("encryption", "none"),
        "flow": get_param("flow", "")
    }
    if not vnext_user["flow"]:
        vnext_user.pop("flow")

    outbound = {
        "protocol": "vless",
        "settings": {
            "vnext": [{
                "address": parsed_node["address"],
                "port": parsed_node["port"],
                "users": [vnext_user]
            }]
        },
        "streamSettings": {
            "network": get_param("type", "tcp"),
            "security": get_param("security", "none")
        }
    }

    security = outbound["streamSettings"]["security"]
    if security == "tls":
        outbound["streamSettings"]["tlsSettings"] = {
            "serverName": get_param("sni", parsed_node["address"]),
            "fingerprint": get_param("fp", "chrome"),
            "allowInsecure": get_param("allowInsecure", "0") in ["1", "true"]
        }
    elif security == "reality":
        outbound["streamSettings"]["realitySettings"] = {
            "serverName": get_param("sni", ""),
            "publicKey": get_param("pbk", ""),
            "fingerprint": get_param("fp", "chrome"),
            "shortId": get_param("sid", "")
        }

    # Protocol Transport Mappings
    network = outbound["streamSettings"]["network"]
    if network == "ws":
        outbound["streamSettings"]["wsSettings"] = {
            "path": get_param("path", "/"),
            "headers": {"Host": get_param("host", "")}
        }
    elif network == "grpc":
        outbound["streamSettings"]["grpcSettings"] = {
            "serviceName": get_param("serviceName", ""),
            "multiMode": get_param("mode", "gun") == "multi"
        }
    elif network == "xhttp":
        outbound["streamSettings"]["xhttpSettings"] = {
            "path": get_param("path", "/"),
            "mode": get_param("mode", "stream-one"),
            "extra": json.loads(urllib.parse.unquote(get_param("extra", "{}"))) if p.get("extra") else {}
        }

    return {
        "log": {"loglevel": "none"},
        "inbounds": [{
            "port": listen_port,
            "listen": "127.0.0.1",
            "protocol": "socks",
            "settings": {"auth": "noauth", "udp": True}
        }],
        "outbounds": [outbound, {"protocol": "freedom", "tag": "direct"}]
    }

def test_node_worker(node, unique_port):
    parsed = parse_vless(node)
    if not parsed:
        return None

    config_json = build_xray_config(parsed, unique_port)
    config_path = f"config_{unique_port}.json"
    
    with open(config_path, "w") as f:
        json.dump(config_json, f)

    proc = subprocess.Popen(
        ["./xray", "run", "-c", config_path],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    time.sleep(1.2) # Allow system socket binding window
    
    is_online = False
    speed_mbps = 0.0
    latency_ms = -1

    try:
        from urllib.request import ProxyHandler, build_opener
        
        # SOCKS5h enforces DNS resolution upstream inside the proxy node channel
        proxy_handler = ProxyHandler({
            'http': f'socks5h://127.0.0.1:{unique_port}',
            'https': f'socks5h://127.0.0.1:{unique_port}'
        })
        opener = build_opener(proxy_handler)
        
        # Test 1: Connectivity Handshake
        t0 = time.time()
        opener.open(TEST_URL, timeout=3.0)
        latency_ms = int((time.time() - t0) * 1000)
        
        # Test 2: Active Chunk Download Speed Measurement (Upload capabilities inferred implicitly via valid data transit)
        t1 = time.time()
        with opener.open(DOWNLOAD_URL, timeout=4.5) as response:
            payload = response.read()
            duration = time.time() - t1
            
        if duration > 0 and len(payload) > 0:
            speed_mbps = round(((len(payload) * 8) / duration) / 1_000_000, 2)
            is_online = speed_mbps > 0.05
    except Exception:
        pass
    finally:
        proc.terminate()
        proc.wait()
        try: os.remove(config_path) 
        except Exception: pass

    if is_online:
        lbl_lower = parsed["label"].lower()
        flag = "🌐"
        for kw, flg in COUNTRY_MAP.items():
            if kw in lbl_lower:
                flag = flg
                break
        return {
            "id": f"node-{hash(node) & 0xfffffff}",
            "name": parsed["label"],
            "flag": flag,
            "protocol": "VLESS",
            "ping": latency_ms,
            "status": "online",
            "downloadMbps": speed_mbps,
            "rawConfig": node
        }
    return None

def main():
    download_xray()
    raw_pool = []
    for url in FEED_URLS:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as r:
                for line in r.read().decode('utf-8').splitlines():
                    clean_line = line.strip()
                    if clean_line.startswith("vless://"):
                        raw_pool.append(clean_line)
        except Exception as e:
            print(f"Failed pulling source {url}: {e}")

    raw_pool = list(set(raw_pool))
    print(f"Loaded {len(raw_pool)} unique node strings. Running validation loops...")

    clean_nodes = []
    starting_port = 25000

    # Parallelize evaluations using thread pools to complete scripts under GitHub action strict timeout constraints
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [
            executor.submit(test_node_worker, node_str, starting_port + idx)
            for idx, node_str in enumerate(raw_pool)
        ]
        for f in futures:
            res = f.result()
            if res:
                clean_nodes.append(res)

    # Sort array so your highest performing nodes land at the very top of user interfaces
    clean_nodes.sort(key=lambda x: x["downloadMbps"], reverse=True)

    with open("clean-nodes.json", "w", encoding="utf-8") as f:
        json.dump(clean_nodes, f, indent=4, ensure_ascii=False)
    print(f"Filtered complete. Outputted {len(clean_nodes)} validated working nodes into clean-nodes.json")

if __name__ == "__main__":
    main()
