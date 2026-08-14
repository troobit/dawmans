# Ableton state integration

Research note for the future `StateSource` capability (reading the user's Ableton session so DAWMans
can say things like "track 3's monitor is Off, that's why you hear nothing").

**Target environment**: Ableton Live 12 Standard on macOS, Akai APC Key 25 mk2, Focusrite Scarlett Solo.

Much of this note was verified directly against the machine this repo lives on
(`/Applications/Ableton Live 12 Standard.app`, build **12.4.3 (2026-07-07_e3d8be4d07)**) rather than
from documentation. Those facts are marked **[verified locally]**. Anything I could not establish is
marked **UNVERIFIED** — do not design against those without checking first.

---

## Bottom line for the design

- **Max for Live is out.** It is a Suite feature. This machine's licence is Standard
  (`Licensing: Installed variant: Standard` in Live's own log) **[verified locally]**. The M4L runtime
  binaries ship inside the Standard app bundle, but the devices need a Suite or paid add-on licence.
  Anything designed around a M4L device is designed around a purchase the user has not made.
- **The `.als` file is the safe, zero-install source, and it is genuinely rich.** Gzipped XML; arm,
  monitor, mute, solo, input/output routing, full device chain with per-parameter values and per-device
  on/off are all in there under stable, readable element names **[verified locally]**. Ableton do not
  document it and it does change between versions, so parsing must be defensive and version-aware.
- **`.als` reflects the last *save*, not the live session — and there is no fresher file to fall back on.**
  Live has no autosave. The crash-recovery `BaseFiles/*.als` is a snapshot taken at *load* time, and
  post-load edits live in `Undo/*.band`, an undocumented binary delta log with no XML and no gzip inside
  **[verified locally]**. Design the `StateSource` contract to carry an explicit "as of" timestamp and a
  staleness flag; do not pretend a file snapshot is live.
- **Live's own `Log.txt` is a cheap, unexpected, zero-install second file source.** It records the
  currently-open set's absolute path, the active audio interface (`Scarlett Solo 4th Gen`), the selected
  control surface (`APC_Key_25_mk2`) and the per-port Track/Sync/Remote toggles **[verified locally]**.
  That answers a real class of "why is nothing happening" questions on its own, and it solves *which*
  `.als` to read for the file source. Treat it as a first-class input, not a curiosity.
- **The only realistic live route without M4L is a MIDI Remote Script**, and the pragmatic form of that
  is **AbletonOSC** — a remote script (no M4L) that exposes the Live Object Model over OSC. It is
  actively maintained and MIT-licensed. It requires the user to drop a folder into their User Library and
  tick a dropdown, and it occupies one of Live's seven control-surface slots.
- **Writing our own remote script is possible but expensive.** Live 12 embeds **Python 3.11.6**, ships all
  factory scripts as **`.pyc` only** (no source), and the `ableton.v3.control_surface` framework they are
  built on is **undocumented by Ableton** **[verified locally + corroborated]**. Community decompiles exist
  for Live 12.4. This is a maintenance liability across Live point releases, not a one-off cost.
- **Ableton Link carries tempo, beat, phase and start/stop. Nothing else.** No track state, no notes,
  no routing. It cannot answer any question this feature exists to answer. Rule it out explicitly.
- **The APC Key 25 mk2 is natively supported in Live 12 and its script is a *different* script from the
  mk1's** — different framework, different capabilities **[verified locally]**. The manual in
  `manuals/` is the mk1's (`akai_apc-key-25_user-guide_v1.0_multi.pdf`) and will give wrong answers about
  the user's hardware. Its active mode is **not observable from software** — it is host-side state held in
  Live's script, with no query message in Akai's protocol.

---

## 1. Max for Live availability

### Edition gating

Ableton's edition comparison lists Max for Live under Suite, describing it as something that
"powers a range of instruments and devices in Live **Suite**"
([Compare Live editions](https://www.ableton.com/en/live/compare-editions/)). Ableton also publish a
support article titled *"Activating Max for Live with a Live Standard license"*, which confirms the
add-on path exists for Standard licences
([help.ableton.com](https://help.ableton.com/hc/en-us/articles/360001296900-Activating-Max-for-Live-with-a-Live-Standard-license)
— note this host is behind Cloudflare and could not be fetched programmatically; title and existence
confirmed via search index only).

So the precise statement is: **M4L ships with Suite; Standard users must buy it separately.**

### This machine

Live's own log is unambiguous **[verified locally]**:

```
info: Licensing: [Variant=Standard]
info: Licensing: Installed variant: Standard
info: Licensing: License type: regular
```

Also **[verified locally]**: the Max runtime *is physically present* in the Standard bundle —
`Contents/App-Resources/Max/Max.app`, `Contents/Frameworks/MaxAudioAPI.framework`,
`MaxLua.framework`, and the `MaxForLive` / `_MxDCore` remote scripts. **Do not read the presence of
these files as evidence that M4L works.** The binaries ship in all editions; the licence gates them.

**UNVERIFIED**: the exact failure mode when an unlicensed Standard install loads a `.amxd` device
(silent no-load vs. explicit error). Not worth verifying — the design should not go here.

### Cost, since it changes the calculus

- Max for Live as a standalone add-on has historically been **~USD 299**. Current Ableton shop pricing
  could not be retrieved (`/en/shop/max-for-live/` returns 404; the live shop is JS-rendered).
  **Treat the figure as approximate — UNVERIFIED for 2026.**
- Live Standard → Suite upgrade pricing sits in a similar band, and secondary sources put Standard at
  ~£259 / $349 and Suite at ~£539 / $749
  ([pushpatterns](https://www.pushpatterns.com/blog/how-much-does-ableton-live-cost),
  [audeobox](https://www.audeobox.com/learn/compare/ableton-pricing-guide/) — third-party, not authoritative).

**Design consequence**: M4L is a several-hundred-currency-unit purchase to enable a *nice-to-have*
diagnostic feature in a localhost helper app. It should not be a prerequisite for any `StateSource`
implementation we plan to build. If the user ever upgrades to Suite, a M4L-backed `StateSource` becomes a
*fourth* implementation behind the same seam — that is exactly what the abstraction buys us, and it is a
reason to keep the seam narrow rather than a reason to build for M4L now.

---

## 2. The `.als` file format

### Confirmed shape **[verified locally]**

Gzip-compressed UTF-8 XML. `file(1)` reports `gzip compressed data, max compression`; `gzip -dc` yields
plain XML. A factory demo set decompressed from ~1 MB to ~7.5 MB / 173k lines.

Root element carries the version fingerprint you must branch on:

```xml
<Ableton MajorVersion="5" MinorVersion="12.0_12402" SchemaChangeCount="5"
         Creator="Ableton Live 12.4.3" Revision="e3d8be4d07c71..." />
```

`MinorVersion` and `SchemaChangeCount` differ between sets saved by different 12.x builds
(observed `12.0_12049` / `SchemaChangeCount="13"` from Live 12.0.5 vs `12.0_12402` / `5` from 12.4.3)
**[verified locally]**. Read these before parsing and refuse politely on anything unrecognised.

### Top-level structure **[verified locally]**

```
<Ableton>
  <LiveSet>
    <Tracks>          # GroupTrack | MidiTrack | AudioTrack | ReturnTrack, in display order
    <MainTrack>       # NOTE: named MasterTrack in Live 11 and earlier
    <PreHearTrack>
    <Scenes> <Transport> <Locators> <ScaleInformation> ...
```

`LiveSet` has ~40 direct children; the ones that matter for diagnostics are `Tracks`, `MainTrack`,
`Transport` and `Scenes`.

### Where per-track state actually lives **[verified locally]**

Every track element contains a `<DeviceChain>` with this shape:

```
<MidiTrack Id="28">
  <Name><EffectiveName Value="2-Zoned Kit"/><UserName Value=""/></Name>
  <Color Value="19"/>
  <TrackGroupId Value="36"/>          # -1 when not grouped
  <Freeze Value="false"/>
  <DeviceChain>
    <AudioInputRouting>  <Target/> <UpperDisplayString/> <LowerDisplayString/> </AudioInputRouting>
    <MidiInputRouting>   ... same shape ...
    <AudioOutputRouting> ... same shape ...
    <MidiOutputRouting>  ... same shape ...
    <Mixer>
      <Speaker><Manual Value="true"/></Speaker>     # audible; false == muted
      <SoloSink Value="false"/>                      # solo
      <Volume>, <Pan>, <Sends>, <CrossFadeState>, <PanMode>
    </Mixer>
    <MainSequencer>
      <MonitoringEnum Value="1"/>                    # In / Auto / Off
      <Recorder><IsArmed Value="false"/></Recorder>  # record-arm
    </MainSequencer>
    <FreezeSequencer>  ...  </FreezeSequencer>       # DECOY — see gotcha below
    <DeviceChain><Devices> ... </Devices></DeviceChain>
  </DeviceChain>
```

Concrete answers to the questions asked:

| State | XPath (relative to the track element) |
|---|---|
| Record-arm | `DeviceChain/MainSequencer/Recorder/IsArmed/@Value` |
| Monitor (In/Auto/Off) | `DeviceChain/MainSequencer/MonitoringEnum/@Value` |
| Mute | `DeviceChain/Mixer/Speaker/Manual/@Value` — **inverted**, `true` means *not* muted |
| Solo | `DeviceChain/Mixer/SoloSink/@Value` |
| Audio From | `DeviceChain/AudioInputRouting/{Target, UpperDisplayString, LowerDisplayString}` |
| MIDI From | `DeviceChain/MidiInputRouting/{...}` |
| Audio To / MIDI To | `DeviceChain/AudioOutputRouting/{...}`, `DeviceChain/MidiOutputRouting/{...}` |
| Device chain | `DeviceChain/DeviceChain/Devices/*` — element **tag** is the device type |
| Device bypassed | `<Device>/On/Manual/@Value` |
| Device parameter | `<Device>/<ParamName>/Manual/@Value` |

Real values pulled from the crash-recovery snapshot of the user's own set **[verified locally]**:

```
AudioTrack  Guitar_1  mon=1 arm=false  audioIn=AudioIn/External/M0   "Ext. In" / "1"
AudioTrack  Vox_2     mon=1 arm=false  audioIn=AudioIn/External/M1   "Ext. In" / "2"
MidiTrack   Squeeze   mon=1 arm=false  midiIn=MidiIn/External.All/-1 "Ext: All Ins"
```

Note the routing pair: `Target` is the stable machine identifier (`AudioIn/External/M0`,
`AudioOut/GroupTrack`, `AudioOut/Main`, `MidiOut/None`), while `UpperDisplayString` /
`LowerDisplayString` are **literally the two lines the user sees in Live's I/O chooser**. Answer text
should quote the display strings; matching logic should key off `Target`.

### Gotchas that will bite a naive parser

1. **`FreezeSequencer` duplicates `MonitoringEnum` and `Recorder/IsArmed`.** A flat
   `grep MonitoringEnum` returns the freeze-sequencer copy too, and in a grouped set the *first* hit
   belongs to a `GroupTrack`'s freeze sequencer — a track that has no monitor setting at all
   **[verified locally]**. Always path through `DeviceChain/MainSequencer`.
2. **`Speaker/Manual` is the inverse of mute.** Getting this backwards produces confidently wrong
   diagnostics, which is the worst possible failure for this feature.
3. **Track numbering is not list position.** `<Tracks>` mixes `GroupTrack`, `MidiTrack`, `AudioTrack`
   and `ReturnTrack` in one ordered list; `MainTrack` is a sibling of `Tracks`, not a member. The Live
   Object Model's `song.tracks` excludes returns and main. "Track 3" in the user's sentence means the
   third thing they can see, which includes group tracks and excludes tracks hidden inside a folded
   group (`TrackGroupId` + `TrackUnfolded`). Normalise this once, in one place.
4. **Group and return tracks have no monitor/arm.** `MainSequencer` is absent; the code must tolerate that.
5. **Parameter values are raw internal units.** `<Cutoff><Manual Value="68.5828857"/>` is not "68.6 Hz"
   and not a display string. The file gives you no formatter. This is the single biggest capability gap
   versus the live route, where `DeviceParameter.display_value` and `str_for_value()` exist
   ([LOM DeviceParameter](https://docs.cycling74.com/apiref/lom/deviceparameter/)). Scope answers about
   device *parameters* accordingly: the file source can reliably say *which devices are present and
   whether they are bypassed*, and should be cautious about reporting parameter values with units.
6. **`MonitoringEnum` semantics.** `1` is Auto — confirmed by observation: every track in the user's own
   real set is `1`, which is Live's default **[verified locally]**. `0 = In`, `2 = Off` is the mapping
   every community tool uses and is consistent with the factory demo (audio tracks set to `2`). Marked
   **partly UNVERIFIED**: Cycling '74's LOM reference page for `Track` does not document
   `current_monitoring_state` at all ([LOM Track](https://docs.cycling74.com/apiref/lom/track/)), though
   the symbol and a `monitoring_states` enum are present in the Live 12.4.3 binary **[verified locally]**.
   Confirm empirically (flip a monitor, save, diff) before shipping a sentence that names In vs Off.

### Documentation status and stability

**Ableton do not document the format.** There is no published schema, no versioning contract and no
support commitment. Confirmed indirectly by the entire tooling ecosystem being reverse-engineered
(`elixirbeats/abletoolz`, `maranedah/pyableton`, several `*/ableton` parsers) and by Ableton's own
support articles only ever discussing `.als` as an opaque file to recover, never to read.

Direct evidence that it *does* drift **[verified locally]**: the master track element was renamed
`MasterTrack` → `MainTrack` in Live 12, tracking the UI rename
([Live 12 manual, Mixing](https://www.ableton.com/en/manual/mixing/)). `SchemaChangeCount` visibly
changes within the 12.x line. Element names are stable enough to be *useful*, not stable enough to be
*assumed*.

### Freshness: the last-save problem, and why the fallbacks don't help

`.als` on disk reflects the last explicit save. Live has **no autosave** — the existence of third-party
products like *LiveSaver* sold specifically to add autosave to Live 11/12 is the practical proof.

Live's crash-recovery machinery lives in `~/Library/Preferences/Ableton/Live <version>/`
([Ableton: Recovering a Set manually after a crash](https://help.ableton.com/hc/en-us/articles/115001878844-Recovering-a-Set-manually-after-a-crash)),
and on this machine contains **[verified locally]**:

```
~/Library/Preferences/Ableton/Live 12.4.3/
  BaseFiles/FeilimsLament.als      # gzipped XML, fully parseable
  Undo/0.band                      # binary
  Undo/bands.cfg                   # {"version":1,"bandDataSize":8388572,"fileTypeId":...,"uuid":...}
  CrashRecoveryInfo.cfg            # binary index
  Crash/                           # timestamped copies of the above, written after a crash
  Log.txt
```

I checked whether this gives fresher state than the saved `.als`. **It does not:**

- `BaseFiles/<Set>.als` is a *base* snapshot whose mtime equals Live's launch time, not the time of the
  last edit **[verified locally]**. It can be *older* than the user's last manual save.
- `Undo/0.band` contains no gzip members, no `<Ableton>`, no `<LiveSet>`, no `MonitoringEnum`. Its
  readable strings are a proprietary delta log: `UpdateAction`, `AddAction`, `DeleteAction`,
  `RemoteableBool`, `RemoteableInt`, device names **[verified locally]**. There is no public parser and
  writing one is not a sane investment.

So: **`BaseFiles` + `Undo` are a recovery mechanism, not a live-state feed.** The design should not
promise freshness it cannot deliver. The honest contract is a snapshot plus an "as of" time, and the
UI should say "as of your last save at 14:32" when the answer depends on possibly-stale state.

### `Log.txt` — the overlooked file source **[verified locally]**

`~/Library/Preferences/Ableton/Live 12.4.3/Log.txt` is plain text, appended live, and contains:

```
info: Loading document "/Users/r/Desktop/Comps/FeilimsLament Project/FeilimsLament.als"
info: Loaded document was created by Ableton Live 12.4.3
info: CoreAudio: Device init: Scarlett Solo 4th Gen (4 In, 2 Out) (Focusrite, ...)
info: Audio In Out: Driver Type: CoreAudio
info: Audio In Out: Input Device: Scarlett Solo 4th Gen (4 In, 2 Out)
info: Audio In Out: Input Channels: 2
info: AMidiIO: Midi Remote Scripts:
  MidiRemoteScript 1 [Control Surface="APC_Key_25_mk2" Input="APC Key 25 mk2 (Control)" Output="APC Key 25 mk2 (Control)"]
  MidiInDevice [Name="APC Key 25 mk2 (Keys)",    Track=true, Sync=false, Remote=true,  MPE=false, ...]
  MidiInDevice [Name="APC Key 25 mk2 (Control)", Track=true, Sync=false, Remote=false, MPE=false, ...]
info: Licensing: Installed variant: Standard
```

Two things fall out of this:

1. It tells us **which `.als` is currently open**, which is how the file-based `StateSource` finds its
   target without asking the user to pick a file.
2. It independently answers a real cluster of home-studio questions — wrong audio device selected,
   control surface not loaded, a MIDI port's Track/Sync/Remote switches wrong, Live running as the wrong
   edition — none of which are in the `.als` at all.

Log format is undocumented and line shapes will drift; parse leniently, prefer the last matching line,
and never hard-fail on it.

---

## 3. Live's remote-control surfaces (routes to live state, no M4L)

### 3a. MIDI Remote Scripts / Control Surface scripts (Python)

**Locations on macOS** (both **[verified locally]**):

- Factory scripts (read-only, inside the app bundle):
  `/Applications/Ableton Live 12 Standard.app/Contents/App-Resources/MIDI Remote Scripts/`
  — 150+ directories, including `APC_Key_25`, `APC_Key_25_mk2`, `_Framework`, `_Generic`,
  `ableton/v2`, `ableton/v3`, `MaxForLive`, `_MxDCore`.
- User scripts (where a third-party script is installed):
  `~/Music/Ableton/User Library/Remote Scripts/`
  — exists on this machine and already contains a third-party script (`Logi_Plugin`), so the mechanism
  is known-good here.
- A separate, unrelated `~/Library/Preferences/Ableton/Live 12.4.3/User Remote Scripts/` exists — that is
  the simple text-file "instant mapping" folder, **not** where Python control surfaces go. Easy to confuse.

**Python runtime**: Live 12.4.3 embeds **CPython 3.11.6** **[verified locally]** — confirmed two ways:
the version string in the `Live` binary, and the `.pyc` magic `a7 0d 0d 0a` (3495 → 3.11) on the factory
scripts. Live 10 and earlier were Python 2; Live 11+ are Python 3, so any script written for Live 10 is
dead.

**Compiled/obfuscated?** Not obfuscated, but **shipped as `.pyc` only — no `.py` sources anywhere in the
bundle** **[verified locally]**. Embedded build paths are still visible
(`output/Live/mac_universal_64_static/Release/python-bundle/MIDI Remote Scripts/...`), and string tables
are readable enough to recover structure, which is how I established the APC mk2 facts below. Structure
Void publishes recovered sources for Live 12.4
([gluon/AbletonLive12_MIDIRemoteScripts](https://github.com/gluon/AbletonLive12_MIDIRemoteScripts)),
with the caveat that Live 12's Python 3.11 bytecode (zero-cost exception tables, adaptive interpreter)
defeats the classic decompilers, so recovery is no longer clean.

**What the Live Object Model exposes.** Everything this feature needs, and more, with live change
notification. From [LOM Track](https://docs.cycling74.com/apiref/lom/track/) (documentation states it
describes Live 12.3.5): `arm`, `mute`, `solo`, `muted_via_solo`, `can_be_armed`, `name`, `color`,
`is_frozen`, `is_grouped`, `is_foldable`, `fold_state`, `is_visible`, `input_routing_type`,
`input_routing_channel`, `output_routing_type`, `output_routing_channel`, plus the `available_*` lists,
plus `input_meter_level` / `output_meter_level`, plus `devices`. Most are `get`/`set`/**`observe`** —
observation is the important word, it means a script can be pushed changes rather than polling.
`DeviceParameter` adds `value`, **`display_value`**, `str_for_value()`, `min`, `max`, `is_quantized`,
`value_items`, `state` — i.e. human-readable parameter values, which the `.als` route cannot give us.

Two caveats worth recording:

- `current_monitoring_state` is **absent from the published LOM `Track` page** even though it exists in
  the Live 12.4.3 binary **[verified locally]** and is used by every community tool. The published LOM
  is incomplete; do not treat its absence as absence.
- AbletonOSC's README documents `current_monitoring_state` as "1=on, 0=off". That is **wrong** — it is a
  three-state enum. Do not copy that description into our docs.

**How badly does it break between Live versions?** Badly enough to plan for. Live 10→11 was a hard break
(Python 2→3). Live 11.3 introduced the `ableton.v3.control_surface` framework and factory scripts have
been migrating to it since, while older scripts still sit on `_Framework` — both trees ship
simultaneously in 12.4.3 **[verified locally]**, so "which framework" is per-script, not per-version.
The framework itself has **never been documented by Ableton**; the community consensus is explicit that
"there is no official documentation or instructions for creating custom control surfaces". The LOM
(the data model) is far more stable than the framework (the plumbing) — which argues for a script that
touches the LOM and almost nothing else.

### 3b. "Live 11.3+ documented/supported control surface API"

Asked to establish whether Ableton publish documentation for the newer format. **They do not.**

What exists **[verified locally]** is `ableton.v3.control_surface` — a real, newer framework, shipped in
Live 12.4.3, and demonstrably the one used by the APC Key 25 mk2 script. Its shape is declarative:
a `ControlSurfaceSpecification` plus `Elements`, `Skin` and a `create_mappings` function. It is a
genuine improvement over `_Framework` for script authors.

But: no Ableton-published reference, no SDK, no stability guarantee, no support channel. Ableton's own
help article on the subject is *"Creating your own Control Surface script"*, which points at the
plain-text instant-mapping folder rather than at the Python API. The nearest thing to documentation is
community-maintained: [midiremotescripts.structure-void.com](https://midiremotescripts.structure-void.com/).

**Design consequence**: there is no "supported API" tier here. Both the old and new script formats are
undocumented, unsupported surfaces we would be building on at our own risk. That does not make the
route unusable — it makes it a route with an ongoing maintenance cost that must be owned explicitly,
and a strong argument for depending on someone else's already-maintained script (3d) rather than our own.

### 3c. Ableton Link — rule it out explicitly

Link synchronises **tempo, beat, phase, and (since Link v3) start/stop** across applications on a machine
or LAN ([Link documentation](https://ableton.github.io/link/),
[Live 12 manual: Synchronizing with Link](https://www.ableton.com/en/manual/synchronizing-with-link-tempo-follower-and-midi/)).

It carries **no** notes, **no** control changes, **no** audio, and **no** session/track state. There is no
track list, no arm/monitor/mute/solo, no routing, no device information. Link cannot answer a single one
of the questions this feature exists for. Its only conceivable value is "is Live playing, and at what
tempo" — which the `.als` `Transport` element and Log.txt already partly cover, without a network
dependency.

Record this as a closed question so nobody re-opens it mid-design.

### 3d. OSC bridges

**AbletonOSC** — [github.com/ideoforms/AbletonOSC](https://github.com/ideoforms/AbletonOSC), MIT,
~794 stars, last pushed 2025-11-19, 71 open issues, self-described stability "beta".

- **It is a MIDI Remote Script, not a Max for Live device.** Install = copy the folder to
  `~/Music/Ableton/User Library/Remote Scripts/`, restart Live, select "AbletonOSC" in
  *Preferences → Link/Tempo/MIDI → Control Surface*. **No M4L, no Suite.** This is the decisive fact.
- Requires Live 11 or above. Listens on UDP **11000**, replies on **11001**.
- Exposes the LOM using LOM's own naming: `/live/track/get/arm`, `/live/track/get/mute`,
  `/live/track/get/solo`, `/live/track/get/current_monitoring_state`,
  `/live/track/get/input_routing_type`, `/live/track/get/output_routing_type`, `/live/track/get/name`,
  `/live/song/get/num_tracks`, `/live/song/get/tempo`, `/live/song/get/is_playing`, and device/clip
  equivalents. `start_listen`/`stop_listen` give push notifications rather than polling.
- `/live/song/get/track_data 0 12 track.name track.arm ...` does bulk multi-track queries in one
  round trip — exactly the "snapshot the whole session" primitive a `StateSource` wants.
- Costs one of Live's seven control-surface slots. Slot 1 here is already the APC; slots 2–7 are free
  **[verified locally]**, so there is room.

**LiveOSC** — [github.com/dinchak/LiveOSC](https://github.com/dinchak/LiveOSC): last pushed
**2016-03-27**, Python 2 era, no licence file. **Dead.** It predates the Python 3 transition and cannot
load in Live 11+. Mention it only to dismiss it; its name still circulates in old forum posts.

**live_rpyc** — [github.com/lucianoiam/live_rpyc](https://github.com/lucianoiam/live_rpyc), GPL-3.0,
~33 stars, last pushed 2024-09. Runs control-surface code in an *external* Python interpreter via RPyC.
Architecturally attractive (our logic lives outside Live, no redeploy-into-Live cycle) but small,
GPL-3.0 (licence-incompatible with a lot of shipping models), and much less proven than AbletonOSC.
Worth a footnote, not a plan.

### Comparison table

Stability and effort are 1–5 (5 = best / least effort).

| Route | Needs M4L? | Install burden | Stability | Effort | What it exposes | Freshness |
|---|---|---|---|---|---|---|
| **Null source** (MVP) | No | None | 5 | 5 | Nothing | n/a |
| **Live `Log.txt`** | No | None | 3 — undocumented text, format may drift | 5 | Open set path, audio device, control surface, MIDI port Track/Sync/Remote flags, Live edition | Live-ish (appended as events occur), but only these facts |
| **Saved `.als`** | No | None | 3 — undocumented, renames across major versions | 4 | Tracks, arm, monitor, mute, solo, in/out routing, device chain, device on/off, raw parameter values, scenes, transport | **Last save only** |
| **Crash-recovery `BaseFiles` + `Undo`** | No | None | 1 — `Undo` is undocumented binary | 1 | `BaseFiles` = same as `.als`; `Undo` = unparseable | **Worse than `.als`** — snapshot at load |
| **AbletonOSC** (remote script) | **No** | User copies a folder + ticks a dropdown; uses 1 of 7 surface slots | 3 — active, MIT, but "beta", 71 open issues, and it rides an undocumented framework | 3 | Effectively the whole LOM, incl. `display_value` for parameters; push notifications via `start_listen` | **Live** |
| **Our own remote script** | No | Same as above, plus we own it | 2 — undocumented framework, Python 3.11 `.pyc`-only factory scripts, per-release breakage risk | 1 | Same as AbletonOSC | **Live** |
| **live_rpyc** | No | Remote script + external interpreter | 2 — small project, GPL-3.0 | 2 | Whole LOM, from outside Live | **Live** |
| **Ableton Link** | No | Toggle in prefs | 5 — documented, stable, official | 5 | **Tempo, beat, phase, start/stop only** | Live, but useless here |
| **Max for Live** | **Yes** | Purchase + device | 4 — documented API | 3 | Whole LOM | Live |

**Recommended shape**: three implementations behind the seam, as planned —
`NullStateSource` (MVP), `FileStateSource` (reads Log.txt to locate the set, then parses the `.als`),
`LiveStateSource` (AbletonOSC over UDP). Keep the interface small enough that all three can honestly
satisfy it, with per-field "unknown" as a first-class value rather than a thrown error — the file source
genuinely cannot know some things the live source can, and vice versa.

---

## 4. The APC Key 25 mk2

### Native support in Live 12 — yes **[verified locally]**

`Contents/App-Resources/MIDI Remote Scripts/APC_Key_25_mk2/` ships in Live 12.4.3 Standard, alongside a
separate `APC_Key_25/` directory for the mk1. It is currently selected and auto-detected on this machine:

```
MidiRemoteScript 1 [Control Surface="APC_Key_25_mk2"
                    Input="APC Key 25 mk2 (Control)" Output="APC Key 25 mk2 (Control)"]
```

The controller presents **two MIDI port pairs** — `(Keys)` and `(Control)`. The script binds `(Control)`;
`(Keys)` is the keybed and sustain input with `Track=true, Remote=true`. A user who mis-assigns these gets
"my keyboard does nothing" or "my pads do nothing" — a diagnosable class of problem, and one that Log.txt
reports directly.

The mk2 script declares `AUTO_LOAD_KEY`, `CONTROLLER_ID_KEY` (vendor/product IDs) and
`identity_response_id_bytes` **[verified locally]**, i.e. Live auto-detects the device by USB ID and
SysEx identity reply rather than requiring manual selection.

### Modes **[verified locally, from the script + Akai's manuals]**

The mk2's Live script is built on `ableton.v3.control_surface` and declares exactly these mode groups:

| Mode group | Values | How the user switches |
|---|---|---|
| `Main_Modes` | `default`, `shift` | Hold **Shift** (momentary) |
| `Track_Button_Modes` | `clip_stop`, `solo`, `mute`, `arm`, `track_select` | Shift + Scene Launch 1–5 |
| `Encoder_Modes` | `volume`, `pan`, `send`, `device` | Shift + Clip Stop buttons 5–8 |

This matches Akai's user guide
([APC Key 25 mk2 User Guide v1.2](https://cdn.inmusicbrands.com/akai/apc-key-25-mkii/APC%20Key%2025%20mk2%20-%20User%20Guide%20-%20v1.2.pdf)).
`send` mode cycles through sends on re-press (`cycle_send_index` in the script). The script also declares
`Session_Navigation` (Shift + the four arrow Clip Stop buttons) and `View_Based_Recording`.

**There is no Note mode and no Drum mode on the Key 25 mk2.** Some press coverage of the mk2 launch
(e.g. [gearnews](https://www.gearnews.com/akai-apc-mini-mk2-apc-key-25-mk2/)) attributes Note/Drum modes
to "the mk2 range", but that is the **APC mini mk2**, not the Key 25 mk2. Verified by direct comparison
**[verified locally]**: `APC_mini_mk2/mappings.pyc` declares `Pad_Modes` with values
`session | note | drum | note_edit`; `APC_Key_25_mk2/mappings.pyc` declares no `Pad_Modes` at all.
Akai's Key 25 mk2 user guide likewise never mentions Note or Drum mode. **If DAWMans ever answers a
question about Note/Drum mode on this user's controller, it will be wrong.** Worth an explicit guard.

### Is the active mode observable from software?

**No, not without becoming the control surface script ourselves.**

- Mode state is **host-side**, held in the `ModesComponent` inside Live's own script instance. It is not
  device state.
- Akai's protocol has **no mode query and no mode-report message**
  ([APC Key 25 mk2 Communications Protocol v1.1](https://cdn.inmusicbrands.com/akai/attachments/APC%20Key%2025%20mk2%20-%20Communication%20Protocol%20-%20v1.1.pdf)).
  The SysEx vocabulary is: Device Inquiry (0x06 0x01/0x02), Introduction message (0x60) whose reply
  (0x61) returns **fader values only**, and an LED-colour customisation message. Nothing about modes.
- **Shift is a momentary button** (Note 0x62), not a latch, so even sniffing MIDI only tells you Shift is
  *being held right now*.
- The LOM's `ControlSurface` object is reachable via `control_surfaces N`
  ([LOM index](https://docs.cycling74.com/apiref/lom/)), but **UNVERIFIED** whether it surfaces the
  script's internal mode; the published documentation for it is thin and I did not confirm any
  mode-related property. Assume not.

**Design consequence**: do not promise "you're in Mute mode, that's why the buttons aren't stopping
clips". The honest form is conditional — "if your Clip Stop buttons are in Mute mode (Shift + Scene
Launch 3 sets that), ...". The mode is a thing we ask the user about, not a thing we read.

### mk1 vs mk2 — the manual gap

`manuals/akai_apc-key-25_user-guide_v1.0_multi.pdf` is the **mk1** guide. The user has the **mk2**.
Concrete differences, all **[verified locally]** unless noted:

| | APC Key 25 (mk1) | APC Key 25 mk2 |
|---|---|---|
| Live 12 script | `APC_Key_25/` | `APC_Key_25_mk2/` — **separate script** |
| Script framework | `_Framework` (`OptimizedControlSurface`, `ModesComponent`, `Layer`) | `ableton.v3.control_surface` (`ControlSurfaceSpecification`, declarative mappings) |
| Pad LEDs | **Bi-colour** — script builds a `make_biled_skin` (green/red, blended yellow) | **Full RGB** — 128-entry `STANDARD_COLOR_PALETTE`, `Rgb` skin, colours follow Live's clip colours |
| Pad LED behaviours | on/off/blink, limited | 16 MIDI channels select brightness (10/25/50/65/75/90/100 %), pulse (1/16…1/2) and blink (1/24…1/2) rates |
| Pad grid | 8×5 = 40 | 8×5 = 40, physically larger and squarer (cosmetic) |
| Keybed | 25 mini velocity-sensitive keys | 25 mini velocity-sensitive keys (unchanged) |
| Knobs | 8 | 8, documented as **Relative** (`AccelTwoCompliment` map mode in the script) |
| Faders | none | none *(the **APC mini** mk2 has 9 faders — different product, do not conflate)* |
| Shift layer | Present | Present, with the mode set enumerated above |
| Note / Drum pad modes | No | **No** (contrary to some press coverage) |
| Auto-detect | Capability keys present | `AUTO_LOAD_KEY` + USB vendor/product ID + SysEx identity reply |

**UNVERIFIED**: whether the mk1's knobs were absolute rather than relative. The mk1 `.pyc` files yielded
no `map_mode` string, and Akai do not publish a mk1 communications protocol document. Don't assert it.

**Action for the corpus**: fetch and add the two mk2 documents, and either remove the mk1 guide or tag it
by hardware revision so retrieval cannot mix them:

- User guide v1.2 — `https://cdn.inmusicbrands.com/akai/apc-key-25-mkii/APC%20Key%2025%20mk2%20-%20User%20Guide%20-%20v1.2.pdf`
- Communications protocol v1.1 — `https://cdn.inmusicbrands.com/akai/attachments/APC%20Key%2025%20mk2%20-%20Communication%20Protocol%20-%20v1.1.pdf`

This is a live correctness bug in the manual corpus today, independent of the `StateSource` work.

---

## Open questions for the design phase

1. **Does the `StateSource` interface expose freshness, or does the caller assume live?** Recommendation:
   every snapshot carries `source_kind` and `captured_at`, and answer templates that depend on mutable
   state must be able to hedge.
2. **How is "track 3" resolved?** Group tracks, folded groups, returns and Main all interact. Needs one
   canonical numbering rule shared by all three implementations, defined against what the user *sees*.
3. **Do we ship parameter-level answers from the file source?** The raw-units problem (gotcha 5) says no,
   or only for enum-ish parameters, until a live source exists.
4. **Is the Log.txt reader a separate source or part of `FileStateSource`?** It answers a disjoint set of
   questions (device/routing config vs. session content) and has a different freshness story. Arguably a
   separate small source composed alongside.
5. **Confirm the `MonitoringEnum` mapping empirically** before any answer names a specific monitor value.

## Reproducing the local checks

Everything marked **[verified locally]** came from read-only inspection:

```
/Applications/Ableton Live 12 Standard.app/Contents/App-Resources/MIDI Remote Scripts/
/Applications/Ableton Live 12 Standard.app/Contents/App-Resources/Python/
~/Library/Preferences/Ableton/Live 12.4.3/{Log.txt,Preferences.cfg,BaseFiles/,Undo/}
~/Music/Ableton/User Library/Remote Scripts/
~/Music/Ableton/Factory Packs/Chop and Swing/Demo Song/Clean Swing.als   # gunzip → XML
```

`.pyc` structure was recovered by extracting printable strings, not by decompilation.

## Sources

- [Ableton — Compare Live editions](https://www.ableton.com/en/live/compare-editions/)
- [Ableton — Activating Max for Live with a Live Standard license](https://help.ableton.com/hc/en-us/articles/360001296900-Activating-Max-for-Live-with-a-Live-Standard-license) (Cloudflare-gated; not fetched)
- [Ableton — Installing third-party remote scripts](https://help.ableton.com/hc/en-us/articles/209072009-Installing-third-party-remote-scripts) (Cloudflare-gated)
- [Ableton — Recovering a Set manually after a crash](https://help.ableton.com/hc/en-us/articles/115001878844-Recovering-a-Set-manually-after-a-crash) (Cloudflare-gated)
- [Ableton Live 12 manual — Mixing](https://www.ableton.com/en/manual/mixing/)
- [Ableton Live 12 manual — Synchronizing with Link, Tempo Follower, and MIDI](https://www.ableton.com/en/manual/synchronizing-with-link-tempo-follower-and-midi/)
- [Ableton Link documentation](https://ableton.github.io/link/)
- [Cycling '74 — Live Object Model index](https://docs.cycling74.com/apiref/lom/) (states it documents Live 12.3.5)
- [Cycling '74 — LOM: Track](https://docs.cycling74.com/apiref/lom/track/)
- [Cycling '74 — LOM: DeviceParameter](https://docs.cycling74.com/apiref/lom/deviceparameter/)
- [AbletonOSC](https://github.com/ideoforms/AbletonOSC) — MIT, ~794★, last pushed 2025-11-19
- [LiveOSC (dinchak)](https://github.com/dinchak/LiveOSC) — last pushed 2016-03-27, unmaintained
- [live_rpyc](https://github.com/lucianoiam/live_rpyc) — GPL-3.0, last pushed 2024-09-27
- [gluon/AbletonLive12_MIDIRemoteScripts](https://github.com/gluon/AbletonLive12_MIDIRemoteScripts) — recovered Live 12.4 script sources
- [midiremotescripts.structure-void.com](https://midiremotescripts.structure-void.com/) — unofficial LOM + framework docs
- [abletoolz](https://github.com/elixirbeats/abletoolz), [pyableton](https://github.com/maranedah/pyableton) — third-party `.als` parsers
- [Akai — APC Key 25 mk2 User Guide v1.2](https://cdn.inmusicbrands.com/akai/apc-key-25-mkii/APC%20Key%2025%20mk2%20-%20User%20Guide%20-%20v1.2.pdf)
- [Akai — APC Key 25 mk2 Communications Protocol v1.1](https://cdn.inmusicbrands.com/akai/attachments/APC%20Key%2025%20mk2%20-%20Communication%20Protocol%20-%20v1.1.pdf)
- [gearnews — Akai APC mini mk2 / APC Key 25 mk2 announcement](https://www.gearnews.com/akai-apc-mini-mk2-apc-key-25-mk2/) (conflates the two products' pad modes — see §4)

Researched 2026-08-14 against Ableton Live 12.4.3 Standard, macOS (Darwin 25.6.0).
