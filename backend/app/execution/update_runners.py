import os
import re

dirs = ["runners/nodes", "runners/triggers"]

for d in dirs:
    for f in os.listdir(d):
        if f.endswith(".py") and f != "__init__.py":
            path = os.path.join(d, f)
            with open(path, "r", encoding="utf-8") as file:
                content = file.read()
            
            # Replace 'def run(self, config: dict, input_data: dict) -> dict:'
            # and variations with 'def run(self, config: dict, input_data: Any, context: dict[str, Any] = None) -> dict:'
            
            # Using a regex to catch most variations
            content = re.sub(
                r'def run\(self, config: (dict|dict\[str, Any\]), input_data: (dict|dict\[str, Any\]|Any)\) -> (dict|dict\[str, Any\]):',
                r'def run(self, config: \1, input_data: \2, context: dict[str, Any] = None) -> \3:',
                content
            )
            
            # Specifically for ChatModel runners which I just added and might have slightly different signatures
            content = re.sub(
                r'def run\(self, config: dict\[str, Any\], input_data: Any\) -> dict\[str, Any\]:',
                r'def run(self, config: dict[str, Any], input_data: Any, context: dict[str, Any] = None) -> dict[str, Any]:',
                content
            )

            with open(path, "w", encoding="utf-8") as file:
                file.write(content)
