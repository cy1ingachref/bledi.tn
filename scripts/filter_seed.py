import json, sys, pathlib
seed_path = pathlib.Path(r'C:\Users\cy1in\bledi.tn\data\seed_all_tunisia_routes.json')
data = json.load(seed_path.open(encoding='utf-8'))
stations = {s.get('id') for s in data.get('stations', []) if s.get('id')}
lines = data.get('lines', [])
filtered = []
for ln in lines:
    stops = ln.get('stations') or ln.get('stops') or []
    valid = [s for s in stops if s in stations]
    # Keep only lines with at least two valid station IDs
    if len(valid) >= 2:
        filtered.append(ln)
print(f'Filtering: kept {len(filtered)} of {len(lines)} lines', file=sys.stderr)
# Update metadata to reflect new line count
if 'metadata' in data:
    data['metadata']['total_lines'] = len(filtered)

data['lines'] = filtered
seed_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
print('Done', file=sys.stderr)
