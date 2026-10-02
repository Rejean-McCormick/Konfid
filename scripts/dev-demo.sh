#!/usr/bin/env bash
set -euo pipefail
BASE=${BASE:-http://localhost:8080}; TENANT=${TENANT:-demo}
TOKEN=${TOKEN:-$(konfid dev-token --subject svc:dev-admin --tenant "$TENANT" --scopes 'konfid:*')}
AUTH=(-H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json')
P=$(curl -sS "${AUTH[@]}" -d "{\"tenant\":\"$TENANT\",\"display_name\":\"Alice\"}" "$BASE/v1/principals")
PID=$(python -c 'import json,sys;print(json.load(sys.stdin)["id"])' <<<"$P")
curl -sS "${AUTH[@]}" -d "{\"tenant\":\"$TENANT\",\"owner_system\":\"konnaxion\",\"name\":\"HR.BASIC\",\"supported_actions\":[\"employee.read\"]}" "$BASE/v1/resources" >/dev/null
curl -sS "${AUTH[@]}" -d "{\"tenant\":\"$TENANT\",\"subject_ref\":\"$PID\",\"actions\":[\"employee.read\"],\"resource_classes\":[\"HR.BASIC\"],\"scope\":{\"organization\":\"$TENANT\"}}" "$BASE/v1/grants" >/dev/null
curl -sS "${AUTH[@]}" -d "{\"request_id\":\"demo-1\",\"tenant\":\"$TENANT\",\"actor\":\"$PID\",\"action\":\"employee.read\",\"resource\":{\"owner\":\"konnaxion\",\"class\":\"HR.BASIC\"},\"scope\":{\"organization\":\"$TENANT\"}}" "$BASE/v1/access/evaluate"; echo
