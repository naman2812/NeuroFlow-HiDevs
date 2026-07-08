import json
from backend.main import app

schema = app.openapi()
missing_descriptions = []

for path, methods in schema["paths"].items():
    for method, operation in methods.items():
        if "description" not in operation:
            missing_descriptions.append(f"{method.upper()} {path} missing description")
        if "summary" not in operation:
            missing_descriptions.append(f"{method.upper()} {path} missing summary")

if not missing_descriptions:
    print("SUCCESS: All endpoints have descriptions and summaries.")
else:
    print("MISSING DESCRIPTIONS:")
    for m in missing_descriptions:
        print(m)
