# Brand assets — drop logo files here

The CSS theme already renders an **ARYX** wordmark + tagline in the sidebar
and a brand banner on Home (see `theme.py` → `.aryx-sidebar-mark` and
`.aryx-brandbar`). The wordmark is text — no image required to ship.

To swap the text wordmark for the actual logo image, drop these files here:

| File | Used by | Suggested size |
|---|---|---|
| `aryx_logo.png` | sidebar header | 512×512 (square, transparent bg) |
| `aryx_logo_wordmark.png` | Home page hero | 1200×400 (wide) |
| `aryx_banner.png` | Home banner background | 1920×640 |
| `aryx_favicon.ico` | browser tab | 32×32 (use `app.py` page_icon) |
| `aryx_logo_white.svg` | dark-mode variant | scalable |
| `aryx_logo_dark.svg` | light-mode variant | scalable |

After dropping files, ping the next session: wiring `st.image()` in
`workspace_bar._brand_mark()` and `home_panel.render()` is a 5-minute change.

Until then the text wordmark is used everywhere — works fine for tonight's
demo.
