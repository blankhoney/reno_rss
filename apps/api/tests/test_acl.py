from uuid import uuid4

from app.domain.acl import ProjectGrant, ProjectRole, authorize, can_edit, can_manage, can_read, highest_role


def test_acl_owner_can_manage_editor_can_edit_viewer_read_only():
    owner = uuid4()
    editor = uuid4()
    viewer = uuid4()
    other = uuid4()
    grants = [
        ProjectGrant(project_id="p1", user_id=owner, role=ProjectRole.OWNER),
        ProjectGrant(project_id="p1", user_id=editor, role=ProjectRole.EDITOR),
        ProjectGrant(project_id="p1", user_id=viewer, role=ProjectRole.VIEWER),
    ]
    assert can_manage(highest_role(grants, user_id=owner, project_id="p1"))
    assert can_edit(highest_role(grants, user_id=editor, project_id="p1"))
    assert can_read(highest_role(grants, user_id=viewer, project_id="p1"))
    assert not can_edit(highest_role(grants, user_id=viewer, project_id="p1"))
    assert highest_role(grants, user_id=other, project_id="p1") is None
    assert authorize(grants, user_id=editor, project_id="p1", need=ProjectRole.VIEWER)
    assert not authorize(grants, user_id=viewer, project_id="p1", need=ProjectRole.EDITOR)
