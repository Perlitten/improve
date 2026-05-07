import os
import ast

source_file = "d:/improve/hermes/run_agent.py"
mixins_dir = "d:/improve/hermes/src/hermes_core/mixins"
os.makedirs(mixins_dir, exist_ok=True)

with open(source_file, "r", encoding="utf-8") as f:
    code = f.read()

tree = ast.parse(code)
methods_code = {}
methods_lines = []

for node in tree.body:
    if isinstance(node, ast.ClassDef) and node.name == 'AIAgent':
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods_code[child.name] = ast.get_source_segment(code, child)
                methods_lines.append((child.lineno, child.end_lineno, child.name))

client_manager = [
    '_client_log_context', '_openai_client_lock', '_is_openai_client_closed',
    '_build_keepalive_http_client', '_create_openai_client', '_force_close_tcp_sockets',
    '_close_openai_client', '_replace_primary_openai_client', '_ensure_primary_openai_client',
    '_cleanup_dead_connections', '_api_kwargs_have_image_parts', '_copilot_headers_for_request',
    '_create_request_openai_client', '_close_request_openai_client',
    '_try_refresh_codex_client_credentials', '_try_refresh_nous_client_credentials',
    '_try_refresh_copilot_client_credentials', '_try_refresh_anthropic_client_credentials',
    '_apply_client_headers_for_base_url', '_swap_credential', '_recover_with_credential_pool',
    '_rebuild_anthropic_client'
]

tool_executor = [
    '_sanitize_tool_calls_for_strict_api', '_sanitize_tool_call_arguments',
    '_should_sanitize_tool_calls', '_set_tool_guardrail_halt',
    '_toolguard_controlled_halt_response', '_append_guardrail_observation',
    '_guardrail_block_result', '_execute_tool_calls', '_dispatch_delegate_task',
    '_invoke_tool', '_wrap_verbose', '_execute_tool_calls_concurrent',
    '_execute_tool_calls_sequential'
]

streaming_api = [
    '_interruptible_api_call', '_reset_stream_delivery_tracking',
    '_record_streamed_assistant_text', '_normalize_interim_visible_text',
    '_interim_content_was_streamed', '_emit_interim_assistant_message',
    '_fire_stream_delta', '_fire_reasoning_delta', '_fire_tool_gen_started',
    '_has_stream_consumers', '_interruptible_streaming_api_call',
    '_run_codex_stream', '_run_codex_create_stream_fallback',
    '_try_activate_fallback', '_restore_primary_runtime', '_try_recover_primary_transport'
]

def write_mixin(name, methods_list, filename):
    content = "import logging\nimport json\nimport asyncio\nimport time\nimport uuid\nimport httpx\nimport threading\n"
    content += "from typing import Any, Optional, Dict, List, Tuple\nfrom hermes_core.network import OpenAI, _get_proxy_from_env, _pool_may_recover_from_rate_limit\n"
    content += "from hermes_core.utils import _is_destructive_command\n\nlogger = logging.getLogger(__name__)\n\n"
    content += f"class {name}:\n"
    for m in methods_list:
        if m in methods_code:
            content += methods_code[m] + "\n\n"
    with open(os.path.join(mixins_dir, filename), "w", encoding="utf-8") as f:
        f.write(content)

write_mixin("ClientManagerMixin", client_manager, "client_manager.py")
write_mixin("ToolExecutionMixin", tool_executor, "tool_executor.py")
write_mixin("StreamingApiMixin", streaming_api, "streaming_api.py")

with open(os.path.join(mixins_dir, "__init__.py"), "w", encoding="utf-8") as f:
    f.write("from .client_manager import ClientManagerMixin\nfrom .tool_executor import ToolExecutionMixin\nfrom .streaming_api import StreamingApiMixin\n")

# Now rewrite run_agent.py
all_extracted = set(client_manager + tool_executor + streaming_api)

with open(source_file, "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
skip_until = -1

imports_added = False

for i, line in enumerate(lines):
    # 0-indexed line number
    lineno = i + 1
    
    if lineno <= skip_until:
        continue
        
    # Check if this line is the start of an extracted method
    matching_method = next((m for m in methods_lines if m[0] == lineno and m[2] in all_extracted), None)
    
    if matching_method:
        skip_until = matching_method[1]
        continue
        
    if line.startswith("class AIAgent:"):
        new_lines.append("from hermes_core.mixins import ClientManagerMixin, ToolExecutionMixin, StreamingApiMixin\n")
        new_lines.append("class AIAgent(ClientManagerMixin, ToolExecutionMixin, StreamingApiMixin):\n")
        continue

    new_lines.append(line)

with open(source_file, "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print("Rewrite complete!")
