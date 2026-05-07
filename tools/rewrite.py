import os

# 1. Clean up network.py
network_path = "d:/improve/hermes/src/hermes_core/network.py"
with open(network_path, "r", encoding="utf-8") as f:
    network_content = f.read()
import re
network_content = re.sub(r'# Guard so the OpenRouter metadata pre-warm.*?\n_openrouter_prewarm_done = threading\.Event\(\)\n', '', network_content, flags=re.DOTALL)
with open(network_path, "w", encoding="utf-8") as f:
    f.write(network_content)

# 2. Rewrite run_agent.py
source_file = "d:/improve/hermes/run_agent.py"
with open(source_file, "r", encoding="utf-8") as f:
    lines = f.readlines()

import_block = """
# ==== Extracted hermes_core imports ====
from hermes_core.network import _load_openai_cls, _OpenAIProxy, OpenAI, _get_proxy_from_env, _get_proxy_for_base_url, _QWEN_CODE_VERSION, _routermint_headers, _pool_may_recover_from_rate_limit, _qwen_portal_headers
from hermes_core.utils import _SafeWriter, _install_safe_stdio, _NEVER_PARALLEL_TOOLS, _PARALLEL_SAFE_TOOLS, _PATH_SCOPED_TOOLS, _MAX_TOOL_WORKERS, _openrouter_prewarm_done, _DESTRUCTIVE_PATTERNS, _REDIRECT_OVERWRITE, _is_destructive_command, _should_parallelize_tool_batch, _extract_parallel_scope_path, _paths_overlap
from hermes_core.budget import IterationBudget
from hermes_core.sanitization import _SURROGATE_RE, _sanitize_surrogates, _sanitize_structure_surrogates, _sanitize_messages_surrogates, _escape_invalid_chars_in_json_strings, _repair_tool_call_arguments, _strip_non_ascii, _sanitize_messages_non_ascii, _sanitize_tools_non_ascii, _sanitize_structure_non_ascii
# =======================================
"""

new_lines = []
new_lines.extend(lines[0:62])
new_lines.append(import_block)
new_lines.extend(lines[91:180])
# 180:445 removed
new_lines.extend(lines[445:447])
# 447:809 removed
new_lines.extend(lines[809:817])
# 817:871 removed
new_lines.extend(lines[871:])

with open(source_file, "w", encoding="utf-8") as f:
    f.writelines(new_lines)
