from konfid.schemas import SecurityEventIn
from konfid.services import overwatch

def test_sensitive_read_burst_emits_signal(db):
    _,s=overwatch.record_event(db,SecurityEventIn(tenant="t",subject_ref="P1",event_type="access",action="employee.read",resource_class="HR.EMPLOYEE.MEDICAL",count=399),"svc")
    assert not s
    _,s=overwatch.record_event(db,SecurityEventIn(tenant="t",subject_ref="P1",event_type="access",action="employee.read",resource_class="HR.EMPLOYEE.MEDICAL",count=1),"svc")
    assert len(s)==1 and s[0].severity=="critical"

def test_false_positive_feedback_does_not_mutate_detector_or_policy(db):
    from konfid.models import DetectorDefinition
    from konfid.schemas import DetectionFeedbackIn, DetectorDefinitionCreate, RiskSignalIn
    from konfid.services import detectors, directory
    from konfid.schemas import PrincipalCreate
    det=detectors.create_detector(db,DetectorDefinitionCreate(tenant="t",detector_id="bulk-sensitive-read",version="17",input_schema="konfid.security.event/v1",owner="security",state="SHADOW",package_digest="sha256:0123456789abcdef"))
    sig=overwatch.create_signal(db,RiskSignalIn(tenant="t",subject_ref="P1",severity="high",detector_id=det.detector_id,detector_version=det.version,reason_codes=["TEST"]))
    analyst=directory.create_principal(db,PrincipalCreate(tenant="t",display_name="Analyst"))
    feedback=overwatch.add_feedback(db,sig.id,DetectionFeedbackIn(tenant="t",analyst_principal=analyst.id,classification="FALSE_POSITIVE",justification="approved maintenance window"))
    assert feedback.classification=="FALSE_POSITIVE"
    assert db.get(DetectorDefinition,det.id).state=="SHADOW"
