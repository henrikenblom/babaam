# BA-BAAM!

**Version 1.0.1**

A feature-rich, action-packed side-scrolling space shooter game that runs in your terminal!

![BA-BAAM Main Menu](/media/ba-baam-menu.png)

## Requirements

- Python 3.6 or higher
- A modern terminal (iTerm2, Terminal.app, etc.) with color support
- macOS, Linux, or Unix-like system (uses curses library)

## Installation

### One-Line Remote Install (Easiest)

Install BA-BAAM! directly from GitHub with a single command:

```bash
curl -s https://raw.githubusercontent.com/henrikenblom/babaam/master/remote-install.sh | bash
```

This will automatically:
- Download the latest version from GitHub
- Check your Python version (requires 3.6+)
- Create a virtual environment
- Install Python dependencies (pynput, pygame, numpy)
- Install the game to `~/.local/share/babaam`
- Create a launcher script in `~/.local/bin/babaam`

After installation, you can run the game from anywhere:

```bash
babaam
```

**Note:** You may need to add `~/.local/bin` to your PATH. The installer will provide instructions if needed.

### Local Install

Clone the repository and run the installer:

```bash
git clone https://github.com/henrikenblom/babaam.git
cd babaam
./install.sh
```

The installer will:
- Check your Python version (requires 3.6+)
- Install Python dependencies (pynput, pygame, numpy)
- Install the game to `~/.local/share/babaam`
- Create a launcher script in `~/.local/bin/babaam`

After installation, you can run the game from anywhere:

```bash
babaam
```

**Note:** You may need to add `~/.local/bin` to your PATH. The installer will provide instructions if needed.

### Alternative: Run Without Installing

If you prefer to run the game directly from the source directory:

```bash
git clone https://github.com/henrikenblom/babaam.git
cd babaam
./babaam
```

The launcher script will automatically install missing dependencies.

### Manual Installation

If you prefer to install dependencies manually:

```bash
pip3 install --user pynput pygame numpy
python3 babaam.py
```

**Dependencies:**
- **pynput**: Responsive keyboard input that doesn't rely on system keyboard repeat settings
- **pygame**: Retro-style software synthesizer for authentic 8-bit/16-bit sound effects
- **numpy**: Waveform generation for the sound synthesizer

You'll be greeted with an awesome animated main menu featuring:
- A scrolling parallax starfield with tiny faint stars and big shiny ones
- A shimmering BA-BAAM! title with a diagonal golden wave effect that sweeps across at 35 degrees (solid red for 12 seconds, then shimmers for 6 seconds)
- A shimmering blue tagline "Kill them. Kill them all." with a horizontal white wave effect (solid blue for 8 seconds, then shimmers for 4 seconds)
- Shimmer effects cycle independently for visual variety
- Hardcore electronic background music at 150 BPM with driving bassline, aggressive melody, and blazing fast arpeggios (77-second extended loop with 4 distinct sections)

## Controls

**Main Menu:**
- **N**: Start New Game
- **I**: Watch Intro
- **B**: Mission Briefing
- **ESC**: Quit

**In-Game:**
- **Arrow Keys**: Move your ship up, down, left, and right
- **Spacebar**: Shoot
- **1**: Switch to Normal weapon
- **2**: Switch to Spread Shot (when unlocked)
- **3**: Switch to Energy Beam (when unlocked)
- **P**: Pause/Resume game
- **ESC**: Quit game

**Game Over Screen:**
- Displays your final score for 3 seconds
- Automatically returns to main menu

## The Story

You are the last surviving pilot of a fleet sent to defend a freight ship carrying a mysterious cargo - an artifact that could either bring peace to the galaxy or become the ultimate weapon of destruction. The initial enemy attack wave devastated your elite squadron. You managed to eliminate their first assault with a tactical nuke, but now you're all that stands between the cargo and those who would use it for evil.

Intelligence reports indicate the enemy has intensified their response, deploying their most advanced fleet in overwhelming numbers. To even the playing field Command has authorized experimental technology: Energy Converters that can forge powerful enhancements from the residual energy of destroyed enemy fighters. Every hostile you eliminate may yield tactical advantages - this is your only edge against their superior numbers.

The freight ship cannot defend itself. If enough enemy fighters reaches it, the mission is over. Hold the line, pilot. The fate of the galaxy rests on your shoulders.

## Game Features

### Core Gameplay
- Your ship (►) appears on the left side, defending the freight ship behind you
- Enemy fighters spawn from the right, attempting to reach the cargo
- Shoot them down before they breach your defensive line
- Each enemy that breaks through costs you 1 health
- You start with 3 health
- Progressive difficulty - enemy waves intensify as you progress

### Enemy Types

