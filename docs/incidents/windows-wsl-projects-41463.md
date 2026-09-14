# Windows + WSL Project incident evidence — openai/codex#41463

## Purpose

This record preserves public evidence from
[`openai/codex#41463`](https://github.com/openai/codex/issues/41463), **[Windows
+ WSL] Cannot create projects – AbsolutePathBuf deserialized without a base
path**. It refines future mock and read-only boundaries without adding behavior
or authorization.

## Scope and evidence policy

The evidence comprises public community reports and a public maintainer
acknowledgement. Reports are evidence, not protocol specifications or universal
product guarantees. The pinned public-source [protocol
research](../protocol/app-server-projects.md) remains authoritative for
protocol-contract claims. Static Desktop inspection and internal-state reports
are version-sensitive, unsupported implementation details.

This record distinguishes upstream public-source protocol facts, direct
community protocol reproduction, Desktop behavior observation, static Desktop
inspection, workaround validation, state synchronization evidence, maintainer
acknowledgement, repository inference, and unresolved hypothesis. Upstream
facts come from the protocol research, not inference from this incident.

## Incident summary

Reports across several Windows Desktop and bundled WSL app-server versions
describe Project initialization, migration, assignment synchronization, and
interactive operations failing with `AbsolutePathBuf deserialized without a
base path`. Direct same-server A/B reports show Linux/WSL Project methods
rejecting Windows drive or UNC roots and accepting corresponding POSIX roots.
Other reports show that fixing migration or persisting an app-server Project
does not alone guarantee Desktop creation or sidebar visibility.

The incident cannot safely be reduced to “Desktop sends UNC and Linux needs
POSIX.” E14 reports a native POSIX UI presentation while create and remove still
fail. A deeper lifecycle or synchronization fault may remain, but that is a
`HYPOTHESIS`, not an established root cause.

## Evidence classification

Controlled evidence classes are `MAINTAINER_ACKNOWLEDGEMENT`,
`DIRECT_PROTOCOL_EVIDENCE`, `DESKTOP_BEHAVIOR_REPRODUCTION`,
`DESKTOP_ACCEPTANCE_EVIDENCE`, `STATIC_DESKTOP_INSPECTION`,
`WORKAROUND_VALIDATION`, `STATE_SYNCHRONIZATION_EVIDENCE`,
`REGRESSION_BOUNDARY_EVIDENCE`, `CURRENT_REGRESSION_STATUS`, and `HYPOTHESIS`.
Independent strength labels are `CONFIRMED_BY_DIRECT_PROTOCOL_REPRODUCTION`,
`OBSERVED_IN_DESKTOP`, `STATIC_INSPECTION_SUPPORTS`,
`WORKAROUND_VALIDATED_ON_REPORTED_INSTALLATION`, `MAINTAINER_ACKNOWLEDGED`, and
`NOT_ESTABLISHED`. Strength applies only to the reported environment and test.

## Evidence matrix

Each row includes the test, result, classification, strength, bounds, repository
relevance, and exact public source.

