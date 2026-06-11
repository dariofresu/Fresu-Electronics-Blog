# Wix → blog.fresuelectronics.com Migration Plan

Source: `www.fresuelectronics.com/blog` (Wix, site ID `7a4f9da8-b132-4f18-a054-4d48c5df90f8`)
Target: this repo → GitHub Pages → `blog.fresuelectronics.com`
Inventory date: 2026-06-11 — **90 published posts on Wix**, 10 migrated so far (+1 original post `emc-mental-model` written directly for the new blog).

---

## 0. Audit findings (current state)

- **8 of the 10 migrated posts are missing their original figures.** Images were downloaded to `assets/images/` with the `<slug>_imgNN` convention but never embedded in the article body — only a new custom hero image is shown. Affected: `electromagnetic-fields-pcb` (9 figures), `emc-filter-topologies` (9), `emi-design-review-pcb` (5), `emi-signal-return-currents` (12), `field-centric-charge-energy` (15), `pcb-90-degree-bends` (9), `pcb-stackup-power-return-path` (7), `why-engineers-fail-emc` (1).
- `emc-current-clamps` (11 figures) and `redefining-current-charge` (12 figures) embed the original images correctly — use these as the reference pattern.
- Titles of migrated posts were editorially rewritten; body text policy is **verbatim** (see commit "Fix: verbatim content, remove fabricated cover image").

**Phase 0 (before migrating anything new): repair the 8 posts above by embedding the already-downloaded figures in their correct positions, with original captions and alt text.**

## 1. Lossless extraction pipeline (per post)

1. **Export** — `GET https://www.wixapis.com/blog/v3/posts/{id}?fieldsets=RICH_CONTENT` returns the Ricos JSON document: every paragraph, heading, list, divider, image node (with caption + alt), video/embed node, in order. This is the source of truth, not the rendered page.
2. **Images** — for every image node, download the original file from `static.wixstatic.com` (strip Wix transformation params to get full resolution) → `assets/images/<new-slug>_imgNN.<ext>`. Cover image → `<new-slug>_cover.<ext>`. Record alt text and captions in a sidecar manifest.
3. **Convert** — Ricos JSON → semantic HTML (`<figure>/<figcaption>`, real headings, lists). Body text stays **verbatim**; only the title/deck may be editorially improved.
4. **Metadata preserved**: original title, publish date, read time, tags/categories, SEO description, original Wix URL (kept as `data-source-url` and in the redirect map).
5. **QA parity gate** (scripted, per post, before it goes in the index):
   - embedded `<img>` count == image-node count in Ricos JSON
   - body text length within ±2% of Wix `contentText`
   - all image files exist in `assets/images/` and are referenced
   - title/date/read-time present; no broken internal links
6. **SEO continuity** — maintain `redirects.json` (old `fresuelectronics.com/post/<slug>` → `blog.fresuelectronics.com/<new-slug>`), set `rel=canonical` on the new posts, JSON-LD `BlogPosting`, OG/Twitter cards.

## 2. Information architecture (content tiers)

The 90 posts are not one homogeneous blog — they fall into three tiers that deserve different treatment:

| Tier | Count | Definition | Treatment |
|---|---|---|---|
| **Pillar guides** | 7 | 15–28 min deep dives (Radiated Emissions, ESD, Conducted Emissions, PDN, EMI Design Review, MPPT review, i.MX8 review) | Full template: sticky TOC, reading progress, section anchors, inline tools |
| **Standard articles** | ~42 | 4–11 min topical posts | Standard post template, related-posts block, one inline tool/diagram where relevant |
| **Micro-notes** | ~40 | 1–3 min posts (mostly Sep–Nov 2024, LinkedIn-style) | Dedicated **"Notes"** section — card grid, image-forward, no TOC. Don't dilute the main feed with these |
| Special | 1 | Italian beginner guide | `/it/` path or `lang` badge; hreflang pair with the English version |

Navigation: topic clusters (Stackup & Layout · Return Currents & Grounding · Filtering & PDN · Emissions & Testing · ESD · Fundamentals · Design Reviews) as filterable tags on the index, plus "series" prev/next links inside clusters.

## 3. UX/UI improvements (post template)

