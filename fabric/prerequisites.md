---
title: Fabric Live Prerequisites
description: Fail-fast evidence gate for live Tiger POC Fabric configuration
ms.date: 2026-09-14
ms.topic: checklist
---

## Gate Policy

Live Phase 4 work must not start until every row is recorded as passed with an owner
and evidence link. Missing or failed rows also block the live portions of Phases 5
and 6. Offline implementation and tests remain permitted.

Run the non-secret check after setting the declarations in your shell:

```bash
uv run python scripts/check_fabric_prerequisites.py --probe-tls
```

The command reads declarations only. Do not place connection strings, shared access
keys, client secrets, or tokens in these variables.

## Required Evidence

| Requirement | Environment declaration | Owner | Evidence | Status |
|-------------|-------------------------|-------|----------|--------|
| Workspace selected | `FABRIC_WORKSPACE_ID` | Unassigned | Not recorded | Blocked |
| Supported Fabric region confirmed | `FABRIC_REGION` | Unassigned | Not recorded | Blocked |
| Fabric capacity or trial active | `FABRIC_CAPACITY_OR_TRIAL` | Unassigned | Not recorded | Blocked |
| Workspace Contributor access confirmed | `FABRIC_CONTRIBUTOR_ACCESS=true` | Unassigned | Not recorded | Blocked |
| Digital twin builder enabled by tenant admin | `FABRIC_DIGITAL_TWIN_BUILDER_ENABLED=true` | Unassigned | Not recorded | Blocked |
| Capacity compatible with Spark Autoscale Billing constraint | `FABRIC_SPARK_AUTOSCALE_BILLING_COMPATIBLE=true` | Unassigned | Not recorded | Blocked |
| Authentication mode selected (`entra` or `sas`) | `FABRIC_AUTH_MODE` | Unassigned | Not recorded | Blocked |
| Custom endpoint hostname recorded without credentials | `FABRIC_EVENTSTREAM_HOSTNAME` | Unassigned | Not recorded | Blocked |
| Private or approved public network policy recorded | `FABRIC_PRIVATE_NETWORK_POLICY` | Unassigned | Not recorded | Blocked |
| TLS certificate verification required | `FABRIC_TLS_VERIFY=true` | Unassigned | Not recorded | Blocked |
| Preview use and absent production SLA approved | `FABRIC_PREVIEW_APPROVED=true` | Unassigned | Not recorded | Blocked |

## Exit Codes

| Code | Meaning | Required action |
|------|---------|-----------------|
| `0` | Non-secret declarations and optional TLS probe passed | Continue with recorded evidence |
| `2` | A declaration is missing or invalid | Correct configuration before publication |
| `3` | A product, access, or security gate is denied | Stop live work and obtain approval |
| `4` | Certificate-verifying TLS connectivity failed | Correct DNS, firewall, proxy, or certificate trust |

Passing the command does not prove tenant settings or authorization. Attach portal,
identity, network, and approval evidence to this checklist before changing resources.