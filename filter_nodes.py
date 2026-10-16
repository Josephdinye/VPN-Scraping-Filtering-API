import json
import os
import re
import subprocess
import time
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
import pycountry

FEED_URLS = [
    "https://raw.githubusercontent.com/Josephdinye/Joseph-fastVPN/refs/heads/main/config1.txt",
    "https://raw.githubusercontent.com/Josephdinye/Joseph-fastVPN/refs/heads/main/configs.txt"
]

TEST_URL = "https://gstatic.com"
DOWNLOAD_URL = "https://cloudflare.com" # 1MB payload target file

def download_xray():
    if os.path.exists("./xray"):
        return
    print("Downloading Xray-core binary...")
    url = "https://github.com"
    
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response, open("xray.zip", "wb") as out_file:
        out_file.write(response.read())
        
    subprocess.run(["unzip", "-q", "-o", "xray.zip", "xray"], check=True)
    subprocess.run(["chmod", "+x", "./xray"], check=True)
    if os.path.exists("xray.zip"):
        os.remove("xray.zip")
    print("Xray core execution binary ready.")

def get_flag_emoji(country_code):
    base = 127397
    return chr(base + ord(country_code)) + chr(base + ord(country_code))

def detect_country_global(label):
    lbl_lower = label.lower()
    shorthands = {
        "usa": "US", "america": "US", "united states": "US",
        "uk": "GB", "united kingdom": "GB", "britain": "GB", "london": "GB",
        "holland": "NL", "uae": "AE", "dubai": "AE", "korea": "KR", "south korea": "KR",
        "russia": "RU", "moscow": "RU", "turkey": "TR", "turkiye": "TR"
    }
    
    for kw, iso in shorthands.items():
        if kw in lbl_lower:
            return iso.lower(), get_flag_emoji(iso)

    for country in pycountry.countries:
        if country.name.lower() in lbl_lower or getattr(country, 'official_name', '').lower() in lbl_lower:
            return country.alpha_2.lower(), get_flag_emoji(country.alpha_2)

    iso_words = re.findall(r'\b[A-Z]{2}\b', label)
    for word in iso_words:
        country = pycountry.countries.get(alpha_2=word)
        if country:
            return country.alpha_2.lower(), get_flag_emoji(country.alpha_2)
            
    return "global", "🌐"

def parse_vless(vless_link):
    try:
        if not vless_link.startswith("vless://"):
            return None
            
        # Enhanced cleanup boundary for trailing text documentation loops
        clean_link = re.split(r'\s+#', vless_link)[0].strip()
        
        parts = clean_link.split("#", 1)
        raw_uri = parts[0]
        label = urllib.parse.unquote(parts[1]).strip() if len(parts) > 1 else "Premium Server"
        
        parsed = urllib.parse.urlparse(raw_uri)
        query = parsed.query if parsed.query else parsed.path.split("?")[-1] if "?" in parsed.path else ""
        
        return {
            "uuid": parsed.username,
            "address": parsed.hostname,
            "port": int(parsed.port) if parsed.port else 443,
            "label": label,
            "params": urllib.parse.parse_qs(query),
            "raw": vless_link
        }
    except Exception:
        return None

def build_xray_config(parsed_node, listen_port):
    p = parsed_node["params"]
    
    def get_param(key, default="none"):
        val = p.get(key)
        return val[0] if val else default

    vnext_user = {
        "id": parsed_node["uuid"],
        "encryption": get_param("encryption", "none"),
        "flow": get_param("flow", "")
    }
    if not vnext_user["flow"] or vnext_user["flow"] == "none":
        vnext_user.pop("flow", None)

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

    packet_encoding = get_param("packetEncoding", "")
    if packet_encoding and packet_encoding != "none":
        outbound["settings"]["packetEncoding"] = packet_encoding

    security = outbound["streamSettings"]["security"]
    if security == "tls":
        outbound["streamSettings"]["tlsSettings"] = {
            "serverName": get_param("sni", parsed_node["address"]),
            "fingerprint": get_param("fp", "chrome"),
            "allowInsecure": True # Allows validation even if handshake testing returns unsigned properties
        }
        alpn_val = get_param("alpn", "")
        if alpn_val and alpn_val != "none":
            outbound["streamSettings"]["tlsSettings"]["alpn"] = [urllib.parse.unquote(alpn_val)]
            
    elif security == "reality":
        outbound["streamSettings"]["realitySettings"] = {
            "serverName": get_param("sni", ""),
            "publicKey": get_param("pbk", ""),
            "fingerprint": get_param("fp", "chrome"),
            "shortId": get_param("sid", "")
        }

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
            "mode": get_param("mode", "stream-one")
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
    time.sleep(1.5) # Increased initiation window to prevent handshake failures on standard Linux runners
    
    is_online = False
    speed_mbps = 0.0
    latency_ms = -1

    try:
        from urllib.request import ProxyHandler, build_opener
        
        proxy_handler = ProxyHandler({
            'http': f'socks5h://127.0.0.1:{unique_port}',
            'https': f'socks5h://127.0.0.1:{unique_port}'
        })
        opener = build_opener(proxy_handler)
        
        # Increased timeouts slightly to catch highly remote server profiles
        t0 = time.time()
        opener.open(TEST_URL, timeout=4.0)
        latency_ms = int((time.time() - t0) * 1000)
        
        t1 = time.time()
        with opener.open(DOWNLOAD_URL, timeout=6.0) as response:
            payload = response.read()
            duration = time.time() - t1
            
        if duration > 0 and len(payload) > 0:
            speed_mbps = round(((len(payload) * 8) / duration) / 1_000_000, 2)
            is_online = speed_mbps > 0.005 # Low baseline cutoff parameters
    except Exception:
        pass
    finally:
        proc.terminate()
        proc.wait()
        try: os.remove(config_path) 
        except Exception: pass

    if is_online:
        iso, flag = detect_country_global(parsed["label"])
        return {
            "id": f"node-{hash(node) & 0xfffffff}",
            "name": parsed["label"],
            "flag": flag,
            "iso": iso,
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
            print(f"Failed pulling source endpoint {url}: {e}")

    raw_pool = list(set(raw_pool))
    print(f"Loaded {len(raw_pool)} unique target configurations. Launching workers sweep...")

    clean_nodes = []
    starting_port = 26000

    # Running max worker limitations to avoid network socket congestion failures on shared GitHub Action runner containers
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [
            executor.submit(test_node_worker, node_str, starting_port + idx)
            for idx, node_str in enumerate(raw_pool)
        ]
        for f in futures:
            res = f.result()
            if res:
                clean_nodes.append(res)

    if clean_nodes:
        clean_nodes.sort(key=lambda x: x["downloadMbps"], reverse=True)
        with open("clean-nodes.json", "w", encoding="utf-8") as f:
            json.dump(clean_nodes, f, indent=4, ensure_ascii=False)
        print(f"Sweep pipeline complete. Compiled {len(clean_nodes)} validated working nodes.")
    else:
        print("Completed processing sweep loop, but zero nodes passed verification checks.")

if __name__ == "__main__":
    main()
