# Gate Runner visual upgrade

## Direction

Continue the classic Dino Jump identity: off-white notebook grid, Google blue, rounded paper cards, and the existing blue pixel dinosaur silhouette. The player and start screen reuse the exact `Dino-Dark.png` mascot from the classic jump game, retaining its stepped silhouette and blue gradient. Individual stride, body sway, shadows, and recruitment animation give the original art movement. Claude Code uses its recognizable terracotta pixel-crab form in the same toy material.

The shell shares the classic game’s 440px app width, Ambassador header and ticket pill, blue rounded game card, bottom control dock, and five-item navigation. Desktop keeps the same app composition. Bottom navigation uses a whitelisted view query in the existing app router.

The perspective track crosses an alpine lake with three atmospheric mountain ridges, faceted snow-capped peaks, mist, reflective water, forested cliff terraces and animated waterfalls. Different parallax strengths separate distant mountains from near shorelines. A small lakeside observatory and daytime hot-air balloon add landmarks; translucent aurora ribbons appear at night. Roadside pines and rounded trees have layered shading, planted banks, rocks and flowers, with warm lanterns after dusk. Decorative motion respects reduced-motion preferences. Five environments blend continuously from daylight through golden hour and rose sunset to twilight and a starry moonlit night, using the classic game’s time-of-day palette. Large arithmetic gates, depth-sorted opponents, contact shadows, hit particles, shockwaves, and stage-clear confetti keep action readable.

## Files

- `public/gate_runner.html`: shared mobile app shell, start/pause/results, HUD, directional controls, and navigation.
- `public/css/gate-runner.css`: scoped responsive visual system.
- `public/js/game/gate_runner.js`: extracted game script, revised rendering and input.
- `public/assets/icons/Dino-Dark.png`: active original dinosaur artwork.
- `public/assets/dino/gate-dino-v2.png`: retained earlier toy-style exploration (not used by the runner).
- `public/assets/icons/gate-claude-v2.png`: new transparent Claude Code-inspired opponent.
- `tests/gate_runner.test.cjs`: dependency-free tests against the actual game script.

Original art files are retained. No new runtime packages or remote asset dependencies.

## Play and verification

Open `/gate_runner.html` through the existing local application server. Select **게임 시작**. Drag to steer, hold the on-screen directional buttons, or use left/right arrows and A/D. Escape/P pauses; the pause and sound buttons are also available. Window blur and hidden tabs pause the game.

Combat uses elapsed-time accumulation and stops forward motion during contact. Final guardians block the track. The opening stages are balanced for an optimal direct-fight route. Logical army size is capped at 500 and its visual flock at 81; the counter always reports the logical total. Each dinosaur has its own stride phase, steering lag, soft separation, and wandering offset. New recruits grow from the group center and spread into a loose flock. Pausing freezes all motion, reduced-motion users get less decorative motion, and screen-edge bounds keep the flock visible.

Stage speeds are 155, 195, 245, 300, and 360 world units/second (final stage is about 2.3× stage one). Every choice gate shares the same blue palette; arithmetic and factual mechanic labels distinguish choices. Outcome feedback appears after crossing. Combat and gate outcomes remain tied to the player’s steering anchor so decorative follower movement does not randomly change the selected gate.

Claude squads now patrol laterally and begin limited pursuit within 800 world units. Their paths ease toward the player rather than snapping; positions lock within 60 units of contact. Guardians retain forced engagement. Up to 21 individually animated Claude sprites form a loose, depth-sorted squad. Reduced-motion settings change decoration without reducing enemy difficulty.

The economy now mixes growth with unavoidable loss-only choices. Stage 4 offers `−100 / ÷2`; stage 5 includes `−180 / −100` and `−150 / ÷2`. Which option is better depends on current army size. Large losses show departing dinosaur particles and the exact before/after total. Advanced gates include sequential arithmetic (`×2 −20`), replacement counts (`→180`), and timed side-swapping with a countdown. Swapping stops 240 units before crossing, leaving at least 0.67 seconds to react at maximum speed; the displayed choice is the applied choice.