1. **Normal Enemy** - Basic enemy, 10 points
   ```
   ╔►
   ╚►
   ```
   - Speed: Medium
   - Health: 1 hit

2. **Fast Enemy** - Quick and dangerous, 20 points
   ```
   ══►
   ```
   - Speed: Fast
   - Health: 1 hit
   - Unlocked at 200+ score

3. **Tank Enemy** - Slow but tough, 30 points
   ```
   ╔▓╗
   ╚▓╝
   ```
   - Speed: Slow
   - Health: 10 hits
   - Unlocked at 1000+ score

4. **Zigzag Enemy** - Unpredictable movement, 25 points
   ```
   ╱►
   ╲►
   ```
   - Speed: Medium
   - Health: 3 hits (can be destroyed with 1 plasma shot)
   - Moves in zigzag pattern
   - Unlocked at 500+ score

### Boss Battles

- Boss appears after defeating 30 enemies (then every 50 enemies)
- Spawning based on enemy kills, not score - prevents bosses appearing too frequently when harder enemies spawn
- Large 3x3 sprite with significant health
- Shoots back at you with bullet patterns
- Moves vertically in patterns
- Displays health bar at bottom of screen
- **WARNING: If the boss reaches the cargo ship, the mission is LOST** - instant game over!
- Drops 3 power-ups when defeated
- Each boss gets progressively harder

### Weapon System

1. **Normal Shot** - Standard single bullet
   - Default weapon
   - Good fire rate
   - **3 DAMAGE per hit** - Concentrated firepower

2. **Spread Shot (W)** - Triple shot pattern
   - Fires 3 bullets (center, up-angle, down-angle)
   - **1 DAMAGE per bullet** (Total: 3 DAMAGE when all hit)
   - Great for covering more area
   - Unlock by collecting 'W' power-up

3. **Energy Beam (E)** - Continuous beam weapon with overheat mechanic
   - Extended range horizontal beam
   - Continuous damage
   - **Rapidly accelerating charge rate** - fires twice as fast as normal weapons for smooth growth, accelerating from +3 to +12 units/shot as you hold position
   - **Starts at medium length and grows when stationary** - begins at 15 units, grows to 60 units max with rapid acceleration
   - **Side cannons activate at maximum power** - once main beam reaches 60 units, both side cannons grow simultaneously (0→60 units each)
   - **Triple beam devastation** - fully charged weapon fires three parallel 60-unit beams with intensified sound (~1 second to full charge)
   - **Overheat mechanic** - as soon as all beams reach maximum power (60 units), they start flickering immediately (high frequency at first, slower near end). After 3 seconds at full power, beams shut down completely
   - **Cooldown required** - after shutdown, you must release the trigger (move or stop firing) before firing again
   - **Dying sound** - beam sound becomes noisy and unstable during flicker phase, indicating imminent shutdown
   - **Resets to minimum length when you actually move** - detects actual position changes, so pressing against walls doesn't reset the beam
   - Unlock by collecting 'E' power-up

Press **1**, **2**, or **3** to switch between unlocked weapons!

### Power-Ups

Power-ups have a 12% chance to drop when you destroy an enemy (rare drops make high scores more challenging). Each power-up collected awards 10 bonus points:

- **R (Rapid Fire)** - Red
  - Dramatically increases fire rate
  - **Doubles energy beam growth rate** - beam charges twice as fast when standing still
  - Lasts 10 seconds
  - Triggers clock ticking music (normal version at 60 BPM)

- **S (Shield)** - Blue
  - Protects from all damage
  - Changes ship appearance to ▶
  - Lasts 12 seconds
  - **Much rarer when Spread Shot is unlocked** (Shield+Spread combo is too powerful!)
  - Triggers clock ticking music (normal version at 60 BPM)
  - **When combined with Rapid Fire**: Triggers intense clock ticking (90 BPM) - double the power, double the urgency!

- **+ (Health)** - Green
  - Restores 1 health point
  - Can overflow up to 6 HP total (3 starting + 3 overflow)
  - Allows you to build up extra lives for harder battles

- **W (Spread Shot)** - Yellow
  - Unlocks Spread Shot weapon
  - Automatically equips it

- **E (Energy Beam)** - Magenta
  - Unlocks Energy Beam weapon
  - Automatically equips it

- **N (Nuke)** - Red (RARE!)
  - Destroys ALL enemies on screen instantly
  - Awards full points for each enemy
  - Can destroy bosses
  - **COSTS 1 HEALTH after use** - a powerful sacrifice for massive destruction
  - Spectacular visual effects: "BA-BAAM!" text, screen flash, and explosions
  - Health is deducted AFTER the animation plays, so you always see the full nuke effect
  - Only 5% drop chance
  - Only appears after defeating the first boss (500+ score)

