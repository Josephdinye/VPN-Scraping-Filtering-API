import re, asyncio, aiohttp

FEED_URLS = [
    "https://raw.githubusercontent.com/Josephdinye/Joseph-fastVPN/refs/heads/main/config1.txt",
    "https://raw.githubusercontent.com/Josephdinye/Joseph-fastVPN/refs/heads/main/configs.txt"
]
VLESS_RE = re.compile(r'vless://[^\s\n]+')

async def fetch(url, session):
    try:
        async with session.get(url, timeout=30) as r:
            txt = await r.text()
            found = VLESS_RE.findall(txt)
            print(f"[OK] {url} -> {len(found)}")
            return found
    except Exception as e:
        print(f"[FAIL] {url}: {e}")
        return []

async def scrape_all():
    async with aiohttp.ClientSession() as s:
        res = await asyncio.gather(*[fetch(u, s) for u in FEED_URLS])
        all_nodes = []
        for lst in res:
            all_nodes.extend(lst)
        # strip trailing comment
        all_nodes = [x.split()[0] for x in all_nodes if x.startswith("vless://")]
        # unique
        all_nodes = list(dict.fromkeys(all_nodes))
        print(f"TOTAL UNIQUE RAW: {len(all_nodes)}")
        with open("raw/all.txt","w",encoding="utf-8") as f:
            f.write("\n".join(all_nodes))
        return all_nodes

if __name__ == "__main__":
    asyncio.run(scrape_all())