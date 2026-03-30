import json
from collections import Counter

with open('tables.json') as f:
    data = json.load(f)

print('=' * 80)
print('📊 RESULTS FROM LATEST RUN')
print('=' * 80)
print(f'Total tables: {len(data)}')

ai_tables = [t for t in data if 'ai_discovery' in t.get('source_method', '')]
print(f'AI-discovered tables: {len(ai_tables)}')
print()

if ai_tables:
    print('AI-discovered table details:')
    for i, t in enumerate(ai_tables[:20]):
        print(f'  {i+1}. {t.get("table_number", "unnumbered")} (page {t.get("page_start")}) - confidence: {t.get("confidence", "unknown")}')
    if len(ai_tables) > 20:
        print(f'  ...and {len(ai_tables)-20} more')
    print()

print('Source methods summary:')
methods = Counter([t.get('source_method', 'unknown') for t in data])
for method, count in methods.most_common():
    print(f'  {method}: {count}')
print()

pages_with_tables = sorted(set(t.get('page_start') for t in data))
print(f'Pages with tables: {len(pages_with_tables)} out of 158')
print(f'Coverage: {len(pages_with_tables)/158*100:.1f}%')
print()
print(f'Page numbers with tables: {pages_with_tables}')
print('=' * 80)
