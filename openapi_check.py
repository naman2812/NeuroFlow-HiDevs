import json
from backend.main import app
import logging
logger = logging.getLogger(__name__)



schema = app.openapi()
missing_descriptions = []

for path, methods in schema["paths"].items():
    for method, operation in methods.items():
        if "description" not in operation:
            missing_descriptions.append(f"{method.upper()} {path} missing description")
        if "summary" not in operation:
            missing_descriptions.append(f"{method.upper()} {path} missing summary")

if not missing_descriptions:
    logger.info("SUCCESS: All endpoints have descriptions and summaries.")
else:
    logger.info("MISSING DESCRIPTIONS:")
    for m in missing_descriptions:
        logger.info(m)
