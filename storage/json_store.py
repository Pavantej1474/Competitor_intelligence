import json, os

def save(data, filename="storage/output/news.json"):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def load(filename):
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)