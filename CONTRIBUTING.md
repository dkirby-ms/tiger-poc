---
title: Contributing to Tiger POC
description: Set up the pinned HVE Core development workflow and prepare scoped contributions
---

## Project scope

For the working baseline, restart commands and open items, see the
[development handoff](docs/development-status.md).

Start with [the core idea](docs/core-idea.md) and [the MVP design](docs/mvp-design.md).
Follow the canonical [Dark Factory Engineering Standards](docs/engineering-standards.md)
for technology choices, composability, and reusable manifest-driven deployments.
Python is the application language; the standards also select OpenCV/YOLO,
RTSP/ONVIF discovery, Docker packaging, and the target platform families.
The shared [vision container baseline](apps/vision/README.md) packages
the existing RTSP/OpenCV/Ultralytics detector. It runs independently of the
[optional rules brain](apps/brain/README.md) and Android app. HVE Core is development tooling, not the
application runtime. Real camera access and model rights remain explicit gates.

Python applications use `apps/<name>/{src,tests}` with one `pyproject.toml`,
`uv.lock` and Dockerfile at the app root. Use each app's Docker `test` stage for
Ruff and pytest; do not use the HVE tooling build for application validation.
Local Compose files and synthetic cross-service tests live in `deploy/local`.

The [Tiger Camera app](apps/tiger-camera/README.md) is a scoped Kotlin exception
for the Android camera source. It uses a CLI-only Gradle build and remains
separate from both the Python vision runtime and Rover. Its first milestone
provides direct RTSP; ONVIF discovery remains follow-up work.

## Contribution model

Use a GitHub Fork + Pull Request model, including when you have upstream WRITE
access. Prepare one focused change on a contribution branch, follow HVE Core
Research, Plan, Implement, Review, and submit it for review through a pull request.
Use Infrastructure as Code and reusable manifests for future deployments.
Creating a fork, pushing a branch, or deploying requires an explicit request;
the workflow setup does not perform those actions.

## Initialize the workflow

Use Git, PowerShell 7, GitHub Copilot CLI, and a current VS Code with Copilot Chat.
Node.js and npm are needed for the optional Context7 MCP server.
From the repository root:

```powershell
git submodule update --init --recursive
code .
```

HVE Core is pinned at `9bf1a30022ca907e06d93baa00f87cf889ee573b` in
`lib/hve-core`. This is a development-main snapshot with manifest version 3.2.2,
not the older `hve-core-v3.2.2` release. Upstream's documented moving release
branches were not available when this snapshot was selected.

All 246 components declared by that snapshot are installed, including experimental
components: 60 agents, 48 prompts, 60 instructions, and 78 skills.
The official component installer copied them into `.github` and records ownership
and file hashes in `.hve-tracking.json`. The submodule retains the canonical source
for controlled updates. Project copies allow CLI path-specific instructions and
their relative references to work without relying on plugin instruction discovery.

VS Code uses the project copies through `.vscode/settings.json`.
The Marketplace HVE extension is not needed and should not be installed alongside
this copy-based setup: its independently versioned content can duplicate or differ
from the pinned components. Current VS Code versions include Copilot Chat;
do not downgrade the built-in extension to install an older Marketplace version.

## Enable the CLI plugin

The CLI also supports qualified HVE agents through its official plugin manifest.
The following commands change your user profile; run them once after deciding to
enable HVE outside this repository:

```powershell
copilot plugin marketplace add "$((Resolve-Path .\lib\hve-core).Path)"
copilot plugin install hve-core@hve-core
copilot plugin list
```

If an `hve-core` marketplace already exists, inspect it before changing registration.
Do not replace another project's registration automatically.
The local marketplace loads the exact submodule live; it does not copy files into
the profile. Keep this worktree available while the registration points to it.
If you move or remove the worktree, re-register the marketplace at the new path.
This CLI version does not accept a commit SHA as a GitHub marketplace branch.

Restart the CLI after installation, then select:

```text
/agent hve-core:rpi-agent
```

Use `/rpi-research` for a bounded research task. In VS Code, reload the window,
open Copilot Chat, and select **RPI Agent** or **Documentation**.
Project-discovered and plugin-qualified agents may both appear in the CLI;
use the qualified name when you want the pinned upstream plugin.

## Tools and authentication

`.vscode/mcp.json` configures GitHub, Context7, and Microsoft Learn using upstream
templates. Approve server trust and GitHub sign-in in VS Code on first use.
This file does not configure the CLI's user-profile MCP servers.
Use the CLI's `/mcp` interface to inspect those separately.

Azure DevOps, Figma, Jira, and GitLab integrations remain optional and unconfigured:
they require accounts or organization-specific settings not selected for this project.
No credentials are stored in these files and no cloud resources are provisioned.
The pinned plugin declares no hooks; older setup documentation mentioning a
telemetry hook does not apply to this snapshot.

Skill content is installed, but specialized runtimes are provisioned on demand
according to each `SKILL.md`. Python/uv environments, browsers, FFmpeg, model
downloads, Graphviz, and authenticated external services are not prerequisites
for the core RPI workflow. Do not install every skill's development or evaluation
dependencies merely to use its instructions.

## Verify and update

Run the upstream installation and manifest checks without installing HVE's entire
development toolchain:

```powershell
pwsh -File .\lib\hve-core\.github\skills\installer\hve-core-installer\scripts\validate-installation.ps1 -BasePath .\lib\hve-core -Method 6
pwsh -File .\lib\hve-core\scripts\plugins\Sync-PluginManifest.ps1 -RepoRoot .\lib\hve-core -Check
git diff --check
```

Keep `.copilot-tracking` artifacts and local skill environments untracked.
For updates, select and review an upstream commit, update the submodule, and use
the upstream `hve-core-installer` upgrade flow against `.hve-tracking.json`.
Review collisions rather than overwriting customized files. Refresh the VS Code
locations when component folders change. Do not use unattended moving-branch updates.

Managed `.github` copies use LF line endings through `.gitattributes`, so their
installation checksums stay consistent across Windows and Linux checkouts.

HVE Core is rapidly evolving and explicitly not a stable production dependency.
Preserve its [MIT license](lib/hve-core/LICENSE) and
[third-party notices](lib/hve-core/THIRD-PARTY-NOTICES).
Some skills use CC BY-SA 4.0; retain their per-skill attribution and license terms.
The installed set follows upstream's distributable plugin manifest, not every
experimental or non-distributable file in the source tree.

## Porting from Rover

The candidate source is [hve-copilot-rover](https://github.com/lovelacer74/hve-copilot-rover).
Agree on a small module or integration boundary before implementation.
Use it as a source of reusable functionality, not an architecture to clone.
Assess compatible orchestration, provider, configuration, and telemetry logic
before deciding what to reuse. No candidate is confirmed reusable by this guidance.
Replace or adapt existing vision components for Python, OpenCV, YOLO, RTSP, and
ONVIF discovery under the [engineering standards](docs/engineering-standards.md).
Decouple motion, clearance, and person-approach semantics from Tiger's factory
observation/event contracts and telemetry, action, and Fabric analytics outputs.
Do not transfer motor control, personal identity data, or robot-specific runtime
agents. Keep the source repository unchanged, bring relevant tests with approved
ports, and describe each component's reusable manifest contract.
This direction does not select a first module or authorize bulk porting.
