import os
os.environ.setdefault("KONFID_DATABASE_URL", "sqlite:////tmp/konfid-pytest.db")
os.environ["KONFID_DEV_MODE"]="true"
os.environ["KONFID_POLICY_MODE"]="local"
import pytest
from konfid.db import Base,engine,SessionLocal
from konfid import models  # noqa
@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    yield
@pytest.fixture
def db():
    with SessionLocal() as s: yield s
