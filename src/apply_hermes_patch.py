import yaml
import os

config_path = os.path.expanduser("~/.hermes/config.yaml")

with open(config_path, 'r') as f:
    config = yaml.safe_load(f)

# Disable fallback chain to stop the loop
if 'runtime' in config:
    config['runtime']['fallback_chain'] = []
    print("Disabled fallback_chain in 'runtime' section.")

with open(config_path, 'w') as f:
    yaml.dump(config, f, default_flow_style=False)

print("Patch applied successfully.")
