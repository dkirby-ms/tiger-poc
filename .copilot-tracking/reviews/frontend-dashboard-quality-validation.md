<!-- markdownlint-disable-file -->
# Frontend dashboard quality validation

## Executive summary
* Status: Partial
* Severity counts: Critical 0, Major 2, Minor 1
* Primary issue: the preview path cannot be served to a browser from the current filesystem layout.

## Findings
### Major
1. IV-001: The app uses absolute local file paths for stored clips.
2. IV-002: The fallback preview asset is missing and the app masks real service failures behind placeholder data.

### Minor
3. IV-003: No automated dashboard tests cover health or preview contract assumptions.

## Evidence
* [apps/vision-pipeline/local_store/service.py](../apps/vision-pipeline/local_store/service.py)
* [apps/dashboard/src/App.tsx](../apps/dashboard/src/App.tsx)
* [apps/dashboard/vite.config.ts](../apps/dashboard/vite.config.ts)

## Recommendation
Implement a browser-safe clip-serving route and update the fallback behavior to show an explicit “no preview available” state, then add a small contract test suite.
