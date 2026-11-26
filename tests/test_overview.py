import pytest
from mybox_diag import overview

@pytest.mark.parametrize('state,level',[('passed','good'),('failed','bad'),('warning','attention'),('needs_action','attention'),('not_tested','neutral'),('running','attention')])
def test_module_health_never_hides_incomplete_or_failed_checks(state,level):
    tests={'sd.read':{'applicable':True},'sd.write':{'applicable':True}}
    result={'sd.read':{'state':'passed'},'sd.write':{'state':state}}
    assert overview.module_health(tests,result,True,True)[0]==level
    assert overview.module_health(tests,result,False,True)[0]=='neutral'
    if state=='passed':
        assert overview.module_health(tests,result,True,False)[0]!='good'
        assert overview.module_health(tests,result,True,True,fresh=False)[0]!='good'

def test_sd_has_its_own_read_write_block_and_every_catalog_test_has_a_block():
    import json
    from pathlib import Path
    catalog=json.loads((Path(__file__).parents[1]/'pc/mybox_diag/test_catalog.json').read_text())
    modules={key for key,_,_ in overview.MODULES}
    assert len(modules)==6
    for test in catalog:assert overview.module_for(test['test']) in modules
    assert overview.module_for('sd.read')==overview.module_for('sd.write')=='sd'
    assert overview.module_for('flash.read')=='flash'

def test_module_selection_does_not_move_grid_or_board(tmp_path):
    from types import SimpleNamespace as NS
    from PySide6.QtWidgets import QApplication,QTabWidget,QPushButton
    from mybox_diag.app import Window
    from mybox_diag.simulator import DemoPeer
    app=QApplication.instance() or QApplication([])
    window=Window(NS(output=str(tmp_path),demo=False,smoke_demo=False));window.show();window._new_session(True);window.on_status('ДЕМОНСТРАЦИЯ')
    try:
        peer=DemoPeer();window.on_frames(peer.request({'id':1,'op':'info'})+peer.request({'id':2,'op':'list'}));window.on_frames(peer.poll());window.refresh_view();app.processEvents()
        assert not window.findChildren(QTabWidget) and window.view.isVisible()
        for size in ((1320,860),(1040,680)):
            window.resize(*size);app.processEvents();board=window.view.geometry();positions={key:card.geometry() for key,card in window.cards.items()};details=window.details_stack.geometry()
            for key,card in window.cards.items():
                card.header.click();app.processEvents()
                assert window.details_title.text()==next(title for module,title,_ in overview.MODULES if module==key)
                assert window.view.geometry()==board and window.details_stack.geometry()==details
                assert {key:card.geometry() for key,card in window.cards.items()}==positions
        assert 'sd.write' in window.module_details['sd'].rows
        assert not any('Подтверд' in b.text() or 'вручную' in b.text() for b in window.findChildren(QPushButton))
    finally:window.close();app.processEvents()
