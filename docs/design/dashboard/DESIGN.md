---
name: ClipForge dashboard
description: The studio's control room; a neutral, dense to-do surface over many short-video accounts.
colors:
  background: "oklch(1 0 0)"
  foreground: "oklch(0.145 0 0)"
  card: "oklch(1 0 0)"
  muted: "oklch(0.97 0 0)"
  muted-foreground: "oklch(0.50 0 0)"
  primary: "oklch(0.205 0 0)"
  primary-foreground: "oklch(0.985 0 0)"
  border: "oklch(0.922 0 0)"
  ring: "oklch(0.708 0 0)"
  good: "oklch(0.52 0.15 150)"
  good-wash: "oklch(0.96 0.04 150)"
  warning: "oklch(0.58 0.13 75)"
  warning-wash: "oklch(0.97 0.05 85)"
  critical: "oklch(0.55 0.20 27)"
  critical-wash: "oklch(0.97 0.03 27)"
  info: "oklch(0.52 0.14 250)"
  info-wash: "oklch(0.97 0.02 250)"
  series-1: "#2a78d6"
  series-2: "#eb6834"
  series-3: "#1baf7a"
  grid: "oklch(0.93 0 0)"
  axis: "oklch(0.80 0 0)"
  dark-background: "oklch(0.145 0 0)"
  dark-card: "oklch(0.205 0 0)"
  dark-muted: "oklch(0.269 0 0)"
  dark-muted-foreground: "oklch(0.72 0 0)"
  dark-foreground: "oklch(0.985 0 0)"
  dark-border: "oklch(1 0 0 / 10%)"
  dark-good: "oklch(0.72 0.17 150)"
  dark-warning: "oklch(0.80 0.14 80)"
  dark-critical: "oklch(0.70 0.18 25)"
  dark-info: "oklch(0.72 0.12 250)"
  dark-series-1: "#3987e5"
  dark-series-2: "#d95926"
  dark-series-3: "#199e70"