- Sticky table of contents + reading-progress bar on pillar posts
- `<figure>` with captions, click-to-zoom lightbox, lazy loading, width/height attributes (no CLS)
- Callout components: "Rule of thumb", "Common mistake", "Standard reference" (IPC/CISPR/EN)
- KaTeX for equations (several posts have formulas rendered as images on Wix — keep image AND add real math where feasible)
- Related posts by tag at article end; course CTA (already in assets) kept but moved below content
- Dark/light theme, consistent with existing brand styling

## 4. Interactive artifacts & tools (the "improve" part)

Build on the existing `tools/emc-fundamentals` pattern; each tool lives in `tools/<name>/` and is embedded inline in the related posts:

| Tool | Embedded in posts about |
|---|---|
| **Stackup Explorer** — drag layers, see return-path quality score | stackup posts (6+ posts) |
| **Return-Current Visualizer** — frequency slider showing current distribution under a trace | return path / grounding posts |
| **Filter Topology Selector** — source/load impedance → recommended C/L/π/T topology | filter posts |
| **PDN / decoupling impedance calculator** | PDN & decoupling posts |
| **dBµV ⇄ dBm ⇄ V converter with CISPR 32 limit lines** | conducted/radiated emissions posts |
| **Microstrip/stripline impedance calculator** | impedance & signal propagation posts |
| **Crosstalk estimator** (spacing/height ratio) | crosstalk posts |
| **Creepage & clearance lookup (IPC-2221)** | creepage post |

## 5. Rollout order

1. **Phase 0** — repair images in the 8 already-migrated posts (no new content).
2. **Phase 1** — 6 remaining pillar posts (ESD, Radiated Emissions, Conducted Emissions, PDN, MPPT review, i.MX8 review).
3. **Phase 2** — standard articles, newest first (the 2025 series).
4. **Phase 3** — micro-notes as the "Notes" section, batched.
5. **Phase 4** — tools, one per topic cluster, embedded retroactively.

Each phase = one PR: posts + index update + QA report.

---

## Full manifest (90 Wix posts)

Status: ✅ migrated (images OK) · ⚠️ migrated, figures not embedded · ⬜ to migrate · 📝 micro-note (Phase 3)

