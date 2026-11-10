# Siege Wing — Game Design

Nov 9, 2026 · @Jack

Siege Wing is a single-scene browser game: one modern attack helicopter against a medieval army of about 2,000 defending a castle at golden hour. The helicopter can destroy anything it can hold a sight on; the difficulty is flying it well enough to hold that sight while arrows, ballista bolts and cannon fire punish every steady moment. A run lasts 8–12 minutes.

## Where the effort goes

A demo is judged in its first minute, so effort is concentrated on the five things a viewer sees and feels immediately, and deliberately withheld from everything else.

| Priority | Area | Share of effort | The bar it has to clear |
| --- | --- | --- | --- |
| 1 | Flight feel | 25% | Weight, drift and recovery feel right within 10 seconds of taking the controls; tuned before anything else is built |
| 2 | Lighting and atmosphere | 20% | Any paused frame looks like a deliberate photograph: low sun, haze, long shadows, smoke catching light |
| 3 | The crowd | 20% | 2,000 soldiers who visibly react: shields go up, lines break, men are thrown by blasts, formations rout. No other browser demo shows this |
| 4 | Impact feedback | 15% | Every trigger pull changes the scene: dust, debris, falling towers, scorched ground, and sound with real low end |
| 5 | The helicopter | 10% | The one model always on screen: detailed exterior, working cockpit, blurred rotors, damage states |
| 6 | Everything else | 10% | HUD, minimap, menus, scoring and the village only need to be clean and unobtrusive |

Things this demo does not attempt: a story, multiple helicopters, multiple levels, multiplayer, progression or unlocks, and enterable buildings.

The two largest risks to the quality claim are asset quality and crowd performance. A weak helicopter or soldier model undoes good lighting, so those two models get the most art attention. The crowd needs a performance prototype in the first week, before any design depends on 2,000 soldiers.

## Flight model and controls

The default layout follows Delta Force: collective and yaw on the keyboard, pitch and roll on the mouse. W climbs; it does not move the helicopter forward. Forward flight comes only from tilting the nose down.

| Input | Action |
| --- | --- |
| W / S | Collective up / down |
| A / D | Yaw left / right |
| Mouse forward / back | Pitch (invert option) |
| Mouse left / right, or Q / E | Roll |
| Left mouse | Fire selected weapon |
| Right mouse (hold) | Gunner mode: the mouse aims the cannon instead of flying |
| 1 / 2 / 3, or wheel | Cannon / rockets / missiles |
| X | Flares |
| C | Switch third-person / cockpit |
| Alt (hold) | Free look |

All keys are rebindable, with a second preset in the Battlefield style: mouse left/right for yaw and A/D for roll. Delta Force players complain that yaw cannot be moved to the mouse, so offering both avoids that.

What the research found, and how sure it is:

