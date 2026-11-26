from pathlib import Path
import json,re,hashlib
ROOT=Path(__file__).resolve().parents[1]
def test_profiles_match_sources_and_pin_functions_are_unique():
    for p in (ROOT/'profiles').glob('*.json'):
        data=json.loads(p.read_text());src=ROOT.parent/data['source']
        if not src.exists():src=ROOT/'hardware'/data['id']/'hwdef.dat'
        assert hashlib.sha256(src.read_bytes()).hexdigest()==data['hwdef_sha256']
        assert len({v['pin'] for v in data['pins']})==len(data['pins'])
        assert len(data['outputs'])==14 if data['index']==0 else len(data['outputs'])==13
        assert [i['channel'] for i in data['outputs']]==list(range(1,len(data['outputs'])+1))
        assert len(data['imus'])==2 if data['index']==2 else len(data['imus'])==1

def test_existing_site_catalog_code_is_unchanged():
    for file,digest in [('app.js','2f194ab9358994e0524850635bbcb663d3753f01'),('live-catalog.js','a547db20c3da71b608fc9d533b0c4a00c141cb34')]:
        content=(ROOT/'site-source'/file).read_bytes();assert hashlib.sha1(f'blob {len(content)}\0'.encode()+content).hexdigest()==digest
    page=(ROOT/'site-source/index.html').read_text()
    for domid in ['firmware-select','vehicle-select','release-list','release-template','inav-guide','ardupilot-guide']:assert f'id="{domid}"' in page
    assert 'hardware-reference.js' in page and 'diagnostics.html' in page

def test_site_reference_uses_actual_pin_mappings():
    for p in (ROOT/'profiles').glob('*.json'):
        d=json.loads(p.read_text());board=['mini','mini-v2','mini-v2-vib'][d['index']];site=json.loads((ROOT/'site-source/reference'/f'{board}.json').read_text())
        assert site['pins']==d['pins'] and site['outputs']==d['outputs']
