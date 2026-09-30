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

`tools/casco.py` builds the boto **from the reference views themselves** (side,
front and bottom — kept locally in `ref/v2/`, not in the repo):

1. **Shape:** the three silhouettes are intersected in a voxel grid (a visual
   hull), so the model matches each view's outline by construction — open jaws
   with teeth, dorsal, bulb crest, twisted fins, flukes. The gaps no view can
   separate (under the belly between the fins) are carved by hand.
2. **Low-poly:** marching cubes, light smoothing, then simplified to ~6,000
   triangles.
3. **Texture:** after a UV unwrap, every texel takes its color from the view that
   sees it most head-on — and only if that view actually sees it (a depth test
   against the voxels keeps a fin from being painted onto the body behind it).
   Hidden spots inherit the nearest visible color. The result is saved at
   **512 px**: plates, rivets, colors and lights copied from the reference, with
   the lighting pre-baked — rendered almost unlit, PS2-style.
4. **Glow:** orange/red and blue pixels (bulbs, eyes, mouth, LED fins) form an
   emission map that drives the bloom; the magenta plates never glow.

```bash
python3 -m venv .venv && .venv/bin/pip install xatlas numpy scipy pillow scikit-image
npm install
npm run bake        # -> public/boto3.glb, boto3_color.jpg, boto3_glow.jpg
npm start           # http://localhost:5174
```

`tools/bake.py` and `tools/modelo.py` are earlier attempts (repainting the
original mesh; modeling by hand from measurements).
