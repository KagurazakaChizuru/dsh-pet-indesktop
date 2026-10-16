# Desktop Pet Experience

The user-facing desktop-pet experience shared by settings, menus, overlays, and
their platform-specific presentations.

## Language

**Shared UX Contract**:
The cross-platform agreement for information architecture, state semantics,
interaction meaning, spacing roles, and brand roles. Platform presentation may
vary without changing this contract.
_Avoid_: Pixel parity, identical native chrome

**Settings System**:
The single product surface that owns every persistent user preference. Legacy
settings may temporarily redirect into it but do not define a second contract.
_Avoid_: Modern settings, legacy settings

**Menu Action Model**:
The shared set of menu commands, canonical labels/icons, callbacks, capability
availability, and runtime enablement semantics, independent of platform
presentation.
_Avoid_: Modern menu behavior, legacy menu behavior

**Menu Layout Tree**:
A versioned tree of stable action IDs and one-level submenus. It owns order and
user visibility, explicit separators, and optional alias/icon presentation
overrides, while the Menu Action Model owns canonical presentation, callbacks,
runtime state, and platform capability. Missing actions from newer versioned
defaults are inserted beside their nearest template sibling; explicit hidden
nodes and user ordering remain authoritative.
_Avoid_: Serialized QAction, platform-specific menu order

**Menu Presentation Override**:
An optional Menu Layout Tree decoration. Aliases replace canonical labels only
at runtime while the editor retains the canonical label for orientation. Icon
overrides may select a semantic icon, suppress the icon, or reference a
validated local image with contain/cover rendering; an unreadable local image
falls back to the Menu Action Model icon.
_Avoid_: Renamed command, embedded image bytes

**Animation Menu Dismissal**:
The interaction rule of the animation submenus: triggering a play-once action
plays it and dismisses the whole menu chain, because the next thing the user
wants to see is the pet. It governs the play-once animation leaves only —
toggles, value pickers, and submenu navigation keep their own rules — and the
`anim_menu_stay_open` preference (default off) restores the stay-open behavior
for users who chain several actions. The random-action list is grouped by the
prefix families already present in the animation names, so no level of that
menu needs scrolling across a whole screen.
_Avoid_: Sticky menu, per-item dismissal flag

**Capability Unavailable**:
An action cannot exist on the current platform or build. The Menu Layout Tree
retains its position for cross-platform editing, while the current runtime may
omit it and the editor explains the capability reason.
_Avoid_: Disabled feature, hidden action

**Runtime Disabled**:
An action exists on the current platform but its owning feature is currently
off or has no configured content. It keeps its Menu Layout Tree position and is
rendered with a disabled style and explanation; changing the feature toggle
never rewrites or filters the tree.
_Avoid_: Capability unavailable, user-hidden

**Dock Recovery Menu**:
The native macOS Dock context menu that keeps core recovery actions, especially
opening the Settings System, reachable when the pet window is hidden or mouse
input passes through it.
_Avoid_: Pet context menu, tray menu

**Settings Popup Surface**:
The shared settings-menu presentation used by selectors and command buttons.
It owns popup anchoring, minimum trigger width, row geometry, disabled state,
submenu arrows, and trailing selection checks; callers only provide actions.
_Avoid_: Copied menu stylesheet, native button menu indicator

**Image Directory Preview**:
An on-demand right-side drawer for image-directory settings. It uses three
shortest-height columns, preserves each thumbnail's useful aspect ratio, labels
every card with an elided filename and full-name tooltip, and defers directory
scanning and image decoding until the user presses Preview.
_Avoid_: Inline settings grid, eager gallery

**Settings Capability Domain**:
A stable sidebar destination organized by user intent. Every persistent setting
has one owning domain; platform support changes availability, not ownership.
_Avoid_: Module page, Windows settings page

**Author Accounts**:
The author's public accounts are a read-only section at the bottom of the Updates
page, not a sidebar destination; every pet identity and both chat-capable and
pet-only builds show it. Copying a handle or opening the GitHub profile does not
write preferences, and the section never participates in Settings Reset. Account
display and clipboard text share one static source in `pet/settings_about.py`;
its icon ink follows the settings window's own theme, not the OS theme.
_Avoid_: About page (there is no separate About page — the accounts live on the
Updates page)

**Settings Reset**:
The whole-settings recovery command in the Settings System sidebar. It restores
every persistent preference to its factory default in one atomic write and keeps
only the AI provider credentials — every provider's key fields plus, for
providers outside the default set, a credential-only entry that holds the name
and the key (`base_url`/`model` return to the default template). It then closes
the settings window, syncs the system login item to the reset value, and asks
the running pet to align its runtime position to the new default so the exit-time
position save cannot write the pre-reset position back. Character and asset
settings take effect on restart. There is no per-page reset.
_Avoid_: Per-page reset, credential reset

**Report Gate**:
The single control for how much of one aggregated event class the pet reports.
It is a pass probability in `0.00–1.00` (`0.00` silences the class, `1.00`
reports every occurrence) and there is no boolean switch: the settings slider is
the only fine-grained control, while the pet menu offers only the two endpoints.
A gate governs the bubble step alone — detectors and the raw-record chain are
never sampled — and it never covers the whole feature.
_Avoid_: Notification toggle, report percentage, global mute

**Gate Group**:
The collapsible settings block that collects every report gate with the
bubble-phrase rows of its own event class, so a gate sits next to what it
controls. It is expanded by default and auto-expands when a search matches a row
inside it.
_Avoid_: Hidden advanced panel, per-feature switch list

**Quiet Mode**:
A process-wide, non-persistent do-not-disturb window covering every pet window
and sprite at once. It suppresses ordinary reminders and bubbles — the pet
bubble and the system notification of that same reminder — while self-talk
(including click responses), link-state bubbles, and every stateful or
interactive event (approval, question, error, lifecycle, balance) keep
presenting, because those are answers the user must act on. Suppressed
reminders are queued with a fixed bound (oldest dropped first) and reported in
one bubble when quiet ends. A fullscreen application counts as quiet only while
the persistent `quiet_also_on_fullscreen` preference is on, and it is the same
fullscreen signal the auto-hide avoidance already uses.
_Avoid_: Notification mute, global sound mute, per-pet mute

**Session-End Spawn Freeze**:
The process-wide latch armed when the operating system announces that the
session is ending (`WM_QUERYENDSESSION`/`WM_ENDSESSION`, or Qt's session
signals as a fallback). While armed, no child ffmpeg process may be spawned and
existing readers are stopped, because a process created inside a tearing-down
Windows session fails DLL initialization (0xc0000142) and blocks shutdown.
The freeze is one-way: a process that survives a cancelled shutdown stays
frozen rather than resuming animation.
_Avoid_: Shutdown option, ffmpeg kill switch
