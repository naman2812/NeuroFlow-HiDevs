import os
import glob

target = 'f"redis://:{settings.redis_password}@{settings.redis_host}:{settings.redis_port}"'
target2 = 'f"redis://:{settings.redis_password}@{settings.redis_host}:{settings.redis_port}",\n            decode_responses=True,'

count = 0
for filepath in glob.glob('backend/**/*.py', recursive=True):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if target in content or target2 in content or 'redis_password' in content:
        new_content = content.replace(target, 'settings.redis_url')
        if target2 in new_content:
            new_content = new_content.replace(target2, 'settings.redis_url,\n            decode_responses=True,')
            
        if new_content != content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            count += 1
            print(f'Updated {filepath}')
print(f'Total files updated: {count}')
