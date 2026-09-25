# Experiment: does Steam overwrite `localconfig.vdf`?

**Question.** The tool prints Steam launch options for the user to paste rather
than writing them into `localconfig.vdf`. That was justified with a claim that
Steam rewrites the file and a managed write can be lost. Half of that was
inference, not evidence. This experiment replaces it with measurement.

**Answer.** Steam **merges** rather than clobbers, and an edit written while
Steam is closed **survives** a full startup-and-rewrite cycle. But Steam keeps
each app's `LaunchOptions` in memory and **reverts an edit made while it is
running**. So a guarded writer is viable — under a precondition, not
unconditionally.

## Method

Machine: CachyOS, Steam client installed at `~/.local/share/Steam`, one user
(`1110180960`), Steam **not** running at the start.

Target file: `~/.local/share/Steam/userdata/1110180960/config/localconfig.vdf`
(166,352 bytes at baseline, last written 2026-07-29 — two months stale, which is
its own evidence that Steam only writes on events).

1. Backed up the file byte-for-byte and verified the SHA-256 matched.
2. Surgically injected two markers, leaving every other byte untouched:
   - a synthetic app block `"99999999"` containing a never-used key — tests
     whether an unknown app survives a rewrite;
   - a **real** `LaunchOptions` on appid `805550` (Assetto Corsa Competizione),
     because that is the exact key the tool would write:
     `"DLSS5CTL_EXPERIMENT=1 %command%"`.
3. Verified the injection: brace balance 0, indentation matching the file's own
   convention (5 tabs for an app key, 6 for its children, two tabs between key
   and value, no CRLF).
4. Started Steam (`steam -silent`) and polled size, mtime and SHA-256 every 10 s.
5. Ran two contrasting sub-tests (below).
6. Removed the injected lines and re-verified against the backup.

## Result 1 — Steam merges, it does not clobber

Within ~20 s of startup Steam rewrote the file (166,692 → 167,064 bytes), and
**both markers survived**. The differences Steam made were its own state:
friends' names and avatars, `name_pending_review` flags, and a large packed
field. It appended its changes without disturbing the injected keys, and it
preserved the injected indentation exactly.

Steam re-wrote the file a further three times during the session and the markers
survived every one.

## Result 2 — an edit made *while Steam runs* is reverted

This is the important one, and it was found by accident rather than by design.

With Steam running, the value was changed externally from
`DLSS5CTL_EXPERIMENT=1` to `DLSS5CTL_EXPERIMENT=VALUE_B_CHANGED_WHILE_RUNNING`.
A 3-minute poll saw no write. But when the file was next read, the value was back
to `DLSS5CTL_EXPERIMENT=1`, and `VALUE_B` appeared **zero** times in the file.

So Steam had the app's `LaunchOptions` in memory, and a later write event
restored its in-memory copy over the external edit. The entry itself was not
deleted — only the value was rolled back. Conclusion: **Steam is authoritative
over this key while it is running.**

## Result 3 — an edit made while Steam is *closed* survives

The decisive test, run cleanly on its own:

| Step | State |
| --- | --- |
| Steam fully exited (verified: zero `ubuntu12_32/steam` processes) | — |
| Wrote `"DLSS5CTL_EXPERIMENT=WRITTEN_WHILE_STEAM_CLOSED %command%"` | value present |
| Started Steam, polled 50 s | file rewritten at +10 s |
| Final value | **`WRITTEN_WHILE_STEAM_CLOSED` — survived** |

Steam rewrote the whole file (its own churn included) and kept our value,
because on startup it **read** the file rather than overwriting it.

## File format facts (needed for a correct writer)

| Property | Value |
| --- | --- |
| Format | plain-text VDF (not binary) |
| Path | `userdata/<steamid>/config/localconfig.vdf` |
| Nesting | `UserLocalConfigStore` / `Software` / `Valve` / `Steam` / `apps` / `<appid>` / `LaunchOptions` |
| Indentation | tabs only; 5 tabs for an app key, 6 for its children |
| Key/value separator | **two tabs** |
| Line endings | LF, no CRLF; file ends with a newline |
| Path check | the appid block sits under `apps`, verified by tab depth |

## What the tool should do with this

A guarded writer is justified, with these conditions:

1. **Refuse to write while Steam is running.** This is not precaution — it is
   Result 2, measured. Detect it by scanning `/proc/*/cmdline` for
   `ubuntu12_32/steam`, not with `pgrep -f`, whose pattern can match the caller's
   own command line.
2. **Surgical single-key edit.** Locate the `apps` section by brace matching,
   find the appid block, and insert or replace exactly one `LaunchOptions` line
   at the right tab depth. Never regenerate the file: it holds friends, avatars,
   cloud-sync state, EULA records and packed fields that are not ours.
