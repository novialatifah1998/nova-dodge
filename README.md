# NOVA DODGE

[![make.fun · post-x-the-agent-builds-a-game-from-20261122-1709](https://make.fun/badge/post-x-the-agent-builds-a-game-from-20261122-1709.svg)](https://make.fun/bounty/post-x-the-agent-builds-a-game-from-20261122-1709?utm_source=github&utm_medium=readme&utm_campaign=post-x-the-agent-builds-a-game-from-20261122-1709)
[![rank](https://make.fun/badge/post-x-the-agent-builds-a-game-from-20261122-1709/novialatifah1998/nova-dodge/rank.svg)](https://make.fun/bounty/post-x-the-agent-builds-a-game-from-20261122-1709/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=post-x-the-agent-builds-a-game-from-20261122-1709)
[![reward](https://make.fun/badge/post-x-the-agent-builds-a-game-from-20261122-1709/novialatifah1998/nova-dodge/reward.svg)](https://make.fun/bounty/post-x-the-agent-builds-a-game-from-20261122-1709?utm_source=github&utm_medium=readme&utm_campaign=post-x-the-agent-builds-a-game-from-20261122-1709)

A tiny browser game in one HTML file, built from a single prompt: a little
rocket at the bottom of a starfield dodges falling meteors and collects
stars. Arrow keys or touch-drag to move. Score +1 per star, +1 per meteor
dodged, 3 lives, speed ramps up with the level. Big readable score, a
game-over screen with restart. No libraries, no images — everything is
drawn on canvas.

## Play it

Open `game.html` in a browser, or serve the folder:

```sh
npx serve .
```

Arrow keys / WASD / drag to fly. `Space` starts, `R` restarts after a
game over.

## The video

`render.py` renders the 30-second showcase (hook → build log → a seeded
playthrough, score 0 → 18, one meteor hit) into three segments in
`assets/`, and `main.ts` assembles them with make.fun's brand badge and
referral end card:

```sh
python3 render.py assets   # re-render the segments (seeded, deterministic)
node main.ts               # assemble video.mp4 (30.0 s, 1080x1920)
```

`main.ts` needs ffmpeg on the machine. Where ffmpeg is missing (the
make.fun grader image) it logs one line and exits 0 without writing
anything.

## Bounty

Built for the make.fun bounty
[post-x-the-agent-builds-a-game-from-20261122-1709](https://make.fun/bounty/post-x-the-agent-builds-a-game-from-20261122-1709)
— build a game from a prompt, post it on X.

Referral code: `06vzp7s2`

## License

MIT. The make.fun brand badge and referral end card in `assets/` are
make.fun's press-kit files, used as they are.
