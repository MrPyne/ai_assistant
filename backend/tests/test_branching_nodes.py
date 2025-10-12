import pytest

pytest.importorskip('sqlalchemy')
from backend.database import SessionLocal
from backend.models import User, Workspace, Workflow, Run, RunLog
from backend import tasks


def test_if_node_routing():
    db = SessionLocal()
    try:
        user = User(email='b@example.com', hashed_password='x')
        db.add(user)
        db.commit()
        db.refresh(user)
        ws = Workspace(name='w', owner_id=user.id)
        db.add(ws)
        db.commit()
        db.refresh(ws)

        # Workflow with an If node
        graph = {
            'nodes': [
                {
                    'id': 'n_if',
                    'data': {'label': 'If', 'config': {'expression': "{{ input.flag }}", 'true_target': 't1', 'false_target': 'f1'}},
                }
            ]
        }
        wf = Workflow(workspace_id=ws.id, name='wf', graph=graph)
        db.add(wf)
        db.commit()
        db.refresh(wf)

        run = Run(workflow_id=wf.id, status='queued', input_payload={'flag': True})
        db.add(run)
        db.commit()
        db.refresh(run)

        res = tasks.process_run(run.id)
        assert res['status'] == 'success'
        out = res['output']
        assert out is not None
        # Expect routed_to recorded for the if node
        assert out.get('n_if') and out['n_if'].get('routed_to') == 't1'

    finally:
        db.close()


def test_switch_node_routing():
    db = SessionLocal()
    try:
        user = User(email='c@example.com', hashed_password='x')
        db.add(user)
        db.commit()
        db.refresh(user)
        ws = Workspace(name='w2', owner_id=user.id)
        db.add(ws)
        db.commit()
        db.refresh(ws)

        graph = {
            'nodes': [
                {
                    'id': 'n_sw',
                    'data': {'label': 'Switch', 'config': {'expression': "{{ input.key }}", 'mapping': {'a': 'tA', 'b': 'tB'}, 'default': 'tDefault'}},
                }
            ]
        }
        wf = Workflow(workspace_id=ws.id, name='wf2', graph=graph)
        db.add(wf)
        db.commit()
        db.refresh(wf)

        run = Run(workflow_id=wf.id, status='queued', input_payload={'key': 'b'})
        db.add(run)
        db.commit()
        db.refresh(run)

        res = tasks.process_run(run.id)
        assert res['status'] == 'success'
        out = res['output']
        assert out.get('n_sw') and out['n_sw'].get('routed_to') == 'tB'

    finally:
        db.close()
