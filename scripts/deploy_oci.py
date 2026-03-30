#!/usr/bin/env python3
"""
Deploy V-Legal backend to an existing OCI VM via SSH.

Usage:
    python scripts/deploy_oci.py

Environment variables (from .env):
    OCI_SSH_CONNECT   - full ssh command, e.g. ssh -i "C:\\Users\\Admin\\.ssh\\XXX" ubuntu@X.X.X.X
    VLEGAL_ENVIRONMENT
    VLEGAL_PUBLIC_BASE_URL
    VLEGAL_CORS_ALLOWED_ORIGINS
    VLEGAL_APPWRITE_ENDPOINT
    VLEGAL_APPWRITE_PROJECT_ID
    VLEGAL_APPWRITE_DATABASE_ID
    VLEGAL_APPWRITE_API_KEY
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv

load_dotenv()

from vlegal_prototype.settings import get_settings


def get_env_lines() -> list[str]:
    settings = get_settings()
    return [
        "PORT=8000",
        f"VLEGAL_ENVIRONMENT={settings.environment}",
        f"VLEGAL_PUBLIC_BASE_URL={settings.public_base_url}",
        f"VLEGAL_CORS_ALLOWED_ORIGINS={settings.cors_allowed_origins}",
        f"VLEGAL_APPWRITE_ENDPOINT={settings.appwrite_endpoint}",
        f"VLEGAL_APPWRITE_PROJECT_ID={settings.appwrite_project_id}",
        f"VLEGAL_APPWRITE_DATABASE_ID={settings.appwrite_database_id}",
        f"VLEGAL_APPWRITE_API_KEY={settings.appwrite_api_key}",
    ]


def run_remote(ssh_cmd: str, *remote_args: str) -> subprocess.CompletedProcess:
    cmd = ssh_cmd.split() + list(remote_args)
    return subprocess.run(cmd, capture_output=True, text=True)


def deploy(ssh_connect: str) -> None:
    env_lines = get_env_lines()
    env_block = "\n".join(env_lines)
    print(f"Target: {ssh_connect}")

    print("\n[1/5] Test SSH connectivity...")
    r = run_remote(ssh_connect, "hostname")
    if r.returncode != 0:
        print(f"SSH failed: {r.stderr}")
        sys.exit(1)
    print(f"  Connected to: {r.stdout.strip()}")

    print("\n[2/5] Check for existing deployment...")
    r = run_remote(ssh_connect, "test", "-d", "~/V-Legal", "&&", "echo", "exists")
    existing = r.stdout.strip() == "exists"
    if existing:
        print("  Repo exists, will pull latest...")
        r = run_remote(ssh_connect, "cd", "~/V-Legal", "&&", "git", "pull")
        if r.returncode != 0:
            print(f"  git pull failed: {r.stderr}")
        else:
            print("  Pulled latest")
    else:
        print("  Cloning fresh...")
        repo_url = input("Enter GitHub repo URL (or press Enter to skip): ").strip()
        if repo_url:
            r = run_remote(ssh_connect, "git", "clone", repo_url, "~/V-Legal")
            if r.returncode != 0:
                print(f"  clone failed: {r.stderr}")
                sys.exit(1)

    print("\n[3/5] Write deploy/oci/.env on remote...")
    r = run_remote(
        ssh_connect,
        "mkdir",
        "-p",
        "~/V-Legal/deploy/oci",
    )
    proc = subprocess.run(
        ssh_connect.split() + ["cat", ">", "~/V-Legal/deploy/oci/.env"],
        input=env_block,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print(f"  Write .env failed: {proc.stderr}")
        sys.exit(1)
    print("  Written")

    print("\n[4/5] Pull latest Docker image...")
    r = run_remote(
        ssh_connect,
        "cd",
        "~/V-Legal",
        "&&",
        "docker",
        "compose",
        "-f",
        "deploy/oci/docker-compose.yml",
        "pull",
    )
    if r.returncode != 0:
        print(f"  docker compose pull failed (no image yet is normal): {r.stderr}")

    print("\n[5/5] Restart service...")
    r = run_remote(
        ssh_connect,
        "cd",
        "~/V-Legal",
        "&&",
        "VLEGAL_BOOTSTRAP_LIMIT=0",
        "docker",
        "compose",
        "-f",
        "deploy/oci/docker-compose.yml",
        "up",
        "-d",
        "--build",
    )
    if r.returncode != 0:
        print(f"  docker compose up failed: {r.stderr}")
        sys.exit(1)
    print("  Service restarted")

    print("\n[Done] Verifying health...")
    r = run_remote(ssh_connect, "curl", "-s", "http://127.0.0.1:8000/health")
    if r.returncode == 0 and "ok" in r.stdout:
        print(f"  Health: {r.stdout.strip()}")
    else:
        print(f"  Health check failed (may still be starting): {r.stdout} {r.stderr}")

    print("\nDeploy complete.")


def main() -> None:
    settings = get_settings()
    ssh_connect = os.environ.get("OCI_SSH_CONNECT", "").strip()
    if not ssh_connect:
        print("ERROR: OCI_SSH_CONNECT env var not set")
        sys.exit(1)

    print(f"Deploying to OCI backend...")
    print(f"  Appwrite DB: {settings.appwrite_database_id}")
    print(f"  Environment: {settings.environment}")
    print()
    deploy(ssh_connect)


if __name__ == "__main__":
    main()