typography:
  headline: { fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif", fontSize: "1.375rem", fontWeight: 650, lineHeight: 1.2, letterSpacing: "-0.01em" }
  title: { fontFamily: "ui-sans-serif, system-ui, sans-serif", fontSize: "1rem", fontWeight: 600 }
  title-sm: { fontFamily: "ui-sans-serif, system-ui, sans-serif", fontSize: "0.875rem", fontWeight: 600 }
  body: { fontFamily: "ui-sans-serif, system-ui, sans-serif", fontSize: "14px", fontWeight: 400, lineHeight: 1.45 }
  body-sm: { fontFamily: "ui-sans-serif, system-ui, sans-serif", fontSize: "0.8125rem", fontWeight: 400 }
  label: { fontFamily: "ui-sans-serif, system-ui, sans-serif", fontSize: "0.75rem", fontWeight: 550 }
  tab-label: { fontFamily: "ui-sans-serif, system-ui, sans-serif", fontSize: "0.6875rem", fontWeight: 500 }
rounded:
  sm: "0.375rem"
  md: "0.5rem"
  lg: "0.625rem"
  pill: "999px"
spacing:
  xs: "0.25rem"
  sm: "0.5rem"
  md: "0.75rem"
  lg: "1rem"
  xl: "1.5rem"
  2xl: "2rem"
components:
  card: { backgroundColor: "{colors.card}", rounded: "{rounded.lg}", padding: "0.875rem 1rem 1rem" }
  button: { backgroundColor: "{colors.background}", textColor: "{colors.foreground}", rounded: "{rounded.md}", padding: "0 0.75rem", height: "2rem", typography: "{typography.body-sm}" }
  button-primary: { backgroundColor: "{colors.primary}", textColor: "{colors.primary-foreground}", rounded: "{rounded.md}", height: "2rem" }
  button-danger: { backgroundColor: "{colors.background}", textColor: "{colors.critical}", rounded: "{rounded.md}" }
  button-lg: { height: "2.75rem", padding: "0 1rem" }
  chip: { textColor: "{colors.muted-foreground}", rounded: "{rounded.pill}", padding: "0.25rem 0.5rem", typography: "{typography.label}" }
  chip-critical: { backgroundColor: "{colors.critical-wash}", textColor: "{colors.critical}", rounded: "{rounded.pill}" }
  notice-critical: { backgroundColor: "{colors.critical-wash}", rounded: "{rounded.lg}", padding: "0.7rem 0.9rem" }
  input: { backgroundColor: "{colors.background}", textColor: "{colors.foreground}", rounded: "{rounded.md}", padding: "0.45rem 0.6rem", height: "2.25rem" }
  meter: { backgroundColor: "{colors.muted}", rounded: "{rounded.pill}", height: "0.5rem" }
---

# Design System: ClipForge dashboard

## Overview

**Creative North Star: "The Control Room To-Do List"**

**Product context.** ClipForge runs many short-video accounts (clips, story, band, avatar, model; EN and ES) through one loop: produce, review, publish, measure, scale. The dashboard is where the single owner works: a ~20-minute daily check-in on the phone (clear "needs me", review with the video playing, read the numbers, + Note) and a weekly hour on the laptop (Accounts → Compare, style, hooks, batches). Each account runs as automatically as it has earned (Produce / Review / Publish / Scale, presets Hands-on → Supervised → Autopilot); Telegram pushes time-bound decisions and its Open button lands on `/act` (spec §0–§7, ADR-44).

**The world and its basis.** No concept seed was run. The mockups create whole surfaces inside an established world (impeccable new-work §3): the S3a Next.js shell (`web/app/globals.css` shadcn neutral oklch tokens, the `w-56` sidebar at ≥1024px, phone header + bottom tabs, `StaleNote`, `statusColors.ts`), with structures pinned by the IA the owner approved at checkpoint A (inbox-first, spec §6). The mockups add status roles, chart series, a meter, dense rows and a state switcher on top. The neutral greys carry everything. Color shows up only when it means something: a status, a series, a post state.

**Key Characteristics:**
- Achromatic shell. Hue is reserved for meaning.
- Dense rows, each one decision with its verb and its time cost.
- The phone comes first: the same content stacks, nothing is hidden behind hover.
- Flat surfaces: hairline borders, no shadows at rest.
- Every page has the same five states (live, empty, loading, error, stale) plus its own.

## Colors

Shadcn's neutral ladder plus four status roles, three chart series and seven post-status colors. Every chromatic value carries meaning.

### Primary
- **Ink** (`primary`): primary buttons, the selected dial stop, the on switch, meter fill. Inverts in dark mode (oklch 0.922).

### Neutral
- **Paper / Card** (`background`, `card`): page and card surfaces. In dark mode the card (0.205) sits above the page (0.145).
- **Muted** (`muted`): hover fills, the active sidebar link, skeletons, the meter track, copy blocks.
- **Quiet text** (`muted-foreground`): context lines, labels, axis text. The build darkened it from S3a's 0.556 to **0.50** (dark: 0.708 → **0.72**) so small text on `muted` stays at or above 4.5:1. `web/` should adopt this value.
- **Hairline** (`border`): every card, row divider, input and table rule. Dark mode uses 10% white.
- **Ring** (`ring`): 2px focus outline, offset 2px, on every interactive element.

### Status roles (each has a wash)
- **Good / Warning / Critical / Info**: text color on a matching low-chroma wash for chips, notices, slots and glyphs. Dark mode raises the lightness of the text color and drops the wash to ~0.30.

**The Glyph-and-Word Rule.** Color never carries a status by itself. Every status ships a glyph and a word: `● ok`, `▲ spend`, `◌ new`, `✓ 08:00`, `✕ 11:00 YT`, `◐ waits for you`, plus a legend line under slot rows.

### Chart series (dataviz slots 1–3)
- Blue `series-1`, orange `series-2`, aqua `series-3`, with separate light and dark values (frontmatter), both validated. Grid and axis lines are recessive greys (`grid`, `axis`).

**The Aqua Relief Rule.** Aqua (`#1baf7a`) is under 3:1 on the white surface. Any chart that uses slot 3 must also carry direct end labels in `foreground` and the "Show as a table" view. Neither is optional.

### Post status (from `web/components/statusColors.ts`, lifted unchanged)
posted `#10b981` · partly `#a3e635` · sent `#0ea5e9` · queued `#71717a` · skipped `#fbbf24` · rejected `#f43f5e` · unavailable `#d946ef`. These are for the status bar only, always paired with the status word.

## Typography

**Font:** the system UI stack (`ui-sans-serif, system-ui, …`), with `ui-monospace` for codes. There are no web fonts.

**Character:** a compact UI voice. Hierarchy comes from weight (550/600/650) more than size.

### Hierarchy
- **Headline** (650, 1.375rem, 1.2, −0.01em): one per page, the page title ("Needs you").
- **Title** (600, 1rem): card headers. **Title-sm** (600, 0.875rem): sub-sections.
- **Body** (400, 14px / 1.45). **Body-sm** (0.8125rem): row context, buttons, tables, notices.
- **Label** (550, 0.75rem): chips, field labels, table heads, legends, the StaleNote line.
- **Tab label** (500, 0.6875rem): bottom tabs only.

**The Tabular Rule.** Every number that can be compared (counts, money, times, right-aligned table cells) uses `tabular-nums`.

## Layout

- **Shell.** Below 1024px: a top bar (brand, + Note, Sign out), a single column `max-width: 28rem` with 0.75rem side padding and a 0.75rem gap, and fixed bottom tabs (Home, Review, Accounts, Results, More) with count dots. At ≥1024px: a fixed 14rem sidebar (8 primary items, a "More" group: Personas, Jobs, Decisions, Desk, Funnel, Settings), main `max-width: 72rem`, 2rem padding, 1.5rem gap. There is one breakpoint, **1024px**.
- **Splits.** `split` is 1.6fr / 1fr on laptop (list left, context right). `grid-2` and `grid-3` stack on the phone.
- **The Min-Width Rule.** Every grid track is `minmax(0, 1fr)` and every grid child gets `min-width: 0`, so long handles truncate instead of blowing out the phone column.
- **Phone vs laptop.** Same content, re-flowed. Tables become stacked rows (`only-lg` / `only-sm`). Row actions move under the text on the phone and to a right column on the laptop. Act's Reject / Approve bar sticks above the tabs, within thumb reach. Sticky side panels (Produce summary, Style preview) apply on laptop only. Phone review opens each item in `/act` (no batch bar).
- **Rhythm.** Steps of 0.25 / 0.5 / 0.75 / 1 / 1.5 / 2 rem. Rows use about 0.6–0.8rem vertical padding with 1rem sides.

## Elevation & Depth

Flat. Depth comes from tonal layering (card above page in dark mode) and 1px hairlines. Exactly two shadows exist, both functional: the chart tooltip (`0 4px 14px oklch(0 0 0 / 0.12)`) and the switch thumb (`0 1px 2px oklch(0 0 0 / 0.25)`).

**The Flat-At-Rest Rule.** Cards, buttons and notices never cast shadows. Only floating or physical things do (the tooltip, the switch thumb).

## Shapes

- `--radius` 0.625rem: cards, notices, the video.
- `radius × 0.8` (0.5rem): buttons, inputs, the dial, sidebar links.
- 0.375rem: skeleton blocks, slot pills.
- Pill: chips, meters, switches, counts.

Borders are 1px hairlines. The 9:16 video frame is the only fixed silhouette.

## Components

- **Card:** a hairline border with `lg` radius. Header `0.875rem 1rem 0.5rem` (title left, quiet "▸" link right), body `0 1rem 1rem`. `flush` lists run edge to edge with dividers.
- **Buttons:** 2rem minimum height (lg 2.75rem for touch-primary actions). Variants:
  - default: outlined, hover `muted`
  - primary: ink, hover 0.9 opacity
  - danger: critical text
  - ghost: no border
  - disabled: 0.5 opacity

  Each row has at most one primary button.
- **Chips:** outlined quiet (default), `solid` (muted fill), and `good` / `warning` / `critical` / `info` (role text on wash, no border).
- **Switch:** 2.25×1.3rem pill. On fills with `foreground`; the thumb slides 160ms `cubic-bezier(0.2,0.8,0.2,1)`. Uses `role="switch"`.
- **Review dial:** a three-stop segmented radiogroup (`review · sample · auto`) with no Off stop (the gate always runs). The selected stop inverts to ink. Each control carries a "waiting on" line beneath it.
- **Meter:** a 0.5rem pill track. The fill is `foreground`, the done part runs at 0.35 opacity, and the fill turns `warn` / `over` at budget limits. It carries `role="meter"` with values, and a figure plus a sentence sits above it.
- **Notice:** glyph plus text on a role wash (`warning`, `critical`, `info`) with a bold lead clause and an inline action.
- **Needs-me row:** a status glyph column (1.5rem), a bold "verb: object" line, and a quiet context line (account · cause · deadline). Actions follow (one primary), then a `~N min` cost. Rows are grouped under "Now (pushed to Telegram)" and "Today (from the 09:00 digest)".
- **Tabs + More:** underline tabs (`seg`, 2px `foreground` underline, horizontally scrollable, no scrollbar). Overflow tabs collapse into a borderless "More" select.
- **Tables / stacked rows:** laptop tables use 0.75rem label heads, hairline rules, a muted 60% hover, and right-aligned tabular numbers. The phone gets the same data as divided list rows: a bold handle, then a wrapping line of quiet numbers.
- **Video placeholder:** 9:16, `lg` radius, dark blue-grey gradient. It shows the product's own caption look (heavy uppercase, black halo, key word `#ffd400`, title top, captions above the bottom 20%). It is shown at about 42vh on Act.
- **Skeleton:** `muted` blocks in the final layout. They pulse at 1.4s, and the pulse stops under `prefers-reduced-motion`.
- **Empty state:** centered, a 1rem/600 sentence ("Nothing needs you."), one quiet line saying what fills the page or what unlocks it, and at most one button.
- **Type tabs (account workspace):** the shared core tabs plus each type's own, in one underline row that wraps to two rows below 1024px; a type tab never renames a core tab. In the mockups the top bar's Type select switches types (`[data-type]` blocks; mockup only, like `data-when`); the build reads the account's `kind`.
- **Persona card:** a 4:5 face thumb, name, role and niche, a status chip, a short key–value list (voices, consistency, looks), the served accounts as chips, and the unrelated-niche warning as a notice inside the card.
- **Step list (creation flows):** numbered circles (done ✓, current inverted to ink), each step with its cost in tabular figures; sticky on a laptop, a compact numbered row on a phone; the running cost sits in the footer next to Back and the next step's verb.
- **StaleNote:** S3a's component, one quiet 0.75rem line at the top of `main` with `role="status"`: "Updated 6 min ago · retrying every 15 s. Actions still work; each one is re-checked when you tap it."

### States
- **live:** "updated 12 s ago" sits in the page subtitle.
- **loading:** skeletons in the final layout, never a centered spinner.
- **error:** a critical notice naming what failed **and what still works** ("The brake still works from Telegram (`/pause all`)"), plus Retry. Old numbers are never shown as current.
- **stale:** the StaleNote line alone. **Nothing dims**, and actions stay enabled at full contrast. The server re-checks each action (409 with the current state).
- **empty:** see the empty state above.
- **Page-specific:**
  - Home: over budget (the meter turns red, plus a promotion notice)
  - Act: spend row, promotion, already handled, not found
  - Review: before S2 (the queue manager)

### Charts (dataviz, as applied in Results)
- One axis per chart, with no dual axes. A cap is a reference line, not a second series.
- Thin marks: 2px lines with round joins, an end dot (r 4) ringed in `card`, and bars on one shared unit axis.
- A recessive grid (`grid`) with a stronger baseline (`axis`), and 11px quiet tick text.
- A legend above every chart, plus selective direct labels at line ends in `foreground` 600. On narrow widths the end labels shrink to the value only.
- A crosshair or per-mark tooltip on pointer **and** keyboard (focusable hit area, ←/→). Tooltips are built with `textContent`, never `innerHTML`.
- "Show as a table" (`details`) under every chart.
- Charts are plain SVG sized from the container's `clientWidth` (height steps down below 560px) and redrawn on resize, with `role="img"` and a sentence-length `aria-label`.

### Sidebar foot: the brake and Sign out
The sidebar foot pins a quiet status line ("Brake: all accounts running"), a default (not danger) **Pause all** button (the fleet scope of the one brake, spec §2.6/S2, the same key as `/pause all`), then **Sign out** as a quiet ghost link below it. On the phone, Sign out sits in the top bar and the brake stays in Telegram (`/pause all`) and on each account's header (Pause this account).

### Build mapping (S3, `web/`)
- **Lift as-is:**
  - the `:root` / dark token blocks (status roles, washes, series, grid/axis, the 0.50/0.72 muted-foreground) into `globals.css`
  - `statusColors.ts`, `StaleNote`
  - the shell breakpoints and widths
  - the chart helpers' approach (SVG, CSS-var colors, `textContent` tooltips, table view)
- **Re-implement with shadcn:**
  - Card, Button (variants above), Badge for chips
  - Switch, ToggleGroup for the dial, Tabs (+ a Select for More)
  - Table, Skeleton, Alert for notices
  - Progress or a small custom meter keeping `role="meter"`
  - Tooltip only outside charts
- **Do not ship:** the mockup bar, `[data-when]` and `[data-type]` switching, and `shell.js`.

## Do's and Don'ts

### Do:
- **Do** name the verb on every action: "Approve $2.08", "Reconnect", "Review the promotion", "Start with the first row ▸". Never "OK" or "Submit".
- **Do** make every error say what still works, and every empty state say what fills or unlocks the page.
- **Do** suffix all sample handles with `.demo` and label sample data in a quiet footer line.
- **Do** show the time and money cost before a commitment (the row's `~N min`, the batch estimate against the cap).
- **Do** keep focus visible: a 2px `ring` outline, offset 2px.

### Don't:
- **Don't** build hero-metric tiles or big-number scoreboards. The fleet is dense rows, and the only large figure is the attention meter's minutes.
- **Don't** use eyebrows (small uppercase kickers above titles).
- **Don't** use modals for routine tasks. Decisions happen in place or on `/act`; the mockups contain no dialogs.
- **Don't** use browser push. Telegram is the only push channel (ADR-44/45).
- **Don't** dim stale content or disable its actions.
- **Don't** let color alone carry a status, a series or a post state.
