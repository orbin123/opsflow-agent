# OpsFlow Design System

**Figma source:** [OpsFlow — Terminal Light Design System](https://www.figma.com/design/p0ZCdLGLjcAUxNV80JJqyM/OpsFlow-%E2%80%94-Terminal-Light-Design-System)

Use this reference for every OpsFlow frontend design or UI implementation. Figma contains three pages: **01 · Foundations**, **02 · Components**, and **03 · Console example**. The console is an editable example built from local component instances and variables.

## Direction

Give OpsFlow the character of a precise operations terminal with the clarity of a light workspace. Use cool gray surfaces, charcoal text, cyan for important actions, rectangular geometry, thin outlines, and restrained terminal details. Keep the interface calm and readable: no dark navy canvas, unnecessary glow, animated flicker, or decorative texture behind reading content.

The reference screenshot's exact typeface is unknown. **VT323** is the selected visual approximation for its pixel-terminal headings and action labels. Pair it with **IBM Plex Mono** for body copy, labels, logs, and metadata. These fonts are present in the Figma design; confirm their availability in the product runtime before implementation and provide suitable monospace fallbacks.

## Color palette

| Role | Token | Value | Use |
|---|---|---:|---|
| Canvas | `color/bg/canvas` | `#EEF1F2` | App background |
| Surface | `color/bg/surface` | `#FAFCFC` | Panels, fields, cards |
| Subtle surface | `color/bg/subtle` | `#DFE6E8` | Dividers, disabled controls, trace panels |
| Primary text | `color/text/primary` | `#17292E` | Main text and icons |
| Secondary text | `color/text/secondary` | `#4F666D` | Supporting text and metadata |
| Links / focus | `color/text/link`, `color/border/focus` | `#126479` | Links, keyboard focus |
| Control border | `color/border/control` | `#6B8087` | Input and secondary control outlines |
| Primary action | `color/action/primary` | `#79D9ED` | Main buttons, selected action |
| Action hover | `color/action/hover` | `#52CADE` | Hover state |
| Action pressed | `color/action/pressed` | `#33B7CF` | Pressed state |
| Action tint | `color/action/tint` | `#DDF6FB` | Quiet hover and status emphasis |
| Success | `color/status/success` / `color/status/success-bg` | `#22654C` / `#E4F2EA` | Completed / ready |
| Warning | `color/status/warning` / `color/status/warning-bg` | `#805300` / `#FFF1CD` | Pending / scheduled |
| Error | `color/status/error` / `color/status/error-bg` | `#A23438` / `#FBE9E9` | Failure and validation |

Primitive color variables also include gray steps `#FAFCFC`, `#EEF1F2`, `#DFE6E8`, `#C8D3D6`, `#6B8087`, `#4F666D`, `#17292E`; cyan steps `#DDF6FB`, `#79D9ED`, `#52CADE`, `#33B7CF`; teal `#126479`; and the semantic status colors above. Semantic variables alias primitives so palette updates flow through the system.

Contrast was checked for representative pairs: primary text on canvas 13.28:1, primary text on cyan 9.30:1, secondary text on canvas 5.36:1, focus teal on canvas 5.92:1, and control border on surface 4.03:1. Recheck contrast if colors or font sizes change.

## Typography

| Style | Typeface | Size / line height | Use |
|---|---|---:|---|
| Display | VT323 Regular | 64 / 64 px | Product statement or major greeting |
| Title | VT323 Regular | 40 / 44 px | Page title |
| Heading | VT323 Regular | 28 / 32 px | Panel and section headings |
| Terminal | VT323 Regular | 24 / 28 px | Button labels and short command text |
| Body | IBM Plex Mono Regular | 14 / 24 px | Main content |
| Label | IBM Plex Mono Medium | 12 / 16 px | Form labels, section tags, controls |
| Caption | IBM Plex Mono Regular | 11 / 16 px | Metadata and helper text |

Use sentence case for content and concise uppercase labels for system metadata. Reserve VT323's distinctive pixel treatment for headings and short actions; use IBM Plex Mono for anything users must read in longer passages.

## Proportion and spacing

Use a 4 px spacing rhythm: `4, 8, 12, 16, 24, 32, 48, 64, 80 px`. The Figma `OpsFlow · Geometry` collection also defines 0 and 2 px radii, 1 and 2 px borders, and 20, 40, 48, and 56 px size tokens.

- Desktop reference: 1440 px wide, 12-column grid, 24 px gutters, 48 px outer margin, and a 240 px navigation rail.
- Keep reading content around 640–760 px wide. Forms generally fit a 400–480 px column.
- Mobile reference: 390 px wide, 4 columns, and 16 px outer margin. Stack panels below 768 px and make primary actions full width.
- Keep interactive targets at least 44 px high. Standard fields and buttons are 48 px high.

Treat these as starting layout rules; keep the hierarchy and usable proportions when adapting to other viewport sizes.

## Borders and terminal details

Use square corners (0 px), 1 px outlines and dividers, and 2 px keyboard-focus indicators with a visible offset. Use 16 px horizontal control padding and 8 px between an icon and its label. The primary button specimen uses subtle, static scanlines; keep them low contrast and decorative. Focus must remain visible, and disabled, loading, error, and pending states need clear text as well as color.

## Reusable Figma components

- **Button:** `Primary`, `Secondary`, and `Quiet` styles; `Default`, `Hover`, `Pressed`, `Focus`, `Disabled`, and `Loading` states. Text label, optional icon visibility, and swappable icon are exposed as properties. Use one primary action per panel. Loading indicates that repeat submission is locked.
- **Input:** `Default`, `Filled`, `Focus`, `Error`, and `Disabled` states. Keep the label visible above the field, and use helper text for instructions or validation.
- **Status:** `Ready`, `Pending` (shown as **SCHEDULED**), `Error` (**FAILED**), and `Neutral` (**DRAFT**). Do not imply that a draft was sent or a scheduled task was delivered. Report **SENT** only after delivery is confirmed.
- **Icons:** eight local components: Terminal, Arrow, Plus, Mail, Clock, Check, Alert, and Search. Use a 20 × 20 px grid, 1.5 px square-cap strokes, and a single ink color. Give icon-only controls a 44 × 44 px target and an accessible name.

The Figma components define visual states. Product code still needs to implement the actual interactions, keyboard behavior, accessibility, loading behavior, and delivery status.

## Daily implementation use

For any frontend request, read this document and inspect the linked Figma page relevant to the requested feature. Reuse semantic color and geometry tokens and match the listed text styles and component states. Keep the design-system document and Figma file aligned when the user agrees to a design change. If a requirement conflicts with the existing system or needs a new reusable pattern, explain the specific choice before expanding the system.

This file records a design specification; it does not mean the tokens or components have been implemented in the application. Confirm fonts, colors, sizing, and responsive behavior against the actual frontend stack as part of implementation.

## Streamlit console adaptation

On 2026-10-06 the connected Figma file exposed only **01 · Foundations**; Components
and Console example were unavailable despite the earlier specification above.
The user approved adapting Foundations and these documented rules into a Streamlit
chat/inspector without expanding the Figma system. `ui/console.css` applies the
palette, typography, square geometry, focus indicators and mobile panel stacking.
VT323 and IBM Plex Mono Regular are bundled locally with their SIL licenses;
monospace remains the fallback. Native JSON syntax coloring and framework icons
remain Streamlit defaults. See [streamlit-console.md](streamlit-console.md).

On 2026-10-07, the user requested an intuitive keyword phrase/score table instead of
repeating phrases and raw JSON. The keyword assistant turn uses a native read-only
Streamlit dataframe with Phrase/Score columns, hidden index, literal-text phrases,
and five-decimal score display. Keep YAKE order, the existing font/palette/layout,
and a brief lower-score relevance caption. Raw full-precision JSON stays in the
inspector. This is a keyword presentation correction; no new CSS or Figma component
is introduced, and the general answer/inline-activity redesign remains deferred.


## Workspace navigation adaptation

On 2026-10-08 the user approved step 9's native sidebar title buttons, New chat,
URL restoration, and multiline composer with Send. Figma inspection remains
blocked by the Starter tool-call limit; this adaptation uses the documented
Foundations tokens and step 6 interaction contract, without adding Figma nodes.
Chat controls use 48 px targets and IBM Plex Mono, literal/truncated titles with
full accessible labels, action tint plus a check and Selected chat text. New chat
and Send use VT323 short action labels; Send uses the existing cyan action states.
The native multiline composer uses square surface/control borders. Focus retains
the 2 px indicator. Existing collapsible mobile sidebar and stacked chat/inspector
remain; live Activity and Docs patterns belong to later steps.