| ID | UTC date; GitHub user | Environment / version | Test or observation; result | Class; strength | Establishes / does **not** establish | Repository relevance | Exact public source |
|---|---|---|---|---|---|---|---|
| E1 | 2026-09-01; `QuentinAd` | Codex for Windows `26.825.6671.0`; Windows + WSL; mixed Windows/WSL UNC roots | Startup migration records the path error; create and edit/save then fail; legacy state remains usable; reported inspection says both wait on `ensureProjectsReady()` / `initializeProjects()`. **Result:** migration and later writes fail. | `DESKTOP_BEHAVIOR_REPRODUCTION`, `STATIC_DESKTOP_INSPECTION`; `OBSERVED_IN_DESKTOP`, `STATIC_INSPECTION_SUPPORTS` | Initialization/migration failure can block later writes on this build / not exact cause or universal lifecycle behavior | Keep mock lifecycle failures separable from list/CRUD | [5487494886](https://github.com/openai/codex/issues/41463#issuecomment-5487494886) |
| E2 | 2026-09-01; `forallthis` | Desktop `26.825.6671.0`; Windows 11; WSL2 Ubuntu 24.04 | Repaired migration; UI create still failed; direct same-server `project/create` with `/home/<user>/code/<repo>` succeeded and emitted `project/changed`; compatible Desktop state plus restart made it listed. **Result:** RPC success and listing required distinct steps. | `DIRECT_PROTOCOL_EVIDENCE`, `STATE_SYNCHRONIZATION_EVIDENCE`; `CONFIRMED_BY_DIRECT_PROTOCOL_REPRODUCTION` on the reported environment | WSL RPC can accept a native root, and RPC success differs from visibility / not universal behavior, supported state editing, or notification-to-visibility guarantee | Separate protocol, persistence, and recognition outcomes | [5487791543](https://github.com/openai/codex/issues/41463#issuecomment-5487791543) |
| E3 | 2026-09-01; `pisceskkk` | Windows + WSL installation; version unstated | Disabled WSL backend, restarted, created with Windows backend, re-enabled WSL, restarted. **Result:** Project remained available under WSL. | `WORKAROUND_VALIDATION`; `WORKAROUND_VALIDATED_ON_REPORTED_INSTALLATION` | Persisted validity and WSL-active creation can be separate surfaces / not a safe universal workaround, cause, or configuration-change permission | Distinguish creation, loading, and backend selection | [5491764227](https://github.com/openai/codex/issues/41463#issuecomment-5491764227) |
| E4 | 2026-09-01; `karthik0899` | Windows 11 + WSL2 Ubuntu; app-server `0.150.0-alpha.8`, `0.150.0-alpha.12.2`, `0.151.0-alpha.7.2`; Desktop `26.825.6671.0` | No matching failure at alpha.8; began at alpha.12.2 and remained at alpha.7.2; mixed `C:\...`, `\\wsl.localhost\<distro>\...`, `\\wsl$\<distro>\...`; Windows-path create also failed after migration failure. **Result:** reported boundary and blocking migration. | `REGRESSION_BOUNDARY_EVIDENCE`, `STATIC_DESKTOP_INSPECTION`; `OBSERVED_IN_DESKTOP`, `STATIC_INSPECTION_SUPPORTS` | A reported version interval and mixed-root surface / not exact introducing commit or source bisect | Record version/context in future tests | [5493861396](https://github.com/openai/codex/issues/41463#issuecomment-5493861396) |
| E5 | 2026-09-02; `yykina` | Desktop `26.831.2377.0`; WSL app-server/CLI `0.152.1`; Windows 11; WSL2 Ubuntu 22.04 | Same-server A/B: `D:\Documents\Note\CSAPP` and `\\wsl.localhost\Ubuntu22.04\home\<user>\my_first_cpu` returned `-32600`; `/mnt/d/Documents/Note/CSAPP` and `/home/<user>/my_first_cpu` succeeded. **Result:** representation changed outcome. | `DIRECT_PROTOCOL_EVIDENCE`; `CONFIRMED_BY_DIRECT_PROTOCOL_REPRODUCTION` | On that server/version, native roots succeed where corresponding Windows/UNC forms fail / not every version/distro or every Desktop failure's cause | Preserve representation; test target interpretation separately | [5510241608](https://github.com/openai/codex/issues/41463#issuecomment-5510241608) |
| E6 | 2026-09-02; `etraut-openai` | Public issue; no build-specific validation | Maintainer said the team understood the problem and was working toward a fix, hopefully in the next app release. **Result:** issue acknowledged. | `MAINTAINER_ACKNOWLEDGEMENT`; `MAINTAINER_ACKNOWLEDGED` | OpenAI maintainer acknowledgement / not cause, contract, community-theory validation, fix content, or release compatibility | Keep technical claims evidence-scoped | [5513682952](https://github.com/openai/codex/issues/41463#issuecomment-5513682952) |
| E7 | 2026-09-02; `hatemzeineV` | Desktop `26.901.1978.0`; WSL app-server/CLI `0.153.0-alpha.5`; Ubuntu 24.04 | Migration succeeded; same-server create with `E:\Development\...` failed and `/mnt/e/Development/...` succeeded; reported packaged-code inspection. **Result:** create stayed broken independently of migration. | `DIRECT_PROTOCOL_EVIDENCE`, `STATIC_DESKTOP_INSPECTION`; `CONFIRMED_BY_DIRECT_PROTOCOL_REPRODUCTION`, `STATIC_INSPECTION_SUPPORTS` | Migration recovery need not repair create, and representation matters on that build / not universal internals or complete cause | Model migration and create independently | [5517500630](https://github.com/openai/codex/issues/41463#issuecomment-5517500630) |
| E8 | 2026-09-04; `Hugo-Polloli` | Desktop `26.901.4073.0`; Linux app-server `0.153.1` | Fixture: import with UNC failed; POSIX succeeded; same idempotency key returned same Project ID; update with POSIX and create with empty roots succeeded. **Result:** multiple method outcomes reproduced. | `DIRECT_PROTOCOL_EVIDENCE`; `CONFIRMED_BY_DIRECT_PROTOCOL_REPRODUCTION` on the reported environment | Evidence beyond create, including import replay and update / not Desktop recovery, cross-version stability, or mutation authorization | Future fake-semantics evidence only | [5546825662](https://github.com/openai/codex/issues/41463#issuecomment-5546825662) |
| E9 | 2026-09-05; `poroburu` | Desktop `26.901.5003.0`, then `26.901.5280.0`; WSL app-server `0.153.x`; Windows 11 + WSL2 Ubuntu | Compared legacy/Electron state and WSL app-server SQLite state; app-server row/project count alone did not populate sidebar. **Result:** persistence and visibility diverged. | `STATE_SYNCHRONIZATION_EVIDENCE`; `OBSERVED_IN_DESKTOP` | “Exists in app-server” is not “visible in Desktop” there / not stable internals or supported repair | Do not equate fake store with sidebar | [5548670696](https://github.com/openai/codex/issues/41463#issuecomment-5548670696), [5553582348](https://github.com/openai/codex/issues/41463#issuecomment-5553582348) |
| E10 | 2026-09-08; `Martin11180` | Desktop `26.901.6511.0`; backend `0.153.4`; Ubuntu 24.04 | Adapter reportedly rewrote only `params.roots[].path` for create/update/import: same-distro UNC and drives to WSL-native, POSIX unchanged. **Result:** create/edit/save restored. | `WORKAROUND_VALIDATION`; `WORKAROUND_VALIDATED_ON_REPORTED_INSTALLATION` | Target-aware adaptation is a plausible direction / not universal support, import integration success, or authorization to adopt/execute wrapper | Any adapter needs separate name, review, tests | [5585627798](https://github.com/openai/codex/issues/41463#issuecomment-5585627798), [5591089645](https://github.com/openai/codex/issues/41463#issuecomment-5591089645) |
| E11 | 2026-09-10; `tdeckers` | Desktop `26.901.6511.0`; WSL backend `0.153.4`; Ubuntu 24.04 | Boundary translation; migration completed for 13 Projects without path error; UI create succeeded; normal launch repeated clean migration. **Result:** Desktop flow recovered. | `WORKAROUND_VALIDATION`, `DESKTOP_ACCEPTANCE_EVIDENCE`; `WORKAROUND_VALIDATED_ON_REPORTED_INSTALLATION` | Strong selected real-flow recovery evidence / not universal compatibility, support, or complete cause | Measure protocol and Desktop acceptance | [5614993259](https://github.com/openai/codex/issues/41463#issuecomment-5614993259) |
| E12 | 2026-09-11; `vindipe` | Desktop `26.903.9818.0`; Windows + WSL | A Project only in WSL `state_5.sqlite` was invisible; reported visibility required legacy entry, order, app-server Project, matching idempotency key, and legacy-ID/UUID bridge. **Result:** layers had to align. | `STATE_SYNCHRONIZATION_EVIDENCE`; `OBSERVED_IN_DESKTOP` | Independently reinforces persistence/UI separation / not stable internals, supported contract, or permission to edit state | Equivalence checks cannot stop at persistence | [5637139247](https://github.com/openai/codex/issues/41463#issuecomment-5637139247), [5637188930](https://github.com/openai/codex/issues/41463#issuecomment-5637188930) |
| E13 | 2026-09-13; `ewbing` | Desktop Appx `26.908.4834.0`; WSL app-server `0.154.0-alpha.6.2`; Windows 11; WSL2 Ubuntu | WSL backend started; Desktop reported assignment-sync path error; no WSL Project record; Windows-native Project had succeeded. **Result:** regression remained with changed terminology. | `CURRENT_REGRESSION_STATUS`; `OBSERVED_IN_DESKTOP` | Persistence into newer builds and migration-to-assignment-sync wording shift / not one unchanged cause, universal status, or contract | Record exact version and lifecycle context | [5656905834](https://github.com/openai/codex/issues/41463#issuecomment-5656905834) |
| E14 | 2026-09-14; `void123-dev` | Latest reported Desktop UI; Windows + WSL; exact version unstated | WSL-selected UI displayed `/home/<user>/...` rather than UNC; create and remove still failed. **Result:** native-looking UI path did not restore management. | `CURRENT_REGRESSION_STATUS`; `OBSERVED_IN_DESKTOP` | UI/path presentation can change while deeper failure remains / not what was sent on wire, exact layer, or one universal cause | Do not reduce incident to UNC-to-POSIX alone | [5661726819](https://github.com/openai/codex/issues/41463#issuecomment-5661726819) |

## Strong conclusions

These are scoped evidence conclusions, not official OpenAI guarantees:

1. Linux/WSL app-server operations reportedly succeed with backend-native POSIX
   roots (E2, E5, E7, E8, E11).
2. Same-target A/B reports show Windows/UNC failure and corresponding POSIX
   success (E5, E7, E8, E11).
3. Direct reports cover `project/create`, `project/import`, `project/update`,
   and idempotent import retry (E2, E5, E7, E8, E11).
4. Initialization/migration failure can block Desktop writes (E1, E4, E11),
   while successful migration does not guarantee create (E2, E7).
5. App-server persistence and Desktop sidebar visibility are not equivalent
   (E2, E9, E12).
6. The regression persisted across multiple versions (E1, E4, E5, E7, E8,
   E10–E14).

## Supported but not universal

Target-aware translation at the Windows-to-WSL app-server boundary restored
behavior in multiple reported installations (E10, E11) and aligns with A/B
evidence (E5, E7, E8). This supports a future architectural direction. It does
**not** establish universal compatibility, complete current root cause,
permission to implement mutation, or permission to modify Desktop state or
SQLite.

## What remains unestablished

All remain `NOT_ESTABLISHED`:

- exact behavior of the user's installed Desktop at future test time;
- Desktop Project-store equivalence;
- exact Desktop-owned endpoint/process appropriate for future integration;
- whether a separately launched app-server shares Desktop state;
- whether a future client-created Project automatically appears in Desktop;
- complete path semantics for every WSL distro/custom mount;
- whether all current Project failures share one root cause;
- whether newest UI changes fixed one path layer but expose another lifecycle or
  synchronization bug;
- whether `project/list` proves sidebar equivalence;
- whether `project/changed` guarantees Desktop visibility;
- exact introducing commit for the reported alpha boundary;
- whether maintainer acknowledgement confirms community root-cause analysis;
- whether path translation alone is universally sufficient;
- whether static Desktop inspection remains valid for later builds;
- cross-version stability of empty-root creation, import idempotency, and update.

## Three independent success questions

Every future experiment must report independently:

1. **Did the RPC succeed?**
2. **Does `project/list` return/persist the Project?**
3. **Does Codex Desktop show or recognize the Project?**

A response, notification, or persisted record does not answer all three. This
distinction governs future PR8 and separately authorized mutation acceptance.

## Path-representation findings

Schema acceptance and backend interpretation are separate. Current
`ProjectRoot` modeling preserves representations and does not translate them.
Direct A/B evidence shows representation matters at reported Linux backends
(E5, E7, E8, E11); pinned research defines the schema boundary.

Translation **must not** be silently inserted into `ProjectRoot.from_wire()` or
generic schema decoding. Any future adapter must be separately named,
target-aware, reviewed, and tested. This delivery changes no schemas.

```text
C:\Users\<user>\...
\\wsl$\<distro>\home\<user>\...
\\wsl.localhost\<distro>\home\<user>\...
/home/<user>/...
/mnt/<drive>/...
```

## Project-store / Desktop-state findings

Only this high-level, version-sensitive picture is supported:

```text
Desktop / legacy presentation state
              ↕ synchronization / mapping
       app-server Project store
```

Underlying reported structures are observed/reported implementation details,
version-sensitive, and unsupported internal state—not stable product contract.
Direct internal-state and SQLite-editing workarounds are outside the approved
approach of this repository. This record neither prescribes nor authorizes them.

## Version/regression timeline

- **2026-09-01:** E4 places a boundary after `0.150.0-alpha.8` and by
  `0.150.0-alpha.12.2`, still at `0.151.0-alpha.7.2`; not a source bisect.
- **2026-09-02–10:** E5, E7, E8, E10, E11 span `0.152.1` through `0.153.4`.
- **2026-09-11–14:** E12–E14 report synchronization distinctions and continued
  failures; E13 covers `0.154.0-alpha.6.2`, and E14 a changed UI without recovery.

This is a report timeline, not a compatibility matrix.

## Implications for this repository

This record supports `RPC-001` and `RPC-002` by separating evidence from the
public-source contract and retaining mock-first boundaries. It does not
exercise `RPC-003`. It reinforces `SAFE-001`, `SAFE-004`, `PATH-001`,
`SECRET-001`, `SECRET-002`, `TEST-003`, `MUT-001`, `MUT-002`, `MUT-003`, and
the still-unsatisfied `GATE-001`. It adds no capability or gate advancement.

## Future PR7 criteria

Future Delivery 3 remains `MOCK_ONLY` and separately human-approved. Keep
independent: wire/schema validation; connection initialization;
`experimentalApi` negotiation; fake Project storage; `project/list` dispatch;
lifecycle errors; handler errors; and Desktop visibility assumptions.

It must not silently rewrite paths during decoding, equate a fake store with the
Desktop sidebar, invoke a real app-server, or access real state. This evidence
refines responsibility boundaries without expanding authorization.

## Future PR8 criteria

Future PR8 is the real read-only `project/list` checkpoint. Ask separately:

- Did initialize succeed?
- Was `experimentalApi` requested/accepted?
- Is `project/list` registered?
- What `codexHome`, `platformFamily`, and `platformOs` were returned?
- Did `project/list` succeed, and what roots were returned?
- Do returned Projects correspond to known Desktop Projects?
- If not, could store/process/synchronization divergence explain it?
- Are returned Projects visible in Desktop?

PR8 remains `READ_ONLY`; do not create, import, update, delete, or move merely
to prove equivalence.

## Mutation-stage implications

Separately approved mutation work must measure: **A.** RPC success; **B.** later
`project/list` persistence; **C.** Desktop recognition. Authorization is exact
method-specific: `project/create` authorization does not authorize
`project/update`, `project/import`, `project/delete`, or `project/move`. Path
adaptation needs separate review. Delete and move remain outside the roadmap.

## Safety and non-goals

This delivery performs no app-server launch; real RPC; Project create, import,
update, delete, or move; `~/.codex` or SQLite access; Desktop bundle inspection;
Desktop configuration change; process wrapper; `CODEX_CLI_PATH` override;
state/database/registry repair; community script or ZIP execution; path rewrite;
or credential/secret access. Reported approaches are summarized only.

Capability remains `NON_FUNCTIONAL`, mutation authorization remains `NONE`, and
`GATE-001` remains unsatisfied. Direct internal-state and SQLite-editing
workarounds are outside the approved approach of this repository.

## Source ledger

Each public permalink was checked on 2026-09-14 for username, UTC date, stated
environment/version, and paraphrased result.

| Evidence | Public source(s) |
|---|---|
| E1 | [`QuentinAd`, 5487494886](https://github.com/openai/codex/issues/41463#issuecomment-5487494886) |
| E2 | [`forallthis`, 5487791543](https://github.com/openai/codex/issues/41463#issuecomment-5487791543) |
| E3 | [`pisceskkk`, 5491764227](https://github.com/openai/codex/issues/41463#issuecomment-5491764227) |
| E4 | [`karthik0899`, 5493861396](https://github.com/openai/codex/issues/41463#issuecomment-5493861396) |
| E5 | [`yykina`, 5510241608](https://github.com/openai/codex/issues/41463#issuecomment-5510241608) |
| E6 | [`etraut-openai`, 5513682952](https://github.com/openai/codex/issues/41463#issuecomment-5513682952) |
| E7 | [`hatemzeineV`, 5517500630](https://github.com/openai/codex/issues/41463#issuecomment-5517500630) |
| E8 | [`Hugo-Polloli`, 5546825662](https://github.com/openai/codex/issues/41463#issuecomment-5546825662) |
| E9 | [`poroburu`, 5548670696](https://github.com/openai/codex/issues/41463#issuecomment-5548670696), [5553582348](https://github.com/openai/codex/issues/41463#issuecomment-5553582348) |
| E10 | [`Martin11180`, 5585627798](https://github.com/openai/codex/issues/41463#issuecomment-5585627798), [5591089645](https://github.com/openai/codex/issues/41463#issuecomment-5591089645) |
| E11 | [`tdeckers`, 5614993259](https://github.com/openai/codex/issues/41463#issuecomment-5614993259) |
| E12 | [`vindipe`, 5637139247](https://github.com/openai/codex/issues/41463#issuecomment-5637139247), [5637188930](https://github.com/openai/codex/issues/41463#issuecomment-5637188930) |
| E13 | [`ewbing`, 5656905834](https://github.com/openai/codex/issues/41463#issuecomment-5656905834) |
| E14 | [`void123-dev`, 5661726819](https://github.com/openai/codex/issues/41463#issuecomment-5661726819) |