3. **Back up first, validate after.** Copy the file, verify the copy's digest,
   then after writing check brace balance and re-read the key.
4. **Verify after a Steam restart, not just after the write.** Result 2 shows a
   write can look correct and later be reverted.
5. **Tell the user Steam must be restarted** for the change to be adopted.

## Limitations of this experiment

Stated plainly, because the conclusions above are narrower than "writing is safe":

- **Steam Cloud sync was not tested.** Whether a launch-option change round-trips
  through the cloud, or gets reverted from it on a later launch, is unknown. The
  user's `cloud` blocks record `last_sync_state: synchronized` for games, so this
  is a real open question.
- **The GUI path was not exercised.** The change was never made through Steam's
  own Properties dialog, so whether Steam's UI and an external writer agree on
  the value is untested. Automating that would need `xdotool`, which is absent
  (this session is Wayland/niri) and which cannot navigate Steam's CEF UI
  reliably anyway.
- **The game was never launched**, so "Steam accepts the value" was not confirmed
  by observing Proton actually receiving the environment variable. The user's two
  pre-existing `LaunchOptions` entries prove the mechanism works, but not that
  our written value is honoured.
- **One Steam version, one user, one machine.** Behavior is not guaranteed
  stable across client updates.
- The monitoring loop had a gap: the Result 2 reversion was noticed when the file
  was next read, not at the moment it happened, so the exact triggering event is
  unidentified. Which event caused the write is unknown; that it caused a revert
  is certain.


---

# Follow-up: end-to-end verification on Hogwarts Legacy

The experiment above used a synthetic marker to learn Steam's behaviour. This is
the closed loop: the tool's own writer, a real game, and Steam's full lifecycle.

**Setup.** appid `990080` (Hogwarts Legacy), which had **no** `LaunchOptions` key
at all — the case the first experiment did not cover. Steam was closed, the
config was brace-balanced, and the original file was copied aside first.

## Result 4 — a newly inserted key survives the full lifecycle

| Step | Observation |
| --- | --- |
| `nvfku launch-options 990080 --value 'DLSS5CTL_VERIFY=1 %command%'` | wrote one line; `verified: True`; file 2766 → 2767 lines |
| Started Steam, polled 300 s | Steam rewrote the file at +20 s |
| Value after that write | **`DLSS5CTL_VERIFY=1 %command%` — preserved** |
| `steam -shutdown`, waited for exit | **Steam wrote again on exit** |
| Value after exit | **still preserved** |

So a key the tool **added** is treated exactly like one Steam already knew about:
it survives startup, the session, and the exit write. Combined with Result 2, the
rule is about *timing*, not about whether Steam recognizes the key:

- edit while Steam is **closed** → adopted and kept;
- edit while Steam is **running** → reverted to its in-memory copy.

## Result 5 — Steam accepts the written value as its own

The decisive evidence is not that the string survived — it is what Steam did
around it. Having read our `LaunchOptions`, Steam **populated its own metadata**
for that app in the same write:

```
"LastPlayed"    "1776661627"
"Playtime"      "372"
"cloud"
"990080_eula_0" "2"
"autocloud"
"BadgeData"     "020000000806"
"PlaytimeDisconnected" "1"
```

It also refreshed `AppInfoChangeNumber`, the license `Ticket` / `EncryptedTicket`
fields, and a packed field. Steam treated the app as fully configured, which is
what "accepted" looks like from the outside. As a side effect this makes the
verification unambiguous: the file was definitely rewritten after our edit, and
our value is still there.

## Result 6 — formatting is preserved, not normalized

After Steam's rewrite the injected line was still

```
						"LaunchOptions"		"DLSS5CTL_VERIFY=1 %command%"
```

— 6 tabs, two tabs between key and value, LF endings, brace balance 0. Steam
reproduces the indentation it read; it does not reformat our line.

## Cleanup

Removed with `nvfku launch-options 990080 --clear`, which is the same guarded
path in reverse. Verified afterwards:

- the marker appears **0** times;
- brace balance 0, line count back to 2766;
- Steam's own keys for `990080` are all untouched — only the one line we added
  was removed;
- the user's two pre-existing `LaunchOptions` entries are intact.

## What this still does not establish

- **Steam Cloud round-trip.** The game's `cloud` block is present and Steam
  rewrote it, but no second machine or cloud restore was involved. Whether a
  cloud sync can revert a launch-option change on a later launch remains
  untested, and is the main open risk.
- **That Proton actually receives the variable.** The game was not launched, so
  "Steam stores the value" is confirmed but "the game process sees it" is not.
  The user's two pre-existing entries prove the mechanism works, not that our
  written value reaches the process.
- **Steam's own Properties dialog agreeing with the file.** The GUI path was
  never exercised; the value was never read back through Steam's UI.
- One Steam version, one account, one machine.