| Date | Min | Wix slug | Status → target folder |
|---|---|---|---|
| 2025-06-24 | 7 | why-smart-engineers-fail-emc-tests-it-s-not-what-you-think | ⚠️ `why-engineers-fail-emc` |
| 2025-05-25 | 4 | a-field-centric-perspective-on-charge-and-energy-transfer-in-classical-electromagnetism | ⚠️ `field-centric-charge-energy` |
| 2025-05-17 | 8 | optimizing-pcb-stackup-design-power-and-return-path-considerations | ⚠️ `pcb-stackup-power-return-path` (verify source mapping vs power-planes post below) |
| 2025-05-12 | 7 | emc-filter-topologies-emi-control-strategies-in-electronics-design | ⚠️ `emc-filter-topologies` |
| 2025-05-07 | 8 | current-return-path-high-speed-vs-low-speed-signals | ⚠️ `emi-signal-return-currents` |
| 2025-05-02 | 8 | 90-degree-bends-in-a-pcb-design | ⚠️ `pcb-90-degree-bends` |
| 2025-04-27 | 6 | emc-design-for-multilayer-pcb-be-aware-of-using-power-planes-as-return-reference-planes | ⬜ (may overlap with `pcb-stackup-power-return-path` — verify) |
| 2025-04-23 | 7 | mastering-electromagnetic-interference | ⬜ |
| 2025-04-20 | 11 | redefining-current-and-charge-a-field-based-perspective-on-electromagnetism | ✅ `redefining-current-charge` |
| 2025-04-17 | 6 | why-ground-falls-short-a-call-for-a-clearer-term-in-circuit-design | ⬜ |
| 2025-04-14 | 7 | understanding-emc-current-clamps-a-key-tool-for-assessing-radiated-emissions | ✅ `emc-current-clamps` |
| 2025-04-13 | 6 | understanding-en-61000-4-6-a-key-standard-for-conducted-rf-immunity-in-emc-design | ⬜ |
| 2025-04-12 | 6 | how-return-reference-planes-impact-emi-control-in-pcb-design | ⬜ |
| 2025-04-11 | 4 | the-essentials-of-electromagnetic-compatibility-training | ⬜ |
| 2025-04-10 | 6 | the-pitfalls-of-overreliance-on-post-design-fixes-in-electromagnetic-compatibility-compliance | ⬜ |
| 2025-04-08 | 4 | mastering-pcb-design-with-ipc-2221-the-industry-s-foundational-standard | ⬜ |
| 2025-04-06 | 8 | signal-integrity-the-key-to-emc-compliance-for-electronic-engineers | ⬜ |
| 2025-04-05 | 7 | why-emi-keeps-ruining-your-pcb-designs-and-what-to-do-before-it-s-too-late | ⬜ |
| 2025-04-04 | 7 | optimizing-pcb-layout-for-emi-control | ⬜ |
| 2025-04-03 | 4 | input-filter-design-emc-compliance-for-power-converters | ⬜ |
| 2025-04-02 | 4 | mastering-pcb-design-tips-for-beginners | ⬜ |
| 2025-03-28 | 5 | your-first-steps-in-pcb-design-a-beginner-s-guide | ⬜ |
| 2025-03-28 | 5 | progettazione-di-schede-a-circuito-stampato-pcb-una-guida-per-principianti | ⬜ Italian — `/it/` |
| 2025-03-27 | 4 | the-role-of-emi-specialists-in-ensuring-compliance | ⬜ |
| 2025-03-26 | 5 | understanding-emi-and-emc-in-electrical-systems | ⬜ |
| 2025-03-21 | 5 | understanding-the-significance-of-radiated-emissions-emi-control-in-achieving-emc-compliance | ⬜ |
| 2024-11-19 | 23 | pcb-design-review-for-low-emi-motherboard-design | ⚠️ `emi-design-review-pcb` |
| 2024-11-19 | 4 | how-do-signals-propagate-in-a-printed-circuit-board-pcb | ⬜ |
| 2024-11-19 | 17 | conducted-emissions | ⬜ pillar |
| 2024-11-18 | 6 | the-concept-of-electromagnetic-fields-in-a-pcb | ⚠️ `electromagnetic-fields-pcb` |
| 2024-11-18 | 10 | pcb-design-for-low-emi-differential-mode-vs-common-mode-currents | ⬜ |
| 2024-11-18 | 24 | radiated-emissions | ⬜ pillar |
| 2024-11-18 | 17 | pcb-design-power-delivery-network-pdn-for-low-emi | ⬜ pillar |
| 2024-11-18 | 28 | esd-electrostatic-discharge | ⬜ pillar |
| 2024-11-18 | 6 | introduction-to-electromagnetic-compatibility-emc | ⬜ |
| 2024-11-18 | 7 | what-is-impedance | ⬜ |
| 2024-11-18 | 5 | electromagnetic-fields-in-a-two-layer-pc-board | ⬜ |
| 2024-11-17 | 1 | mastering-emi-control-in-pcb-design-decoupling-strategies-for-pdn | 📝 |
| 2024-11-17 | 1 | failing-to-manage-emi-begins-with-the-pcb-stackup | 📝 |
| 2024-11-16 | 1 | mastering-emi-control-in-pcb-design-how-to-design-pcbs-for-low-emi | 📝 |
| 2024-11-16 | 17 | pcb-layout-review-for-emc-and-signal-integrity-mppt-charge-controller | ⬜ pillar |
| 2024-11-16 | 1 | mastering-emi-control-in-pcb-design-crosstalk-prevention-for-better-emi | 📝 |
| 2024-11-16 | 20 | i-mx8-som-emi-design-layout-review | ⬜ pillar |
| 2024-11-13 | 9 | fundamentals-of-pcb-design-for-emc-emi | ⬜ |
| 2024-11-03 | 3 | understanding-the-role-of-electronics-in-modern-engineering | 📝 |
| 2024-11-02 | 4 | how-open-hardware-is-transforming-the-tech-world | ⬜ |
| 2024-11-01 | 3 | decoupling-strategies-for-emc-design | 📝 |
| 2024-11-01 | 5 | how-to-avoid-signal-crosstalk | ⬜ |
| 2024-11-01 | 4 | the-role-of-stitching-vias-in-layer-transitions-of-pcb-stackups-and-emi | ⬜ |
| 2024-10-31 | 5 | step-by-step-guide-to-mastering-pcb-design | ⬜ |
| 2024-10-18 | 2 | is-this-the-best-choice-to-avoid-emi-in-your-pcb | 📝 |
| 2024-10-16 | 1 | how-to-choose-the-stackup-for-emc-design | 📝 |
| 2024-10-15 | 1 | gnd-connections-in-a-pcb | 📝 |
| 2024-10-11 | 2 | the-problem-with-routing-over-power-planes | 📝 |
| 2024-10-10 | 2 | 2-layers-board-stackup-for-low-emi | 📝 |
| 2024-10-08 | 1 | mastering-emi-control-in-pcb-design-component-placement-for-emc | 📝 |
| 2024-10-07 | 1 | mastering-emi-the-key-to-successful-pcb-design | 📝 |
| 2024-10-04 | 1 | you-don-t-have-to-be-10-years-into-pcb-design-to-become-an-emi-specialist | 📝 |
| 2024-10-03 | 2 | 5-simple-steps-to-avoid-emi-in-your-pcb-design | 📝 |
| 2024-09-29 | 1 | this-is-why-you-keep-failing-emi | 📝 |
| 2024-09-25 | 1 | does-electricity-work-like-water-in-the-pipes | 📝 |
| 2024-09-23 | 1 | pcb-design-for-low-emi-in-practice-ground-is-the-place-where-potatoes-and-carrots-thrive | 📝 |
| 2024-09-18 | 2 | don-t-rely-too-much-on-your-emi-filters | 📝 |
| 2024-09-13 | 2 | the-real-job-of-a-pcb-designer-controlling-electromagnetic-energy | 📝 |
| 2024-09-10 | 1 | emi-how-an-invisible-force-challenges-the-very-essence-of-pcb-design | 📝 |
| 2024-09-10 | 2 | maximising-the-value-of-the-schematics | 📝 |
| 2024-09-10 | 1 | common-mode-currents-what-a-nightmare | 📝 |
| 2024-09-10 | 2 | want-to-pass-emc-tests-avoid-this | 📝 |
| 2024-09-10 | 4 | creepage-and-clearance | 📝 |
| 2024-09-10 | 1 | low-emi-layer-stackup-tips-picture-this-first | 📝 |
| 2024-09-10 | 2 | two-layers-pcbs-be-aware-of-this | 📝 |
| 2024-09-10 | 2 | capacitors-choice-in-high-frequency-emi-issues | 📝 |
| 2024-09-10 | 1 | transitioning-stitching-vias-emc-simulations | 📝 |
| 2024-09-10 | 1 | the-most-important-picture-you-need-to-see-in-emi | 📝 |
| 2024-09-10 | 2 | emc-common-mode-currents-through-parasitic-paths | 📝 |
| 2024-09-10 | 1 | emc-design-in-practice-conducted-emissions | 📝 |
| 2024-09-10 | 2 | emc-in-practice-conducted-emissions-smps | 📝 |
| 2024-09-10 | 2 | digital-signals-harmonics-in-emc | 📝 |
| 2024-09-10 | 2 | radiations-from-differential-mode-currents | 📝 |
| 2024-09-10 | 1 | shielding | 📝 |
| 2024-09-10 | 2 | radiations-from-differential-mode-currents-ribbon-cables | 📝 |
| 2024-09-10 | 2 | two-layers-stackup-with-both-signals-layers | 📝 |
| 2024-09-10 | 1 | electrostatic-discharge-esd | 📝 |
| 2024-09-10 | 2 | radiations-from-common-mode-currents-in-pcbs | 📝 |
| 2024-09-10 | 1 | subtle-design-mistakes-in-emc | 📝 |
| 2024-09-10 | 2 | esd-chassis-and-parasitic-capacitance | 📝 |
| 2024-09-10 | 2 | how-to-choose-the-stackup-of-the-board | 📝 |
| 2024-09-10 | 2 | signal-propagation-in-a-pcb | 📝 |
| 2024-09-10 | 1 | radiated-emissions-and-current-loops | 📝 |
| 2024-09-10 | 2 | how-to-reduce-crosstalk-in-our-pcb-and-reduce-emi | 📝 |