- Delta Force has no official control documentation. The W/S collective, A/D yaw, Q/E roll and mouse pitch layout comes from a [17173 guide](https://news.17173.com/z/lzyd/content/08072024/094518130.shtml) and Steam threads; [Shacknews](https://www.shacknews.com/article/140883/delta-force-hawk-ops-controls-keybindings) lists Shift and Ctrl for climb and descend instead.
- Players describe the handling as heavy, with flips that are hard to recover and nowhere to practise ([Steam thread](https://steamcommunity.com/app/2507950/discussions/0/4509877496947190183)). The opening approach in this design is the answer to the last point.
- Battlefield 4 uses the same W/S, A/D and mouse split, with C for view and X for countermeasures ([Gamepressure](https://www.gamepressure.com/battlefield4/assault-helicopter/z36175)). In Battlefield, pitching forward costs altitude unless collective is added.
- The flare, view and free-look keys in Delta Force could not be confirmed; the keys above are this design's choice.

The physics model is the same in both difficulty modes; only damping and assists differ. The values below are starting points for tuning, not sourced figures.

| Element | Behaviour |
| --- | --- |
| Thrust | Acts along the helicopter's own up axis; maximum 1.8 times its weight |
| Banking | Vertical lift falls with tilt angle, so every turn needs added collective |
| Momentum | Low drag: the helicopter keeps drifting and must be flared to stop |
| Ground effect | 10–15% extra lift within one rotor diameter of the ground |
| Translational lift | 10% extra lift above 15 m/s |
| Yaw at speed | Tail authority falls 40% at top speed, and the nose is pulled toward the direction of travel |
| Torque coupling | Raising collective swings the nose and must be corrected with yaw |

## Difficulty modes

The player picks a mode on the start screen. Punishing is the default and the intended experience; Stabilized keeps the same physics and adds assists, the approach DCS uses for its "Game Flight" mode.

| Aspect | Punishing (default) | Stabilized |
| --- | --- | --- |
| Pitch and roll | Mouse sets a rotation rate, up to 90°/s; the tilt stays where it is left | Mouse sets a target angle, up to 30° |
| Releasing the mouse | Nothing levels the helicopter | Returns to level in about 0.6 s |
| Tilt limit | About 70°, beyond which it tumbles | 30° |
| Collective | No hold; released keys give slightly less than hover lift, so it slowly sinks | Auto-hover: holds altitude with no input |
| Drift | Carries until the pilot flares | Extra braking when controls are neutral |
| Torque coupling and yaw fade | On | Off |
| Gunner mode | Helicopter keeps its last tilt and drifts while aiming | Helicopter holds a hover while aiming |
| Subsystem damage | Full effects | Effects halved |
| Score multiplier | 1.0 | 0.5 |

Enemy counts, accuracy and damage are identical in both modes, so the difference between them is purely the flying.

## Cameras

Both views are available at all times and C switches between them. Third-person is better for judging drift and dodging; cockpit is better for weapon delivery.

| Aspect | Third-person chase | Cockpit |
| --- | --- | --- |
| Position | Behind and above, on a spring so the helicopter visibly leads the camera | Pilot's eye point inside a modelled cockpit |
| Motion | Looks ahead along the velocity; swings behind the direction of travel at speed | Locked to the airframe, so every tilt is felt |
| Field of view | 70° in a hover, widening to 85° at top speed | 75°, narrowing to 40° in gunner mode |
| Aiming | Reticle projected onto the ground where rockets will land | Fixed sight for rockets; cannon sight moves with the mouse in gunner mode, within 60° of the nose |
| Instruments | HUD overlay: altitude, speed, vertical speed, attitude, heat, ammunition | Working gauges and warning lights, plus a minimal HUD |
| Damage | Smoke trail, visible missing parts | Cracked canopy glass, flickering panels, alarm tones |
| Free look | Orbit around the helicopter | Head turn, recentring in 0.4 s |

## Weapons

Every weapon is lethal, and every weapon demands a flight posture that exposes the helicopter to one of the threats.

| Weapon | Ammo | Use | Posture it forces | Limit |
| --- | --- | --- | --- | --- |
| 30 mm chin cannon | 600 rounds | Formations, crews, archers on walls | Slow and stable; the turret follows the mouse within a 60° cone | Overheats after 4 s of fire; spread grows with airframe rotation |
| Rocket pods | 38 rockets | Area damage, walls, siege engines | Nose-down dive along the line of fire | Unguided; fires where the nose points |
| Guided missiles | 8 | One-shot kill on a tower, trebuchet or gate | 2 s of steady lock inside a small reticle | Lock breaks if the target leaves the reticle |
| Flares | 6 | Decoy flaming projectiles and break ballista aim for 3 s | None | 10 s cooldown |

Rearming requires landing on a pad on the far hill. The pad accepts a touchdown under 2 m/s vertical and 3 m/s horizontal, so rearming is itself a flying test under time pressure.

## Threats

The defenders cover every altitude band, so no height is safe and the player must keep moving between bad options.

| Threat | Count | Dangerous band | Behaviour | What it punishes | Counter |
| --- | --- | --- | --- | --- | --- |
| Archer companies | 6 companies of 80 | 0–80 m | Massed volleys in visible arcs, 5 s cycle; each hit is small | Low hovering | Stay above 80 m or keep moving; cannon the company |
| Ballistae | 8, on towers | 0–250 m | Fast, accurate bolt with a 1.5 s aim tell; causes subsystem damage | Slow, straight flight | Jink during the tell; flares; missile the tower |
| Bombards | 5, on walls | 100–300 m | Burst shot with a flak-like cloud; 12 s reload | Loitering at mid altitude | Count the reload; rocket the battery |
| Trebuchets | 3, behind the walls | Any, at range | Flaming boulder on a long, readable arc | Target fixation | Watch the arc; change position |
| Fire pots | Courtyard | 0–60 m | Thick smoke columns that block sight | Hovering over the courtyard | Rotor wash clears smoke at low height |
| Infantry and knights | About 1,400 | None | Hold formation, raise shields, scatter under fire, rout when their banner falls | Nothing; they are the score | Any weapon |

Counts and ranges are starting values for tuning.

## Damage and failure

Damage changes how the helicopter flies instead of draining a single health bar. Each subsystem has its own hit points and a degraded state.

| Subsystem | Typical cause | Effect when degraded |
| --- | --- | --- |
| Tail rotor | Ballista bolt, arrows from behind | Constant yaw drift the pilot must hold against; total loss means an unrecoverable spin below 40 km/h |
| Engine | Bombard burst | Collective power drops 35%; climbing out of a dive takes far longer |
| Hydraulics | Ballista bolt | Pitch and roll response slows by half |
| Main rotor | Arrow volleys, obstacle strike | Vibration, camera shake, reduced lift |
| Canopy | Arrows | Cracks obscure the cockpit view |
| Weapons | Any hit to the stub wings | One pod or the turret jams |

The run ends in a loss when any of these happens:

- The helicopter hits terrain or a structure faster than 6 m/s.
- The main rotor strikes a wall, tower or tree.
- The hull reaches zero after accumulated hits.
- The helicopter descends vertically into its own downwash for too long and loses lift near the ground.

A crash plays out in full: the spin, the impact, the fireball and the soldiers cheering.

## Level and mission flow

The whole game is one valley. The play area is a circle of 1.5 km radius (3 km across) centred between the castle and the field, inside about 8 km of visible terrain, so the horizon never shows an edge. A low sun sits behind the castle.

- **Castle on the ridge:** curtain wall, four gate towers, a keep and a tight courtyard.
- **Field below:** the army drawn up in blocks with banners, tents and a supply camp.
- **Village and river:** cover for archer companies, and landmarks for orientation.
- **Forest edge:** trees tall enough to strike a rotor.
- **Far hill:** the rearm pad, 40 seconds of flight from the castle.

The mission has three phases:

1. **Break the field army.** Rout four of the six formations by killing their banner guards. Arrows are the main threat.
2. **Silence the walls.** Destroy the four gate towers and their ballistae. Bombards and trebuchets join in.
3. **Kill the warlord.** His banner guard holds the courtyard, which is the hardest place in the level to fly: walls on four sides, smoke, and arrows from every parapet.

The player wins by killing the warlord and loses by crashing, being shot down, or staying outside the play area for 10 seconds. The score counts time, hull condition, ammunition used and rearm landings.

## Play area and minimap

Leaving the 1.5 km circle starts a 10-second countdown, and the run is lost if the helicopter is still outside when it reaches zero.

- **Warning band:** within 150 m of the edge, the boundary on the minimap turns amber and a tone sounds.
- **Outside:** the screen edges darken, a large countdown appears with a "return to combat area" call, and an arrow points to the nearest point of the circle.
- **Timer recovery:** once back inside, the timer refills at one second per second instead of resetting, so skimming the edge repeatedly is not a way to escape fire.
- **Ceiling:** lift fades above 400 m, so the player cannot climb out of every threat.

The minimap sits in the bottom-left corner, about 220 px across, and rotates so the helicopter's heading is always up.

| Shown on the minimap | Appearance |
| --- | --- |
| Play-area boundary | Ring; amber in the warning band, red when outside |
| Helicopter | Centre arrow with a view cone |
| Castle, towers, village, river | Simplified terrain outline |
| Rearm pad | Fixed icon, with distance |
| Formations | Blocks that shrink as they take losses and fade when routed |
| Ballistae, bombards, trebuchets | Icons that appear once spotted or once they fire |
| Incoming trebuchet shots | Predicted impact marker |
| Current objective | Pulsing marker |

## Gameplay additions

The first draft had strong threats but weak reasons to take risks. These seven changes make dangerous flying the most rewarding way to play and make every loss feel earned.

| Addition | What it does | Why it strengthens the game |
| --- | --- | --- |
| Morale and fear | A pass below 30 m at speed panics a formation and breaks its shield wall for 8 s; killing a banner guard routs it | Rewards exactly the low flying that arrows punish, and saves ammunition |
| Gunner mode | Holding the aim button moves the cannon with the mouse, and the mouse stops flying the helicopter | Precision fire costs control; the central trade of the game sits in one button |
| Readable tells | Every threat announces itself: a horn before a volley, a glint and tone for ballista aim, a smoke puff for bombards | Deaths feel fair, and skill is learning the tells |
| Defenders adapt | Each phase changes the defence: pavise shields come out, fire pots are lit, bombards are re-laid to the altitude the player uses most | Stops one safe tactic from working for the whole run |
| Limp home | The rearm pad also repairs one subsystem per 5 s on the ground | Turns damage into a decision: push on with a failing tail rotor or spend a minute flying back |
| Sunset clock | The sun sets over 12 minutes; in the last 2 minutes the valley is lit by fires and tracers | A soft time limit with no timer on screen, and the lighting change is itself a showpiece |
| Opening approach | The run starts 40 seconds out behind the far hill, with no enemies in range, then crests the ridge onto the full army | Teaches the controls safely and delivers the reveal shot |

Restart after a loss takes under 3 seconds and skips the approach, because a hard game is only enjoyable when retrying is instant.

## Visual and audio targets

The target is a frame that passes for a console game screenshot at 60 fps on a mid-range desktop GPU. True photorealism is out of reach in a browser, and most of the perceived quality comes from lighting and effects, not model detail.

| Area | Technique |
| --- | --- |
| Renderer | Three.js on WebGPU, with a WebGL 2 fallback |
| Lighting | HDRI sky, one low sun, cascaded shadow maps, ambient occlusion |
| Atmosphere | Height fog, volumetric light shafts through smoke, distance haze |
| Post-processing | Filmic tone mapping, bloom, motion blur on rotors, depth of field in cockpit view, film grain |
| Crowd | GPU-instanced soldiers with animations baked to textures, three detail levels, about 2,000 on screen |
| Terrain | Height-mapped valley with blended PBR ground materials and instanced grass |
| Rotor wash | Grass flattens, dust and smoke are pushed outward, banners whip |
| Weapon effects | Tracers, muzzle flash lighting, layered explosion sprites, lingering smoke, scorch decals |
| Destruction | Towers and wall sections swap to pre-fractured chunks that fall under simple physics |
| Camera | Shake from hits and firing, heat haze behind the exhaust |

Audio does as much work as the picture:

- Rotor thump that deepens under load and changes with damage.
- Cannon reports and explosions delayed by distance.
- Arrows clattering on the hull, and a warning tone for ballista aim.
- A crowd bed of shouts, horns and drums that thins as formations rout.

## Build order

Flight feel is built and tuned first, because every other system depends on it.

1. **Flyable prototype.** Terrain, sky and lighting, the flight model in both difficulty modes, both cameras, and the cannon against static targets.
2. **Crowd.** Instanced soldiers with baked animation, formations, scatter and rout behaviour.
3. **Threats.** Archer volleys, ballistae, bombards and trebuchets, with subsystem damage and crash handling.
4. **Castle and destruction.** Final castle assets, tower and wall destruction, rockets and missiles, the rearm pad.
5. **Mission and polish.** Three phases, HUD, audio, post-processing, performance passes and menus.

## Open questions

- [ ] Is the play area 1.5 km in radius, as written here, or 1.5 km across?
- [ ] Is "Siege Wing" acceptable as the working title?
- [ ] What is the minimum hardware the demo must run well on?
