import pytest
from fastapi import HTTPException
from konfid.schemas import PrincipalCreate,ResourceClassCreate,GrantCreate,AccessRequest,DelegationCreate,IdentityBindingCreate
from konfid.services import access,directory
from konfid.utils import utcnow
from datetime import timedelta

def setup_reader(db,tenant="t"):
    p=directory.create_principal(db,PrincipalCreate(tenant=tenant,display_name="Alice"))
    access.create_resource_class(db,ResourceClassCreate(tenant=tenant,owner_system="konnaxion",name="HR.BASIC",supported_actions=["employee.read"])); access.create_grant(db,GrantCreate(tenant=tenant,subject_ref=p.id,actions=["employee.read"],resource_classes=["HR.BASIC"],scope={"organization":tenant,"project":"A"}),"svc")
    return p

def test_scope_allows_only_inside_grant(db):
    p=setup_reader(db)
    ok=access.evaluate_access(db,AccessRequest(request_id="req-1",tenant="t",actor=p.id,action="employee.read",resource={"owner":"konnaxion","class":"HR.BASIC"},scope={"organization":"t","project":"A"}))
    bad=access.evaluate_access(db,AccessRequest(request_id="req-2",tenant="t",actor=p.id,action="employee.read",resource={"owner":"konnaxion","class":"HR.BASIC"},scope={"organization":"t","project":"B"}))
    assert ok.decision=="ALLOW"; assert bad.decision=="DENY"

def test_email_does_not_merge_identities(db):
    a=directory.create_principal(db,PrincipalCreate(tenant="t",display_name="A")); b=directory.create_principal(db,PrincipalCreate(tenant="t",display_name="B"))
    directory.add_identity_binding(db,IdentityBindingCreate(tenant="t",principal_id=a.id,provider_type="google",issuer="https://accounts.google.com",subject="sub-a",email_hint="same@example.com"),"svc")
    x=directory.add_identity_binding(db,IdentityBindingCreate(tenant="t",principal_id=b.id,provider_type="google",issuer="https://accounts.google.com",subject="sub-b",email_hint="same@example.com"),"svc")
    assert x.principal_id==b.id
    with pytest.raises(HTTPException): directory.add_identity_binding(db,IdentityBindingCreate(tenant="t",principal_id=b.id,provider_type="google",issuer="https://accounts.google.com",subject="sub-a",email_hint="other@example.com"),"svc")

def test_delegation_cannot_expand_authority(db):
    owner=setup_reader(db); other=directory.create_principal(db,PrincipalCreate(tenant="t",display_name="B"))
    with pytest.raises(HTTPException) as e:
        access.create_delegation(db,DelegationCreate(tenant="t",from_principal=owner.id,to_principal=other.id,actions=["employee.read"],resource_classes=["HR.BASIC"],scope={"organization":"t","project":"B"},valid_until=utcnow()+timedelta(hours=1),reason="coverage"),"svc")
    assert e.value.detail=="DELEGATION_EXCEEDS_AUTHORITY"

def test_same_external_identity_can_be_scoped_per_tenant(db):
    from konfid.schemas import PrincipalCreate, IdentityBindingCreate
    from konfid.services import directory
    p1=directory.create_principal(db,PrincipalCreate(tenant="a",display_name="A"))
    p2=directory.create_principal(db,PrincipalCreate(tenant="b",display_name="B"))
    b1=directory.add_identity_binding(db,IdentityBindingCreate(tenant="a",principal_id=p1.id,provider_type="oidc",issuer="https://accounts.google.com",subject="same-sub"),"svc:test")
    b2=directory.add_identity_binding(db,IdentityBindingCreate(tenant="b",principal_id=p2.id,provider_type="oidc",issuer="https://accounts.google.com",subject="same-sub"),"svc:test")
    assert b1.principal_id != b2.principal_id
    assert directory.resolve_identity(db,"a",b1.issuer,b1.subject)[0].id == p1.id
    assert directory.resolve_identity(db,"b",b2.issuer,b2.subject)[0].id == p2.id

def test_scope_comparison_never_turns_specific_grant_into_broader_authority(db):
    from konfid.utils import scope_contains
    assert scope_contains({"organization":"A"},{"organization":"A","project":"X"}) is True
    assert scope_contains({"organization":"A","project":"X"},{"organization":"A"}) is False
    assert scope_contains({"organization":"A","project":["X","Y"]},{"organization":"A","project":"X"}) is True
    assert scope_contains({"organization":"A","project":"X"},{"organization":"A","project":"Y"}) is False
