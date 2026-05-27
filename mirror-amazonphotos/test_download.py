#!/usr/bin/env python3
"""Quick test to see the actual response from get_download_url."""

import json
import logging
from pathlib import Path

import db
from amazon_client import AmazonPhotosClient

logging.basicConfig(level=logging.DEBUG, format="%(levelname)-7s %(message)s")
log = logging.getLogger(__name__)

session_file = Path(__file__).parent.parent / "sync-amazonphotos" / "session.json"
if not session_file.exists():
    print(f"Session not found at {session_file}")
    exit(1)

client = AmazonPhotosClient(session_file, dry_run=False)

# Get first 5 photos
log.info("▶ Getting first 5 photos...")
nodes = client.list_nodes("IMAGE")
if not nodes:
    log.error("No photos found")
    client.close()
    exit(1)

log.info("Found %d photos, testing first one...", len(nodes))
test_node = nodes[0]
node_id = test_node.get("id")
name = test_node.get("name", "unknown")

log.info("Testing node: id=%s, name=%s", node_id, name)

# Try to get download URL
log.info("Calling get_download_url(%s)...", node_id)
url = client.get_download_url(node_id)
if url:
    log.info("✓ Got URL: %s", url[:100])
    log.info("  Full URL: %s", url)
else:
    log.error("✗ No URL returned")

client.close()
