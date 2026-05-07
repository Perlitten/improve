import os

mixins_dir = "d:/improve/hermes/src/hermes_core/mixins"
for f in ["client_manager.py", "tool_executor.py", "streaming_api.py"]:
    path = os.path.join(mixins_dir, f)
    with open(path, "r", encoding="utf-8") as file:
        lines = file.readlines()
    
    new_lines = []
    in_class = False
    for line in lines:
        if line.startswith("class "):
            in_class = True
            new_lines.append(line)
        elif in_class:
            if line.strip() == "":
                new_lines.append("\n")
            elif not line.startswith(" ") and not line.startswith("\t"):
                new_lines.append("    " + line)
            else:
                # If it already starts with space, we might still need to add 4 spaces
                # because the body was 8 spaces, and the def was 4.
                # Actually, if get_source_segment stripped common indent, then def is 0 and body is 4.
                # So we just add 4 spaces to everything!
                new_lines.append("    " + line)
        else:
            new_lines.append(line)
            
    with open(path, "w", encoding="utf-8") as file:
        file.writelines(new_lines)
