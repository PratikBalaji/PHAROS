"""Build canonical, per-area exercise bundles from the committed catalogue."""
import json
from pathlib import Path

DATA=Path(__file__).resolve().parents[1]/'dist'/'data'

def build_plan(geoids,mode='auto'):
    if mode not in ('auto','all'): raise ValueError('Unknown language strategy')
    catalogue=json.loads((DATA/'alert-templates.json').read_text())
    districts=json.loads((DATA/'districts.json').read_text())
    by_id={f['properties']['GEOID']:f['properties'] for f in districts['features']}
    meta={lang['code']:lang for lang in catalogue['languages']}
    areas=[]
    for geoid in dict.fromkeys(geoids):
        if geoid not in by_id: raise ValueError('Unknown recipient district')
        p=by_id[geoid]
        candidates=[l for l in p.get('languages',[]) if l['code'] in meta and l['code']!='en' and float(l.get('share',0))>0]
        candidates.sort(key=lambda l:float(l.get('share',0))*float(p.get('population',0)),reverse=True)
        codes=list(meta) if mode=='all' else ['en']+list(dict.fromkeys(l['code'] for l in candidates))
        gaps=[l.get('label',l['code']) for l in p.get('languages',[]) if float(l.get('share',0))>0 and (l['code'] not in meta or any(t in l.get('label','').lower() for t in ['other','unspecified','slavic','indo-european']))]
        areas.append({'geoid':geoid,'name':p['name'],'demographics_source':p.get('demographics_source','unknown'),'gaps':gaps,'messages':[{'code':code,'text':catalogue['templates'][code].replace('{area}',p['name']),'reviewed':meta[code]['reviewed'],'rtl':meta[code].get('rtl',False)} for code in codes]})
    return {'mode':mode,'areas':areas,'languages':list(dict.fromkeys(m['code'] for a in areas for m in a['messages'])),'message_count':sum(len(a['messages']) for a in areas),'requires_language_review':any(not m['reviewed'] for a in areas for m in a['messages']),'has_illustrative_data':any(not a['demographics_source'].startswith('ACS') for a in areas),'has_coverage_gaps':any(a['gaps'] for a in areas)}
