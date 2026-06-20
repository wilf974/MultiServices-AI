# MultiService IA — launch video (Remotion)

A 40-second "problem video" telling the DunkBot story: a decision (Day 1), a correction
(Day 3), and the same question 30 days later — answered wrong **without** memory and right
**with** MultiService IA, which also explains *why* the truth changed.

Built with [Remotion](https://www.remotion.dev) (React → MP4). 1920×1080, 30 fps.

## Run locally

```bash
cd video
npm install
npm start            # open Remotion Studio to preview / tweak
npm run render       # render out/multiservice-demo.mp4
npm run still        # poster frame -> out/poster.png
```

## Edit

Everything is in `src/Video.tsx` (one file, four scenes: Title, Timeline, Split, Closing).
Colours and timing are constants at the top. `DURATION` / `FPS` live there too.

> The rendered `out/multiservice-demo.mp4` is gitignored (binary). Re-render with `npm run render`.
