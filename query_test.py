import urllib.request
import urllib.parse
import json
import jwt
import time

url = 'https://grateful-trust-production-1456.up.railway.app/query'

SECRET_KEY = "supersecretkey_change_in_production"
ALGORITHM = "HS256"
payload = {
    "sub": "testuser",
    "scopes": ["query"],
    "exp": int(time.time()) + 3600
}
token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

data = json.dumps({"query": "What is NeuroFlow?", "pipeline_id": "840e3701-1953-4ee7-bc9e-7e810f9ffd71"}).encode('utf-8')

req = urllib.request.Request(url, data=data)
req.add_header('Content-Type', 'application/json')
req.add_header('Authorization', f'Bearer {token}')

try:
    response = urllib.request.urlopen(req)
    print(response.getcode())
    response_body = response.read().decode('utf-8')
    print(response_body)
    
    # Extract run_id to test streaming
    run_id = json.loads(response_body).get("run_id")
    if run_id:
        stream_url = f'{url}/{run_id}/stream'
        print(f"Testing stream endpoint: {stream_url}")
        stream_req = urllib.request.Request(stream_url)
        stream_req.add_header('Authorization', f'Bearer {token}')
        stream_resp = urllib.request.urlopen(stream_req)
        print(stream_resp.getcode())
        print(stream_resp.read(100).decode('utf-8'))
        
except Exception as e:
    print(f"Error: {e}")
    if hasattr(e, 'read'):
        print(e.read().decode('utf-8'))
