#!/usr/bin/env python3
"""Daily backup to Google Drive. Backs up hermes config, scripts, workspace docs, Postgres dump."""
import os
import sys
import json
import gzip
import shutil
import subprocess
import tarfile
import tempfile
import datetime
import requests
from pathlib import Path

TOKEN_FILE = Path("/home/Bilirubin/.hermes/google_token.json")
DRIVE_FOLDER_NAME = "Hermes Backups"
FOLDER_ID_CACHE = Path("/home/Bilirubin/.hermes/gdrive_folder_id.txt")
KEEP_BACKUPS = 7

BACKUP_PATHS = [
    "/home/Bilirubin/.hermes/config.yaml",
    "/home/Bilirubin/.hermes/google_token.json",
    "/home/Bilirubin/.hermes/gdrive_folder_id.txt",
    "/home/Bilirubin/workspace/hermes_workspace_.hermes.md",
    "/usr/local/bin/health_optimization_loop.py",
    "/usr/local/bin/safe_write.py",
    "/usr/local/bin/hermes_agent_guard.sh",
    "/usr/local/bin/safe_restart_gateway.sh",
    "/usr/local/bin/gdrive_backup.py",
    "/usr/local/bin/gdrive_reauth.py",
    "/etc/systemd/system/hermes-agent-guard.service",
    "/etc/systemd/system/gdrive-backup.service",
    "/etc/systemd/system/gdrive-backup.timer",
]


def load_token():
    data = json.loads(TOKEN_FILE.read_text())
    scopes = data.get("scopes", [])
    has_write = any("drive.file" in s or s == "https://www.googleapis.com/auth/drive" for s in scopes)
    if not has_write:
        print("ERROR: Google token lacks drive.file scope.", file=sys.stderr)
        print("Run: python3 /usr/local/bin/gdrive_reauth.py", file=sys.stderr)
        sys.exit(1)
    return data


def refresh_token(token_data):
    resp = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": token_data["client_id"],
        "client_secret": token_data["client_secret"],
        "refresh_token": token_data["refresh_token"],
        "grant_type": "refresh_token",
    }, timeout=30)
    resp.raise_for_status()
    new_data = resp.json()
    access_token = new_data["access_token"]
    # Persist updated token
    token_data["access_token"] = access_token
    TOKEN_FILE.write_text(json.dumps(token_data, indent=2))
    return access_token


def get_or_create_folder(access_token, folder_name):
    # Use cached folder ID to avoid files.list (not allowed with drive.file scope)
    if FOLDER_ID_CACHE.exists():
        folder_id = FOLDER_ID_CACHE.read_text().strip()
        if folder_id:
            print(f"Using cached folder id: {folder_id}")
            return folder_id
    headers = {"Authorization": f"Bearer {access_token}"}
    meta = {"name": folder_name, "mimeType": "application/vnd.google-apps.folder"}
    r = requests.post("https://www.googleapis.com/drive/v3/files",
                      headers=headers,
                      json=meta, timeout=30)
    r.raise_for_status()
    folder_id = r.json()["id"]
    FOLDER_ID_CACHE.write_text(folder_id)
    return folder_id


def create_backup_archive():
    ts = datetime.datetime.now().strftime("%Y-%m-%d_%H%M")
    archive_name = f"hermes_backup_{ts}.tar.gz"
    tmp_dir = Path(tempfile.mkdtemp())
    archive_path = tmp_dir / archive_name

    with tarfile.open(archive_path, "w:gz") as tar:
        for path_str in BACKUP_PATHS:
            p = Path(path_str)
            if p.exists():
                tar.add(str(p), arcname=p.name)
                print(f"  + {p.name}")
            else:
                print(f"  - skipped (missing): {p.name}")

        # Postgres dump via Docker container
        pg_dump = tmp_dir / "postgres_dump.sql.gz"
        try:
            result = subprocess.run(
                ["docker", "exec", "automation-postgres", "pg_dump",
                 "-U", "automation", "-d", "postgres",
                 "--schema=automation", "--schema=rag",
                 "--no-owner", "--no-acl"],
                capture_output=True, timeout=120
            )
            if result.returncode == 0:
                with gzip.open(pg_dump, "wb") as f:
                    f.write(result.stdout)
                tar.add(str(pg_dump), arcname="postgres_dump.sql.gz")
                size_mb = pg_dump.stat().st_size / 1024 / 1024
                print(f"  + postgres_dump.sql.gz ({size_mb:.1f} MB)")
            else:
                print(f"  - postgres dump failed: {result.stderr.decode()[:200]}", file=sys.stderr)
        except Exception as e:
            print(f"  - postgres dump error: {e}", file=sys.stderr)

    size_mb = archive_path.stat().st_size / 1024 / 1024
    print(f"Archive: {archive_name} ({size_mb:.1f} MB)")
    return archive_path, archive_name, tmp_dir


def upload_file(access_token, folder_id, archive_path, archive_name):
    headers = {"Authorization": f"Bearer {access_token}"}
    meta = {"name": archive_name, "parents": [folder_id]}
    with open(archive_path, "rb") as f:
        r = requests.post(
            "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
            headers=headers,
            files={
                "metadata": ("metadata", json.dumps(meta), "application/json"),
                "file": (archive_name, f, "application/gzip"),
            },
            timeout=300,
        )
    r.raise_for_status()
    file_id = r.json()["id"]
    print(f"Uploaded: {archive_name} (id={file_id})")
    return file_id


def rotate_old_backups(access_token, folder_id, keep=KEEP_BACKUPS):
    headers = {"Authorization": f"Bearer {access_token}"}
    # drive.file scope allows listing files within a folder the app created
    q = f"'{folder_id}' in parents and trashed=false"
    r = requests.get("https://www.googleapis.com/drive/v3/files",
                     headers=headers,
                     params={"q": q, "fields": "files(id,name,createdTime)",
                             "orderBy": "createdTime desc"},
                     timeout=30)
    if r.status_code == 403:
        print("Skipping rotation (drive.file scope cannot list older backups)")
        return
    r.raise_for_status()
    files = r.json().get("files", [])
    to_delete = files[keep:]
    for f in to_delete:
        requests.delete(f"https://www.googleapis.com/drive/v3/files/{f['id']}",
                        headers=headers, timeout=30)
        print(f"Deleted old backup: {f['name']}")


def main():
    print(f"=== Hermes Drive Backup {datetime.datetime.now().isoformat()} ===")
    token_data = load_token()
    print("Refreshing access token...")
    access_token = refresh_token(token_data)
    print("Getting/creating Drive folder...")
    folder_id = get_or_create_folder(access_token, DRIVE_FOLDER_NAME)
    print(f"Folder id: {folder_id}")
    print("Building archive...")
    archive_path, archive_name, tmp_dir = create_backup_archive()
    print("Uploading to Drive...")
    upload_file(access_token, folder_id, archive_path, archive_name)
    print("Rotating old backups...")
    rotate_old_backups(access_token, folder_id)
    print("Cleaning up local temp...")
    shutil.rmtree(tmp_dir, ignore_errors=True)
    print("Done.")


if __name__ == "__main__":
    main()