- **D (Drone)** - Cyan
  - **Spawns THREE autonomous fighting drones** that fight alongside you
  - Each drone has 8-second lifespan with visual countdown timer
  - Shoot synthetic plasma bolts with precision at enemies and bosses
  - Unique robotic shot sound with frequency modulation
  - Automatically track and engage nearest targets
  - Maintain safe distance from targets to avoid collisions
  - **Circle around your ship when no enemies are present**
  - Move freely across the entire play area
  - If accidentally collides with an enemy, both are destroyed
  - Only appears after defeating the second boss

**Cheat Codes:**
- Type "00000" to spawn three drones (testing purposes)
- Type "EEEEE" to unlock and equip Energy Beam weapon (testing purposes)

### Sound Effects

The game features a retro software synthesizer inspired by the hardware synthesizer chips found in consoles and home computers in the 80's, generating authentic 8-bit/16-bit style sounds using sawtooth waves, lowpass filters, and vibrato effects:

- **Shoot**: Punchy, powerful shot with three-layer design - bright sawtooth attack with pitch sweep (1000→800 Hz), bass punch with kick (200→50 Hz), and impact noise burst for maximum satisfaction
- **Drone Shot**: Synthetic, robotic shot with triangle wave and frequency modulation (600→750 Hz sweep with 35 Hz modulation) - higher-pitched and more mechanical than player shot
- **Energy Beam**: Descending pitch sweep using filtered sawtooth (sci-fi energy beam)
- **Energy Beam Dying**: Same as energy beam but with added noise - unstable, flickering sound when beam is overheating
- **Blocked**: Short low buzz (250→210 Hz) - indicates energy beam cannot fire while moving
- **Explosion**: Gritty sawtooth + noise burst with heavy filtering (enemy destruction)
- **Powerup**: Ascending arpeggio with bright filtered sawtooth (C-E-G musical notes)
- **Damage**: Deep filtered sawtooth (player hit)
- **Boss**: Dramatic frequency sweep with sawtooth, filtering, and vibrato (boss appearance/defeat)
- **Boss Hit**: Metallic clang using filtered sawtooth with noise (satisfying boss damage feedback)
- **Nuke**: Massive explosion with weight and punch - sub-bass impact kick (80→15 Hz), layered sawtooth rumble, and heavy noise. Three-layer design creates devastating sound wall
- **Game Start Fanfare**: Punchy multi-channel E minor ascent (1.2 seconds) - triumphant 4-channel arrangement with melody (sawtooth E4→G4→B4→E5), harmony (square G4→B4→D5→G5), bass (triangle E3→E2), and punchy kick impact (120→30 Hz). Bright and exciting with slight reverb. Plays when starting new game
- **Game Over**: Dramatic multi-channel E minor descent (1.5 seconds) - emotional 4-channel arrangement with melody (sawtooth E5→B4→G4→E4→E3), harmony (square G5→D5→B4→G4→G3), bass (triangle E3→D3→C3), and final impact thud (100→20 Hz). Three waveforms create rich, punchy ending with vibrato on final note for emotional impact
- **Menu Music**: Hardcore electronic theme at 150 BPM (77-second extended loop)
  - 4 channels: kick drum (4-on-the-floor), pulsing bassline, aggressive lead synth, blazing 32nd-note arpeggios
  - Minor key progression (Em - C - D - Em) repeated across 4 sections for dark, epic atmosphere
  - Each section adds variation and development while maintaining the core theme
  - Tight, punchy sound with bright filtering for maximum energy
- **In-Game Clock Ticking**: Conditional power-up timer music
  - **Normal version** (60 BPM): Plays when player has shield OR rapid fire active
    - TICK at 2000 Hz, TOCK at 1400 Hz
    - Subtle reminder that power-up time is limited
  - **Intense version** (90 BPM): Plays when player has BOTH shield AND rapid fire
    - TICK at 2400 Hz, TOCK at 1700 Hz - higher pitched and faster
    - Higher urgency matches the powerful but temporary double power-up state
  - Automatically starts when picking up shield or rapid fire
  - Automatically stops when power-ups expire
  - Switches between versions dynamically as power-ups are gained/lost
  - Very quiet volume to not interfere with gameplay sounds
  - Pauses/resumes with game pause (P key)
- **Engine Idle**: Pure noise-based continuous rumble (baseline - ship constantly hurtling through space)
- **Engine Right**: More intense noise-based swoosh (moving forward/right - most powerful)
- **Engine Left**: Less intense rumble (moving left - slowing down)
- **Engine Vertical**: Slightly more intense (moving up/down only)

The engine sound dynamically changes based on your direction:
- Moving right (forward) = most intense (unless at right boundary, then same as idle)
- Moving left (backward) = reduced intensity (slowing down)
- Moving up/down only = moderate intensity increase
- Moving diagonally = uses the most intense sound (e.g., right+up uses right, left+up uses vertical)
- No input or at right boundary = idle baseline

