"""Install an isolated Windows SnpEff runtime from its official distribution.

Run with the project's Python environment. Downloaded software and databases
stay in ignored tools/snpeff; runtime.json pins their observed file hashes.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import zipfile

import httpx

ROOT = Path(__file__).resolve().parents[1]
TOOL_ROOT = ROOT / "tools" / "snpeff"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download(client, url, target, expected=None):
    print(f"Downloading {target.name}", flush=True)
    with client.stream("GET", url, timeout=120) as response:
        response.raise_for_status()
        with target.open("wb") as stream:
            size=0
            for chunk in response.iter_bytes():
                size+=len(chunk)
                if size>2_000_000_000:
                    raise ValueError("Download exceeded the 2 GB installer limit")
                stream.write(chunk)
    if expected and sha(target)!=expected:
        raise ValueError(f"Publisher checksum failed for {target.name}")


def extract(archive, destination):
    base=destination.resolve()
    with zipfile.ZipFile(archive) as source:
        for entry in source.infolist():
            if not (base / entry.filename).resolve().is_relative_to(base):
                raise ValueError("Unsafe archive member")
        source.extractall(base)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--genome",default="GRCh38.mane.1.0.ensembl")
    args=parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}",args.genome):
        raise ValueError("Invalid SnpEff database name")
    TOOL_ROOT.mkdir(parents=True,exist_ok=True)
    if (TOOL_ROOT/"runtime.json").exists():
        print("A pinned runtime already exists. Inspect tools/snpeff/runtime.json before changing it.")
        return
    with httpx.Client(follow_redirects=True,timeout=30) as client:
        metadata=client.get("https://api.adoptium.net/v3/assets/latest/21/hotspot",params={"architecture":"x64","image_type":"jre","os":"windows","vendor":"eclipse"})
        metadata.raise_for_status()
        package=metadata.json()[0]["binary"]["package"]
        java_zip=TOOL_ROOT/"temurin-jre.zip"
        download(client,package["link"],java_zip,package["checksum"])
        extract(java_zip,TOOL_ROOT/"java")
        snpeff_url="https://snpeff-public.s3.amazonaws.com/versions/snpEff_latest_core.zip"
        tool_zip=TOOL_ROOT/"snpeff-core.zip"
        download(client,snpeff_url,tool_zip)
        extract(tool_zip,TOOL_ROOT)
    java=next((TOOL_ROOT/"java").glob("*/bin/java.exe"))
    jar=TOOL_ROOT/"snpEff"/"snpEff.jar"
    config=jar.with_name("snpEff.config")
    data=jar.parent/"data"
    print(f"Downloading database {args.genome}",flush=True)
    completed=subprocess.run([str(java),"-Xmx4g","-jar",str(jar),"download","-noLog","-v",args.genome],
                             cwd=jar.parent,capture_output=True,text=True,timeout=600)
    print(completed.stderr[-6000:],flush=True)
    if completed.returncode:
        raise RuntimeError("SnpEff database download failed")
    files={str(path.relative_to(data/args.genome)).replace('\\','/'):sha(path)
           for path in sorted((data/args.genome).rglob('*')) if path.is_file()}
    if not files:
        raise RuntimeError("SnpEff database has no files")
    version=subprocess.run([str(java),"-jar",str(jar),"-version"],capture_output=True,text=True,timeout=30)
    if version.returncode:
        raise RuntimeError("Unable to read installed SnpEff version")
    database_urls=re.findall(r'https://snpeff-public\.s3\.amazonaws\.com/[^\s\x27]+\.zip',completed.stderr)
    manifest={"installed_at":datetime.now(timezone.utc).isoformat(),"java":str(java),"java_sha256":sha(java),
        "jar":str(jar),"jar_sha256":sha(jar),"config":str(config),"config_sha256":sha(config),
        "data_dir":str(data),"genome":args.genome,"database_files":files,
        "snpeff_version":(version.stdout+version.stderr).strip(),
        "sources":{"java":package["link"],"java_publisher_sha256":package["checksum"],
                   "snpeff":snpeff_url,"snpeff_archive_sha256":sha(tool_zip),
                   "database":database_urls[-1] if database_urls else f"SnpEff download {args.genome}; URL not reported"},
        "documentation":"https://pcingola.github.io/SnpEff/download/"}
    (TOOL_ROOT/"runtime.json").write_text(json.dumps(manifest,indent=2)+"\n")
    print(f"Pinned runtime saved to {TOOL_ROOT/'runtime.json'}",flush=True)


if __name__=="__main__":
    main()
