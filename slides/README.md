# NEXUS — Hackathon Presentation Deck

This folder contains the 10-slide pitch deck for the Kite AI Global Hackathon 2026 submission, written as Marp-compatible markdown so you can export to PowerPoint, PDF, or HTML in one command.

## What's here

| File | Purpose |
| --- | --- |
| `nexus-deck.md` | The 10-slide deck — full content, design tokens, and Marp directives baked in |
| `README.md` | This file — three ways to turn the markdown into a real .pptx |

---

## Three ways to turn this into a real PowerPoint

### Option A — Use Marp CLI (fastest, recommended for the .pptx export)

Marp is the de-facto markdown→slides tool. One command turns `nexus-deck.md` into a `.pptx`.

```bash
# Install once (needs Node.js 18+)
npm install -g @marp-team/marp-cli

# Export to PowerPoint
marp nexus-deck.md -o nexus-deck.pptx

# Or to PDF
marp nexus-deck.md -o nexus-deck.pdf --pdf

# Or to a single-file HTML deck you can present from a browser
marp nexus-deck.md -o nexus-deck.html
```

The CSS styling (dark mode, Kite gradient, font sizing) is embedded at the top of `nexus-deck.md` — Marp will respect it on export.

### Option B — Use the VS Code Marp extension (visual preview)

1. Install the **"Marp for VS Code"** extension by marp-team.
2. Open `nexus-deck.md` — a live preview button appears at the top right.
3. Right-click in the editor → **"Export slide deck"** → choose `.pptx` or `.pdf`.

Best for tweaking content while seeing the slides update live.

### Option C — Manual paste into Google Slides or PowerPoint

If you'd rather skip the CLI entirely:

1. Open a new Google Slides deck (recommended — dark theme matches our design).
2. For each slide in `nexus-deck.md`:
   - Read the `## Subheader` and `# Big Header` lines — those go at the top of the slide.
   - The bullets / table / numbered list go in the body.
   - Use **Inter** or **Space Grotesk** for headings, plain sans-serif body.
   - Use the Kite brand palette: background `#0E0E10`, accent gold `#FCD34D`, accent orange `#E86F2C`, accent blue `#2563EB`.
3. Slide 1 (title) should be visually arresting — centered headline + tagline + live URL.
4. Slide 6 (architecture) — the ASCII diagram in the markdown is best replaced with a real diagram in your slide tool (use Google Slides' shape tools or import from Excalidraw / Mermaid).

---

## Slide-by-slide content map

| # | Title | Key message |
| --- | --- | --- |
| 1 | NEXUS (Title) | Project name + tagline + live URL + chain |
| 2 | The Problem | Agents work alone today — no shared identity / payments / rules / reputation |
| 3 | Why Now | Kite gives the 4 missing primitives; NEXUS is the first to wire them together |
| 4 | The Solution | 11 agents, 23 capabilities, open marketplace, autonomous trigger |
| 5 | Traction | Real stats: 1,293 tx, $0.1487, 906 autonomous runs, 76 tests |
| 6 | How it works | 8-step pipeline diagram from query → on-chain audit trail |
| 7 | Autonomy | Market Pulse runs every hour with no human in the loop |
| 8 | DevEx | New agent joins in 1 API call — any language, no code review |
| 9 | Differentiation | Side-by-side vs LangChain / ChatGPT Plugins / Coinbase AgentKit |
| 10 | Vision + Close | Roadmap (now / +30 / +60 / +90 / mainnet) + final URL & GitHub |

---

## Suggested visuals to add per slide

| Slide | What to drop in |
| --- | --- |
| 1 | NEXUS logo from `frontend/src/components/ui/NexusLogo.tsx` (export as PNG at 512px) |
| 5 | Screenshot of `/pulse` page showing the live runs table — crop to ~5 rows |
| 6 | Build a clean architecture diagram in Excalidraw / Figma — much cleaner than ASCII |
| 7 | Screenshot of `/pulse` with one row expanded showing the ECDSA signature + payment table |
| 8 | Screenshot of the `+ Register Agent` modal on the dashboard |
| 9 | Keep the comparison table as a table — judges read tables faster than prose |
| 10 | QR code generated from `https://44-215-246-131.nip.io` (use any QR generator) |

---

## Final delivery checklist

- [ ] Convert `nexus-deck.md` to `nexus-deck.pptx` (Option A or B above)
- [ ] Open in PowerPoint, verify all slides render correctly
- [ ] Add screenshots from the suggestions above
- [ ] Add a QR code to slide 10 for easy phone-scanning by judges
- [ ] Export a PDF backup (`nexus-deck.pdf`) and commit it next to this README
- [ ] Submit the `.pptx` or `.pdf` link in the Encode submission form

Done.