All sounds are generated programmatically using techniques inspired by the Commodore 64's SID chip: sawtooth waveforms, lowpass filtering, ADSR envelopes, and vibrato modulation!

### High Score System

- **Top 5 Leaderboard** - Tracks the best 5 scores of all time
- **Enter Your Initials** - When you make the top 5, enter your 3-letter name
- **Persistent Storage** - Scores saved to `.babaam_high_score.json`
- **Main Menu Display** - Leaderboard prominently displayed with colored rankings:
  - 🥇 1st place: Gold (bright yellow)
  - 🥈 2nd place: Silver (bright white)
  - 🥉 3rd place: Bronze (red)
  - 4th-5th place: Green
- **Game Over** - Special "HIGH SCORE!" message when you make the list
- **Always Up-to-Date** - Leaderboard reloads each time you return to the main menu

### Visual Effects

- **Animated main menu** - Scrolling parallax starfield (160 stars across 3 layers) with shimmering title
- **Ship startup flash** - Your ship flashes between cyan and white for 3 seconds at the start of each game, making it easy to spot
- **Multi-layer scrolling starfield** with parallax effect - creates the illusion of speeding through space
  - 3 distinct layers moving at different speeds (far, mid, close)
  - 65 total stars across all layers
  - Seamlessly wraps around for continuous scrolling
- Color-coded elements for easy identification
- Explosion animations when enemies are destroyed
- Boss has special large explosions
- Shield changes player ship appearance
- Real-time power-up timers displayed on screen
- Boss health bar visualization
- Drone countdown timer gauge (tracks first active drone)
- Unicode characters for enhanced graphics
- Autonomous drone AI with compact, bold cyan diamond sprite (◆)
- Multiple drones can be active simultaneously, each with independent AI

## HUD Information

**Top Left:**
- Health bar (similar gauge to boss health bar showing current/max HP)
- Active shield timer (if active)
- Active rapid fire timer (if active)

**Top Right:**
- Current score
- High score

**Bottom Left:**
- Current weapon
- Available weapons (shown as numbers)

**Bottom Right:**
- Boss health bar (during boss fights)
- Drone timer gauge (when drones are active) - shows remaining lifetime of first drone in seconds

## Gameplay Tips

- **Collect power-ups!** They make a huge difference
- **Prioritize tank enemies** - they take multiple hits
- **Watch for zigzag enemies** - their movement is unpredictable
- **Use spread shot** for dealing with multiple enemies
- **Use energy beam** for boss battles (continuous damage)
- **Energy beam accelerates rapidly** - starts at 15 units, fires twice as fast for smooth growth, accelerating dramatically if you commit to holding position (3→6→9→12 growth tiers)
- **Energy beam triple power** - keep standing still after main beam maxes out to activate intensified side cannons for devastating triple-beam coverage
- **Energy beam overheat management** - beams last 3 seconds at full power before shutdown. As soon as all beams max out, flickering starts! Release trigger (stop firing) to reset cooldown. Use strategically in short, devastating bursts
- **Shield becomes rare after unlocking Spread** - the combo is powerful but hard to get!
- **Save shield power-ups** for boss fights if possible
- **Keep moving!** Staying still makes you an easy target (except when using energy beam strategically)
- **Don't let enemies pile up** - they get harder to manage
- **Boss strategy**: Find a safe spot, stand still, and use rapid fire + energy beam - rapid fire doubles beam growth rate for devastating quick charges!
- **Nuke strategy**: Save nukes for overwhelming situations or boss battles - they're extremely rare and cost 1 health to use! Only use when the situation is truly desperate.
- **Drone strategy**: Three drones fight autonomously, circling protectively when calm and engaging threats when they appear - with triple firepower, they can handle multiple enemies while you focus on dodging!

## Difficulty Progression

- **0-200 points**: Only normal enemies
- **200-500 points**: Fast enemies start appearing
- **500-1000 points**: Zigzag enemies join the fight
- **1000+ points**: All enemy types including tanks
- **After 30 kills, then every 50 kills**: Boss battle!
- Enemy spawn rate increases every 10 seconds

## Technical Details

- Runs at 30 FPS for smooth gameplay
- All game state is updated frame-by-frame
- Collision detection uses distance calculations
- Power-up timers count down in real-time
- High score stored in JSON format
- **Independent Color Scheme** - Uses fixed colors from the 256-color palette (colors 16-231) that cannot be overridden by your terminal's theme, ensuring consistent bright arcade colors on all terminals

## File Created

- `.babaam_high_score.json` - Stores your high scores (organized by terminal dimension)

Enjoy the game and see how high you can score!
