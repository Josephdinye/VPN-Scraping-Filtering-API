from fastapi import FastAPI
import json, os

app = FastAPI(title="VPN Scraping Filtering API - Working Only")

@app.get("/")
def index():
    return {"service": "VPN-Scraping-Filtering-API", "mode": "working-only", "feeds": 2}

@app.get("/api/working")
def working(limit: int = 200):
    path = "dist/working.json"
    if not os.path.exists(path):
        return {"error": "not built yet"}
    data = json.load(open(path))
    return {"count": len(data), "nodes": [d["raw"] for d in data[:limit]]}

@app.get("/api/working-full")
def working_full(limit: int = 200):
    path = "dist/working.json"
    if not os.path.exists(path):
        return {"error": "not built yet"}
    data = json.load(open(path))
    return {"count": len(data), "nodes": data[:limit]}

@app.get("/config.txt")
def txt():
    if os.path.exists("dist/working.txt"):
        return open("dist/working.txt").read()
    return ""