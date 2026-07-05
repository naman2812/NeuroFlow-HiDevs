import re

try:
    with open(r'C:\Users\Naman\.gemini\antigravity\brain\07288fe2-2da0-4f8e-8dce-b95c6c7d9d62\.system_generated\steps\7488\content.md', encoding='utf-8', errors='ignore') as f:
        data = f.read()
    
    matches = re.findall(r'"name":"([^"]+)"[^}]*?"conclusion":"failure"', data)
    print("FAILED:", matches)
except Exception as e:
    print("Error:", e)
