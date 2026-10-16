import asyncio, socket, ssl, time, json
from urllib.parse import urlparse, parse_qs

def parse_node(uri):
    try:
        p = urlparse(uri)
        if not p.hostname or not p.port: return None
        qs = parse_qs(p.query)
        return {
            "raw": uri,
            "host": p.hostname,
            "port": p.port,
            "uuid": p.username or "",
            "sni": qs.get("sni",[""])[0],
            "type": qs.get("type",["tcp"])[0],
            "key": f"{p.hostname}:{p.port}:{p.username}"
        }
    except:
        return None

async def tcp_alive(node, timeout=3):
    try:
        loop = asyncio.get_event_loop()
        start = time.time()
        await asyncio.wait_for(
            loop.run_in_executor(None, lambda: socket.create_connection((node["host"], node["port"]), timeout=timeout)),
            timeout=timeout+1
        )
        node["latency_ms"] = int((time.time()-start)*1000)
        return True
    except:
        return False

async def tls_handshake(node, timeout=4):
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        sni = node["sni"] or node["host"]
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(node["host"], node["port"], ssl=ctx, server_hostname=sni),
            timeout=timeout
        )
        writer.close()
        await writer.wait_closed()
        return True
    except:
        return False

async def filter_file(input_path="raw/all.txt"):
    with open(input_path, encoding="utf-8", errors="ignore") as f:
        raw = [l.strip() for l in f if l.strip().startswith("vless://")]

    parsed = [parse_node(r) for r in raw]
    parsed = [p for p in parsed if p]
    # dedup, prefer tcp
    uniq = {}
    for p in parsed:
        k = p["key"]
        if k not in uniq or (uniq[k]["type"]=="xhttp" and p["type"]=="tcp"):
            uniq[k] = p
    nodes = list(uniq.values())
    print(f"Dedup {len(raw)} -> {len(nodes)}")

    # stage 1 tcp
    alive = []
    sem = asyncio.Semaphore(200)
    async def c1(n):
        async with sem:
            if await tcp_alive(n):
                alive.append(n)
    await asyncio.gather(*[c1(n) for n in nodes])
    print(f"TCP alive {len(alive)}/{len(nodes)}")

    # stage 2 reality handshake
    working = []
    sem2 = asyncio.Semaphore(100)
    async def c2(n):
        async with sem2:
            if await tls_handshake(n):
                working.append(n)
    await asyncio.gather(*[c2(n) for n in alive])
    print(f"WORKING {len(working)}/{len(alive)}")

    working.sort(key=lambda x: x["latency_ms"])
    # save
    with open("dist/working.json","w") as f:
        json.dump(working, f, indent=2)
    with open("dist/working.txt","w", encoding="utf-8") as f:
        for w in working:
            f.write(w["raw"]+"\n")
    with open("dist/all.txt","w", encoding="utf-8") as f:
        f.write("\n".join(raw))
    return working

if __name__ == "__main__":
    asyncio.run(filter_file())