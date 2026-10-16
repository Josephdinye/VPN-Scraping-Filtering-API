import json, os, datetime
# just ensures dist files exist for api
if not os.path.exists("dist/working.json"):
    print("No working.json yet")
else:
    data = json.load(open("dist/working.json"))
    print(f"Publishing {len(data)} nodes - {datetime.datetime.utcnow().isoformat()}")