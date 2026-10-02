.PHONY: install test check run migrate migrate-check token outbox audit worker openapi build clean
install:
	python -m pip install -e '.[test]'
test:
	PYTHONPATH=src pytest
check:
	PYTHONPATH=src python -m compileall -q src tests
	PYTHONPATH=src pytest
run:
	uvicorn konfid.app:app --reload --port 8080
migrate:
	alembic upgrade head
migrate-check:
	rm -f /tmp/konfid-migration-check.db
	KONFID_DATABASE_URL=sqlite:////tmp/konfid-migration-check.db alembic upgrade head
	KONFID_DATABASE_URL=sqlite:////tmp/konfid-migration-check.db alembic downgrade base
	KONFID_DATABASE_URL=sqlite:////tmp/konfid-migration-check.db alembic upgrade head
token:
	konfid dev-token --subject svc:dev-admin --tenant demo --scopes 'konfid:*'
outbox:
	konfid process-outbox
audit:
	konfid export-audit
worker:
	konfid worker --interval 1
openapi:
	PYTHONPATH=src python -c "import json; from konfid.app import app; json.dump(app.openapi(), open('openapi.json','w'), indent=2)"
build:
	python -m build --wheel
clean:
	rm -rf build dist *.egg-info .pytest_cache openapi.json
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
