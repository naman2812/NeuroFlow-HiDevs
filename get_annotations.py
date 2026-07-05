import json
data = json.load(open('checks.json', encoding='utf-8'))
for check in data['check_runs']:
    if check['status'] == 'completed' and check['conclusion'] == 'failure':
        print(check['name'])
        if 'output' in check and check['output'] and 'annotations' in check['output']:
            for ann in check['output']['annotations']:
                print(f"{ann['path']}:{ann['start_line']} - {ann['message']}")
