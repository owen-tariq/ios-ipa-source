import urllib.request
import json
import re
import os
import subprocess
from datetime import datetime

def fetch_json(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode())

def download_file(url, filename):
    print(f"Downloading {url} to {filename}...")
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response, open(filename, 'wb') as out_file:
        out_file.write(response.read())

def get_or_create_mirror_release(tag_name, original_url, app_name):
    # Release tag like "APEX-0.1.5"
    mirror_tag = f"{app_name}-{tag_name}"
    
    # Check if this release already exists in our repo
    try:
        # gh release view APEX-0.1.5 --json assets
        result = subprocess.run(["gh", "release", "view", mirror_tag, "--json", "assets"], capture_output=True, text=True)
        if result.returncode == 0:
            release_data = json.loads(result.stdout)
            if release_data.get("assets"):
                print(f"Mirror for {mirror_tag} already exists.")
                return release_data["assets"][0]["url"]
    except Exception as e:
        print(f"Error checking release {mirror_tag}: {e}")

    # If it doesn't exist or doesn't have assets, we need to download and upload it
    print(f"Creating mirror release for {mirror_tag}...")
    filename = f"{mirror_tag}.ipa"
    try:
        download_file(original_url, filename)
        
        # Create release and upload asset
        subprocess.run(["gh", "release", "create", mirror_tag, filename, "--title", f"{app_name} {tag_name} Mirror", "--notes", f"Mirrored from {original_url}"], check=True)
        
        # Get the new URL
        result = subprocess.run(["gh", "release", "view", mirror_tag, "--json", "assets"], capture_output=True, text=True, check=True)
        release_data = json.loads(result.stdout)
        
        # Clean up local file
        os.remove(filename)
        
        return release_data["assets"][0]["url"]
    except Exception as e:
        print(f"Failed to mirror {mirror_tag}: {e}")
        if os.path.exists(filename):
            os.remove(filename)
        return original_url # Fallback to original URL if mirroring fails

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
                original_url = match.group(1)
                
                # Mirror the IPA since Catbox links can be unreliable
                mirrored_url = get_or_create_mirror_release(rel['tag_name'], original_url, "APEX")
                
                versions.append({
                    "version": rel['tag_name'],
                    "date": rel['published_at'],
                    "size": 100000000,
                    "downloadURL": mirrored_url,
                    "localizedDescription": body
                })
        return versions
    except Exception as e:
        print("Error fetching APEX:", e)
        return []

source = {
    "name": "My Custom iOS Source",
    "identifier": "com.owentariq.feathersource",
    "iconURL": "https://raw.githubusercontent.com/luqmanfadlli/NuvioMobile-iOS/cmp-rewrite/iosApp/iosApp/Assets.xcassets/AppIcon.appiconset/app-icon-1024.png",
    "news": [],
    "apps": [
        {
            "name": "Nuvio",
            "bundleIdentifier": "com.luqmanfadlli.nuvio",
            "developerName": "luqmanfadlli",
            "subtitle": "Watch your library, anywhere",
            "localizedDescription": "Nuvio Mobile for iOS and iPadOS",
            "iconURL": "https://raw.githubusercontent.com/luqmanfadlli/NuvioMobile-iOS/cmp-rewrite/iosApp/iosApp/Assets.xcassets/AppIcon.appiconset/app-icon-1024.png",
            "version": "0.0.0",
            "versions": get_nuvio_versions()
        },
        {
            "name": "APEX",
            "bundleIdentifier": "com.google.ios.youtube",
            "developerName": "lowiqentity",
            "subtitle": "YouTube for iOS",
            "localizedDescription": "APEX is a build of YouTube with custom enhancements.",
            "iconURL": "https://raw.githubusercontent.com/lowiqentity/APEX/main/Assets/repo_icon.png",
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
