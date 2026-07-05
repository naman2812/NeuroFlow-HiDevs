import urllib.request
import urllib.parse
import json
import mimetypes
import os

url = 'https://grateful-trust-production-1456.up.railway.app/ingest'
filepath = 'test_doc.txt'

with open(filepath, 'w') as f:
    f.write('This is a test document about NeuroFlow.')

boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
with open(filepath, 'rb') as f:
    file_content = f.read()

body = (
    f'--{boundary}\r\n'
    f'Content-Disposition: form-data; name="file"; filename="{os.path.basename(filepath)}"\r\n'
    f'Content-Type: text/plain\r\n\r\n'
).encode('utf-8') + file_content + f'\r\n--{boundary}--\r\n'.encode('utf-8')

try:
    import jwt
except ImportError:
    print("Please pip install PyJWT")
    exit(1)
import time

SECRET_KEY = "supersecretkey_change_in_production"
ALGORITHM = "HS256"
payload = {
    "sub": "testuser",
    "scopes": ["ingest"],
    "exp": int(time.time()) + 3600
}
token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

req = urllib.request.Request(url, data=body)
req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
req.add_header('Authorization', f'Bearer {token}')

try:
    response = urllib.request.urlopen(req)
    print(response.getcode())
    print(response.read().decode('utf-8'))
except Exception as e:
    print(f"Error: {e}")
    if hasattr(e, 'read'):
        print(e.read().decode('utf-8'))
