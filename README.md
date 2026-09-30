# boto-metal

Interactive 3D **boto-aparelhagem** in riveted metal: magenta and steel plates,
copper spine with orange bulbs, glowing eyes and mouth, blue LED fins — with a
baked, low-res "PS2" texture. Built with three.js.

**Live widget:** https://cdjpia.github.io/boto-metal/

Made by **Lucas Preginato** ([@cdjpia](https://github.com/cdjpia)). Code under the
[MIT license](LICENSE). Sister project: [boto-loop](https://github.com/cdjpia/boto-loop).

## Widget (Framer)

- Fills whatever frame it's placed in — no fixed ratio.
- The boto is always centered and the same size at every angle (framed for its full
  rotation sweep).
- **Rotate in any direction:** drag, scroll wheel / trackpad, or arrow keys.
  Auto-spin is on by default. An animated hand shows how the first time it's seen.
- **Adjustments** button (glow, auto-spin + speed, background): the panel stays
  tucked in it. Opened, it slides in on the right side on landscape frames
  (desktop, tablet) and up from the bottom on portrait frames (phone).

In Framer, insert an **Embed** (HTML) and paste:

```html
<iframe src="https://cdjpia.github.io/boto-metal/" title="Boto Metal 3D" loading="lazy"
  allowtransparency="true" style="width:100%;height:100%;border:0;display:block;background:transparent;"></iframe>
```

Because dragging and scrolling rotate the boto, touches and wheel scrolls over the
widget don't scroll the page.

| parameter | example | effect |
|---|---|---|
| `bg` | `?bg=black` | background: `transparent` (default), `black`, `white` |
| `spin` | `?spin=0` | start without auto-spin |
| `speed` | `?speed=40` | spin speed, degrees/second |
| `glow` | `?glow=0.8` | bloom strength (0–1.5) |
| `hint` | `?hint=0` | skip the rotate animation |
| `ui` | `?ui=0` | no panel or button |

## How the model is made

`tools/modelo.py` **builds** the boto from four generated reference views (side,
front, bottom, three-quarter — kept locally in `ref/v2/`, not in the repo). The
side and bottom views share one scale (~740 px per unit, length 2), so body
heights and widths were read off them on a coordinate grid:

1. Body: rings of 10 facets lofted through measured stations, slightly jittered
   so the seams don't form a grid. Each facet (quad or triangle) is one plate.
2. Open jaws, cone teeth, glowing mouth walls, octagonal eyes, steel spine band
   with 11 bulbs, dorsal fin, twisted pectoral fins with LED panels (the reference
   shows their LED face from the side, front *and* bottom), belly fins, and
   angled tail flukes — all as flat extruded plates.
3. Each plate's color (magenta or steel) is sampled from the view that sees it
   best; grain patches are cut from seam-free areas of the same views.
4. Texture: xatlas unwrap, then per texel a dark seam, a bevel and a row of
   rivets along every plate edge — a 1024 px atlas for the PS2 look.
5. Lights (mouth, bulbs, eyes, LEDs) are separate meshes with colors above 1.0,
   which is what the bloom picks up.

```bash
python3 -m venv .venv && .venv/bin/pip install xatlas numpy scipy pillow
npm run bake        # -> public/boto2.glb, boto2_color.jpg, led.jpg
npm start           # http://localhost:5174
```

`tools/bake.py` is the earlier version, which painted the original `boto.glb`.