For balance reference, selecting the largest resulting army and fighting every squad directly leaves 5, 6, 60, 125, and 5 survivors across stages. This is a deterministic arithmetic check, not a claim that every human run has that outcome: dodging, pursuit, and timed swaps affect live runs. Gate arrangements avoid a single permanently advantageous side.

Run `node --test tests/gate_runner.test.cjs` from `gemini-dino-jump`. The suite covers combat, lifecycle, five-stage completion via a live 60fps controller, economy/variant arithmetic, swap display/collision consistency, high-speed collisions, neutral gate styling, both flocks, environment rendering, directional controls, and router whitelist. Browser verification covers desktop and mobile layouts, loaded sprites, start, defeat/restart, pause/resume, sound toggle, and console errors. This upgrade does not change the classic game's server-side score/prize system.

## Asset generation

The earlier toy dinosaur and active Claude enemy PNGs were created with the built-in `image_gen` tool and copied into the project. The player now uses the original Dino Jump artwork instead of the generated dinosaur. They preserve generated alpha; no external image service is needed while playing.

### Dinosaur prompt

Use case: stylized-concept. Create a single high quality polished mobile-game character sprite, isolated on genuine transparent background with alpha. Input 1 is primary identity reference: blue pixel T-rex silhouette, sky blue to periwinkle gradients. Input 2 is accessory reference only: graduation cap and tiny backpack. Develop the blue pixel dinosaur into a premium soft 3D vinyl toy mascot for Team Gemini casual runner. Preserve recognizable chunky stepped square T-rex head, tiny arms, large feet and upward tail of image 1, rounded bevels on voxel-like geometry, blue glazed polymer with subtle lavender on belly, large dark expressive square eye with highlight, friendly confident expression. Small navy graduation cap with short golden tassel, compact blue backpack with small yellow and red accents. Entire character in dynamic running pose, front three-quarter view, facing slightly left; viewed slightly from above like a casual mobile game. Strong clean silhouette readable at 48 pixels, minimal simplified details, studio soft top left lighting, gorgeous ambient occlusion, no texture noise. Fill 85% square image with full body, feet tail and hat visible, centered. No decorative aura, no sparks, no stars around character, no floor, no ground shadow, no background, no text or lettering or watermark. This is one individual production game sprite, not a sprite sheet.

References: `public/assets/icons/Dino-Dark.png`, `public/assets/dino/gemini_dino_anime.jpg`.

### Claude Code prompt

Generate a premium game enemy character sprite on genuinely transparent alpha background. Reference image is STYLE ONLY: match soft 3D beveled voxel toy material quality, same studio top left lighting. Subject: Claude Code Clawd mascot, famous simple orange pixel crab. Preserve EXACT iconic silhouette: wide horizontally rectangular block body/head (one unified block, no separate torso), short rectangular arms protruding sideways midway on left and right, four short thin pixel legs extending downward spaced as two on each side. Two small vertical dark rectangular eyes cut into face, spaced far apart. Warm terracotta orange (#D97757), lighter apricot top beveled surfaces, darker sienna extruded side, subtle glossy highlights, soft friendly mischievous expression. Three-quarter front view, slightly above, very shallow turn to show right face thickness. A chunky 3D extrusion of the minimalist pixel crab, not a humanoid robot. No antenna, no hands, no mouth, no clothing, no text or lettering, no symbol, no decorative effects, no background or floor. Entire character centered with generous transparent margins and fully visible legs, occupies 80% width. High quality match to the attached blue toy dinosaur for opposing army in mobile casual game; clean silhouette readable at 40px.

Style reference: `public/assets/dino/gate-dino-v2.png`. Existing `public/assets/icons/claude_code.svg` geometry remains as the canvas fallback.
