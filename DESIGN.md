# Design system

## Direction

Spoke & Spanner is a daylight service workbench: a fixed request area beside a larger evidence-and-draft area. Familiar controls and direct language support an associate answering one question at a time. The working assumption is a small desktop or tablet in a bright repair shop; narrow screens stack the same tasks vertically.

The visual reference is the clarity of a bicycle route cue sheet, translated into a web application rather than imitated as paper. The signature is a consistent fact/source pair: the plain-language observation on the left and its exact source ID on the right. Mobile moves the ID under its fact, preserving the relationship.

## Tokens

| Role | Value |
| --- | --- |
| Text and header | `#193445` |
| Secondary text | `#526573` |
| Page ground | `#eef3f5` |
| Request panel | `#e6eff1` |
| Content | `#ffffff` |
| Rules | `#cbd7dc` |
| Primary action | `#176451` |
| Action hover | `#104b3d` |
| Warning text / surface | `#79520d` / `#fff5dd` |
| Error text | `#983d30` |
| Keyboard focus | `#a85200` |

Type uses the operating system's UI stack, with Segoe UI first where present. Body: 16 px / 1.55. Page title: 28 px / 1.2, reducing to 24 px on narrow screens. Section heading: 19 px. Labels and compact controls: 14 px. Small metadata: 12–13 px. No downloaded fonts or display assets.

Main spacing uses 4, 8, 12, 16, 20, 24, 28, 32, and 36 px. Control corners are 5 px; the outer workspace is 8 px. Separation is achieved through space, background, and one-pixel rules, without decorative shadows.

## Interaction and states

- Buttons have at least 44 px height; keyboard focus uses a visible 3 px outline.
- Result stages are records, unresolved items, draft, then expandable technical detail.
- Initial state explains the task. Busy state disables duplicate submissions and shows stable placeholders. Errors preserve the question and identify the next action.
- Ambiguous results expose exact-ticket buttons. Each issues a new explicit question; the app does not guess.
- Copy feedback reports success or selects the draft for manual copying. There is no send action.
- Mode selection is explicit; result labels report the mode that produced that result.
- Color is supported by text labels, including warnings and failures.
- Hover transitions last 160 ms and disappear under reduced-motion preference. There is no decorative animation.
- At 760 px and below, the request and results stack; long trace text wraps within an independently scrollable preformatted area.

## Verification limits

The source implements these rules. Automated checks cover the HTTP surface and JavaScript syntax. No browser, screenshots, visual inspection, keyboard walkthrough, or assistive-technology test was used. These remain verification tasks, not implied passes.
