import os
import re

def fix_examples_in_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # We need to replace `example=X` with `examples=[X]` in Field(...) definitions.
    # regex: example=(.*?)(?=,|\)$)
    # Be careful not to replace example in json_schema_extra={"example": ...} which we already have in some files!
    
    # Let's find occurrences of example=... that are not preceded by a quote
    # A safer approach is just regex on: r'\bexample=([^,\n\)]+)'
    
    def replacer(match):
        val = match.group(1).strip()
        return f"examples=[{val}]"

    new_content, count = re.subn(r'\bexample=([^,\n\)]+)', replacer, content)
    if count > 0:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Fixed {count} instances in {filepath}")

for root, _, files in os.walk('backend'):
    for file in files:
        if file.endswith('.py'):
            fix_examples_in_file(os.path.join(root, file))
