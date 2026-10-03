# blinky-emulator

A software stand-in for the **Pimoroni Blinky 2350** — the badge handed
out as the "Workday DevCon 2026 DevKit" — for developing "badgeware" apps
without the physical hardware.

Built because live hardware for this device has repeatedly hung mid-session
in ways unrelated to the app code being tested (see
[SkolDisplayWDDDK](https://github.com/erikm6872/SkolDisplayWDDDK), the
project this was extracted from, for the full story), making iteration on
real hardware impractical at times.

## Running

```
python3 server.py --app /path/to/your/app/__init__.py
```

Then open http://localhost:8765/ (or `--port` to use a different one) in a
browser. The page shows the 39×26 LED matrix (rendered as dots), clickable
`Button A/B/C`, and an `Online/Offline` toggle to exercise both the
connected and disconnected branches of your app's logic.

**The panel isn't actually a rectangle.** Five physical buttons are
embedded directly in the LED grid's footprint (confirmed live by
photographing the badge fully lit — see `panel_shape.py`), and content
drawn into those regions will look different on real hardware than it
does here. Those dead zones are rendered in red by default
(`Device.to_image(show_dead_zones=True)`, the default) specifically so a
layout mistake like that gets caught in the emulator instead of only
showing up on a hardware check-in — which is exactly how this was
discovered in the first place (SkolDisplay's default screen ran "VIKINGS"
straight through the bottom three buttons).

`urequests.get()` is wired to the real `requests` library, so an app that
fetches from a real HTTP endpoint can exercise the actual network path
(not just a mock) while "online" — generally more useful than mocking,
since this machine's network is usually far more reliable than the
badge's.

## How it works

- `sys_modules.py` installs fake `network`/`wifi`/`ntptime`/`badgeware`/
  `urequests` modules into `sys.modules` before the app is loaded, so its
  `import` statements resolve to these instead of erroring (desktop Python
  has none of these real modules). `badgeware.State` persists to a
  `.emulator_state/` directory created next to the app's own `__init__.py`
  (mirroring `/state/*.json` on the real device) — not inside this tool's
  own checkout, so running multiple different apps through the same
  emulator install doesn't collide.
- `stubs.py` provides the globals the real badgeware launcher injects into
  an app's namespace: `screen`, `badge`, `color`, `rom_font`,
  `BUTTON_A/B/C`, `run`, `fatal_error`. It covers what's been confirmed in
  use across badgeware apps so far — if your app needs something not yet
  stubbed, add it following the same pattern (ideally confirming the real
  behavior on hardware first rather than guessing).
- `server.py` reads the app's source, `exec`s it against those stubs (the
  same technique `badgeware.launch()` uses on the real device), captures
  the function passed to `run()`, and drives it in a loop on a background
  thread. Each frame renders to a PNG served over a tiny page that polls
  `/frame.png` + `/status` every 150ms.

## Fidelity — what's accurate vs. approximate

- **Exact**: `badge.ticks` timing, button edge-detection, and — for
  specific strings that have actually been measured live on hardware via
  real `screen.measure_text()` calls — text width and height (see
  `font_metrics.py`). Right now that's `"SKOL"` and `"VIKINGS"` across all
  37 `rom_font` entries, from SkolDisplay's development. **Add more
  measured strings to `font_metrics.py` as you discover them on real
  hardware** — the more real data points per font, the better the
  interpolation gets for everything else in that font.
- **Approximate**: actual glyph *shapes*, and text sizing for any string
  not in `font_metrics.py`'s measured set (interpolated from whatever has
  been measured for that font). We don't have the device's real `.ppf`
  bitmap font files, so text is rendered with a real system font (Hack
  Nerd Font Mono Bold), iteratively size-fit so its rendered width matches
  the target — see `_fit_font` in `stubs.py`. This was broken on the first
  attempt (sizing purely by height badly overflowed/clipped text, visually
  confirmed) before the width-fit approach fixed it — worth knowing if you
  extend this further.
- **Not emulated at all**: genuine hardware/firmware behaviors rather than
  application logic — e.g. (from the Blinky 2350 specifically) the
  display only flipping once per completed `update()` call, the
  `machine.WDT` danger (survives a normal reset on this chip), Disk Mode's
  manual non-persistent toggle, the DTR-reset-on-serial-close gotcha. A
  feature working here doesn't guarantee identical behavior on hardware —
  only that the application-level logic is sound. Periodic real-hardware
  check-ins are still worth doing, just not for every small iteration.

## Extending to other apps/projects

This was built against one app (SkolDisplay) but the stub layer is
intentionally app-agnostic. To use it with a different badgeware project:
point `--app` at that project's `__init__.py`. If it uses globals this
doesn't stub yet, you'll get a `NameError` or `AttributeError` at exec
time — add the missing piece to `stubs.py` (or a new fake module in
`sys_modules.py`), ideally confirmed against real hardware behavior first.
