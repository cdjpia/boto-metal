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

## How the texture is made

`boto.glb` has no UVs and no material, and its pose doesn't match the reference
renders in `ref/` (jaw, belly and tail differ), so the reference images can't be
projected directly. `tools/bake.py` paints the texture instead:

1. `build_mid.glb` (~18k triangles) is unwrapped with xatlas.
2. Every texel becomes a 3D point; plates are the triangles of the dual of a
   Poisson-disk Voronoi on the surface — straight seams, like the reference's facets.
3. Each plate gets its color by region (steel head, rostrum, tail; magenta body
   with a few steel plates), a grain patch cut automatically from seam-free areas
   of the reference images, a dark seam, a bevel and a row of rivets.
4. Special regions per texel: copper spine, bulbs (found as peaks along the spine),
   eyes, mouth and teeth (teeth = surface relief peaks), fin LED grids.
5. A second map holds the emission (bulbs, eyes, mouth, LEDs) that drives the bloom.

The dorsal fin isn't in the mesh: it's a separate outline (`public/fin.json`) with
its own baked texture, extruded in the widget.

The reference images (`ref/LEFT.png`, `RIGHT.png`, `FRONT.png`, `BACK.png`) aren't
in the repo; the bake needs them locally for the palette and grain.

```bash
python3 -m venv .venv && .venv/bin/pip install xatlas numpy scipy pillow matplotlib
npm install
npm run bake        # -> public/boto.glb, boto_color.jpg, boto_glow.jpg, boto_fin.jpg, fin.json
npm start           # http://localhost:5174
```

`tools/` also has the debug pages used to map the anatomy (`shot.html` renders
orthographic views with a coordinate grid, `preview.html` the textured model).
