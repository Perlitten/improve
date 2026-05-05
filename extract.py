import os

source_file = "d:/improve/hermes/run_agent.py"
dest_dir = "d:/improve/hermes/src/hermes_core"

with open(source_file, "r", encoding="utf-8") as f:
    lines = f.readlines()

def write_file(filename, content):
    with open(os.path.join(dest_dir, filename), "w", encoding="utf-8") as f:
        f.write(content)

# budget.py
budget_content = "import threading\n\n" + "".join(lines[270:314])
write_file("budget.py", budget_content)

# network.py
network_content = """import os
import urllib.request
from typing import Optional
from hermes_core.utils import base_url_hostname, normalize_proxy_url

"""
network_content += "".join(lines[62:91]) + "\n"
network_content += "".join(lines[229:262]) + "\n"
network_content += "".join(lines[343:345]) + "\n"  # prewarm
network_content += "".join(lines[817:871])
write_file("network.py", network_content)

# utils.py
utils_content = """import sys
import os
import re
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def base_url_hostname(url: str) -> str:
    from urllib.parse import urlparse
    try:
        return urlparse(url).hostname or ""
    except Exception:
        return ""

def normalize_proxy_url(url: str) -> str:
    return url

"""
utils_content += "".join(lines[180:229]) + "\n"
utils_content += "".join(lines[262:270]) + "\n"
utils_content += "".join(lines[314:445])
write_file("utils.py", utils_content)

# sanitization.py
sanitization_content = """import re
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

"""
sanitization_content += "".join(lines[447:809])
write_file("sanitization.py", sanitization_content)
