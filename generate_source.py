import urllib.request
import json
import re
from datetime import datetime

def fetch_json(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode())

def get_nuvio_versions():
    try:
        releases = fetch_json("https://api.github.com/repos/luqmanfadlli/NuvioMobile-iOS/releases")
        versions = []
        for rel in releases:
            for asset in rel.get('assets', []):
                if asset['name'].endswith('.ipa'):
                    versions.append({
                        "version": rel['tag_name'] + ("-Enhanced" if "Enhanced" in asset['name'] else "-Full"),
                        "date": rel['published_at'],
                        "size": asset['size'],
                        "downloadURL": asset['browser_download_url'],
                        "localizedDescription": rel.get('body', '')
                    })
        return versions
    except Exception as e:
        print("Error fetching Nuvio:", e)
        return []

def get_apex_versions():
    try:
        releases = fetch_json("https://api.github.com/repos/lowiqentity/APEX/releases")
        versions = []
        for rel in releases:
            body = rel.get('body', '')
            match = re.search(r'(https?://[^\s]+\.ipa)', body)
            if match:
                url = match.group(1)
                versions.append({
                    "version": rel['tag_name'],
                    "date": rel['published_at'],
                    "size": 100000000,
                    "downloadURL": url,
                    "localizedDescription": body
                })
        return versions
    except Exception as e:
        print("Error fetching APEX:", e)
        return []

source = {
    "name": "My Custom iOS Source",
    "identifier": "com.owentariq.feathersource",
    "apps": [
        {
            "name": "Nuvio",
            "bundleIdentifier": "com.luqmanfadlli.nuvio",
            "developerName": "luqmanfadlli",
            "version": "0.0.0",
            "versions": get_nuvio_versions()
        },
        {
            "name": "APEX",
            "bundleIdentifier": "com.lowiqentity.apex",
            "developerName": "lowiqentity",
            "version": "0.0.0",
            "versions": get_apex_versions()
        }
    ]
}

if source["apps"][0]["versions"]:
    source["apps"][0]["version"] = source["apps"][0]["versions"][0]["version"]
if source["apps"][1]["versions"]:
    source["apps"][1]["version"] = source["apps"][1]["versions"][0]["version"]

with open("source.json", "w") as f:
    json.dump(source, f, indent=2)

print("Successfully generated source.json")
