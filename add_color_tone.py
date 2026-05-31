# add_color_tone.py
"""Add a '色调' field with value '暖橙色调' to every clip's attributes in all JSON files under the data directory.
Usage: python add_color_tone.py
"""
import json
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

def update_file(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    clips = data.get("clips", {})
    changed = False
    for clip_key, clip in clips.items():
        attrs = clip.get("attributes", {})
        if "色调" not in attrs:
            attrs["色调"] = "暖橙色调"
            clip["attributes"] = attrs
            changed = True
    if changed:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"Updated {path}")
    else:
        print(f"No changes needed for {path}")

if __name__ == "__main__":
    for filename in os.listdir(DATA_DIR):
        if filename.lower().endswith('.json'):
            update_file(os.path.join(DATA_DIR, filename))
