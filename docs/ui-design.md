# UI design spec — applying the apple-design skill

The engine is finished and tested; what remains is the surface. This document is
the design decisions *before* the widgets, so the Dart below is the second half
of a decision rather than a guess.

The skill's framing: **an interface feels alive when motion starts from the
current on-screen value, inherits the user's velocity, projects momentum, and can
be grabbed and reversed at any instant.** For an installer, that translates into
one dominant requirement — the user must never lose the sense that they are
looking at *their* machine, and must be able to watch and reverse anything the
tool does.

## What the app is for (§16 Purpose)

Three jobs, in this order, and nothing else:

1. **Show me my games and what each one supports.** The library.
2. **Tell me exactly what will change before it changes.** The plan.
3. **Let me undo it completely.** The journal.

Anything that does not serve one of those is not built. No settings maze, no
account, no telemetry, no dashboard of statistics.

## The eight principles, made concrete

| Principle | Decision |
| --- | --- |
| **Purpose** | One window, three views: Library → Game → Plan. No navigation chrome beyond a back affordance. |
| **Agency** | Every install shows its plan first, and `--yes` is a *press* in the UI, not a modal to dismiss. Rollback is a first-class button, not a buried menu item. |
| **Responsibility** | Anti-cheat and "not the measured build" warnings appear where the decision is made, not in a log. The model is never downloaded or copied silently. |
| **Familiarity** | A sidebar/tree of games with a detail pane, like every file manager the user already knows. Route rows read like the CLI's own output because that is the vocabulary the docs use. |
| **Flexibility** | Density adapts: the same data as a table on a wide window, as cards when narrow. Nothing breaks if text size grows — all spacing is in logical units tied to `MediaQuery.textScaler`. |
| **Simplicity** | Route viability is stated as a word (`viable` / `blocked`) with the *reason* one level deeper. The common path — pick game, press Install — is one press from the library. |
| **Craft** | Size-specific tracking, no fixed letter-spacing (§15). Status colours that adapt to light/dark. Every action answers within one frame. |
| **Delight** | Not confetti. The delight is that rollback works, that the plan was honest, and that pressing Install gives *immediate* feedback and a live, cancellable journal. |

## Motion decisions (§1–§11)

The skill's rules that actually apply here, and the ones that do not:

- **Response on pointer-down (§1).** Installing is a heavy operation. The button
  must react on `onTapDown`, not `onTap`. A press that waits for the process to
  start feels broken.
- **Feedback is continuous during the interaction (§1).** The install is
  journalled step by step. Each step appears as it completes — never all at once
  at the end. This is the file-operation equivalent of 1:1 drag tracking.
- **Interruptibility (§3).** The install is stoppable at a step boundary, and
  stopping offers rollback. Starting from the *current* state rather than
  unwinding blindly is the same principle as animating from the presentation
  value.
- **Springs, not fixed durations (§4).** Route-row expansion and the detail pane
  use a critically damped spring (`damping 1.0`, `response 0.3–0.4` in Apple's
  terms). No bounce: nothing here was flicked.
- **Spatial consistency (§7).** The plan expands *from* the route row that
  produced it, anchored at its origin. Dismissing returns along the same path.
- **Reduced motion (§14).** `prefers-reduced-motion` maps to Flutter's
  `MediaQuery.disableAnimations`. When set, springs become short cross-fades and
  the progress bar stops animating position — it still updates, so
  comprehension is preserved.

Deliberately **not** implemented, because inventing them would be unearned:
momentum projection (§6) and rubber-banding (§9). There is no flingable,
bounded surface in this app. Adding a scroll physics flourish to a list that
does not need it would be decoration, which §16 Purpose argues against.

## Materials and hierarchy (§12)

Flutter has no `backdrop-filter`, so translucency is approximated honestly rather
than faked:

- The status bar (install progress, journal id) is a **tonal surface** with a
  hairline top edge — not a floating glass pane. Where a blur is available
  (`BackdropFilter` over an image), it is used for the game-cover header only.
- **One** translucent layer at a time. The skill warns that stacking light
  translucent surfaces collapses legibility; there is exactly one.
- Depth encodes hierarchy: the detail pane is a raised surface over the library
  background, not a border box.

## Typography (§15)

```dart
// Tracking is size-specific; never one value for all sizes.
static const display = TextStyle(fontSize: 28, height: 1.15, letterSpacing: -0.5, fontWeight: FontWeight.w600);
static const title   = TextStyle(fontSize: 17, height: 1.25, letterSpacing: -0.2, fontWeight: FontWeight.w600);
static const body    = TextStyle(fontSize: 14, height: 1.45, letterSpacing: 0);
static const mono    = TextStyle(fontSize: 12.5, height: 1.5, fontFamily: 'monospace', letterSpacing: 0);
```

Body copy is near `0` tracking; only large text tightens. Layout spacing derives
from `MediaQuery.textScaler` so a larger system font does not clip the rows.

## The four kinds of feedback (§16)

Status, completion, warning, error — mapped onto the engine's own vocabulary so
the UI invents nothing:

| UI state | Engine source |
| --- | --- |
| Status | the current install step, streamed from `install()`'s logger |
| Completion | `InstallResult.verified` |
| Warning | `InstallResult.warnings`, plan `severity == "warning"` |
| Error | `InstallRefused`, plan `severity == "blocker"` |

## Wayfinding (§16)

Every view answers where am I / where can I go / how do I get out:

- Library: title says "N games", the filter is visible, each row says what the
  game is.
- Game: the game name, its directory, and the three routes with a verdict each.
- Plan: the route, the game, READY or BLOCKED, and the exact `rollback` command
  if anything was written.

## Reducing "success" to honesty

The skill's §3 Responsibility principle applied to this tool specifically: it
must not claim success it cannot verify. Concretely, the UI never says "DLSS 5
installed and working" — it says which files were written, which digest was
verified, which build of the model was used, and what remains manual (launching
the game, checking `ReShade.log`). The engine already reports exactly that; the
UI must not round it up.
