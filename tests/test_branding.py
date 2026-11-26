from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def test_brand_name_in_current_sources():
    obsolete='may'+'box'
    paths=[ROOT/'README.ru.md',ROOT/'tools/package_site.py',ROOT/'pc/run.py']
    for folder in ['firmware','pc/mybox_diag','docs']:
        paths.extend(p for p in (ROOT/folder).rglob('*') if p.is_file() and p.suffix in ('.py','.cpp','.h','.md','.json'))
    for p in paths:assert obsolete not in p.read_text(encoding='utf-8').lower(),str(p)
    assert 'MYBOX · диагностика' in (ROOT/'pc/mybox_diag/app.py').read_text()
    assert (ROOT/'firmware/MyboxDiag.cpp').exists()
