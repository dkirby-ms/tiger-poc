---
title: Fabric Security and Recovery Checklist
description: Security controls and evidence required for Tiger POC Fabric projection
ms.date: 2026-09-14
ms.topic: checklist
---

## MVP Gateway Gates

* [ ] TLS 1.2 or later is required, certificate validation is enabled, and no plaintext fallback exists.
* [ ] The endpoint hostname contains no credentials, user information, query parameters, or embedded port.
* [ ] Entra workload identity is used where available; SAS is scoped to send-only and loaded from a secret store for local development.
* [ ] Workspace access follows least privilege and Contributor access is limited to implementation owners.
* [ ] Private networking is used where supported, or the approved public path and compensating controls are documented.
* [ ] Raw video remains at the edge; only derived process events enter Fabric.
* [ ] Eventstream at-least-once delivery is mitigated by `eventId` deduplication and station sequence checks.
* [ ] Preview-service risk, unsupported production SLA, supported region, and capacity constraints are accepted in writing.
* [ ] Exported definitions are inspected for credentials and tenant identifiers before version control.
* [ ] Generated digital twin builder base tables are read-only to operators and applications.

## Production Evolution Gates

These controls are not claims of the MVP gateway and require separate production
design and evidence.

* [ ] Leaf devices use X.509 identities with enrollment, renewal, revocation, and a managed certificate lifecycle.
* [ ] AIO-to-cloud and gateway-to-Event Hubs connections use managed identity.
* [ ] Event Hubs or IoT Hub uses a dedicated Fabric consumer group.
* [ ] Identity provisioning, rotation, emergency revocation, and access review are automated.
* [ ] Private endpoints, DNS, firewall paths, and approved fallback controls have connectivity evidence.
* [ ] Outbox capacity, retention, disk monitoring, retry alerts, expiry, overflow policy, and recovery point objective are approved.
* [ ] Lakehouse, digital twin definition, and mapping backups have named owners, retention, and restore evidence.
* [ ] A rollback exercise restores the prior exported twin definition and mappings without editing generated tables.
* [ ] Recovery time and recovery point objectives are measured for edge replay and cloud restoration.
* [ ] Publisher-to-Eventhouse and Lakehouse-to-twin latency objectives are measured and approved separately.
* [ ] Region, scale, support, identity automation, recovery, and SLA requirements are met before twins become authoritative.
* [ ] Azure Digital Twins source-of-truth transition is planned before enabling live graph mutation or command workflows.

See [Production Evolution](../docs/production-evolution.md) for component selection,
source-of-truth ownership, and reversal triggers.

## Evidence Record

| Control area | Owner | Evidence location | Last verified | Result |
|--------------|-------|-------------------|---------------|--------|
| Managed identity and least privilege | Unassigned | Not recorded | Not verified | Blocked |
| Dedicated consumer groups | Unassigned | Not recorded | Not verified | Blocked |
| X.509 lifecycle | Unassigned | Not recorded | Not verified | Blocked |
| TLS and private network path | Unassigned | Not recorded | Not verified | Blocked |
| Queue capacity and monitoring | Unassigned | Not recorded | Not verified | Blocked |
| Backup, restore, RPO, and RTO | Unassigned | Not recorded | Not verified | Blocked |
| Preview limitations and SLA approval | Unassigned | Not recorded | Not verified | Blocked |