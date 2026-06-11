# Fresu Electronics — Engineering Blog

Technical blog by **Dario Fresu**, Principal EMC Architect.  
Live at: **[blog.fresuelectronics.com](https://blog.fresuelectronics.com)**

Migrated from the Wix blog at `fresuelectronics.com/blog` — see `MIGRATION.md` for the full plan, manifest (90 posts), and status.

## Posts

| Slug | Title | Tier |
|---|---|---|
| `/emc-mental-model` | Why Your Team Keeps Failing EMC Tests | Original |
| `/why-engineers-fail-emc` | Why Smart Engineers Fail EMC Tests | Standard |
| `/field-centric-charge-energy` | A Field-Centric View of Energy Transfer | Standard |
| `/pcb-stackup-power-return-path` | PCB Stackup Design: Power & Return Paths | Standard |
| `/emc-filter-topologies` | EMC Filter Topologies | Standard |
| `/emi-signal-return-currents` | Low & High-Speed Signal Return Currents | Standard |
| `/pcb-90-degree-bends` | 90-Degree Bends in PCB Design | Standard |
| `/redefining-current-charge` | Redefining Current and Charge | Standard |
| `/emc-current-clamps` | Radiated Emissions Testing & EMC Current Clamps | Standard |
| `/electromagnetic-fields-pcb` | Electromagnetic Fields in a PCB | Standard |
| `/emi-design-review-pcb` | How to Conduct an EMI Design Review | Deep Dive (23 min) |
| `/radiated-emissions` | Understanding Radiated Emissions | Deep Dive (24 min) |
| `/conducted-emissions` | Conducted Emissions | Deep Dive (17 min) |
| `/esd-electrostatic-discharge` | Understanding ESD | Deep Dive (28 min) |
| `/pdn-low-emi` | Power Delivery Network (PDN) for Low EMI | Deep Dive (17 min) |
| `/pcb-review-mppt-charge-controller` | MPPT Charge Controller Layout Review | Deep Dive (17 min) |
| `/pcb-review-imx8-som` | i.MX8 SOM EMI Layout Review | Deep Dive (20 min) |

## Structure

- Each post lives in its own folder as `index.html`; blog index at root `index.html` (topic filters + search).
- Images: `assets/images/<slug>_imgNN.<ext>` and `<slug>_cover.<ext>` — originals downloaded from Wix at full resolution.
- Long-form posts use `templates/pillar-post.html` (sticky TOC + scrollspy, reading progress bar, figure lightbox, JSON-LD).
- Interactive tools live in `tools/`.

## Adding a Post

1. Copy `templates/pillar-post.html` to `[post-slug]/index.html` and fill every `{{PLACEHOLDER}}`
2. Put images in `assets/images/` following the naming convention
3. Add a card to root `index.html` (with `data-topics`, and `data-deep="1"` for 15+ min reads)
4. Update `MIGRATION.md` if the post comes from the Wix blog

## Custom Domain

`blog.fresuelectronics.com` → DNS CNAME → `dariofresu.github.io`
