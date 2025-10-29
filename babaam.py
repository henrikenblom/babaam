#!/usr/bin/env python3
"""
BA-BAAM! - Terminal Space Shooter
A feature-rich side-scrolling space shooter for the terminal

Controls:
  Arrow keys - Move ship
  Space - Shoot
  1-3 - Switch weapons (when unlocked)
  P - Pause/Resume
  ESC - Quit
"""

import curses
import random
import time
import json
import os
import math
import sys
import threading
from dataclasses import dataclass
from typing import List, Tuple
from enum import Enum
from pynput import keyboard
import numpy as np

# Suppress pygame welcome message
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

# Prevent microphone permission request on macOS
# These settings prevent SDL/pygame from requesting audio input permissions
if sys.platform == 'darwin':  # macOS
    os.environ['SDL_AUDIODRIVER'] = 'coreaudio'
    os.environ['SDL_AUDIO_DEVICE_ADD_CAPTURE'] = '0'

import pygame


class WeaponType(Enum):
    """Different weapon types"""
    NORMAL = 1
    SPREAD = 2
    ENERGY_BEAM = 3


class PowerUpType(Enum):
    """Power-up types"""
    RAPID_FIRE = 1
    SHIELD = 2
    HEALTH = 3
    SPREAD_SHOT = 4
    ENERGY_BEAM = 5
    NUKE = 6
    DRONE = 7


class EnemyType(Enum):
    """Enemy types"""
    NORMAL = 1
    FAST = 2
    TANK = 3
    ZIGZAG = 4


@dataclass
class GameObject:
    """Base class for all game objects"""
    x: float
    y: float
    char: str
    color: int = 1


class Player(GameObject):
    """Player's ship"""
    def __init__(self, x: float, y: float):
        super().__init__(x, y, "►", 2)
        self.health = 3
        self.max_health = 3
        self.score = 0
        self.shield = False
        self.shield_timer = 0
        self.rapid_fire = False
        self.rapid_fire_timer = 0
        self.fire_cooldown = 0
        self.weapon = WeaponType.NORMAL
        self.unlocked_weapons = {WeaponType.NORMAL}
        self.vx = 0.0  # Horizontal velocity
        self.vy = 0.0  # Vertical velocity
        self.speed = 0.5  # Movement speed
        self.energy_beam_length = 15  # Current energy beam length (grows when stationary)
        self.energy_beam_top_length = 0  # Top cannon beam length (grows after main beam maxed)
        self.energy_beam_bottom_length = 0  # Bottom cannon beam length (grows after top beam maxed)
        self.energy_beam_charge_time = 0  # Frames spent charging (for accelerating growth)
        self.energy_beam_active_time = 0  # Frames beam has been firing (for overheat/flicker)
        self.energy_beam_decay_time = 0  # Frames at full power (triggers decay/flicker)
        self.energy_beam_overheated = False  # True when beam has shut down and needs trigger release
        self.energy_beam_trigger_was_pressed = False  # Track previous trigger state for release detection
        self.was_stationary = False  # Track if player was stationary last frame
        self.prev_x = x  # Track previous position for actual movement detection
        self.prev_y = y  # Track previous position for actual movement detection
        self.spark_timer = 0  # Timer for blocked beam spark effect
        self.spark_char = '*'  # Character for spark effect
        self.side_beams_activated = False  # Track if side beam activation sound has played
        self.flash_timer = 0  # Flash when taking damage
        # Sleek, solid, pointy ship - no gaps
        self.sprite = ["╱█►", "██►", "╲█►"]
        self.sprite_shield = ["╱█▶", "██▶", "╲█▶"]
        self.width = 3
        self.height = 3


class Bullet(GameObject):
    """Player's bullets"""
    def __init__(self, x: float, y: float, dy: float = 0, damage: int = 1):
        super().__init__(x, y, "─", 3)
        self.speed = 2.0
        self.dy = dy  # Vertical velocity for spread shot
        self.damage = damage  # Damage dealt to enemies


class EnergyBeam(GameObject):
    """Energy beam"""
    def __init__(self, x: float, y: float, length: int = 20):
        super().__init__(x, y, "═", 6)
        self.length = length
        self.lifetime = 10


class Enemy(GameObject):
    """Enemy ships"""
    def __init__(self, x: float, y: float, enemy_type: EnemyType = EnemyType.NORMAL):
        self.type = enemy_type

        if enemy_type == EnemyType.FAST:
            super().__init__(x, y, "≻", 1)
            self.sprite = ["══►"]
            self.width = 3
            self.height = 1
            self.speed = 0.6
            self.health = 1
            self.points = 20
        elif enemy_type == EnemyType.TANK:
            super().__init__(x, y, "▓", 7)
            self.sprite = ["╔▓╗", "╚▓╝"]
            self.width = 3
            self.height = 2
            self.speed = 0.2
            self.health = 10  # Increased from 9 (+10% armor)
            self.points = 30
        elif enemy_type == EnemyType.ZIGZAG:
            super().__init__(x, y, "⟩", 8)
            self.sprite = ["╱►", "╲►"]
            self.width = 2
            self.height = 2
            self.speed = 0.4
            self.health = 3  # Can be destroyed with one plasma shot (3 damage)
            self.points = 25
            self.direction = random.choice([-1, 1])
        else:  # NORMAL
            super().__init__(x, y, "►", 1)
            self.sprite = ["╔►", "╚►"]
            self.width = 2
            self.height = 2
            self.speed = 0.3
            self.health = 1
            self.points = 10

        # Flash timer for hit feedback
        self.flash_timer = 0


class Boss(GameObject):
    """Boss enemy"""
    def __init__(self, x: float, y: float, boss_num: int):
        super().__init__(x, y, "◈", 9)
        self.health = 33 + (boss_num * 22)  # Increased from 30 + (boss_num * 20) (+10% armor)
        self.max_health = self.health
        self.speed = 0.15
        self.points = 200 + (boss_num * 100)
        self.shoot_timer = 0
        self.move_pattern = 0
        self.flash_timer = 0  # Flash timer for hit feedback


class BossBullet(GameObject):
    """Boss's bullets"""
    def __init__(self, x: float, y: float):
        super().__init__(x, y, "●", 1)
        self.speed = -0.8
        self.dy = 0  # Vertical velocity for ricochets


class PowerUp(GameObject):
    """Power-up items"""
    def __init__(self, x: float, y: float, powerup_type: PowerUpType):
        self.type = powerup_type

        if powerup_type == PowerUpType.RAPID_FIRE:
            super().__init__(x, y, "R", 10)
        elif powerup_type == PowerUpType.SHIELD:
            super().__init__(x, y, "S", 11)
        elif powerup_type == PowerUpType.HEALTH:
            super().__init__(x, y, "+", 12)
        elif powerup_type == PowerUpType.SPREAD_SHOT:
            super().__init__(x, y, "W", 13)
        elif powerup_type == PowerUpType.ENERGY_BEAM:
            super().__init__(x, y, "E", 14)
        elif powerup_type == PowerUpType.NUKE:
            super().__init__(x, y, "N", 15)
        else:  # DRONE
            super().__init__(x, y, "D", 16)

        self.speed = 0.2


class Drone(GameObject):
    """Autonomous fighting drone"""
    def __init__(self, x: float, y: float, initial_cooldown: int = 0):
        super().__init__(x, y, "◆", 11)  # Filled diamond, cyan color
        self.lifetime = 480  # 16 seconds at 30 FPS
        self.max_lifetime = 480
        self.fire_cooldown = initial_cooldown
        self.target = None  # Current enemy target
        self.speed = 0.4  # Movement speed
        # Compact sprite - no empty space
        self.char = "◆"
        self.width = 1
        self.height = 1
        # Circle parameters for when no target
        self.circle_angle = 0  # Current angle in circle
        self.circle_radius = 8  # Radius around player


class Explosion(GameObject):
    """Explosion effect"""
    def __init__(self, x: float, y: float, big: bool = False):
        chars = ["*", "✦", "✧", "○"] if big else ["*", "·"]
        super().__init__(x, y, random.choice(chars), 4)
        self.lifetime = 8 if big else 5


class ShipDebris(GameObject):
    """Ship debris that spreads during destruction"""
    def __init__(self, x: float, y: float, vx: float, vy: float):
        chars = ["█", "▓", "▒", "░", "■", "▪", "●", "◆", "◈", "╱", "╲", "═", "║"]
        super().__init__(x, y, random.choice(chars), random.choice([1, 3, 4, 10]))
        self.vx = vx  # Horizontal velocity
        self.vy = vy  # Vertical velocity
        self.lifetime = 60  # 2 seconds at 30 FPS
        self.gravity = 0.05  # Gravity acceleration


class RetroSynth:
    """Retro-style software synthesizer for 8-bit/16-bit game sounds"""

    def __init__(self):
        # Initialize pygame mixer for audio playback
        pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
        self.sample_rate = 22050
        self.sounds = {}
        self.music_channel = None
        self.game_music_channel = None
        self.hero_music_channel = None
        self.intro_drone_channel = None
        self._generate_sounds()
        self._generate_menu_music()
        self._generate_game_music()
        self._generate_intro_drone()
        self._generate_hero_music()

    def _generate_square_wave(self, frequency: float, duration: float, volume: float = 0.3) -> np.ndarray:
        """Generate a square wave (classic 8-bit sound)"""
        t = np.linspace(0, duration, int(self.sample_rate * duration))
        wave = volume * np.sign(np.sin(2 * np.pi * frequency * t))
        return wave

    def _generate_triangle_wave(self, frequency: float, duration: float, volume: float = 0.3) -> np.ndarray:
        """Generate a triangle wave (smoother retro sound)"""
        t = np.linspace(0, duration, int(self.sample_rate * duration))
        wave = volume * 2 * np.abs(2 * ((frequency * t) % 1) - 1) - volume
        return wave

    def _generate_sawtooth_wave(self, frequency: float, duration: float, volume: float = 0.3) -> np.ndarray:
        """Generate a sawtooth wave (bright, buzzy SID-chip sound)"""
        t = np.linspace(0, duration, int(self.sample_rate * duration))
        wave = volume * 2 * ((frequency * t) % 1) - volume
        return wave

    def _apply_lowpass_filter(self, wave: np.ndarray, cutoff_freq: float = 2000) -> np.ndarray:
        """Simple lowpass filter to soften harsh sounds (SID-chip style)"""
        # Simple moving average filter
        window_size = max(1, int(self.sample_rate / cutoff_freq))
        kernel = np.ones(window_size) / window_size
        filtered = np.convolve(wave, kernel, mode='same')
        return filtered

    def _add_vibrato(self, wave: np.ndarray, rate: float = 5, depth: float = 0.05) -> np.ndarray:
        """Add vibrato effect (SID-chip character)"""
        t = np.linspace(0, len(wave) / self.sample_rate, len(wave))
        vibrato = 1 + depth * np.sin(2 * np.pi * rate * t)
        return wave * vibrato

    def _apply_envelope(self, wave: np.ndarray, attack: float = 0.01, decay: float = 0.1) -> np.ndarray:
        """Apply ADSR-like envelope to make sounds more punchy"""
        length = len(wave)
        attack_samples = int(attack * self.sample_rate)
        decay_samples = int(decay * self.sample_rate)

        envelope = np.ones(length)

        # Attack
        if attack_samples > 0:
            envelope[:attack_samples] = np.linspace(0, 1, attack_samples)

        # Decay
        if decay_samples > 0 and decay_samples < length:
            envelope[-decay_samples:] = np.linspace(1, 0, decay_samples)

        return wave * envelope

    def _make_sound(self, wave: np.ndarray) -> pygame.mixer.Sound:
        """Convert numpy array to pygame Sound object"""
        # Normalize and convert to 16-bit integers
        wave = np.clip(wave * 32767, -32767, 32767).astype(np.int16)
        # Create stereo by duplicating mono channel
        stereo = np.column_stack((wave, wave))
        return pygame.mixer.Sound(stereo)

    def _generate_sounds(self):
        """Generate all game sound effects"""

        # Shoot sound - punchy, powerful shot with bass kick and bright attack
        # High frequency component - bright attack with pitch sweep for punch
        t = np.linspace(0, 0.06, int(self.sample_rate * 0.06))
        freq_sweep = 1000 - 200 * (t / 0.06)  # Quick pitch drop from 1000 Hz to 800 Hz
        high_freq = 0.28 * 2 * ((freq_sweep * t) % 1) - 0.28  # Sawtooth with sweep
        high_freq = self._apply_lowpass_filter(high_freq, 4000)  # Filtered to reduce shrillness
        high_freq = self._apply_envelope(high_freq, 0.0005, 0.03)  # Very sharp attack, quick decay

        # Low frequency component - bass punch/kick
        bass_freq_sweep = 200 - 150 * (t / 0.06)  # Drop from 200 Hz to 50 Hz for punch
        bass = 0.35 * np.sin(2 * np.pi * bass_freq_sweep * t)
        bass = self._apply_envelope(bass, 0.001, 0.035)  # Punchy bass

        # Add slight noise for impact character
        noise = np.random.uniform(-0.08, 0.08, len(t))
        noise = self._apply_lowpass_filter(noise, 3000)  # Filtered to reduce harshness
        noise = self._apply_envelope(noise, 0.0003, 0.02)  # Very short noise burst

        # Combine all components
        shoot_wave = high_freq + bass + noise
        self.sounds['shoot'] = self._make_sound(shoot_wave)

        # Spread Shoot sound - triple shot with slight delays between each
        # Create three copies of the shoot sound with delays
        delay_between_shots = 0.015  # 15ms delay between shots
        total_duration = 0.06 + (2 * delay_between_shots)  # Base duration + 2 delays
        spread_wave = np.zeros(int(self.sample_rate * total_duration))

        # First shot at start (reduced volume)
        spread_wave[:len(shoot_wave)] += shoot_wave * 0.6

        # Second shot delayed by 15ms (reduced volume)
        delay1_samples = int(delay_between_shots * self.sample_rate)
        spread_wave[delay1_samples:delay1_samples+len(shoot_wave)] += shoot_wave * 0.6

        # Third shot delayed by 30ms (reduced volume)
        delay2_samples = int(2 * delay_between_shots * self.sample_rate)
        spread_wave[delay2_samples:delay2_samples+len(shoot_wave)] += shoot_wave * 0.6

        self.sounds['spread_shoot'] = self._make_sound(spread_wave)

        # Energy beam sound - constant pitch sawtooth for continuous monotone beam
        # Longer duration for smooth looping when triggered repeatedly
        t = np.linspace(0, 0.2, int(self.sample_rate * 0.2))
        freq = 250  # Constant frequency two octaves lower - no pitch sweep
        # Generate sawtooth wave with constant frequency
        energy_beam_wave = 0.18 * 2 * ((freq * t) % 1) - 0.18
        energy_beam_wave = self._apply_lowpass_filter(energy_beam_wave, 5000)  # Brighter, less filtered
        # Very gentle envelope for seamless looping
        energy_beam_wave = self._apply_envelope(energy_beam_wave, 0.01, 0.04)
        self.sounds['energy_beam'] = self._make_sound(energy_beam_wave)

        # Energy beam dying sound - constant pitch with heavy noise for instability
        t = np.linspace(0, 0.2, int(self.sample_rate * 0.2))
        freq = 250  # Same constant frequency as normal beam (two octaves lower)
        # Generate sawtooth wave with constant frequency
        energy_beam_dying_wave = 0.18 * 2 * ((freq * t) % 1) - 0.18
        # Add significant noise for dying/unstable crackling effect
        noise = np.random.uniform(-0.15, 0.15, len(t))  # Much louder noise
        noise = self._apply_lowpass_filter(noise, 6000)  # Less filtering - keep high frequencies for crackle
        energy_beam_dying_wave = energy_beam_dying_wave + noise
        energy_beam_dying_wave = self._apply_lowpass_filter(energy_beam_dying_wave, 5000)  # Brighter, less filtered
        # Very gentle envelope for seamless looping
        energy_beam_dying_wave = self._apply_envelope(energy_beam_dying_wave, 0.01, 0.04)
        self.sounds['energy_beam_dying'] = self._make_sound(energy_beam_dying_wave)

        # Blocked/denied sound - metallic "error" burst similar to beam but with harsh modulation
        t = np.linspace(0, 0.15, int(self.sample_rate * 0.15))
        freq = 250  # Same base frequency as energy beam for consistency
        # Generate sawtooth wave (metallic like beam)
        blocked_wave = 0.28 * 2 * ((freq * t) % 1) - 0.28
        # Add harsh amplitude modulation for "error" character (25 Hz tremolo)
        modulation = 1 + 0.6 * np.sin(2 * np.pi * 25 * t)
        blocked_wave = blocked_wave * modulation
        # Metallic filtering (similar to beam but slightly harsher)
        blocked_wave = self._apply_lowpass_filter(blocked_wave, 1500)
        blocked_wave = self._apply_envelope(blocked_wave, 0.002, 0.08)
        self.sounds['blocked'] = self._make_sound(blocked_wave)

        # Explosion - descending pitch sweep like energy beam but with noise
        t = np.linspace(0, 0.18, int(self.sample_rate * 0.18))
        freq = 800 - 600 * t / 0.18  # Sweep from 800 Hz down to 200 Hz
        # Generate sawtooth wave with pitch sweep
        explosion_wave = 0.2 * 2 * ((freq * t) % 1) - 0.2
        # Add noise for explosive character
        noise = np.random.uniform(-0.1, 0.1, len(explosion_wave))
        explosion_wave = explosion_wave + noise
        explosion_wave = self._apply_lowpass_filter(explosion_wave, 3500)
        explosion_wave = self._apply_envelope(explosion_wave, 0.005, 0.1)
        self.sounds['explosion'] = self._make_sound(explosion_wave)

        # Power-up - ascending arpeggio with bright sawtooth
        powerup_wave = np.concatenate([
            self._generate_sawtooth_wave(523, 0.08, 0.14),  # C
            self._generate_sawtooth_wave(659, 0.08, 0.14),  # E
            self._generate_sawtooth_wave(784, 0.08, 0.14),  # G
        ])
        powerup_wave = self._apply_lowpass_filter(powerup_wave, 4000)
        powerup_wave = self._apply_envelope(powerup_wave, 0.01, 0.1)
        self.sounds['powerup'] = self._make_sound(powerup_wave)

        # Intro versions - distant sounds with heavy filtering, reverb, and echoes
        # These are used in the intro sequence to sound like action viewed from afar

        # Intro Shoot - heavily filtered and echoed shoot sound
        intro_shoot_base = shoot_wave.copy()
        # Heavy lowpass filtering to simulate distance
        intro_shoot_base = self._apply_lowpass_filter(intro_shoot_base, 1200)
        # Increase volume for more presence
        intro_shoot_base = intro_shoot_base * 0.8

        # Create buffer for echoes and reverb
        intro_shoot_duration = 0.6  # Longer to accommodate echoes
        intro_shoot = np.zeros(int(self.sample_rate * intro_shoot_duration))
        intro_shoot[:len(intro_shoot_base)] = intro_shoot_base

        # Add reverb (multiple small delays to simulate room reflections)
        reverb_delays = [0.02, 0.04, 0.06, 0.08, 0.10]
        reverb_volumes = [0.24, 0.19, 0.16, 0.13, 0.10]
        for delay, volume in zip(reverb_delays, reverb_volumes):
            delay_samples = int(delay * self.sample_rate)
            if delay_samples + len(intro_shoot_base) < len(intro_shoot):
                intro_shoot[delay_samples:delay_samples+len(intro_shoot_base)] += intro_shoot_base * volume

        # Add distinct echoes
        echo_delays = [0.15, 0.30, 0.45]
        echo_volumes = [0.56, 0.32, 0.19]
        for delay, volume in zip(echo_delays, echo_volumes):
            delay_samples = int(delay * self.sample_rate)
            if delay_samples + len(intro_shoot_base) < len(intro_shoot):
                intro_shoot[delay_samples:delay_samples+len(intro_shoot_base)] += intro_shoot_base * volume

        self.sounds['intro_shoot'] = self._make_sound(intro_shoot)

        # Intro Explosion - heavily filtered and echoed explosion sound
        intro_explosion_base = explosion_wave.copy()
        # Heavy lowpass filtering to simulate distance
        intro_explosion_base = self._apply_lowpass_filter(intro_explosion_base, 1000)
        # Increase volume for more presence
        intro_explosion_base = intro_explosion_base * 0.9

        # Create buffer for echoes and reverb
        intro_explosion_duration = 0.8  # Longer to accommodate echoes
        intro_explosion = np.zeros(int(self.sample_rate * intro_explosion_duration))
        intro_explosion[:len(intro_explosion_base)] = intro_explosion_base

        # Add reverb (multiple small delays)
        for delay, volume in zip(reverb_delays, reverb_volumes):
            delay_samples = int(delay * self.sample_rate)
            if delay_samples + len(intro_explosion_base) < len(intro_explosion):
                intro_explosion[delay_samples:delay_samples+len(intro_explosion_base)] += intro_explosion_base * volume

        # Add distinct echoes
        explosion_echo_delays = [0.18, 0.36, 0.54]
        explosion_echo_volumes = [0.64, 0.40, 0.24]
        for delay, volume in zip(explosion_echo_delays, explosion_echo_volumes):
            delay_samples = int(delay * self.sample_rate)
            if delay_samples + len(intro_explosion_base) < len(intro_explosion):
                intro_explosion[delay_samples:delay_samples+len(intro_explosion_base)] += intro_explosion_base * volume

        self.sounds['intro_explosion'] = self._make_sound(intro_explosion)

        # Squadron Ship Explosion - medium intensity, between intro_explosion and nuke
        # Less filtered than intro_explosion for more punch, but still with some distance
        squadron_explosion_base = explosion_wave.copy()
        # Moderate lowpass filtering - less than intro but still filtered
        squadron_explosion_base = self._apply_lowpass_filter(squadron_explosion_base, 2500)
        # Higher volume than intro_explosion
        squadron_explosion_base = squadron_explosion_base * 1.1

        # Create buffer for shorter echoes (less reverb than intro)
        squadron_explosion_duration = 0.5
        squadron_explosion = np.zeros(int(self.sample_rate * squadron_explosion_duration))
        squadron_explosion[:len(squadron_explosion_base)] = squadron_explosion_base

        # Add moderate reverb
        squad_reverb_delays = [0.02, 0.04, 0.06]
        squad_reverb_volumes = [0.20, 0.15, 0.10]
        for delay, volume in zip(squad_reverb_delays, squad_reverb_volumes):
            delay_samples = int(delay * self.sample_rate)
            if delay_samples + len(squadron_explosion_base) < len(squadron_explosion):
                squadron_explosion[delay_samples:delay_samples+len(squadron_explosion_base)] += squadron_explosion_base * volume

        # Add shorter, punchier echoes
        squad_echo_delays = [0.12, 0.24]
        squad_echo_volumes = [0.45, 0.25]
        for delay, volume in zip(squad_echo_delays, squad_echo_volumes):
            delay_samples = int(delay * self.sample_rate)
            if delay_samples + len(squadron_explosion_base) < len(squadron_explosion):
                squadron_explosion[delay_samples:delay_samples+len(squadron_explosion_base)] += squadron_explosion_base * volume

        self.sounds['squadron_explosion'] = self._make_sound(squadron_explosion)

        # Damage - harsh low sound with filtered sawtooth
        damage_wave = self._generate_sawtooth_wave(150, 0.15, 0.28)
        damage_wave = self._apply_lowpass_filter(damage_wave, 1200)
        damage_wave = self._apply_envelope(damage_wave, 0.005, 0.08)
        self.sounds['damage'] = self._make_sound(damage_wave)

        # Boss appear - dramatic low to high sweep with sawtooth
        t = np.linspace(0, 0.4, int(self.sample_rate * 0.4))
        freq = 200 + 400 * (t / 0.4) ** 2
        # Generate frequency sweep with sawtooth
        boss_wave = 0.22 * 2 * ((freq * t) % 1) - 0.22
        boss_wave = self._apply_lowpass_filter(boss_wave, 2000)
        boss_wave = self._add_vibrato(boss_wave, rate=7, depth=0.04)  # Add drama
        boss_wave = self._apply_envelope(boss_wave, 0.02, 0.15)
        self.sounds['boss'] = self._make_sound(boss_wave)

        # Nuke - massive explosion with weight, punch, and rumble
        # CRACK - ultra-sharp high-frequency transient for instant punch
        crack_t = np.linspace(0, 0.008, int(self.sample_rate * 0.008))
        crack_freq = 3000 - 2500 * (crack_t / 0.008)  # Sharp drop from 3000 Hz to 500 Hz
        crack = 0.65 * np.sin(2 * np.pi * crack_freq * crack_t)
        crack = self._apply_envelope(crack, 0.0001, 0.006)  # Extremely sharp attack

        # PUNCH - mid-frequency impact for chest-hitting punch
        punch_t = np.linspace(0, 0.05, int(self.sample_rate * 0.05))
        punch_freq = 250 - 180 * (punch_t / 0.05)  # 250 Hz → 70 Hz
        punch = 0.6 * np.sin(2 * np.pi * punch_freq * punch_t)
        punch = self._apply_envelope(punch, 0.0003, 0.03)  # Sharp punch

        # Sub-bass kick for weight (increased volume)
        impact_t = np.linspace(0, 0.15, int(self.sample_rate * 0.15))
        impact_freq = 80 - 65 * (impact_t / 0.15)  # Drop from 80 Hz to 15 Hz
        impact = 0.65 * np.sin(2 * np.pi * impact_freq * impact_t)  # Increased from 0.5
        impact = self._apply_envelope(impact, 0.0008, 0.08)  # Sharper attack

        # Mid rumble layers - sawtooth waves for grit (increased volume)
        rumble = np.concatenate([
            self._generate_sawtooth_wave(100, 0.1, 0.42),  # Increased from 0.35
            self._generate_sawtooth_wave(80, 0.15, 0.42),
            self._generate_sawtooth_wave(60, 0.2, 0.38),
        ])

        # Heavy noise layer - massive explosion character (increased volume and pitch)
        noise = np.random.uniform(-0.55, 0.55, len(rumble))  # Much louder for intense chaos
        noise = self._apply_lowpass_filter(noise, 2500)  # Higher pitch for sharper, more violent sound

        # Combine layers - crack + punch + impact + rumble + noise
        # Pad shorter layers to match rumble length
        crack_padded = np.zeros(len(rumble))
        crack_padded[:len(crack)] = crack

        punch_padded = np.zeros(len(rumble))
        punch_padded[:len(punch)] = punch

        impact_padded = np.zeros(len(rumble))
        impact_padded[:len(impact)] = impact

        nuke_wave = crack_padded + punch_padded + impact_padded + rumble + noise
        nuke_wave = self._apply_lowpass_filter(nuke_wave, 1100)  # Slightly brighter filtering
        nuke_wave = self._apply_envelope(nuke_wave, 0.0001, 0.28)  # Much sharper initial attack
        self.sounds['nuke'] = self._make_sound(nuke_wave)

        # Nuke echo sounds - each one octave lower
        # Echo 1 - one octave down (all frequencies × 0.5)
        crack_freq_echo1 = (3000 - 2500 * (crack_t / 0.008)) * 0.5
        crack_echo1 = 0.65 * np.sin(2 * np.pi * crack_freq_echo1 * crack_t)
        crack_echo1 = self._apply_envelope(crack_echo1, 0.0001, 0.006)

        punch_freq_echo1 = (250 - 180 * (punch_t / 0.05)) * 0.5
        punch_echo1 = 0.6 * np.sin(2 * np.pi * punch_freq_echo1 * punch_t)
        punch_echo1 = self._apply_envelope(punch_echo1, 0.0003, 0.03)

        impact_freq_echo1 = (80 - 65 * (impact_t / 0.15)) * 0.5
        impact_echo1 = 0.65 * np.sin(2 * np.pi * impact_freq_echo1 * impact_t)
        impact_echo1 = self._apply_envelope(impact_echo1, 0.0008, 0.08)

        rumble_echo1 = np.concatenate([
            self._generate_sawtooth_wave(50, 0.1, 0.42),
            self._generate_sawtooth_wave(40, 0.15, 0.42),
            self._generate_sawtooth_wave(30, 0.2, 0.38),
        ])
        noise_echo1 = np.random.uniform(-0.55, 0.55, len(rumble_echo1))
        noise_echo1 = self._apply_lowpass_filter(noise_echo1, 1250)

        crack_padded_echo1 = np.zeros(len(rumble_echo1))
        crack_padded_echo1[:len(crack_echo1)] = crack_echo1
        punch_padded_echo1 = np.zeros(len(rumble_echo1))
        punch_padded_echo1[:len(punch_echo1)] = punch_echo1
        impact_padded_echo1 = np.zeros(len(rumble_echo1))
        impact_padded_echo1[:len(impact_echo1)] = impact_echo1

        nuke_wave_echo1 = crack_padded_echo1 + punch_padded_echo1 + impact_padded_echo1 + rumble_echo1 + noise_echo1
        nuke_wave_echo1 = self._apply_lowpass_filter(nuke_wave_echo1, 550)
        nuke_wave_echo1 = self._apply_envelope(nuke_wave_echo1, 0.0001, 0.28)
        self.sounds['nuke_echo_1'] = self._make_sound(nuke_wave_echo1)

        # Echo 2 - two octaves down (all frequencies × 0.25)
        crack_freq_echo2 = (3000 - 2500 * (crack_t / 0.008)) * 0.25
        crack_echo2 = 0.65 * np.sin(2 * np.pi * crack_freq_echo2 * crack_t)
        crack_echo2 = self._apply_envelope(crack_echo2, 0.0001, 0.006)

        punch_freq_echo2 = (250 - 180 * (punch_t / 0.05)) * 0.25
        punch_echo2 = 0.6 * np.sin(2 * np.pi * punch_freq_echo2 * punch_t)
        punch_echo2 = self._apply_envelope(punch_echo2, 0.0003, 0.03)

        impact_freq_echo2 = (80 - 65 * (impact_t / 0.15)) * 0.25
        impact_echo2 = 0.65 * np.sin(2 * np.pi * impact_freq_echo2 * impact_t)
        impact_echo2 = self._apply_envelope(impact_echo2, 0.0008, 0.08)

        rumble_echo2 = np.concatenate([
            self._generate_sawtooth_wave(25, 0.1, 0.42),
            self._generate_sawtooth_wave(20, 0.15, 0.42),
            self._generate_sawtooth_wave(15, 0.2, 0.38),
        ])
        noise_echo2 = np.random.uniform(-0.55, 0.55, len(rumble_echo2))
        noise_echo2 = self._apply_lowpass_filter(noise_echo2, 625)

        crack_padded_echo2 = np.zeros(len(rumble_echo2))
        crack_padded_echo2[:len(crack_echo2)] = crack_echo2
        punch_padded_echo2 = np.zeros(len(rumble_echo2))
        punch_padded_echo2[:len(punch_echo2)] = punch_echo2
        impact_padded_echo2 = np.zeros(len(rumble_echo2))
        impact_padded_echo2[:len(impact_echo2)] = impact_echo2

        nuke_wave_echo2 = crack_padded_echo2 + punch_padded_echo2 + impact_padded_echo2 + rumble_echo2 + noise_echo2
        nuke_wave_echo2 = self._apply_lowpass_filter(nuke_wave_echo2, 275)
        nuke_wave_echo2 = self._apply_envelope(nuke_wave_echo2, 0.0001, 0.28)
        self.sounds['nuke_echo_2'] = self._make_sound(nuke_wave_echo2)

        # Echo 3 - three octaves down (all frequencies × 0.125)
        crack_freq_echo3 = (3000 - 2500 * (crack_t / 0.008)) * 0.125
        crack_echo3 = 0.65 * np.sin(2 * np.pi * crack_freq_echo3 * crack_t)
        crack_echo3 = self._apply_envelope(crack_echo3, 0.0001, 0.006)

        punch_freq_echo3 = (250 - 180 * (punch_t / 0.05)) * 0.125
        punch_echo3 = 0.6 * np.sin(2 * np.pi * punch_freq_echo3 * punch_t)
        punch_echo3 = self._apply_envelope(punch_echo3, 0.0003, 0.03)

        impact_freq_echo3 = (80 - 65 * (impact_t / 0.15)) * 0.125
        impact_echo3 = 0.65 * np.sin(2 * np.pi * impact_freq_echo3 * impact_t)
        impact_echo3 = self._apply_envelope(impact_echo3, 0.0008, 0.08)

        rumble_echo3 = np.concatenate([
            self._generate_sawtooth_wave(12.5, 0.1, 0.42),
            self._generate_sawtooth_wave(10, 0.15, 0.42),
            self._generate_sawtooth_wave(7.5, 0.2, 0.38),
        ])
        noise_echo3 = np.random.uniform(-0.55, 0.55, len(rumble_echo3))
        noise_echo3 = self._apply_lowpass_filter(noise_echo3, 312)

        crack_padded_echo3 = np.zeros(len(rumble_echo3))
        crack_padded_echo3[:len(crack_echo3)] = crack_echo3
        punch_padded_echo3 = np.zeros(len(rumble_echo3))
        punch_padded_echo3[:len(punch_echo3)] = punch_echo3
        impact_padded_echo3 = np.zeros(len(rumble_echo3))
        impact_padded_echo3[:len(impact_echo3)] = impact_echo3

        nuke_wave_echo3 = crack_padded_echo3 + punch_padded_echo3 + impact_padded_echo3 + rumble_echo3 + noise_echo3
        nuke_wave_echo3 = self._apply_lowpass_filter(nuke_wave_echo3, 137)
        nuke_wave_echo3 = self._apply_envelope(nuke_wave_echo3, 0.0001, 0.28)
        self.sounds['nuke_echo_3'] = self._make_sound(nuke_wave_echo3)

        # Game Over - punchy multi-channel descent in E minor (1.5 seconds total)
        # MELODY CHANNEL - quick descending phrase (sawtooth - bright)
        melody_notes = [
            (659, 0.0, 0.15),    # E5
            (494, 0.15, 0.15),   # B4
            (392, 0.3, 0.2),     # G4
            (330, 0.5, 0.25),    # E4
            (165, 0.75, 0.75),   # E3 - final low note
        ]
        melody = np.zeros(int(self.sample_rate * 1.5))
        for freq, start, duration in melody_notes:
            note = self._generate_sawtooth_wave(freq, duration, 0.22)
            note = self._apply_lowpass_filter(note, 3500)
            note = self._apply_envelope(note, 0.01, 0.15)
            start_sample = int(start * self.sample_rate)
            end_sample = start_sample + len(note)
            melody[start_sample:end_sample] += note

        # HARMONY CHANNEL - falling thirds (square wave - 8-bit character)
        harmony_notes = [
            (784, 0.0, 0.15),    # G5
            (587, 0.15, 0.15),   # D5
            (494, 0.3, 0.2),     # B4
            (392, 0.5, 0.25),    # G4
            (196, 0.75, 0.75),   # G3
        ]
        harmony = np.zeros(int(self.sample_rate * 1.5))
        for freq, start, duration in harmony_notes:
            note = self._generate_square_wave(freq, duration, 0.15)
            note = self._apply_lowpass_filter(note, 2800)
            note = self._apply_envelope(note, 0.01, 0.15)
            start_sample = int(start * self.sample_rate)
            end_sample = start_sample + len(note)
            harmony[start_sample:end_sample] += note

        # BASS CHANNEL - powerful descending bass (triangle wave - warm)
        bass_notes = [
            (165, 0.0, 0.3),     # E3
            (147, 0.3, 0.3),     # D3
            (131, 0.6, 0.9),     # C3 - final bass note
        ]
        bass = np.zeros(int(self.sample_rate * 1.5))
        for freq, start, duration in bass_notes:
            note = self._generate_triangle_wave(freq, duration, 0.28)
            note = self._apply_lowpass_filter(note, 600)
            note = self._apply_envelope(note, 0.02, 0.2)
            start_sample = int(start * self.sample_rate)
            end_sample = start_sample + len(note)
            bass[start_sample:end_sample] += note

        # IMPACT - punchy low thud at the end
        impact_t = np.linspace(0, 0.15, int(self.sample_rate * 0.15))
        impact_freq = 100 - 80 * (impact_t / 0.15)
        impact = 0.35 * np.sin(2 * np.pi * impact_freq * impact_t)
        impact = self._apply_envelope(impact, 0.001, 0.1)
        impact_padded = np.zeros(int(self.sample_rate * 1.5))
        impact_start = int(0.75 * self.sample_rate)
        impact_padded[impact_start:impact_start+len(impact)] = impact

        # Combine all channels
        gameover_wave = melody + harmony + bass + impact_padded

        # Add vibrato to final section
        final_section_start = int(0.75 * self.sample_rate)
        vibrato_length = len(gameover_wave) - final_section_start
        vibrato = 0.12 * np.sin(2 * np.pi * 5 * np.linspace(0, 0.75, vibrato_length))
        gameover_wave[final_section_start:] *= (1 + vibrato)

        gameover_wave = self._apply_envelope(gameover_wave, 0.01, 0.3)
        self.sounds['gameover'] = self._make_sound(gameover_wave)

        # Boss Hit - metallic clang with sawtooth (satisfying feedback for damaging boss)
        # Two-tone metallic hit with quick pitch drop
        hit1 = self._generate_sawtooth_wave(600, 0.04, 0.22)
        hit2 = self._generate_sawtooth_wave(450, 0.06, 0.18)
        boss_hit_wave = np.concatenate([hit1, hit2])
        boss_hit_wave = self._apply_lowpass_filter(boss_hit_wave, 2500)  # Bright but controlled
        # Add some noise for metallic texture
        noise = np.random.uniform(-0.08, 0.08, len(boss_hit_wave))
        boss_hit_wave = boss_hit_wave + noise
        boss_hit_wave = self._apply_envelope(boss_hit_wave, 0.001, 0.05)
        self.sounds['boss_hit'] = self._make_sound(boss_hit_wave)

        # Ricochet - metallic ping/zing when bullets bounce off wall
        ricochet_t = np.linspace(0, 0.12, int(self.sample_rate * 0.12))
        # DESCENDING pitch sweep for realistic metal bounce (3500 Hz → 800 Hz)
        ricochet_freq = 3500 - 2700 * (ricochet_t / 0.12) ** 0.7

        # FUNDAMENTAL - main tone with triangle wave for metallic character
        ricochet_wave = 0.18 * 2 * np.abs(2 * ((ricochet_freq * ricochet_t) % 1) - 1) - 0.18

        # INHARMONIC OVERTONES - multiple non-integer harmonics for metallic timbre
        # Real metal has overtones at non-harmonic ratios (not exact multiples)
        harmonic1 = 0.12 * np.sin(2 * np.pi * ricochet_freq * 2.76 * ricochet_t)  # 2.76x
        harmonic2 = 0.09 * np.sin(2 * np.pi * ricochet_freq * 5.40 * ricochet_t)  # 5.40x
        harmonic3 = 0.07 * np.sin(2 * np.pi * ricochet_freq * 8.93 * ricochet_t)  # 8.93x (high zing)
        ricochet_wave = ricochet_wave + harmonic1 + harmonic2 + harmonic3

        # IMPACT TRANSIENT - DOMINANT ultra-sharp high-frequency click at the start
        impact_t = np.linspace(0, 0.004, int(self.sample_rate * 0.004))
        # High-frequency metallic crack (8000 Hz)
        impact = 0.55 * np.sin(2 * np.pi * 8000 * impact_t)  # Much louder and higher
        # Add super-bright overtone for extra metallic crack
        impact_overtone = 0.38 * np.sin(2 * np.pi * 12000 * impact_t)
        impact = impact + impact_overtone
        impact = self._apply_envelope(impact, 0.00005, 0.003)  # Extremely sharp
        impact_padded = np.zeros(len(ricochet_wave))
        impact_padded[:len(impact)] = impact
        ricochet_wave = ricochet_wave + impact_padded

        # BRIGHT METALLIC NOISE - high-frequency noise for shimmer
        noise = np.random.uniform(-0.08, 0.08, len(ricochet_wave))
        noise = self._apply_lowpass_filter(noise, 9000)  # Even brighter
        ricochet_wave = ricochet_wave + noise

        # SHIMMER - slight frequency modulation for metallic character
        shimmer = 1 + 0.06 * np.sin(2 * np.pi * 15 * ricochet_t)  # Fast shimmer
        ricochet_wave = ricochet_wave * shimmer

        ricochet_wave = self._apply_lowpass_filter(ricochet_wave, 8000)  # Very bright and metallic
        ricochet_wave = self._apply_envelope(ricochet_wave, 0.0001, 0.08)  # Ultra-sharp attack, quick decay
        self.sounds['ricochet'] = self._make_sound(ricochet_wave)

        # Boss Fire - deep, menacing shot
        boss_fire_t = np.linspace(0, 0.12, int(self.sample_rate * 0.12))
        # Deep frequency sweep (150 Hz → 100 Hz) for menacing rumble
        boss_fire_freq = 150 - 50 * (boss_fire_t / 0.12)
        boss_fire_wave = 0.32 * np.sin(2 * np.pi * boss_fire_freq * boss_fire_t)
        # Add mid-frequency punch (400 Hz → 300 Hz)
        mid_freq = 400 - 100 * (boss_fire_t / 0.12)
        mid_punch = 0.22 * 2 * ((mid_freq * boss_fire_t) % 1) - 0.22  # Sawtooth for edge
        boss_fire_wave = boss_fire_wave + mid_punch
        # Heavy noise for aggressive character
        noise = np.random.uniform(-0.1, 0.1, len(boss_fire_wave))
        noise = self._apply_lowpass_filter(noise, 2000)
        boss_fire_wave = boss_fire_wave + noise
        boss_fire_wave = self._apply_lowpass_filter(boss_fire_wave, 1800)  # Deep and menacing
        boss_fire_wave = self._apply_envelope(boss_fire_wave, 0.003, 0.08)  # Slower, more menacing attack
        self.sounds['boss_fire'] = self._make_sound(boss_fire_wave)

        # Engine Idle - pure noise-based rumble (baseline, always playing)
        # Simulates constant motion through space
        engine_duration = 1.0
        # Generate pure noise (increased volume)
        idle_wave = np.random.uniform(-0.28, 0.28, int(self.sample_rate * engine_duration))
        # Heavy lowpass filtering for deep engine rumble
        idle_wave = self._apply_lowpass_filter(idle_wave, 600)
        # Smooth envelope for seamless looping
        fade_samples = int(0.08 * self.sample_rate)
        envelope = np.ones(len(idle_wave))
        envelope[:fade_samples] = np.linspace(0.7, 1, fade_samples)
        envelope[-fade_samples:] = np.linspace(1, 0.7, fade_samples)
        idle_wave = idle_wave * envelope
        self.sounds['engine_idle'] = self._make_sound(idle_wave)

        # Engine Right - more intense (moving forward/right)
        right_duration = 0.8
        right_wave = np.random.uniform(-0.38, 0.38, int(self.sample_rate * right_duration))
        right_wave = self._apply_lowpass_filter(right_wave, 1300)
        fade_samples = int(0.06 * self.sample_rate)
        envelope = np.ones(len(right_wave))
        envelope[:fade_samples] = np.linspace(0.6, 1, fade_samples)
        envelope[-fade_samples:] = np.linspace(1, 0.6, fade_samples)
        right_wave = right_wave * envelope
        self.sounds['engine_right'] = self._make_sound(right_wave)

        # Engine Left - less intense (slowing down)
        left_duration = 0.9
        left_wave = np.random.uniform(-0.23, 0.23, int(self.sample_rate * left_duration))
        left_wave = self._apply_lowpass_filter(left_wave, 500)
        fade_samples = int(0.07 * self.sample_rate)
        envelope = np.ones(len(left_wave))
        envelope[:fade_samples] = np.linspace(0.75, 1, fade_samples)
        envelope[-fade_samples:] = np.linspace(1, 0.75, fade_samples)
        left_wave = left_wave * envelope
        self.sounds['engine_left'] = self._make_sound(left_wave)

        # Engine Vertical - moderately intense (up/down maneuvering)
        vert_duration = 0.85
        vert_wave = np.random.uniform(-0.32, 0.32, int(self.sample_rate * vert_duration))
        vert_wave = self._apply_lowpass_filter(vert_wave, 900)
        fade_samples = int(0.065 * self.sample_rate)
        envelope = np.ones(len(vert_wave))
        envelope[:fade_samples] = np.linspace(0.65, 1, fade_samples)
        envelope[-fade_samples:] = np.linspace(1, 0.65, fade_samples)
        vert_wave = vert_wave * envelope
        self.sounds['engine_vertical'] = self._make_sound(vert_wave)

        # Drone Shot - menacing, aggressive synthetic plasma bolt
        # Lower frequency with harsh sawtooth and mechanical noise
        t = np.linspace(0, 0.09, int(self.sample_rate * 0.09))
        # Lower base frequency for more menacing tone (400 Hz → 520 Hz)
        freq_sweep = 400 + 120 * (t / 0.09)
        # Sawtooth wave for aggressive edge
        drone_shot = 0.18 * 2 * (((freq_sweep * t) % 1) - 0.5)
        # Aggressive frequency modulation for mechanical menace
        modulation = 1 + 0.15 * np.sin(2 * np.pi * 45 * t)  # Deeper, faster modulation
        drone_shot = drone_shot * modulation
        # Add mechanical noise for harshness
        noise = np.random.uniform(-0.08, 0.08, len(t))
        noise = self._apply_lowpass_filter(noise, 3000)
        drone_shot = drone_shot + noise
        # Aggressive filtering - keep more bite
        drone_shot = self._apply_lowpass_filter(drone_shot, 5000)
        drone_shot = self._apply_envelope(drone_shot, 0.001, 0.05)
        self.sounds['drone_shoot'] = self._make_sound(drone_shot)

        # Side Beam Activation - aggressive downward surge for power-up
        t = np.linspace(0, 0.44, int(self.sample_rate * 0.44))
        # Aggressive downward sweep from 275 Hz to 100 Hz (menacing descent)
        freq_sweep = 275 - 175 * (t / 0.44) ** 1.5  # Exponential sweep for punch

        # MAIN TONE - sawtooth wave for harsh metallic character
        side_beam_wave = 0.30 * 2 * ((freq_sweep * t) % 1) - 0.30

        # HARSH HARMONICS - add aggressive overtones
        harmonic1 = 0.18 * 2 * ((freq_sweep * 2.1 * t) % 1) - 0.18  # Inharmonic overtone
        harmonic2 = 0.12 * 2 * ((freq_sweep * 3.2 * t) % 1) - 0.12  # Even harsher
        side_beam_wave = side_beam_wave + harmonic1 + harmonic2

        # AGGRESSIVE NOISE - add crackle for menacing character
        noise = np.random.uniform(-0.12, 0.12, len(t))
        noise = self._apply_lowpass_filter(noise, 7000)  # Bright aggressive noise
        side_beam_wave = side_beam_wave + noise

        # Harsh filtering - keep high frequencies for aggression
        side_beam_wave = self._apply_lowpass_filter(side_beam_wave, 6000)

        # Sharp attack for punch
        side_beam_wave = self._apply_envelope(side_beam_wave, 0.005, 0.06)
        self.sounds['side_beam_activate'] = self._make_sound(side_beam_wave)

        # Game Start Fanfare - dark, menacing multi-channel E minor ascent (1.2 seconds total)
        # MELODY CHANNEL - ominous ascending pattern with dissonance (sawtooth - aggressive)
        melody_notes = [
            (330, 0.0, 0.15),     # E4 - tonic
            (392, 0.15, 0.15),    # G4 - minor third
            (466, 0.3, 0.2),      # Bb4 - tritone for tension
            (659, 0.5, 0.7),      # E5 - octave sustain
        ]
        melody = np.zeros(int(self.sample_rate * 1.2))
        for freq, start, duration in melody_notes:
            note = self._generate_sawtooth_wave(freq, duration, 0.32)
            note = self._apply_lowpass_filter(note, 2000)  # Darker, more aggressive
            note = self._apply_envelope(note, 0.005, 0.15)
            start_sample = int(start * self.sample_rate)
            end_sample = start_sample + len(note)
            melody[start_sample:end_sample] += note

        # HARMONY CHANNEL - ascending dissonant intervals (square wave - harsh)
        harmony_notes = [
            (196, 0.0, 0.15),     # G3 - minor third below melody
            (233, 0.15, 0.15),    # Bb3 - tritone tension
            (294, 0.3, 0.2),      # D4 - rising
            (392, 0.5, 0.7),      # G4 - sustain harmony
        ]
        harmony = np.zeros(int(self.sample_rate * 1.2))
        for freq, start, duration in harmony_notes:
            note = self._generate_square_wave(freq, duration, 0.20)
            note = self._apply_lowpass_filter(note, 1800)  # Darker
            note = self._apply_envelope(note, 0.005, 0.15)
            start_sample = int(start * self.sample_rate)
            end_sample = start_sample + len(note)
            harmony[start_sample:end_sample] += note

        # BASS CHANNEL - menacing sub-bass ascent (sawtooth - gritty)
        bass_notes = [
            (82, 0.0, 0.5),      # E2 - low tonic
            (82, 0.5, 0.7),      # E2 - steady dark foundation
        ]
        bass = np.zeros(int(self.sample_rate * 1.2))
        for freq, start, duration in bass_notes:
            note = self._generate_sawtooth_wave(freq, duration, 0.40)
            note = self._apply_lowpass_filter(note, 450)  # Very dark
            note = self._apply_envelope(note, 0.010, 0.20)
            start_sample = int(start * self.sample_rate)
            end_sample = start_sample + len(note)
            bass[start_sample:end_sample] += note

        # IMPACT - heavy kick with more weight
        impact_t = np.linspace(0, 0.10, int(self.sample_rate * 0.10))
        impact_freq = 100 - 85 * (impact_t / 0.10)  # 100 Hz → 15 Hz - deeper
        impact = 0.45 * np.sin(2 * np.pi * impact_freq * impact_t)
        impact = self._apply_envelope(impact, 0.001, 0.07)
        impact_padded = np.zeros(int(self.sample_rate * 1.2))
        impact_padded[:len(impact)] = impact

        # Combine all channels
        fanfare_wave = melody + harmony + bass + impact_padded

        # Add darker reverb with longer decay
        delay_samples = int(0.08 * self.sample_rate)
        delayed = np.zeros(len(fanfare_wave))
        delayed[delay_samples:] = fanfare_wave[:-delay_samples] * 0.30
        fanfare_wave = fanfare_wave + delayed

        fanfare_wave = self._apply_envelope(fanfare_wave, 0.008, 0.30)
        self.sounds['game_start'] = self._make_sound(fanfare_wave)

        # Achievement Ding - pleasant chime for point increments
        # Simple ascending two-note chime (C6 -> E6) with triangle wave for soft, pleasant tone
        ding_wave = np.concatenate([
            self._generate_triangle_wave(1047, 0.08, 0.15),  # C6
            self._generate_triangle_wave(1319, 0.08, 0.15),  # E6
        ])
        ding_wave = self._apply_lowpass_filter(ding_wave, 5000)  # Soft filtering
        ding_wave = self._apply_envelope(ding_wave, 0.005, 0.08)
        self.sounds['ding'] = self._make_sound(ding_wave)

    def _generate_menu_music(self):
        """Generate dark, menacing electronic menu music for space shooter"""
        # Faster, driving tempo: 0.4 seconds per beat = 150 BPM - dark and energetic
        beat = 0.4
        bar = beat * 4  # 1.6 seconds per bar

        # Notes frequencies
        C4, D4, E4, F4, G4, A4, B4 = 262, 294, 330, 349, 392, 440, 494
        C5, D5, E5, F5, G5, A5, B5, C6 = 523, 587, 659, 698, 784, 880, 988, 1047
        D6, E6, F6, G6 = 1175, 1319, 1397, 1568
        C3, D3, E3, F3, G3, A3, B3 = 131, 147, 165, 175, 196, 220, 247
        C2, E2, G2 = 65, 82, 98

        # Create extended 48-bar loop (76.8 seconds total) - epic journey!
        total_duration = bar * 48

        # KICK DRUM CHANNEL - Heavy, menacing 4-on-the-floor beat
        kick = np.zeros(int(self.sample_rate * total_duration))
        kick_beat_count = int(total_duration / beat)
        for i in range(kick_beat_count):
            # Deep, heavy kick for dark atmosphere
            t = np.linspace(0, 0.15, int(self.sample_rate * 0.15))
            # Deeper pitch sweep from 120 Hz down to 25 Hz (heavier, darker kick)
            freq_sweep = 120 - 95 * (t / 0.15)
            kick_wave = 0.50 * np.sin(2 * np.pi * freq_sweep * t)
            kick_wave = self._apply_envelope(kick_wave, 0.001, 0.10)
            start_sample = int(i * beat * self.sample_rate)
            end_sample = start_sample + len(kick_wave)
            kick[start_sample:end_sample] += kick_wave

        # BASS CHANNEL - Aggressive pulsing bassline
        bass = np.zeros(int(self.sample_rate * total_duration))
        # Driving minor key progression: Em - C - D - Em repeated 4 times (32 bars)
        # Each 8-bar section has the same chord progression but we'll vary it slightly

        def add_bass_pattern(bass_array, start_bar, intensity=0.32):
            """Helper to add 8-bar bass pattern starting at given bar"""
            bass_notes = [
                # Bar 1-2: E minor
                (E2, start_bar*bar, beat*0.5), (E2, start_bar*bar+beat*0.5, beat*0.5), (E2, start_bar*bar+beat, beat*0.5), (E3, start_bar*bar+beat*1.5, beat*0.5),
                (E2, start_bar*bar+beat*2, beat*0.5), (E2, start_bar*bar+beat*2.5, beat*0.5), (E2, start_bar*bar+beat*3, beat*0.5), (G2, start_bar*bar+beat*3.5, beat*0.5),
                (E2, (start_bar+1)*bar, beat*0.5), (E2, (start_bar+1)*bar+beat*0.5, beat*0.5), (E2, (start_bar+1)*bar+beat, beat*0.5), (E3, (start_bar+1)*bar+beat*1.5, beat*0.5),
                (E2, (start_bar+1)*bar+beat*2, beat*0.5), (E2, (start_bar+1)*bar+beat*2.5, beat*0.5), (E2, (start_bar+1)*bar+beat*3, beat*0.5), (G2, (start_bar+1)*bar+beat*3.5, beat*0.5),
                # Bar 3-4: C major
                (C2, (start_bar+2)*bar, beat*0.5), (C2, (start_bar+2)*bar+beat*0.5, beat*0.5), (C2, (start_bar+2)*bar+beat, beat*0.5), (C3, (start_bar+2)*bar+beat*1.5, beat*0.5),
                (C2, (start_bar+2)*bar+beat*2, beat*0.5), (C2, (start_bar+2)*bar+beat*2.5, beat*0.5), (C2, (start_bar+2)*bar+beat*3, beat*0.5), (E2, (start_bar+2)*bar+beat*3.5, beat*0.5),
                (C2, (start_bar+3)*bar, beat*0.5), (C2, (start_bar+3)*bar+beat*0.5, beat*0.5), (C2, (start_bar+3)*bar+beat, beat*0.5), (C3, (start_bar+3)*bar+beat*1.5, beat*0.5),
                (C2, (start_bar+3)*bar+beat*2, beat*0.5), (C2, (start_bar+3)*bar+beat*2.5, beat*0.5), (C2, (start_bar+3)*bar+beat*3, beat*0.5), (E2, (start_bar+3)*bar+beat*3.5, beat*0.5),
                # Bar 5-6: D major
                (D3, (start_bar+4)*bar, beat*0.5), (D3, (start_bar+4)*bar+beat*0.5, beat*0.5), (D3, (start_bar+4)*bar+beat, beat*0.5), (D3, (start_bar+4)*bar+beat*1.5, beat*0.5),
                (D3, (start_bar+4)*bar+beat*2, beat*0.5), (D3, (start_bar+4)*bar+beat*2.5, beat*0.5), (D3, (start_bar+4)*bar+beat*3, beat*0.5), (F3, (start_bar+4)*bar+beat*3.5, beat*0.5),
                (D3, (start_bar+5)*bar, beat*0.5), (D3, (start_bar+5)*bar+beat*0.5, beat*0.5), (D3, (start_bar+5)*bar+beat, beat*0.5), (D3, (start_bar+5)*bar+beat*1.5, beat*0.5),
                (D3, (start_bar+5)*bar+beat*2, beat*0.5), (D3, (start_bar+5)*bar+beat*2.5, beat*0.5), (D3, (start_bar+5)*bar+beat*3, beat*0.5), (F3, (start_bar+5)*bar+beat*3.5, beat*0.5),
                # Bar 7-8: E minor (return)
                (E2, (start_bar+6)*bar, beat*0.5), (E2, (start_bar+6)*bar+beat*0.5, beat*0.5), (E2, (start_bar+6)*bar+beat, beat*0.5), (E3, (start_bar+6)*bar+beat*1.5, beat*0.5),
                (E2, (start_bar+6)*bar+beat*2, beat*0.5), (E2, (start_bar+6)*bar+beat*2.5, beat*0.5), (E2, (start_bar+6)*bar+beat*3, beat*0.5), (G2, (start_bar+6)*bar+beat*3.5, beat*0.5),
                (E2, (start_bar+7)*bar, beat*0.5), (E2, (start_bar+7)*bar+beat*0.5, beat*0.5), (E2, (start_bar+7)*bar+beat, beat*0.5), (E3, (start_bar+7)*bar+beat*1.5, beat*0.5),
                (E2, (start_bar+7)*bar+beat*2, beat*0.5), (E2, (start_bar+7)*bar+beat*2.5, beat*0.5), (E2, (start_bar+7)*bar+beat*3, beat*0.5), (G2, (start_bar+7)*bar+beat*3.5, beat*0.5),
            ]
            for freq, start, duration in bass_notes:
                note = self._generate_sawtooth_wave(freq, duration, intensity)
                note = self._apply_lowpass_filter(note, 400)  # Darker, more aggressive bass
                note = self._apply_envelope(note, 0.002, 0.05)
                start_sample = int(start * self.sample_rate)
                end_sample = start_sample + len(note)
                bass_array[start_sample:end_sample] += note

        # Add 6 repetitions of the 8-bar pattern with slight intensity variations
        add_bass_pattern(bass, 0, 0.30)   # Bars 0-7 (quieter intro)
        add_bass_pattern(bass, 8, 0.32)   # Bars 8-15 (normal)
        add_bass_pattern(bass, 16, 0.34)  # Bars 16-23 (building)
        add_bass_pattern(bass, 24, 0.34)  # Bars 24-31 (sustained)
        add_bass_pattern(bass, 32, 0.33)  # Bars 32-39 (slight drop)
        add_bass_pattern(bass, 40, 0.32)  # Bars 40-47 (return to normal)

        # MELODY CHANNEL - Aggressive lead synth (extended to 48 bars, lowered by one octave)
        melody = np.zeros(int(self.sample_rate * total_duration))
        # Create 6 sections of 8 bars each with variations

        # Section 1 (Bars 0-7): Opening theme (lowered octave)
        melody_section_1 = [
            (E4, 0, beat*0.5), (G4, beat*0.5, beat*0.5), (B4, beat, beat), (G4, beat*2, beat*0.5), (E4, beat*2.5, beat*0.5),
            (D4, beat*3, beat), (E4, bar, beat*0.5), (G4, bar+beat*0.5, beat*0.5), (B4, bar+beat, beat),
            (C5, bar+beat*2, beat), (B4, bar+beat*3, beat),
            (G4, bar*2, beat*0.5), (C5, bar*2+beat*0.5, beat*0.5), (E5, bar*2+beat, beat), (C5, bar*2+beat*2, beat*0.5),
            (G4, bar*2+beat*2.5, beat*0.5), (E4, bar*2+beat*3, beat), (G4, bar*3, beat*0.5), (C5, bar*3+beat*0.5, beat*0.5),
            (E5, bar*3+beat, beat), (D5, bar*3+beat*2, beat), (C5, bar*3+beat*3, beat),
            (D5, bar*4, beat*0.5), (F5, bar*4+beat*0.5, beat*0.5), (A4, bar*4+beat, beat), (D5, bar*4+beat*2, beat*0.5),
            (F5, bar*4+beat*2.5, beat*0.5), (D5, bar*4+beat*3, beat), (A4, bar*5, beat*0.5), (D5, bar*5+beat*0.5, beat*0.5),
            (F5, bar*5+beat, beat*1.5), (E5, bar*5+beat*2.5, beat*1.5),
            (G5, bar*6, beat*0.5), (E5, bar*6+beat*0.5, beat*0.5), (B4, bar*6+beat, beat), (G4, bar*6+beat*2, beat),
            (E5, bar*6+beat*3, beat), (G5, bar*7, beat*0.5), (E5, bar*7+beat*0.5, beat*0.5), (B4, bar*7+beat, beat*1.5),
            (E5, bar*7+beat*2.5, beat*1.5),
        ]

        # Section 2 (Bars 8-15): Variation (lowered octave)
        melody_section_2 = [
            (B4, bar*8, beat*0.5), (E5, bar*8+beat*0.5, beat*0.5), (G5, bar*8+beat, beat), (E5, bar*8+beat*2, beat),
            (B4, bar*8+beat*3, beat), (G4, bar*9, beat*0.5), (B4, bar*9+beat*0.5, beat*0.5), (E5, bar*9+beat, beat*1.5),
            (D5, bar*9+beat*2.5, beat*1.5),
            (C5, bar*10, beat*0.5), (E5, bar*10+beat*0.5, beat*0.5), (G5, bar*10+beat, beat), (E5, bar*10+beat*2, beat),
            (C5, bar*10+beat*3, beat), (G4, bar*11, beat*0.5), (C5, bar*11+beat*0.5, beat*0.5), (E5, bar*11+beat, beat*2),
            (F5, bar*12, beat*0.5), (A4, bar*12+beat*0.5, beat*0.5), (D5, bar*12+beat, beat), (F5, bar*12+beat*2, beat),
            (A4, bar*12+beat*3, beat), (D5, bar*13, beat*0.5), (F5, bar*13+beat*0.5, beat*0.5), (A4, bar*13+beat, beat*2),
            (E5, bar*14, beat), (D5, bar*14+beat, beat), (C5, bar*14+beat*2, beat), (B4, bar*14+beat*3, beat),
            (E5, bar*15, beat*2), (G5, bar*15+beat*2, beat*2),
        ]

        # Section 3 (Bars 16-23): Build up (lowered octave)
        melody_section_3 = [
            (E5, bar*16, beat*0.5), (G5, bar*16+beat*0.5, beat*0.5), (E5, bar*16+beat, beat*0.5), (B4, bar*16+beat*1.5, beat*0.5),
            (E5, bar*16+beat*2, beat*0.5), (G5, bar*16+beat*2.5, beat*0.5), (B4, bar*16+beat*3, beat), (E5, bar*17, beat*2),
            (D5, bar*17+beat*2, beat), (C5, bar*17+beat*3, beat),
            (G4, bar*18, beat*0.5), (C5, bar*18+beat*0.5, beat*0.5), (E5, bar*18+beat, beat*0.5), (G5, bar*18+beat*1.5, beat*0.5),
            (E5, bar*18+beat*2, beat), (C5, bar*18+beat*3, beat), (G5, bar*19, beat*2), (E5, bar*19+beat*2, beat*2),
            (D5, bar*20, beat*0.5), (F5, bar*20+beat*0.5, beat*0.5), (A4, bar*20+beat, beat*0.5), (D5, bar*20+beat*1.5, beat*0.5),
            (F5, bar*20+beat*2, beat), (D5, bar*20+beat*3, beat), (A4, bar*21, beat), (F5, bar*21+beat, beat),
            (D5, bar*21+beat*2, beat), (F5, bar*21+beat*3, beat),
            (G5, bar*22, beat*0.5), (E5, bar*22+beat*0.5, beat*0.5), (B4, bar*22+beat, beat*0.5), (G4, bar*22+beat*1.5, beat*0.5),
            (E5, bar*22+beat*2, beat*1.5), (G5, bar*22+beat*3.5, beat*0.5), (B4, bar*23, beat), (E5, bar*23+beat, beat),
            (G5, bar*23+beat*2, beat*2),
        ]

        # Section 4 (Bars 24-31): Return (lowered octave)
        melody_section_4 = [
            (E4, bar*24, beat*0.5), (G4, bar*24+beat*0.5, beat*0.5), (B4, bar*24+beat, beat), (E5, bar*24+beat*2, beat*2),
            (B4, bar*25, beat), (G4, bar*25+beat, beat), (E5, bar*25+beat*2, beat), (D5, bar*25+beat*3, beat),
            (C5, bar*26, beat*2), (E5, bar*26+beat*2, beat), (G5, bar*26+beat*3, beat),
            (E5, bar*27, beat*2), (D5, bar*27+beat*2, beat), (C5, bar*27+beat*3, beat),
            (D5, bar*28, beat), (F5, bar*28+beat, beat), (A4, bar*28+beat*2, beat), (D5, bar*28+beat*3, beat),
            (F5, bar*29, beat*1.5), (E5, bar*29+beat*1.5, beat*2.5),
            (G5, bar*30, beat*0.5), (E5, bar*30+beat*0.5, beat*0.5), (B4, bar*30+beat, beat*0.5), (G4, bar*30+beat*1.5, beat*0.5),
            (E5, bar*30+beat*2, beat*2), (G5, bar*31, beat), (E5, bar*31+beat, beat),
            (B4, bar*31+beat*2, beat), (E5, bar*31+beat*3, beat),
        ]

        # Section 5 (Bars 32-39): Variation reprise (lowered octave)
        melody_section_5 = [
            (B4, bar*32, beat*0.5), (E5, bar*32+beat*0.5, beat*0.5), (G5, bar*32+beat, beat), (E5, bar*32+beat*2, beat),
            (B4, bar*32+beat*3, beat), (G4, bar*33, beat*0.5), (B4, bar*33+beat*0.5, beat*0.5), (E5, bar*33+beat, beat*1.5),
            (D5, bar*33+beat*2.5, beat*1.5),
            (C5, bar*34, beat*0.5), (E5, bar*34+beat*0.5, beat*0.5), (G5, bar*34+beat, beat), (E5, bar*34+beat*2, beat),
            (C5, bar*34+beat*3, beat), (G4, bar*35, beat*0.5), (C5, bar*35+beat*0.5, beat*0.5), (E5, bar*35+beat, beat*2),
            (F5, bar*36, beat*0.5), (A4, bar*36+beat*0.5, beat*0.5), (D5, bar*36+beat, beat), (F5, bar*36+beat*2, beat),
            (A4, bar*36+beat*3, beat), (D5, bar*37, beat*0.5), (F5, bar*37+beat*0.5, beat*0.5), (A4, bar*37+beat, beat*2),
            (E5, bar*38, beat), (D5, bar*38+beat, beat), (C5, bar*38+beat*2, beat), (B4, bar*38+beat*3, beat),
            (E5, bar*39, beat*2), (G5, bar*39+beat*2, beat*2),
        ]

        # Section 6 (Bars 40-47): Final climax and resolution (lowered octave)
        melody_section_6 = [
            (E4, bar*40, beat*0.5), (G4, bar*40+beat*0.5, beat*0.5), (B4, bar*40+beat, beat), (E5, bar*40+beat*2, beat*2),
            (B4, bar*41, beat), (G4, bar*41+beat, beat), (E5, bar*41+beat*2, beat), (D5, bar*41+beat*3, beat),
            (C5, bar*42, beat*2), (E5, bar*42+beat*2, beat), (G5, bar*42+beat*3, beat),
            (E5, bar*43, beat*2), (D5, bar*43+beat*2, beat), (C5, bar*43+beat*3, beat),
            (D5, bar*44, beat), (F5, bar*44+beat, beat), (A4, bar*44+beat*2, beat), (D5, bar*44+beat*3, beat),
            (F5, bar*45, beat*1.5), (E5, bar*45+beat*1.5, beat*2.5),
            (G5, bar*46, beat*0.5), (E5, bar*46+beat*0.5, beat*0.5), (B4, bar*46+beat, beat*0.5), (G4, bar*46+beat*1.5, beat*0.5),
            (E5, bar*46+beat*2, beat*2), (G5, bar*47, beat), (E5, bar*47+beat, beat),
            (B4, bar*47+beat*2, beat), (E5, bar*47+beat*3, beat),
        ]

        # Combine all sections
        all_melody_notes = melody_section_1 + melody_section_2 + melody_section_3 + melody_section_4 + melody_section_5 + melody_section_6

        for freq, start, duration in all_melody_notes:
            note = self._generate_sawtooth_wave(freq, duration, 0.32)
            note = self._apply_lowpass_filter(note, 2000)  # Dark, aggressive melody with more presence
            note = self._apply_envelope(note, 0.005, 0.08)
            start_sample = int(start * self.sample_rate)
            end_sample = start_sample + len(note)
            melody[start_sample:end_sample] += note

        # ARPEGGIO CHANNEL - Super fast 32nd note arpeggios for intensity (48 bars)
        arp = np.zeros(int(self.sample_rate * total_duration))
        arp_beat = beat / 8  # 32nd notes - blazing fast!
        # Chord progression repeated 6 times: Em - Em - C - C - D - D - Em - Em (8 bars per cycle)
        chords = [
            [E4, G4, B4, E5],  # bar 0 - Em
            [E4, G4, B4, E5],  # bar 1 - Em
            [C4, E4, G4, C5],  # bar 2 - C
            [C4, E4, G4, C5],  # bar 3 - C
            [D4, F4, A4, D5],  # bar 4 - D
            [D4, F4, A4, D5],  # bar 5 - D
            [E4, G4, B4, E5],  # bar 6 - Em
            [E4, G4, B4, E5],  # bar 7 - Em
        ] * 6  # Repeat 6 times for 48 bars total

        for bar_num in range(48):
            chord = chords[bar_num]
            for i in range(32):  # 32nd notes per bar
                freq = chord[i % 4]
                # Vary intensity slightly through the song
                if bar_num < 16:
                    intensity = 0.10  # First third - quieter
                elif bar_num < 32:
                    intensity = 0.11  # Middle third - louder
                else:
                    intensity = 0.10  # Final third - back to quieter
                note = self._generate_sawtooth_wave(freq, arp_beat, intensity)
                note = self._apply_lowpass_filter(note, 6000)
                note = self._apply_envelope(note, 0.002, 0.04)
                start_sample = int((bar_num * bar + i * arp_beat) * self.sample_rate)
                end_sample = start_sample + len(note)
                arp[start_sample:end_sample] += note

        # Mix all channels
        music = kick + bass + melody * 0.9 + arp * 0.7

        # Normalize
        max_val = np.max(np.abs(music))
        if max_val > 0:
            music = music / max_val * 0.75

        self.sounds['menu_music'] = self._make_sound(music)

    def _generate_game_music(self):
        """Generate two versions of clock ticking: normal and intense"""
        # NORMAL VERSION - 60 BPM (for single power-up)
        tick_interval = 0.5  # 0.5 seconds between tick and tock
        total_duration = 2.0  # 2-second loop
        music_normal = np.zeros(int(self.sample_rate * total_duration))
        num_ticks = int(total_duration / tick_interval)

        for i in range(num_ticks):
            is_tick = (i % 2 == 0)
            if is_tick:
                # TICK - high-pitched, sharp
                t = np.linspace(0, 0.015, int(self.sample_rate * 0.015))
                freq_sweep = 2000 - 200 * (t / 0.015)
                tick_wave = 0.3 * np.sin(2 * np.pi * freq_sweep * t)
                overtone = 0.15 * np.sin(2 * np.pi * freq_sweep * 2.5 * t)
                tick_wave = tick_wave + overtone
                tick_wave = self._apply_envelope(tick_wave, 0.0005, 0.01)
                noise = np.random.uniform(-0.05, 0.05, len(tick_wave))
                tick_wave = tick_wave + noise
            else:
                # TOCK - lower-pitched
                t = np.linspace(0, 0.020, int(self.sample_rate * 0.020))
                freq_sweep = 1400 - 200 * (t / 0.020)
                tick_wave = 0.28 * np.sin(2 * np.pi * freq_sweep * t)
                overtone = 0.12 * np.sin(2 * np.pi * freq_sweep * 1.8 * t)
                tick_wave = tick_wave + overtone
                tick_wave = self._apply_envelope(tick_wave, 0.001, 0.015)
                noise = np.random.uniform(-0.04, 0.04, len(tick_wave))
                tick_wave = tick_wave + noise

            start_sample = int(i * tick_interval * self.sample_rate)
            end_sample = start_sample + len(tick_wave)
            if end_sample <= len(music_normal):
                music_normal[start_sample:end_sample] += tick_wave

        max_val = np.max(np.abs(music_normal))
        if max_val > 0:
            music_normal = music_normal / max_val * 0.20
        self.sounds['game_music'] = self._make_sound(music_normal)

        # INTENSE VERSION - 90 BPM (for double power-up)
        tick_interval_intense = 0.333  # Faster: ~90 BPM
        total_duration_intense = 2.0
        music_intense = np.zeros(int(self.sample_rate * total_duration_intense))
        num_ticks_intense = int(total_duration_intense / tick_interval_intense)

        for i in range(num_ticks_intense):
            is_tick = (i % 2 == 0)
            if is_tick:
                # TICK - even higher-pitched and sharper
                t = np.linspace(0, 0.012, int(self.sample_rate * 0.012))
                freq_sweep = 2400 - 300 * (t / 0.012)
                tick_wave = 0.35 * np.sin(2 * np.pi * freq_sweep * t)
                overtone = 0.18 * np.sin(2 * np.pi * freq_sweep * 2.5 * t)
                tick_wave = tick_wave + overtone
                tick_wave = self._apply_envelope(tick_wave, 0.0003, 0.008)
                noise = np.random.uniform(-0.06, 0.06, len(tick_wave))
                tick_wave = tick_wave + noise
            else:
                # TOCK - higher and punchier
                t = np.linspace(0, 0.015, int(self.sample_rate * 0.015))
                freq_sweep = 1700 - 300 * (t / 0.015)
                tick_wave = 0.32 * np.sin(2 * np.pi * freq_sweep * t)
                overtone = 0.15 * np.sin(2 * np.pi * freq_sweep * 1.8 * t)
                tick_wave = tick_wave + overtone
                tick_wave = self._apply_envelope(tick_wave, 0.0005, 0.012)
                noise = np.random.uniform(-0.05, 0.05, len(tick_wave))
                tick_wave = tick_wave + noise

            start_sample = int(i * tick_interval_intense * self.sample_rate)
            end_sample = start_sample + len(tick_wave)
            if end_sample <= len(music_intense):
                music_intense[start_sample:end_sample] += tick_wave

        max_val = np.max(np.abs(music_intense))
        if max_val > 0:
            music_intense = music_intense / max_val * 0.25  # Slightly louder for intensity
        self.sounds['game_music_intense'] = self._make_sound(music_intense)

    def _generate_intro_drone(self):
        """Generate ominous dark drone for intro sequence"""
        duration = 30.0  # 30 second loop

        # Deep bass drone (55 Hz - low A)
        bass_t = np.linspace(0, duration, int(self.sample_rate * duration))
        bass_drone = 0.20 * np.sin(2 * np.pi * 55 * bass_t)

        # Add harmonics for richness
        bass_drone += 0.12 * np.sin(2 * np.pi * 110 * bass_t)  # Octave
        bass_drone += 0.08 * np.sin(2 * np.pi * 165 * bass_t)  # Fifth

        # Mid-range ominous tone (110 Hz with slow vibrato)
        vibrato = 1 + 0.03 * np.sin(2 * np.pi * 0.2 * bass_t)  # Very slow vibrato
        mid_drone = 0.15 * np.sin(2 * np.pi * 110 * bass_t * vibrato)

        # Dark pad layer (220 Hz with detuning)
        pad1 = 0.08 * np.sin(2 * np.pi * 220 * bass_t)
        pad2 = 0.08 * np.sin(2 * np.pi * 222 * bass_t)  # Slightly detuned for tension

        # Combine all layers
        intro_drone = bass_drone + mid_drone + pad1 + pad2

        # Heavy lowpass for dark, rumbling character
        intro_drone = self._apply_lowpass_filter(intro_drone, 600)

        # Gentle fade in and out for seamless looping
        fade_samples = int(2.0 * self.sample_rate)
        envelope = np.ones(len(intro_drone))
        envelope[:fade_samples] = np.linspace(0, 1, fade_samples)
        envelope[-fade_samples:] = np.linspace(1, 0, fade_samples)
        intro_drone = intro_drone * envelope

        self.sounds['intro_drone'] = self._make_sound(intro_drone)

    def _generate_hero_music(self):
        """Generate ceremonial, hope-inspiring hero music for high score initials entry"""
        # CEREMONIAL tempo: 70 BPM (0.86 seconds per beat) - steady and majestic
        beat = 0.86
        bar = beat * 4  # 3.44 seconds per bar

        # D major scale notes - hopeful, triumphant key
        D3, E3, Fs3, G3, A3, B3 = 147, 165, 185, 196, 220, 247
        D4, E4, Fs4, G4, A4, B4 = 294, 330, 370, 392, 440, 494
        Cs5, D5, E5, Fs5, G5, A5, B5 = 554, 587, 659, 740, 784, 880, 988
        Cs6, D6 = 1109, 1175

        # 4-bar ceremonial phrase (13.76 seconds total)
        total_duration = bar * 4

        # MELODY CHANNEL - Hopeful, ascending melody (sawtooth - bright and uplifting)
        melody = np.zeros(int(self.sample_rate * total_duration))
        melody_notes = [
            # Bar 1: Rising hope (D major)
            (D4, 0, beat*1.5),           # D - strong start
            (Fs4, beat*1.5, beat*0.5),   # F# - major third, hopeful
            (A4, beat*2, beat),          # A - rising
            (D5, beat*3, beat),          # D - octave up, triumph

            # Bar 2: Sustained majesty
            (Fs5, bar, beat*2),          # Hold the brightness
            (E5, bar+beat*2, beat),      # E - flowing
            (D5, bar+beat*3, beat),      # D - resolving

            # Bar 3: Building triumph
            (A4, bar*2, beat),           # A - foundation
            (B4, bar*2+beat, beat),      # B - rising
            (Cs5, bar*2+beat*2, beat*1.5), # C# - leading tone
            (D5, bar*2+beat*3.5, beat*0.5), # D - peak

            # Bar 4: Triumphant finale
            (Fs5, bar*3, beat*4),        # Final bright sustained note
        ]

        for freq, start, duration in melody_notes:
            note = self._generate_sawtooth_wave(freq, duration, 0.32)
            note = self._apply_lowpass_filter(note, 2000)  # Warm, present filtering
            note = self._apply_envelope(note, 0.02, 0.18)
            # Add gentle vibrato for warmth
            t = np.linspace(0, duration, len(note))
            vibrato = 1 + 0.04 * np.sin(2 * np.pi * 4 * t)
            note = note * vibrato
            start_sample = int(start * self.sample_rate)
            end_sample = start_sample + len(note)
            melody[start_sample:end_sample] += note

        # HARMONY CHANNEL - Major thirds and consonant harmonies (square wave - bright character)
        harmony = np.zeros(int(self.sample_rate * total_duration))
        harmony_notes = [
            # Bar 1: Major thirds and consonance
            (A4, 0, beat*1.5),
            (D5, beat*1.5, beat*0.5),
            (Fs5, beat*2, beat),
            (A5, beat*3, beat),

            # Bar 2
            (D5, bar, beat*2),
            (Cs5, bar+beat*2, beat),
            (A4, bar+beat*3, beat),

            # Bar 3
            (Fs4, bar*2, beat),
            (G4, bar*2+beat, beat),
            (A4, bar*2+beat*2, beat*1.5),
            (Fs4, bar*2+beat*3.5, beat*0.5),

            # Bar 4
            (A4, bar*3, beat*4),
        ]

        for freq, start, duration in harmony_notes:
            note = self._generate_square_wave(freq, duration, 0.16)
            note = self._apply_lowpass_filter(note, 2000)  # Brighter harmonies
            note = self._apply_envelope(note, 0.02, 0.18)
            start_sample = int(start * self.sample_rate)
            end_sample = start_sample + len(note)
            harmony[start_sample:end_sample] += note

        # BASS CHANNEL - Triumphant foundation (triangle wave - warm and solid)
        bass = np.zeros(int(self.sample_rate * total_duration))
        bass_notes = [
            # Bar 1: Root progression
            (D3, 0, bar),                # D - bright tonic

            # Bar 2
            (A3, bar, bar),              # A - dominant, uplifting

            # Bar 3
            (B3, bar*2, bar),            # B - rising anticipation

            # Bar 4: Triumphant resolution
            (D3, bar*3, bar),            # D - victorious return
        ]

        for freq, start, duration in bass_notes:
            note = self._generate_triangle_wave(freq, duration, 0.32)
            note = self._apply_lowpass_filter(note, 800)
            note = self._apply_envelope(note, 0.03, 0.2)
            start_sample = int(start * self.sample_rate)
            end_sample = start_sample + len(note)
            bass[start_sample:end_sample] += note

        # TIMPANI CHANNEL - Epic percussion hits for drama
        timpani = np.zeros(int(self.sample_rate * total_duration))
        # Timpani hits on strong beats
        timpani_hits = [
            0,           # Bar 1 beat 1
            beat*3,      # Bar 1 beat 4
            bar,         # Bar 2 beat 1
            bar*2,       # Bar 3 beat 1
            bar*3,       # Bar 4 beat 1 (final)
        ]

        for hit_time in timpani_hits:
            # Timpani is a low frequency drum with pitch drop
            t = np.linspace(0, 0.15, int(self.sample_rate * 0.15))
            freq_sweep = 100 - 60 * (t / 0.15)  # 100 Hz -> 40 Hz
            timp = 0.30 * np.sin(2 * np.pi * freq_sweep * t)
            timp = self._apply_envelope(timp, 0.001, 0.1)
            start_sample = int(hit_time * self.sample_rate)
            end_sample = start_sample + len(timp)
            if end_sample <= len(timpani):
                timpani[start_sample:end_sample] += timp

        # Mix all channels
        hero_music = melody + harmony + bass + timpani

        # Add slight reverb for epic space
        delay_samples = int(0.08 * self.sample_rate)
        delayed = np.zeros(len(hero_music))
        delayed[delay_samples:] = hero_music[:-delay_samples] * 0.3
        hero_music = hero_music + delayed

        # Normalize
        max_val = np.max(np.abs(hero_music))
        if max_val > 0:
            hero_music = hero_music / max_val * 0.70

        self.sounds['hero_music'] = self._make_sound(hero_music)

    def play(self, sound_name: str):
        """Play a sound effect"""
        if sound_name in self.sounds:
            self.sounds[sound_name].play()

    def start_menu_music(self):
        """Start playing menu background music in a loop"""
        if 'menu_music' in self.sounds:
            self.music_channel = self.sounds['menu_music'].play(loops=-1)  # Loop infinitely

    def stop_menu_music(self):
        """Stop the menu background music"""
        if self.music_channel:
            self.music_channel.stop()
            self.music_channel = None

    def start_game_music(self, intense=False):
        """Start playing clock ticking music (normal or intense version)"""
        # Stop any currently playing game music first
        self.stop_game_music()

        music_key = 'game_music_intense' if intense else 'game_music'
        if music_key in self.sounds:
            self.game_music_channel = self.sounds[music_key].play(loops=-1)

    def stop_game_music(self):
        """Stop the in-game background music"""
        if self.game_music_channel:
            self.game_music_channel.stop()
            self.game_music_channel = None

    def start_hero_music(self):
        """Start playing epic hero music (plays once, no loop)"""
        if 'hero_music' in self.sounds:
            self.hero_music_channel = self.sounds['hero_music'].play(loops=0)  # Play once

    def stop_hero_music(self):
        """Stop the hero background music"""
        if self.hero_music_channel:
            self.hero_music_channel.stop()
            self.hero_music_channel = None

    def start_intro_drone(self):
        """Start ominous intro drone (loops)"""
        if self.intro_drone_channel is None:
            self.intro_drone_channel = self.sounds['intro_drone'].play(loops=-1)
            if self.intro_drone_channel:
                self.intro_drone_channel.set_volume(0.4)

    def stop_intro_drone(self):
        """Stop intro drone"""
        if self.intro_drone_channel:
            self.intro_drone_channel.stop()
            self.intro_drone_channel = None

    def is_game_music_playing(self):
        """Check if game music is currently playing"""
        return self.game_music_channel is not None


class Game:
    """Main game class"""

    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.height, self.width = stdscr.getmaxyx()

        # Store initial dimensions - game will pause if terminal becomes smaller than this
        self.initial_height = self.height
        self.initial_width = self.width

        # Create a pad for double buffering (eliminates flicker)
        self.pad = curses.newpad(self.height, self.width)

        # Track if terminal size is valid
        self.terminal_too_small = False
        self.saved_paused_state = False
        self.showing_dialog = False  # Flag to suppress PAUSED message when showing dialog

        # Initialize retro synth for game sounds
        self.synth = RetroSynth()

        # Start player at center of horizontally allowed area (vertically centered accounting for 3-row sprite)
        right_limit = (self.width // 3) + 8
        ship_width = 3  # Player ship is 3 characters wide
        # Center between left limit (x=2) and rightmost position (right_limit - ship_width)
        player_x = (2 + (right_limit - ship_width)) / 2
        self.player = Player(player_x, (self.height // 2) - 1)
        self.bullets: List[Bullet] = []
        self.energy_beams: List[EnergyBeam] = []
        self.enemies: List[Enemy] = []
        self.boss: Boss = None
        self.boss_bullets: List[BossBullet] = []
        self.powerups: List[PowerUp] = []
        self.explosions: List[Explosion] = []
        self.drones: List[Drone] = []
        self.drone_bullets: List[Bullet] = []  # Bullets fired by drones
        self.game_over = False
        self.game_over_reason = None  # Track why game ended: 'cargo_captured' or 'player_died'
        self.frame_count = 0
        self.enemy_spawn_rate = 30
        self.boss_level = 1
        self.enemies_killed = 0  # Track enemies killed for boss spawning
        self.next_boss_kills = 30  # First boss after 30 enemies, then every 50
        self.high_scores = self.load_high_scores()
        self.nuke_effect_timer = 0  # Timer for nuke visual effects
        self.wall_flash_timer = 0  # Timer for wall flash when hit by enemy
        self.paused = False  # Pause state
        self.ship_flash_timer = 30  # Flash ship for 1 second at start (30 frames at 30 FPS)
        self.cheat_code_input = ""  # Track cheat code input

        # Notification system for HUD messages
        self.notification_text = ""  # Current notification message
        self.notification_timer = 0  # Duration to show notification
        self.notification_scroll_offset = 0  # For scrolling effect
        self.energy_beam_tip_shown = False  # Track if energy beam tip has been shown

        # Achievement tracking
        self.enemies_breached = 0  # Track enemies that got through to the wall
        self.total_shots_fired = 0  # Track all plasma/spread shots fired
        self.total_hits = 0  # Track successful hits with plasma/spread shots
        self.plasma_only_kills = True  # Flag for achievement 2 (only plasma kills)
        self.nukes_used = 0  # Track nukes used

        # Multi-layer scrolling starfield for parallax effect
        self.starfield = self._generate_starfield()

        # Engine sound tracking
        self.prev_vx = 0.0
        self.prev_vy = 0.0
        self.engine_sound_channel = None  # Channel for looping engine sound

        # GENESIS freight ship properties
        self.genesis_width = 24
        self.genesis_height = self.height - 4  # Almost full height
        self.genesis_x = -23  # Positioned so rightmost column is at x=0 (replaces frame border)
        self.genesis_wobble_phase = 0.0
        self.genesis_wobble_x = 0.0
        self.genesis_wobble_y = 0.0

        # Track actual key states (True = pressed, False = released)
        self.arrow_keys_state = {
            keyboard.Key.up: False,
            keyboard.Key.down: False,
            keyboard.Key.left: False,
            keyboard.Key.right: False,
            keyboard.Key.space: False
        }

        # Start keyboard listener in background thread
        self.keyboard_listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release)
        self.keyboard_listener.start()

        # Setup curses
        curses.curs_set(0)
        stdscr.nodelay(1)
        stdscr.timeout(0)

        # Setup colors using 256-color palette (independent of terminal color scheme)
        # "Dirty" cyberpunk aesthetic with dark blue background and washed-out complementary colors
        curses.start_color()

        # Define color constants from 256-color palette
        # Background: Dark navy blue
        COLOR_BG = 17               # Very dark blue background (r=0, g=0, b=1)

        # Washed-out, complementary foreground colors
        COLOR_DUSTY_ORANGE = 173    # Muted orange for enemies (r=3, g=2, b=1)
        COLOR_PALE_CYAN = 116       # Washed teal/cyan for player (r=2, g=3, b=4)
        COLOR_AMBER = 179           # Muted amber for bullets (r=3, g=3, b=1)
        COLOR_BLUE_GRAY = 146       # Blue-gray for explosions/text (r=2, g=3, b=2)
        COLOR_MOSS_GREEN = 108      # Muted moss green for UI (r=2, g=3, b=0)
        COLOR_DUSTY_PURPLE = 140    # Washed purple for energy beam (r=2, g=2, b=4)
        COLOR_SLATE = 103           # Slate gray for tanks (r=2, g=2, b=1)
        COLOR_SALMON = 174          # Dusty salmon/pink for powerups (r=3, g=2, b=2)
        COLOR_STEEL_BLUE = 67       # Steel blue for shield (r=1, g=2, b=3)
        COLOR_RUST = 130            # Rust/brown-orange for boss (r=2, g=1, b=0)

        # Initialize color pairs using "dirty" palette
        curses.init_pair(1, COLOR_DUSTY_ORANGE, COLOR_BG)       # Enemies
        curses.init_pair(2, COLOR_PALE_CYAN, COLOR_BG)          # Player
        curses.init_pair(3, COLOR_AMBER, COLOR_BG)              # Bullets
        curses.init_pair(4, COLOR_BLUE_GRAY, COLOR_BG)          # Explosions/default text
        curses.init_pair(5, COLOR_MOSS_GREEN, COLOR_BG)         # UI
        curses.init_pair(6, COLOR_DUSTY_PURPLE, COLOR_BG)       # Energy beam
        curses.init_pair(7, COLOR_SLATE, COLOR_BG)              # Tank
        curses.init_pair(8, COLOR_AMBER, COLOR_BG)              # Zigzag
        curses.init_pair(9, COLOR_RUST, COLOR_BG)               # Boss
        curses.init_pair(10, COLOR_DUSTY_ORANGE, COLOR_BG)      # Rapid fire powerup
        curses.init_pair(11, COLOR_STEEL_BLUE, COLOR_BG)        # Shield powerup
        curses.init_pair(12, COLOR_MOSS_GREEN, COLOR_BG)        # Health powerup
        curses.init_pair(13, COLOR_AMBER, COLOR_BG)             # Spread powerup
        curses.init_pair(14, COLOR_DUSTY_PURPLE, COLOR_BG)      # Energy beam powerup
        curses.init_pair(15, COLOR_SALMON, COLOR_BG)            # Nuke powerup
        curses.init_pair(16, COLOR_PALE_CYAN, COLOR_BG)         # Drone powerup

        # Set default window colors
        stdscr.bkgd(' ', curses.color_pair(4))  # White on black for default text
        self.pad.bkgd(' ', curses.color_pair(4))

    def _show_confirmation_dialog(self, title, message):
        """Show a Yes/No confirmation dialog. Returns True if Yes, False if No."""
        # Save current screen state
        saved_paused = self.paused
        self.paused = True  # Pause game while showing dialog
        self.showing_dialog = True  # Suppress PAUSED message

        # Pause sounds
        if self.engine_sound_channel:
            self.engine_sound_channel.pause()
        if self.synth.game_music_channel:
            self.synth.game_music_channel.pause()

        # Draw the dialog
        dialog_width = max(len(title), len(message), 20) + 4
        dialog_height = 6

        y_start = (self.height - dialog_height) // 2
        x_start = (self.width - dialog_width) // 2

        # Draw current game state once
        self.draw()

        # Draw dialog box overlay once
        try:
            # Draw box
            for i in range(dialog_height):
                y = y_start + i
                if i == 0:
                    self.stdscr.addstr(y, x_start, "╔" + "═" * (dialog_width - 2) + "╗", curses.color_pair(3))
                elif i == dialog_height - 1:
                    self.stdscr.addstr(y, x_start, "╚" + "═" * (dialog_width - 2) + "╝", curses.color_pair(3))
                else:
                    self.stdscr.addstr(y, x_start, "║" + " " * (dialog_width - 2) + "║", curses.color_pair(3))

            # Draw title (centered)
            title_x = x_start + (dialog_width - len(title)) // 2
            self.stdscr.addstr(y_start + 1, title_x, title, curses.color_pair(1) | curses.A_BOLD)

            # Draw message (centered)
            msg_x = x_start + (dialog_width - len(message)) // 2
            self.stdscr.addstr(y_start + 2, msg_x, message, curses.color_pair(4))

            # Draw options
            options = "[Y] Yes    [N] No"
            opt_x = x_start + (dialog_width - len(options)) // 2
            self.stdscr.addstr(y_start + 4, opt_x, options, curses.color_pair(3))

            self.stdscr.refresh()
        except:
            pass

        # Wait for input in a loop without redrawing
        while True:
            key = self.stdscr.getch()
            if key == ord('y') or key == ord('Y'):
                result = True
                break
            elif key == ord('n') or key == ord('N') or key == 27:  # N or ESC
                result = False
                break

        # Restore pause state and sounds
        self.showing_dialog = False  # Re-enable PAUSED message
        self.paused = saved_paused
        if not self.paused:
            if self.engine_sound_channel:
                self.engine_sound_channel.unpause()
            if self.synth.game_music_channel:
                self.synth.game_music_channel.unpause()

        return result

    def _check_terminal_size(self):
        """Check if terminal is at least as large as initial size, and handle resize gracefully"""
        try:
            current_height, current_width = self.stdscr.getmaxyx()

            # Check if terminal is smaller than initial size
            if current_height < self.initial_height or current_width < self.initial_width:
                if not self.terminal_too_small:
                    # Terminal just became too small - save pause state and force pause
                    self.terminal_too_small = True
                    self.saved_paused_state = self.paused
                    self.paused = True
                    # Pause engine sound (not stop, so it can be unpaused later)
                    if self.engine_sound_channel:
                        self.engine_sound_channel.pause()
                    # Pause game music if playing
                    if self.synth.game_music_channel:
                        self.synth.game_music_channel.pause()
                return False
            else:
                if self.terminal_too_small:
                    # Terminal just became large enough again
                    self.terminal_too_small = False
                    # Keep game paused - player needs to press 'P' to unpause
                    # (Don't restore saved_paused_state)
                    self.paused = True
                    # Update our stored dimensions and recreate pad (but keep initial size unchanged)
                    self.height = current_height
                    self.width = current_width
                    # Recreate the pad with new dimensions
                    try:
                        self.pad = curses.newpad(self.height, self.width)
                        self.pad.bkgd(' ', curses.color_pair(4))
                    except:
                        pass
                    # Clear screen to remove resize message residue
                    self.stdscr.clear()
                    self.stdscr.refresh()
                return True
        except:
            return True  # If we can't check size, assume it's ok

    def _on_key_press(self, key):
        """Callback for key press events from pynput"""
        if key in self.arrow_keys_state:
            self.arrow_keys_state[key] = True

    def _on_key_release(self, key):
        """Callback for key release events from pynput"""
        if key in self.arrow_keys_state:
            self.arrow_keys_state[key] = False

    def _generate_starfield(self):
        """Generate multi-layer starfield with parallax scrolling effect"""
        stars = []

        # Layer 1: Far background stars (slowest, dimmest)
        # Speed 0.12 - slower than tank enemies (0.2)
        for _ in range(30):
            stars.append({
                'x': random.uniform(0, self.width - 1),
                'y': random.randint(1, self.height - 2),
                'speed': 0.12,
                'char': '·',
                'layer': 1
            })

        # Layer 2: Mid-distance stars (medium speed)
        # Speed 0.25 - between tank (0.2) and normal (0.3), doesn't match any enemy
        for _ in range(20):
            stars.append({
                'x': random.uniform(0, self.width - 1),
                'y': random.randint(1, self.height - 2),
                'speed': 0.25,
                'char': '·',
                'layer': 2
            })

        # Layer 3: Closer stars (faster)
        # Speed 0.5 - between zigzag (0.4) and fast (0.6), doesn't match any enemy
        for _ in range(15):
            stars.append({
                'x': random.uniform(0, self.width - 1),
                'y': random.randint(1, self.height - 2),
                'speed': 0.5,
                'char': '·',
                'layer': 3
            })

        return stars

    def _generate_menu_starfield(self):
        """Generate menu starfield with parallax scrolling effect"""
        stars = []

        # Layer 1: Tiny faint stars (slowest, most numerous, dimmest)
        for _ in range(100):
            stars.append({
                'x': random.uniform(0, self.width - 1),
                'y': random.randint(1, self.height - 2),
                'speed': 0.12,
                'char': random.choice(['·', '·', '·', '.']),
                'color': 4,  # White
                'bold': False
            })

        # Layer 2: Medium stars (medium speed)
        for _ in range(40):
            stars.append({
                'x': random.uniform(0, self.width - 1),
                'y': random.randint(1, self.height - 2),
                'speed': 0.25,
                'char': random.choice(['·', '*', '·']),
                'color': 5,  # Green
                'bold': False
            })

        # Layer 3: Big shiny stars (fastest, least numerous, brightest)
        for _ in range(20):
            stars.append({
                'x': random.uniform(0, self.width - 1),
                'y': random.randint(1, self.height - 2),
                'speed': 0.5,
                'char': random.choice(['✦', '✧', '★', '✵', '*']),
                'color': random.choice([3, 5, 11]),  # Yellow, Green, or Blue
                'bold': True
            })

        return stars

    def _update_menu_starfield(self, stars):
        """Update menu starfield positions for parallax scrolling"""
        for star in stars:
            star['x'] -= star['speed']

            # Wrap around when star goes off left edge
            if star['x'] < 1:
                star['x'] = self.width - 2
                star['y'] = random.randint(1, self.height - 2)

    def _update_starfield(self):
        """Update starfield positions for parallax scrolling"""
        for star in self.starfield:
            star['x'] -= star['speed']

            # Wrap around when star goes off left edge
            if star['x'] < 1:
                star['x'] = self.width - 2
                star['y'] = random.randint(1, self.height - 2)

    def _get_dimension_key(self) -> str:
        """Get the dimension key for current terminal size (e.g., '80x24')"""
        return f"{self.initial_width}x{self.initial_height}"

    def load_high_scores(self) -> list:
        """Load top 5 high scores for current terminal dimension from file"""
        try:
            if os.path.exists('.babaam_high_score.json'):
                with open('.babaam_high_score.json', 'r') as f:
                    data = json.load(f)
                    dimension_key = self._get_dimension_key()
                    return data.get(dimension_key, [])
        except:
            pass
        return []

    def save_high_scores(self):
        """Save top 5 high scores for current terminal dimension to file"""
        try:
            # Load existing data
            data = {}
            if os.path.exists('.babaam_high_score.json'):
                with open('.babaam_high_score.json', 'r') as f:
                    data = json.load(f)

            # Update scores for current dimension
            dimension_key = self._get_dimension_key()
            data[dimension_key] = self.high_scores

            # Save back
            with open('.babaam_high_score.json', 'w') as f:
                json.dump(data, f, indent=2)
        except:
            pass

    def check_high_score(self, score: int) -> int:
        """Check if score makes top 5. Returns position (0-4) or -1 if not in top 5"""
        for i, entry in enumerate(self.high_scores):
            if score > entry['score']:
                return i
        if len(self.high_scores) < 5:
            return len(self.high_scores)
        return -1

    def add_high_score(self, score: int, initials: str):
        """Add a new high score entry"""
        position = self.check_high_score(score)
        if position >= 0:
            self.high_scores.insert(position, {'score': score, 'initials': initials.upper()})
            # Keep only top 5
            self.high_scores = self.high_scores[:5]
            self.save_high_scores()

    def check_achievements(self) -> list:
        """Check which achievements the player has earned. Returns list of achievement names."""
        achievements = []

        # Common criteria: not aborted and second boss defeated
        if self.game_over_reason != 'aborted' and self.boss_level >= 3:
            # Achievement 1: Not letting a single enemy get through
            if self.enemies_breached == 0:
                achievements.append("PERFECT DEFENSE")

            # Achievement 2: Only plasma weapon kills
            if self.plasma_only_kills:
                achievements.append("PLASMA PURIST")

            # Achievement 3: More than 18% accuracy with plasma/spread shots
            if self.total_shots_fired > 0:
                accuracy = self.total_hits / self.total_shots_fired
                if accuracy > 0.18:
                    achievements.append("SHARPSHOOTER")

        return achievements

    def prompt_for_initials(self) -> str:
        """Prompt player to enter their initials (1-3 letters)"""
        self.stdscr.clear()
        self.stdscr.bkgd(' ', curses.color_pair(4))  # Set white on black
        curses.curs_set(1)

        # Start epic hero music
        self.synth.start_hero_music()

        prompt_text = [
            "╔═══════════════════════════════╗",
            "║                               ║",
            "║  YOU MADE THE HIGH SCORE!     ║",
            "║                               ║",
            "║   Enter your initials:        ║",
            "║                               ║",
            "║           _ _ _               ║",
            "║                               ║",
            "╚═══════════════════════════════╝"
        ]

        start_y = max(2, (self.height - len(prompt_text)) // 2)

        # Draw prompt box
        for i, line in enumerate(prompt_text):
            y = start_y + i
            x = max(1, (self.width - len(line)) // 2)
            try:
                self.stdscr.addstr(y, x, line, curses.color_pair(3) | curses.A_BOLD)
            except:
                pass

        # Position cursor for input - aligned with the underscores
        input_y = start_y + 6
        # Calculate where the box starts (same as drawing code)
        box_x = max(1, (self.width - 33) // 2)  # Box is 33 chars wide
        # First underscore "_ _ _" is at position 12 within the line
        input_x = box_x + 12

        initials = ""
        while len(initials) < 3:
            try:
                # Position cursor at the appropriate underscore (every 2 chars: positions 0, 2, 4)
                self.stdscr.move(input_y, input_x + (len(initials) * 2))
                self.stdscr.refresh()
                ch = self.stdscr.getch()

                # Check for Enter key to finish early (need at least 1 character)
                if ch in (10, 13) and len(initials) >= 1:  # Enter/Return
                    break

                # Only accept letters
                if 65 <= ch <= 90 or 97 <= ch <= 122:  # A-Z or a-z
                    letter = chr(ch).upper()
                    initials += letter
                    # Display letter at the position of the underscore
                    self.stdscr.addstr(input_y, input_x + ((len(initials) - 1) * 2), letter,
                                      curses.color_pair(3) | curses.A_BOLD)
                    self.stdscr.refresh()  # Refresh to show the letter immediately
            except:
                pass

        # Pause to show initials before closing dialog
        time.sleep(0.8)
        curses.curs_set(0)

        # Stop hero music
        self.synth.stop_hero_music()

        return initials

    def spawn_enemy(self):
        """Spawn a new enemy at the right edge"""
        y = random.randint(2, self.height - 3)

        # Determine enemy type based on score
        rand = random.random()
        if self.player.score > 1000:
            if rand < 0.3:
                enemy_type = EnemyType.FAST
            elif rand < 0.5:
                enemy_type = EnemyType.TANK
            elif rand < 0.7:
                enemy_type = EnemyType.ZIGZAG
            else:
                enemy_type = EnemyType.NORMAL
        elif self.player.score > 500:
            if rand < 0.3:
                enemy_type = EnemyType.FAST
            elif rand < 0.5:
                enemy_type = EnemyType.ZIGZAG
            else:
                enemy_type = EnemyType.NORMAL
        elif self.player.score > 200:
            enemy_type = EnemyType.FAST if rand < 0.3 else EnemyType.NORMAL
        else:
            enemy_type = EnemyType.NORMAL

        self.enemies.append(Enemy(self.width - 2, y, enemy_type))

    def spawn_powerup(self, x: float, y: float):
        """Spawn a random power-up"""
        # Check for rare nuke drop (5% chance, only after first boss)
        if self.player.score >= 500 and random.random() < 0.05:
            self.powerups.append(PowerUp(x, y, PowerUpType.NUKE))
            return

        # Regular powerups (12% chance - reduced for more difficulty)
        if random.random() < 0.12:
            # Shield+Spread combo is too powerful, so make shields rare when spread is unlocked
            if WeaponType.SPREAD in self.player.unlocked_weapons:
                # When spread is unlocked, shields are 10x rarer
                powerup_types = [
                    PowerUpType.RAPID_FIRE,
                    PowerUpType.RAPID_FIRE,  # Add duplicates to weight the odds
                    PowerUpType.RAPID_FIRE,
                    PowerUpType.RAPID_FIRE,
                    PowerUpType.HEALTH,
                    PowerUpType.HEALTH,
                    PowerUpType.HEALTH,
                    PowerUpType.HEALTH,
                    PowerUpType.HEALTH,
                    PowerUpType.SHIELD,  # Only 1 in 10 chance
                ]
            else:
                # Normal distribution when spread not unlocked
                powerup_types = [
                    PowerUpType.RAPID_FIRE,
                    PowerUpType.SHIELD,
                    PowerUpType.HEALTH,
                ]

            # Add weapon powerups if not unlocked
            if WeaponType.SPREAD not in self.player.unlocked_weapons:
                powerup_types.append(PowerUpType.SPREAD_SHOT)
            if WeaponType.ENERGY_BEAM not in self.player.unlocked_weapons:
                powerup_types.append(PowerUpType.ENERGY_BEAM)

            # Add drone powerup after second boss (boss_level >= 3)
            if self.boss_level >= 3:
                powerup_types.append(PowerUpType.DRONE)

            powerup_type = random.choice(powerup_types)
            self.powerups.append(PowerUp(x, y, powerup_type))

    def spawn_boss(self):
        """Spawn a boss"""
        # Randomize boss vertical spawn position (keep 5 rows from edges for boss sprite size)
        y = random.randint(5, self.height - 8)
        self.boss = Boss(self.width - 5, y, self.boss_level)
        self.synth.play('boss')  # Dramatic boss appearance sound

    def shoot(self):
        """Player shoots based on weapon type"""
        if self.player.fire_cooldown > 0:
            return

        # Set cooldown (reduced for faster firing, energy beam fires faster for smoother growth)
        if self.player.weapon == WeaponType.ENERGY_BEAM:
            self.player.fire_cooldown = 2  # Energy beam fires fast for smooth growth
        else:
            self.player.fire_cooldown = 2 if self.player.rapid_fire else 5

        if self.player.weapon == WeaponType.NORMAL:
            # Spawn bullet from center of ship (accounting for 3-line sprite)
            # Normal plasma shot deals 3 damage (3x powerful)
            self.bullets.append(Bullet(self.player.x + self.player.width, self.player.y + 1.0, damage=3))
            self.synth.play('shoot')
            self.total_shots_fired += 1  # Track for achievement
        elif self.player.weapon == WeaponType.SPREAD:
            # Spawn spread bullets from wings and center - all going straight forward
            # Each spread bullet deals 1 damage
            # Center bullet from middle row
            self.bullets.append(Bullet(self.player.x + self.player.width, self.player.y + 1.0, 0, damage=1))
            # Top bullet from top wing (row 0) - straight forward
            self.bullets.append(Bullet(self.player.x + self.player.width, self.player.y + 0.0, 0, damage=1))
            # Bottom bullet from bottom wing (row 2) - straight forward
            self.bullets.append(Bullet(self.player.x + self.player.width, self.player.y + 2.0, 0, damage=1))
            self.synth.play('spread_shoot')
            self.total_shots_fired += 3  # Track for achievement (3 bullets)
        elif self.player.weapon == WeaponType.ENERGY_BEAM:
            # Check if overheated - if so, can't fire (need to release trigger first)
            if self.player.energy_beam_overheated:
                # Don't fire, just play blocked sound and show spark
                sound = self.synth.sounds['blocked']
                sound.set_volume(0.3)  # Lower volume
                sound.play()
                # Trigger spark effect
                self.player.spark_timer = 6  # Show spark for 6 frames
                self.player.spark_char = random.choice(['*', '✦', '✧', '✵', '✶', '✷', '✸', '✹', '※', '⁕', '⁎', '∗', '⋆', '★', '☆'])
            # Check if player is actually stationary (position not changing)
            # was_stationary is updated in update() method based on actual position changes
            elif self.player.was_stationary:
                # Check if all beams are at full power
                beams_at_full_power = (self.player.energy_beam_length >= 60 and
                                      self.player.energy_beam_top_length >= 60 and
                                      self.player.energy_beam_bottom_length >= 60)

                # Only grow beams if not at full power (decay/shutdown managed in update())
                if not beams_at_full_power:
                    # Still growing - accelerating growth rate
                    self.player.energy_beam_charge_time += 1

                    # Accelerating growth tiers (halved for smoother growth with 2x fire rate)
                    if self.player.energy_beam_charge_time < 30:  # First second
                        growth_rate = 3
                    elif self.player.energy_beam_charge_time < 60:  # 1-2 seconds
                        growth_rate = 6
                    elif self.player.energy_beam_charge_time < 90:  # 2-3 seconds
                        growth_rate = 9
                    else:  # 3+ seconds (full charge)
                        growth_rate = 12

                    # Double growth rate if Rapid Fire is active
                    if self.player.rapid_fire:
                        growth_rate *= 2

                    # First grow main (center) beam to max
                    if self.player.energy_beam_length < 60:
                        self.player.energy_beam_length = min(self.player.energy_beam_length + growth_rate, 60)
                    # Once main beam is maxed, grow both side beams simultaneously
                    elif self.player.energy_beam_top_length < 60 or self.player.energy_beam_bottom_length < 60:
                        # Play side beam activation sound when they first start growing
                        if not self.player.side_beams_activated and self.player.energy_beam_top_length == 0:
                            self.synth.play('side_beam_activate')
                            self.player.side_beams_activated = True

                        self.player.energy_beam_top_length = min(self.player.energy_beam_top_length + growth_rate, 60)
                        self.player.energy_beam_bottom_length = min(self.player.energy_beam_bottom_length + growth_rate, 60)

                # Create beams (flicker visibility managed in update() which may clear them)
                # Create main energy beam with current length from center of ship (convert to int for range())
                self.energy_beams.append(EnergyBeam(self.player.x + self.player.width, self.player.y + 1.0, int(self.player.energy_beam_length)))

                # Create top beam if it has length
                if self.player.energy_beam_top_length > 0:
                    self.energy_beams.append(EnergyBeam(self.player.x + self.player.width, self.player.y + 0.0, int(self.player.energy_beam_top_length)))

                # Create bottom beam if it has length
                if self.player.energy_beam_bottom_length > 0:
                    self.energy_beams.append(EnergyBeam(self.player.x + self.player.width, self.player.y + 2.0, int(self.player.energy_beam_bottom_length)))

                # Play sound based on beam state
                if self.player.energy_beam_decay_time > 0:
                    # Flickering/dying phase - use dying sound with noise (no volume decrease)
                    sound = self.synth.sounds['energy_beam_dying']
                    sound.set_volume(0.9)  # Keep volume high
                    sound.play()
                else:
                    # Normal operation - full power sound
                    sound = self.synth.sounds['energy_beam']
                    if self.player.energy_beam_top_length > 0 or self.player.energy_beam_bottom_length > 0:
                        # Side beams active - play at 1.5x volume for more intensity
                        sound.set_volume(0.9)  # Increased from base 0.6
                    else:
                        # Normal single beam - use base volume
                        sound.set_volume(0.6)
                    sound.play()
            else:
                # Player is moving - play blocked sound to indicate action is not allowed
                sound = self.synth.sounds['blocked']
                sound.set_volume(0.3)  # Lower volume
                sound.play()
                # Trigger spark effect
                self.player.spark_timer = 6  # Show spark for 6 frames
                self.player.spark_char = random.choice(['*', '✦', '✧', '✵', '✶', '✷', '✸', '✹', '※', '⁕', '⁎', '∗', '⋆', '★', '☆'])

    def handle_input(self):
        """Handle player input"""
        # Read all available input from curses (for non-arrow keys)
        while True:
            try:
                key = self.stdscr.getch()
                if key == -1:  # No more input
                    break

                # Handle other keys
                if key == 27:  # ESC key
                    # Show confirmation dialog
                    if self._show_confirmation_dialog("ABORT MISSION?", "Are you sure you want to quit?"):
                        self.game_over = True
                        self.game_over_reason = 'aborted'
                elif key == ord('p') or key == ord('P'):
                    self.paused = not self.paused  # Toggle pause
                    # Pause/resume engine sound and game music
                    if self.paused:
                        if self.engine_sound_channel:
                            self.engine_sound_channel.pause()
                        if self.synth.game_music_channel:
                            self.synth.game_music_channel.pause()
                    else:
                        if self.engine_sound_channel:
                            self.engine_sound_channel.unpause()
                        if self.synth.game_music_channel:
                            self.synth.game_music_channel.unpause()
                elif key == ord('1'):
                    self.player.weapon = WeaponType.NORMAL
                elif key == ord('2') and WeaponType.SPREAD in self.player.unlocked_weapons:
                    self.player.weapon = WeaponType.SPREAD
                elif key == ord('3') and WeaponType.ENERGY_BEAM in self.player.unlocked_weapons:
                    self.player.weapon = WeaponType.ENERGY_BEAM

                # Cheat code handling
                if key == ord('0'):
                    self.cheat_code_input += '0'
                    # Keep only last 5 digits
                    if len(self.cheat_code_input) > 5:
                        self.cheat_code_input = self.cheat_code_input[-5:]
                    # Check for drone cheat code
                    if self.cheat_code_input == "00000":
                        # Spawn three drones at different positions around player
                        player_center_y = self.player.y + 1  # Center of player's 3-line sprite

                        # Drone 1: Above player (further away: 8 units up, 12 units right)
                        drone1_x = self.player.x + 12
                        drone1_y = player_center_y - 8
                        self.drones.append(Drone(drone1_x, drone1_y, 0))  # Fire immediately

                        # Drone 2: Level with player (15 units right)
                        drone2_x = self.player.x + 15
                        drone2_y = player_center_y
                        self.drones.append(Drone(drone2_x, drone2_y, 3))  # Offset by 3 frames

                        # Drone 3: Below player (8 units down, 12 units right)
                        drone3_x = self.player.x + 12
                        drone3_y = player_center_y + 8
                        self.drones.append(Drone(drone3_x, drone3_y, 6))  # Offset by 6 frames

                        self.cheat_code_input = ""
                elif key == ord('e') or key == ord('E'):
                    self.cheat_code_input += 'E'
                    # Keep only last 5 characters
                    if len(self.cheat_code_input) > 5:
                        self.cheat_code_input = self.cheat_code_input[-5:]
                    # Check for energy weapon cheat code
                    if self.cheat_code_input == "EEEEE":
                        # Unlock and equip energy beam
                        self.player.unlocked_weapons.add(WeaponType.ENERGY_BEAM)
                        self.player.weapon = WeaponType.ENERGY_BEAM
                        self.cheat_code_input = ""
                else:
                    # Reset cheat code on non-zero input
                    if key != -1 and not (curses.KEY_UP <= key <= curses.KEY_RIGHT):
                        self.cheat_code_input = ""
            except:
                break

        # Update velocity based on actual key states from pynput
        # This gives us instant press/release detection without keyboard repeat delays
        self.player.vx = 0
        self.player.vy = 0

        if self.arrow_keys_state[keyboard.Key.up]:
            self.player.vy = -self.player.speed
        if self.arrow_keys_state[keyboard.Key.down]:
            self.player.vy = self.player.speed
        if self.arrow_keys_state[keyboard.Key.left]:
            self.player.vx = -self.player.speed
        if self.arrow_keys_state[keyboard.Key.right]:
            self.player.vx = self.player.speed

        # Handle continuous firing when spacebar is held
        if self.arrow_keys_state[keyboard.Key.space]:
            self.shoot()

        # Manage continuous engine sounds based on direction
        # Priority order (most to least intense): Right (0.13) > Vertical (0.115) > Idle (0.10) > Left (0.08)
        # When moving diagonally, use the most intense sound
        desired_sound = None

        if self.player.vx > 0:  # Moving right (with or without vertical)
            # Check if at right boundary
            if self.player.x >= self.width // 3:
                desired_sound = 'engine_idle'  # At limit, same as idle
            else:
                desired_sound = 'engine_right'  # Most intense - forward thrust
        elif self.player.vx < 0 and self.player.vy != 0:  # Moving left AND vertically (diagonal)
            # Use vertical (0.115) since it's more intense than left (0.08)
            desired_sound = 'engine_vertical'
        elif self.player.vx < 0:  # Moving left only
            desired_sound = 'engine_left'  # Slowing down
        elif self.player.vy != 0:  # Moving vertically only
            desired_sound = 'engine_vertical'
        else:  # Not maneuvering
            desired_sound = 'engine_idle'  # Baseline

        # Switch sound if needed
        velocity_changed = (self.player.vx != self.prev_vx or self.player.vy != self.prev_vy)

        if velocity_changed:
            if self.engine_sound_channel:
                self.engine_sound_channel.stop()
            self.engine_sound_channel = self.synth.sounds[desired_sound].play(loops=-1)

        # Update previous velocity for next frame
        self.prev_vx = self.player.vx
        self.prev_vy = self.player.vy

    def update(self):
        """Update game state"""
        # Don't update if paused
        if self.paused:
            return

        self.frame_count += 1

        # Update GENESIS wobble
        self.genesis_wobble_phase += 0.02
        self.genesis_wobble_x = math.sin(self.genesis_wobble_phase * 1.3) * 0.5
        self.genesis_wobble_y = math.cos(self.genesis_wobble_phase * 0.9) * 0.3

        # Update scrolling starfield
        self._update_starfield()

        # Apply player velocity (continuous movement)
        self.player.x += self.player.vx
        self.player.y += self.player.vy

        # Keep player within bounds (accounting for 3-row sprite and GENESIS ship)
        at_right_boundary = False
        # Check collision with GENESIS - player can't move into it
        # Calculate the rightmost visible column of GENESIS (accounting for wobble)
        genesis_right_edge = self.genesis_x + self.genesis_wobble_x + self.genesis_width

        # Player ship sprite is 3 chars wide (╱█►, ██►, ╲█►)
        # Ensure leftmost part of player doesn't overlap with GENESIS
        # Add 1 char padding so player doesn't visually touch the wall
        if self.player.x < genesis_right_edge + 1:
            self.player.x = genesis_right_edge + 1
        right_limit = (self.width // 3) + 8  # Allow more rightward movement
        # Account for ship width - right edge of ship can't exceed boundary
        if self.player.x + self.player.width > right_limit:
            self.player.x = right_limit - self.player.width
            at_right_boundary = True
        if self.player.y < 1:
            self.player.y = 1
        # Bottom bound: player.y + height must stay inside border (height - 1)
        if self.player.y > self.height - 1 - self.player.height:
            self.player.y = self.height - 1 - self.player.height

        # Energy beam reset logic - reset beams when player actually moves (position changes)
        # Check if position actually changed (not just velocity/key input)
        is_stationary = (self.player.x == self.player.prev_x and self.player.y == self.player.prev_y)
        if not is_stationary:
            # Player actually moved - reset all energy beam lengths and charge time
            self.player.energy_beam_length = 15
            self.player.energy_beam_top_length = 0
            self.player.energy_beam_bottom_length = 0
            self.player.energy_beam_charge_time = 0
            self.player.energy_beam_active_time = 0
            self.player.energy_beam_decay_time = 0
            self.player.energy_beam_overheated = False
            self.player.side_beams_activated = False
            # Clear all existing beams immediately to prevent "painting" walls
            self.energy_beams.clear()
        # Update stationary state for next frame
        self.player.was_stationary = is_stationary
        # Update previous position for next frame
        self.player.prev_x = self.player.x
        self.player.prev_y = self.player.y

        # Energy beam trigger release detection - reset overheat when trigger is released
        # Check if spacebar is currently pressed
        trigger_currently_pressed = self.arrow_keys_state.get(keyboard.Key.space, False)

        # If trigger was pressed last frame but not now, it's been released
        if self.player.energy_beam_trigger_was_pressed and not trigger_currently_pressed and self.player.weapon == WeaponType.ENERGY_BEAM:
            # Trigger released - reset all beam state
            self.player.energy_beam_overheated = False
            self.player.energy_beam_active_time = 0
            self.player.energy_beam_decay_time = 0
            self.player.energy_beam_length = 15
            self.player.energy_beam_top_length = 0
            self.player.energy_beam_bottom_length = 0
            self.player.energy_beam_charge_time = 0
            self.player.side_beams_activated = False
            # Clear any existing beams
            self.energy_beams.clear()

        # Update trigger state for next frame
        if self.player.weapon == WeaponType.ENERGY_BEAM:
            self.player.energy_beam_trigger_was_pressed = trigger_currently_pressed

        # Switch to idle sound if at right boundary and still trying to move right
        if at_right_boundary and self.player.vx > 0:
            if self.engine_sound_channel:
                self.engine_sound_channel.stop()
            self.engine_sound_channel = self.synth.sounds['engine_idle'].play(loops=-1)

        # Update cooldowns
        if self.player.fire_cooldown > 0:
            self.player.fire_cooldown -= 1

        # Update power-up timers
        if self.player.shield_timer > 0:
            self.player.shield_timer -= 1
            if self.player.shield_timer == 0:
                self.player.shield = False

        if self.player.rapid_fire_timer > 0:
            self.player.rapid_fire_timer -= 1
            if self.player.rapid_fire_timer == 0:
                self.player.rapid_fire = False

        # Manage clock ticking music based on active power-ups
        has_shield = self.player.shield
        has_rapid_fire = self.player.rapid_fire
        has_either_powerup = has_shield or has_rapid_fire
        has_both_powerups = has_shield and has_rapid_fire

        if has_both_powerups:
            # Both active - play intense version
            if not self.synth.is_game_music_playing():
                self.synth.start_game_music(intense=True)
            # If normal is playing, switch to intense
            elif self.synth.game_music_channel and 'game_music_intense' not in str(self.synth.game_music_channel):
                self.synth.start_game_music(intense=True)
        elif has_either_powerup:
            # Only one active - play normal version
            if not self.synth.is_game_music_playing():
                self.synth.start_game_music(intense=False)
            # If intense is playing, switch to normal
            elif self.synth.game_music_channel and 'game_music_intense' in str(self.synth.game_music_channel):
                self.synth.start_game_music(intense=False)
        else:
            # No power-ups active - stop music
            if self.synth.is_game_music_playing():
                self.synth.stop_game_music()

        # Update nuke effect timer
        if self.nuke_effect_timer > 0:
            self.nuke_effect_timer -= 1

        # Update ship flash timer
        if self.ship_flash_timer > 0:
            self.ship_flash_timer -= 1

        # Update player damage flash timer
        if self.player.flash_timer > 0:
            self.player.flash_timer -= 1

        # Update wall flash timer
        if self.wall_flash_timer > 0:
            self.wall_flash_timer -= 1

        # Update spark effect timer
        if self.player.spark_timer > 0:
            self.player.spark_timer -= 1

        # Update notification timer and scroll offset
        if self.notification_timer > 0:
            self.notification_timer -= 1
            # Scroll the text leftward (increase offset every 2 frames for smooth scroll)
            if self.frame_count % 2 == 0:
                self.notification_scroll_offset += 1

        # Spawn boss if enough enemies killed
        if self.enemies_killed >= self.next_boss_kills and self.boss is None:
            self.spawn_boss()
            self.enemies.clear()  # Clear regular enemies for boss fight

        # Spawn enemies (not during boss fight)
        if self.boss is None and self.frame_count % self.enemy_spawn_rate == 0:
            self.spawn_enemy()

        # Update bullets
        for bullet in self.bullets[:]:
            bullet.x += bullet.speed
            bullet.y += bullet.dy
            if bullet.x >= self.width - 1 or bullet.y < 1 or bullet.y >= self.height - 1:
                self.bullets.remove(bullet)

        # Update energy beams
        for energy_beam in self.energy_beams[:]:
            energy_beam.lifetime -= 1
            if energy_beam.lifetime <= 0:
                self.energy_beams.remove(energy_beam)

        # Energy beam decay and flicker management (runs every frame for smooth flicker)
        if self.player.weapon == WeaponType.ENERGY_BEAM and self.player.was_stationary:
            trigger_pressed = self.arrow_keys_state.get(keyboard.Key.space, False)

            if trigger_pressed and not self.player.energy_beam_overheated:
                # Check if all beams are at full power
                beams_at_full_power = (self.player.energy_beam_length >= 60 and
                                      self.player.energy_beam_top_length >= 60 and
                                      self.player.energy_beam_bottom_length >= 60)

                if beams_at_full_power:
                    # Increment decay timer (happens every frame for smooth flicker)
                    self.player.energy_beam_decay_time += 1

                    # Check for shutdown after 3 seconds at full power
                    if self.player.energy_beam_decay_time >= 90:
                        self.player.energy_beam_overheated = True
                        self.energy_beams.clear()
                        sound = self.synth.sounds['blocked']
                        sound.set_volume(0.3)  # Lower volume
                        sound.play()
                        # Trigger spark effect
                        self.player.spark_timer = 6  # Show spark for 6 frames
                        self.player.spark_char = random.choice(['*', '✦', '✧', '✵', '✶', '✷', '✸', '✹', '※', '⁕', '⁎', '∗', '⋆', '★', '☆'])
                    else:
                        # Flicker logic - runs every frame for high-frequency flicker
                        flicker_time = self.player.energy_beam_decay_time - 1  # 0-89 frames

                        # Calculate flicker period based on time
                        if flicker_time < 30:  # First second - very fast flicker (15 Hz)
                            flicker_period = 2
                        elif flicker_time < 60:  # Second second - slowing down
                            flicker_period = 2 + ((flicker_time - 30) // 5)
                        else:  # Final second - very slow, long outages
                            flicker_period = 8 + ((flicker_time - 60) // 3)

                        # Determine if beams should be visible this frame
                        beam_visible = (flicker_time % flicker_period) < (flicker_period // 2)

                        # Clear beams if they should be invisible
                        if not beam_visible:
                            self.energy_beams.clear()

        # Update drones
        for drone in self.drones[:]:
            drone.lifetime -= 1
            if drone.lifetime <= 0:
                self.drones.remove(drone)
                continue

            # Update fire cooldown
            if drone.fire_cooldown > 0:
                drone.fire_cooldown -= 1

            # Find nearest enemy or boss
            nearest_target = None
            nearest_dist = float('inf')

            # Check all enemies
            for enemy in self.enemies:
                dist = ((drone.x - enemy.x) ** 2 + (drone.y - enemy.y) ** 2) ** 0.5
                if dist < nearest_dist:
                    nearest_dist = dist
                    nearest_target = enemy

            # Check boss
            if self.boss:
                boss_dist = ((drone.x - self.boss.x) ** 2 + (drone.y - self.boss.y) ** 2) ** 0.5
                if boss_dist < nearest_dist:
                    nearest_dist = boss_dist
                    nearest_target = self.boss

            # Move towards target and shoot, or circle player if no target
            if nearest_target:
                # Calculate direction to target
                dx = nearest_target.x - drone.x
                dy = nearest_target.y - drone.y
                dist = (dx ** 2 + dy ** 2) ** 0.5

                if dist > 0:
                    # Maintain safe distance - only move if too far away
                    # Stop at 8 units to avoid crashing, optimal shooting range
                    safe_distance = 8.0
                    if dist > safe_distance:
                        # Normalize and move toward target
                        drone.x += (dx / dist) * drone.speed
                        drone.y += (dy / dist) * drone.speed

                        # Keep drone within screen bounds (accounting for sprite size)
                        drone.x = max(2, min(self.width - 1 - drone.width, drone.x))
                        drone.y = max(1, min(self.height - 1 - drone.height, drone.y))

                    # Shoot if in range and cooldown is ready
                    if dist < 30 and drone.fire_cooldown == 0:
                        # Calculate bullet trajectory with precision
                        bullet_dx = dx / dist
                        bullet_dy = dy / dist
                        # Create bullet aimed at target from drone position
                        bullet = Bullet(drone.x, drone.y)
                        bullet.char = "✦"  # Small star for omnidirectional movement
                        bullet.color = 3  # Amber to match player's plasma shots
                        bullet.speed = 2.0 * bullet_dx  # Apply direction to speed
                        bullet.dy = 2.0 * bullet_dy
                        self.drone_bullets.append(bullet)
                        self.synth.play('drone_shoot')  # Unique synthetic drone shot sound
                        # Add slight randomization (7-9 frames) to keep drones staggered
                        drone.fire_cooldown = random.randint(7, 9)
            else:
                # No target - circle around player
                # Increment angle for smooth circular motion (0.1 radians per frame)
                drone.circle_angle += 0.1
                if drone.circle_angle > 2 * math.pi:
                    drone.circle_angle -= 2 * math.pi

                # Calculate target position on circle around player
                # Player center is player.y + 1 (middle of 3-line sprite)
                player_center_x = self.player.x + self.player.width / 2
                player_center_y = self.player.y + 1

                target_x = player_center_x + drone.circle_radius * math.cos(drone.circle_angle)
                target_y = player_center_y + drone.circle_radius * math.sin(drone.circle_angle)

                # Move smoothly toward target position on circle
                dx = target_x - drone.x
                dy = target_y - drone.y
                dist = math.sqrt(dx ** 2 + dy ** 2)

                if dist > 0.5:  # Only move if not close enough to target position
                    # Move toward target position
                    drone.x += (dx / dist) * drone.speed
                    drone.y += (dy / dist) * drone.speed

                # Keep drone within screen bounds
                drone.x = max(2, min(self.width - 1 - drone.width, drone.x))
                drone.y = max(1, min(self.height - 1 - drone.height, drone.y))

        # Update drone bullets
        for bullet in self.drone_bullets[:]:
            bullet.x += bullet.speed
            bullet.y += bullet.dy
            if bullet.x >= self.width - 1 or bullet.y < 1 or bullet.y >= self.height - 1 or bullet.x < 1:
                self.drone_bullets.remove(bullet)

        # Update enemies
        for enemy in self.enemies[:]:
            enemy.x -= enemy.speed

            # Update flash timer
            if enemy.flash_timer > 0:
                enemy.flash_timer -= 1

            # Zigzag movement
            if enemy.type == EnemyType.ZIGZAG:
                enemy.y += enemy.direction * 0.2
                # Clamp position and force direction to prevent flickering
                if enemy.y <= 2:
                    enemy.y = 2
                    enemy.direction = 1  # Force downward
                elif enemy.y >= self.height - 3:
                    enemy.y = self.height - 3
                    enemy.direction = -1  # Force upward

            if enemy.x <= 0:
                # Kamikaze bomber hit the wall! Create explosion
                self.explosions.append(Explosion(enemy.x + enemy.width/2, enemy.y + enemy.height/2, True))
                self.synth.play('explosion')
                self.enemies.remove(enemy)
                self.enemies_breached += 1  # Track for achievement
                self.wall_flash_timer = 6  # Flash wall when hit
                if not self.player.shield:
                    self.player.health -= 1
                    if self.player.health <= 0:
                        self.game_over = True
                        self.game_over_reason = 'cargo_captured'

        # Update boss
        if self.boss:
            self.boss.x -= self.boss.speed

            # Update flash timer
            if self.boss.flash_timer > 0:
                self.boss.flash_timer -= 1

            # Boss movement pattern
            self.boss.move_pattern += 1
            if self.boss.move_pattern % 60 < 30:
                if self.boss.y < self.height - 5:
                    self.boss.y += 0.1
            else:
                if self.boss.y > 5:
                    self.boss.y -= 0.1

            # Boss shooting
            self.boss.shoot_timer += 1
            if self.boss.shoot_timer >= 40:
                self.boss_bullets.append(BossBullet(self.boss.x - 1, self.boss.y))
                self.synth.play('boss_fire')  # Deep, menacing boss shot sound
                self.boss.shoot_timer = 0

            # Boss reached left side - massive wall impact!
            if self.boss.x <= 0:
                # Create massive explosions when boss hits wall
                self.explosions.append(Explosion(self.boss.x, self.boss.y, True))
                for _ in range(5):
                    ex = self.boss.x + random.uniform(-2, 2)
                    ey = self.boss.y + random.uniform(-2, 2)
                    self.explosions.append(Explosion(ex, ey, True))
                self.synth.play('nuke')  # Massive explosion sound
                self.boss = None
                self.player.health = 0
                self.game_over = True
                self.game_over_reason = 'cargo_captured'

        # Update boss bullets
        for bullet in self.boss_bullets[:]:
            bullet.x += bullet.speed
            bullet.y += bullet.dy

            # Ricochet off the wall!
            if bullet.x <= 2 and bullet.speed < 0:  # Heading toward wall
                bullet.speed = abs(bullet.speed)  # Reverse direction (bounce back)
                bullet.dy = random.uniform(-0.6, 0.6)  # Random vertical velocity
                self.explosions.append(Explosion(2, bullet.y, False))  # Small spark at wall
                self.synth.play('ricochet')  # Metallic ricochet sound

            # Remove if goes off screen (right side or top/bottom)
            if bullet.x >= self.width - 1 or bullet.y < 1 or bullet.y >= self.height - 1:
                self.boss_bullets.remove(bullet)

        # Update powerups
        for powerup in self.powerups[:]:
            powerup.x -= powerup.speed
            if powerup.x <= 0:
                self.powerups.remove(powerup)

        # Update explosions
        for explosion in self.explosions[:]:
            explosion.lifetime -= 1
            if explosion.lifetime <= 0:
                self.explosions.remove(explosion)

        # Check drone bullet-enemy collisions
        for bullet in self.drone_bullets[:]:
            for enemy in self.enemies[:]:
                # Check if bullet is within enemy bounding box
                if (bullet.x >= enemy.x and bullet.x < enemy.x + enemy.width and
                    bullet.y >= enemy.y and bullet.y < enemy.y + enemy.height):
                    if bullet in self.drone_bullets:
                        self.drone_bullets.remove(bullet)
                    enemy.health -= 1
                    if enemy.health <= 0:
                        if enemy in self.enemies:
                            self.enemies.remove(enemy)
                        self.enemies_killed += 1  # Track kills for boss spawning
                        self.plasma_only_kills = False  # Track for achievement (non-plasma kill)
                        self.explosions.append(Explosion(enemy.x + enemy.width/2, enemy.y + enemy.height/2))
                        self.player.score += enemy.points
                        self.spawn_powerup(enemy.x, enemy.y)
                        self.synth.play('explosion')
                    else:
                        # Enemy hit but not destroyed - flash and play sound
                        enemy.flash_timer = 6  # Flash for 6 frames
                        self.synth.play('boss_hit')
                    break

        # Check drone bullet-boss collisions
        if self.boss:
            for bullet in self.drone_bullets[:]:
                if (abs(bullet.x - self.boss.x) < 2 and
                    abs(bullet.y - self.boss.y) < 2):
                    if bullet in self.drone_bullets:
                        self.drone_bullets.remove(bullet)
                    self.boss.health -= 1
                    self.explosions.append(Explosion(self.boss.x, self.boss.y, False))
                    self.boss.flash_timer = 6  # Flash for 6 frames
                    self.synth.play('boss_hit')  # Satisfying hit sound

                    if self.boss.health <= 0:
                        self.explosions.append(Explosion(self.boss.x, self.boss.y, True))
                        self.player.score += self.boss.points
                        self.boss = None
                        self.boss_level += 1
                        self.next_boss_kills += 50  # Next boss after 50 more kills
                        self.synth.play('boss')  # Boss defeated!
                        # Drop multiple powerups
                        for _ in range(3):
                            self.spawn_powerup(self.width - 10, random.randint(2, self.height - 3))
                    break

        # Check bullet-enemy collisions
        for bullet in self.bullets[:]:
            for enemy in self.enemies[:]:
                # Check if bullet is within enemy bounding box
                if (bullet.x >= enemy.x and bullet.x < enemy.x + enemy.width and
                    bullet.y >= enemy.y and bullet.y < enemy.y + enemy.height):
                    if bullet in self.bullets:
                        self.bullets.remove(bullet)
                    self.total_hits += 1  # Track for achievement (accuracy)
                    enemy.health -= bullet.damage  # Use bullet's damage value
                    if enemy.health <= 0:
                        if enemy in self.enemies:
                            self.enemies.remove(enemy)
                        self.enemies_killed += 1  # Track kills for boss spawning
                        # PLASMA PURIST: Only allow plasma cannon (damage=3), not spread shot (damage=1)
                        if bullet.damage != 3:
                            self.plasma_only_kills = False
                        self.explosions.append(Explosion(enemy.x + enemy.width/2, enemy.y + enemy.height/2))
                        self.player.score += enemy.points
                        self.spawn_powerup(enemy.x, enemy.y)
                        self.synth.play('explosion')
                    else:
                        # Enemy hit but not destroyed - flash and play sound
                        enemy.flash_timer = 6  # Flash for 6 frames
                        self.synth.play('boss_hit')
                    break

        # Check energy beam-enemy collisions
        for energy_beam in self.energy_beams[:]:
            for enemy in self.enemies[:]:
                # Check if energy beam intersects with enemy
                if (energy_beam.x < enemy.x + enemy.width and energy_beam.x + energy_beam.length > enemy.x and
                    energy_beam.y >= enemy.y and energy_beam.y < enemy.y + enemy.height):
                    enemy.health -= 1
                    if enemy.health <= 0:
                        if enemy in self.enemies:
                            self.enemies.remove(enemy)
                        self.enemies_killed += 1  # Track kills for boss spawning
                        self.plasma_only_kills = False  # Track for achievement (non-plasma kill)
                        self.explosions.append(Explosion(enemy.x + enemy.width/2, enemy.y + enemy.height/2))
                        self.player.score += enemy.points
                        self.spawn_powerup(enemy.x, enemy.y)
                        self.synth.play('explosion')
                    else:
                        # Enemy hit but not destroyed - flash and play sound occasionally to avoid spam
                        enemy.flash_timer = 6  # Flash for 6 frames
                        if int(enemy.health * 2) % 3 == 0:
                            self.synth.play('boss_hit')

        # Check bullet-boss collisions
        if self.boss:
            for bullet in self.bullets[:]:
                if (abs(bullet.x - self.boss.x) < 2 and
                    abs(bullet.y - self.boss.y) < 2):
                    if bullet in self.bullets:
                        self.bullets.remove(bullet)
                    self.boss.health -= bullet.damage  # Use bullet's damage value
                    self.explosions.append(Explosion(self.boss.x, self.boss.y, False))
                    self.boss.flash_timer = 6  # Flash for 6 frames
                    self.synth.play('boss_hit')  # Satisfying hit sound

                    if self.boss.health <= 0:
                        self.explosions.append(Explosion(self.boss.x, self.boss.y, True))
                        self.player.score += self.boss.points
                        self.boss = None
                        self.boss_level += 1
                        self.next_boss_kills += 50  # Next boss after 50 more kills
                        self.synth.play('boss')  # Boss defeated!
                        # Drop multiple powerups
                        for _ in range(3):
                            self.spawn_powerup(self.width - 10, random.randint(2, self.height - 3))
                    break

            # Check energy beam-boss collisions (only if boss still exists)
            if self.boss:
                for energy_beam in self.energy_beams[:]:
                    if (abs(energy_beam.x - self.boss.x) < energy_beam.length and
                        abs(energy_beam.y - self.boss.y) < 2):
                        self.boss.health -= 0.5  # Energy beam does continuous damage
                        self.boss.flash_timer = 6  # Flash for 6 frames
                        # Play hit sound only occasionally for continuous energy beam damage (avoid spam)
                        if int(self.boss.health * 2) % 3 == 0:
                            self.synth.play('boss_hit')
                        if self.boss.health <= 0:
                            self.explosions.append(Explosion(self.boss.x, self.boss.y, True))
                            self.player.score += self.boss.points
                            self.boss = None
                            self.boss_level += 1
                            self.next_boss_kills += 50  # Next boss after 50 more kills
                            self.synth.play('boss')  # Boss defeated by energy beam!
                            for _ in range(3):
                                self.spawn_powerup(self.width - 10, random.randint(2, self.height - 3))
                            break

        # Check boss bullet-player collisions (accounting for 3x3 player sprite)
        for bullet in self.boss_bullets[:]:
            if (bullet.x >= self.player.x and bullet.x < self.player.x + self.player.width and
                bullet.y >= self.player.y and bullet.y < self.player.y + self.player.height):
                self.boss_bullets.remove(bullet)
                if not self.player.shield:
                    self.player.health -= 1
                    self.player.flash_timer = 6  # Flash ship when hit
                    # Center explosion on player sprite
                    self.explosions.append(Explosion(self.player.x + self.player.width/2, self.player.y + self.player.height/2))
                    self.synth.play('damage')
                    if self.player.health <= 0:
                        self.game_over = True
                        self.game_over_reason = 'player_died'

        # Check drone-enemy collisions
        for drone in self.drones[:]:
            for enemy in self.enemies[:]:
                # Check if drone overlaps with enemy
                if (drone.x < enemy.x + enemy.width and drone.x + drone.width > enemy.x and
                    drone.y < enemy.y + enemy.height and drone.y + drone.height > enemy.y):
                    # Collision! Destroy both
                    if drone in self.drones:
                        self.drones.remove(drone)
                    if enemy in self.enemies:
                        self.enemies.remove(enemy)
                    self.enemies_killed += 1  # Track kills for boss spawning
                    # Drone kills are allowed for PLASMA PURIST achievement
                    # Create explosions for both
                    self.explosions.append(Explosion(enemy.x + enemy.width/2, enemy.y + enemy.height/2))
                    self.explosions.append(Explosion(drone.x + drone.width/2, drone.y + drone.height/2))
                    self.player.score += enemy.points
                    self.spawn_powerup(enemy.x, enemy.y)
                    self.synth.play('explosion')
                    break

        # Check player-enemy collisions
        for enemy in self.enemies[:]:
            # Check if player overlaps with enemy (accounting for player sprite size)
            if (self.player.x < enemy.x + enemy.width and self.player.x + self.player.width > enemy.x and
                self.player.y < enemy.y + enemy.height and self.player.y + self.player.height > enemy.y):
                self.enemies.remove(enemy)
                self.enemies_killed += 1  # Track kills for boss spawning
                # Ramming is allowed for PLASMA PURIST achievement
                self.explosions.append(Explosion(enemy.x + enemy.width/2, enemy.y + enemy.height/2))
                self.synth.play('explosion')  # Play explosion sound for enemy
                if not self.player.shield:
                    self.player.health -= 1
                    self.player.flash_timer = 6  # Flash ship when hit
                    self.synth.play('damage')
                    if self.player.health <= 0:
                        self.game_over = True
                        self.game_over_reason = 'player_died'

        # Check powerup-player collisions (generous hitbox for 3x3 player)
        for powerup in self.powerups[:]:
            if (abs(self.player.x + self.player.width/2 - powerup.x) < 3 and
                abs(self.player.y + self.player.height/2 - powerup.y) < 2):
                self.powerups.remove(powerup)
                self.player.score += 10  # Bonus points for collecting power-ups
                self.apply_powerup(powerup.type)
                self.synth.play('powerup')

        # Increase difficulty over time
        if self.frame_count % 300 == 0 and self.enemy_spawn_rate > 10:
            self.enemy_spawn_rate -= 1

    def apply_powerup(self, powerup_type: PowerUpType):
        """Apply power-up effect"""
        if powerup_type == PowerUpType.RAPID_FIRE:
            self.player.rapid_fire = True
            self.player.rapid_fire_timer = 300  # 10 seconds
        elif powerup_type == PowerUpType.SHIELD:
            self.player.shield = True
            self.player.shield_timer = 360  # 12 seconds
        elif powerup_type == PowerUpType.HEALTH:
            # Allow overflow up to 3 extra lives (max_health + 3 = 6 total)
            if self.player.health < self.player.max_health + 3:
                self.player.health += 1
        elif powerup_type == PowerUpType.SPREAD_SHOT:
            self.player.unlocked_weapons.add(WeaponType.SPREAD)
            self.player.weapon = WeaponType.SPREAD
        elif powerup_type == PowerUpType.ENERGY_BEAM:
            self.player.unlocked_weapons.add(WeaponType.ENERGY_BEAM)
            # Show notification tip only the first time
            if not self.energy_beam_tip_shown:
                self.notification_text = "ENERGY BEAM UNLOCKED! Efficient against CAPITAL WARSHIPS. Press 3 to equip."
                self.notification_timer = 240  # Show for 8 seconds (at 30 FPS)
                self.notification_scroll_offset = 0
                self.energy_beam_tip_shown = True
        elif powerup_type == PowerUpType.NUKE:
            # Activate nuke visual effects FIRST
            self.nuke_effect_timer = 20  # Effect lasts 20 frames
            self.nukes_used += 1  # Track nuke usage

            # Destroy all enemies on screen (nukes are allowed for PLASMA PURIST achievement)
            for enemy in self.enemies[:]:
                self.explosions.append(Explosion(enemy.x + enemy.width/2, enemy.y + enemy.height/2, True))
                self.player.score += enemy.points
                self.enemies_killed += 1  # Track each kill for boss spawning
            self.enemies.clear()

            # Destroy boss if present
            if self.boss:
                self.explosions.append(Explosion(self.boss.x, self.boss.y, True))
                self.player.score += self.boss.points
                self.boss = None
                self.boss_level += 1
                self.next_boss_kills += 50  # Next boss after 50 more kills

            # Add random explosions across screen for effect
            for _ in range(15):
                ex = random.randint(5, self.width - 5)
                ey = random.randint(2, self.height - 3)
                self.explosions.append(Explosion(ex, ey, True))

            self.synth.play('nuke')  # Massive explosion sound!

            # Using a nuke costs 1 health (deducted AFTER the effect so animation plays)
            self.player.health -= 1
            if self.player.health <= 0:
                self.game_over = True
                self.game_over_reason = 'nuke_sacrifice'
        elif powerup_type == PowerUpType.DRONE:
            # Spawn three drones at different positions around player
            player_center_y = self.player.y + 1  # Center of player's 3-line sprite

            # Drone 1: Above player (further away: 8 units up, 12 units right)
            drone1_x = self.player.x + 12
            drone1_y = player_center_y - 8
            self.drones.append(Drone(drone1_x, drone1_y, 0))  # Fire immediately

            # Drone 2: Level with player (15 units right)
            drone2_x = self.player.x + 15
            drone2_y = player_center_y
            self.drones.append(Drone(drone2_x, drone2_y, 3))  # Offset by 3 frames

            # Drone 3: Below player (8 units down, 12 units right)
            drone3_x = self.player.x + 12
            drone3_y = player_center_y + 8
            self.drones.append(Drone(drone3_x, drone3_y, 6))  # Offset by 6 frames

    def draw(self):
        """Draw everything to the screen"""
        # Use erase() instead of clear() to avoid flicker
        self.pad.erase()

        # Draw border with explicit white color
        self.pad.attron(curses.color_pair(4))  # White
        self.pad.border()
        self.pad.attroff(curses.color_pair(4))

        # Draw boundary markers to show right movement limit (where ship can't go further right)
        try:
            right_limit = (self.width // 3) + 8
            # Add markers every few characters leading to the boundary
            for offset in range(0, 10, 2):  # Markers at -8, -6, -4, -2, 0 from boundary
                marker_x = right_limit - offset
                if marker_x > 1 and marker_x < self.width - 1:
                    # Top border marker
                    self.pad.addstr(0, marker_x, "▼", curses.color_pair(3))
                    # Bottom border marker
                    self.pad.addstr(self.height - 1, marker_x, "▲", curses.color_pair(3))

            # Final boundary line - more prominent
            if right_limit < self.width - 1:
                self.pad.addstr(0, right_limit, "║", curses.color_pair(3) | curses.A_BOLD)
                self.pad.addstr(self.height - 1, right_limit, "║", curses.color_pair(3) | curses.A_BOLD)
        except:
            pass

        # Draw scrolling starfield (background layer)
        for star in self.starfield:
            try:
                # Different brightness based on layer (parallax depth)
                if star['layer'] == 1:
                    # Far stars - dimmest
                    self.pad.addstr(int(star['y']), int(star['x']), star['char'], curses.color_pair(4))
                elif star['layer'] == 2:
                    # Mid-distance stars - medium brightness
                    self.pad.addstr(int(star['y']), int(star['x']), star['char'], curses.color_pair(5))
                else:
                    # Close stars - brightest
                    self.pad.addstr(int(star['y']), int(star['x']), star['char'], curses.color_pair(5) | curses.A_BOLD)
            except:
                pass

        # Draw GENESIS freight ship on the left side (only right edge visible)
        try:
            genesis_x = int(self.genesis_x + self.genesis_wobble_x)
            genesis_center_y = (self.height // 2) + int(self.genesis_wobble_y)

            # Determine colors based on flash/shield state (match intro's two-color scheme)
            if self.wall_flash_timer > 0:
                border_color = 4  # White when hit
                rivet_color = 4
                texture_color = 4
            else:
                border_color = 11 if self.player.shield else 5  # Blue when shielded, green (like intro)
                rivet_color = 11 if self.player.shield else 4   # Blue when shielded, white (like intro)
                texture_color = 11 if self.player.shield else 7  # Blue when shielded, gray (like intro)

            y_start = genesis_center_y - self.genesis_height // 2
            wall_patterns = ["▓", "▒", "░", "█"]

            # Draw only the visible right portion of GENESIS (matching intro exactly)
            # Draw up to 2 columns to ensure frame is always covered
            for row in range(self.genesis_height):
                y = y_start + row
                if 0 < y < self.height - 1:
                    # The rightmost visible wall is at genesis_x + width - 1
                    right_wall_x = genesis_x + self.genesis_width - 1

                    # Determine what character to use based on row position (matching intro pattern exactly)
                    if row == 0:
                        # Top corner
                        wall_char = "╗"
                        wall_color = border_color
                    elif row == self.genesis_height - 1:
                        # Bottom corner
                        wall_char = "╝"
                        wall_color = border_color
                    else:
                        # Middle rows: textured wall pattern (EXACT match to intro lines 4169-4177)
                        if row % 3 == 0:
                            wall_char = "║"
                            wall_color = border_color
                        elif row % 7 == 0:
                            wall_char = "●"
                            wall_color = rivet_color
                        else:
                            wall_char = wall_patterns[row % 4]
                            wall_color = texture_color

                    # Draw rightmost column (the right wall)
                    if right_wall_x >= 0 and right_wall_x < self.width:
                        self.pad.addstr(y, right_wall_x, wall_char, curses.color_pair(wall_color))

                    # Also draw column to the left if wobble pushes GENESIS right, to cover frame
                    # This column should show the interior (░), not the wall pattern
                    if right_wall_x == 1:
                        # When wobbled right, also draw at x=0 to cover frame
                        if row == 0:
                            # Top border
                            self.pad.addstr(y, 0, "═", curses.color_pair(border_color))
                        elif row == self.genesis_height - 1:
                            # Bottom border
                            self.pad.addstr(y, 0, "═", curses.color_pair(border_color))
                        else:
                            # Interior fill (matching intro line 4185)
                            self.pad.addstr(y, 0, "░", curses.color_pair(texture_color))
        except:
            pass

        # Draw UI
        # Health bar (using half-blocks - 3 chars = 6 HP)
        max_health = 6  # Max possible health (3 starting + 3 overflow)
        bar_width = 3  # 3 characters = 6 HP (2 HP per character, half-blocks for odd HP)
        filled_full = self.player.health // 2  # Number of full blocks
        has_half = (self.player.health % 2 == 1)  # Check if odd HP (needs half block)
        gauge_str = '█' * filled_full
        if has_half and filled_full < bar_width:
            gauge_str += '▌'
        gauge_str = gauge_str.ljust(bar_width)
        health_str = f"HP [{gauge_str}]"

        score_str = f"Score: {self.player.score}"
        # Show current high score, but update in real-time if player beats it
        stored_high_score = self.high_scores[0]['score'] if self.high_scores else 0
        current_high_score = max(stored_high_score, self.player.score)
        high_score_str = f"High: {current_high_score}"

        # Draw HP gauge with blinking when health is 1
        if self.player.health == 1:
            blink_cycle = self.frame_count % 16
            if blink_cycle < 8:  # Show for first 8 frames
                self.pad.addstr(0, 2, health_str, curses.color_pair(12))
            else:
                self.pad.addstr(0, 2, "        ", curses.color_pair(12))
        else:
            self.pad.addstr(0, 2, health_str, curses.color_pair(12))

        # Show shield indicator
        if self.player.shield:
            shield_str = f" [SHIELD:{self.player.shield_timer//30}s]"
            self.pad.addstr(0, 2 + len(health_str), shield_str, curses.color_pair(11))

        # Show rapid fire indicator
        if self.player.rapid_fire:
            rapid_str = f" [RAPID:{self.player.rapid_fire_timer//30}s]"
            offset = len(health_str) + (len(f" [SHIELD:{self.player.shield_timer//30}s]") if self.player.shield else 0)
            self.pad.addstr(0, 2 + offset, rapid_str, curses.color_pair(10))

        self.pad.addstr(0, self.width - len(score_str) - 2, score_str,
                          curses.color_pair(5))
        self.pad.addstr(0, self.width - len(score_str) - len(high_score_str) - 4,
                          high_score_str, curses.color_pair(5))

        # Draw weapon info
        # Display names for weapons
        weapon_display_name = {
            WeaponType.NORMAL: "PLASMA",
            WeaponType.SPREAD: "SPREAD",
            WeaponType.ENERGY_BEAM: "ENERGY"
        }
        weapon_str = f"Weapon: {weapon_display_name[self.player.weapon]} [1"
        if WeaponType.SPREAD in self.player.unlocked_weapons:
            weapon_str += "/2"
        if WeaponType.ENERGY_BEAM in self.player.unlocked_weapons:
            weapon_str += "/3"
        weapon_str += "]"
        self.pad.addstr(self.height - 1, 2, weapon_str, curses.color_pair(5))

        # Draw drone timer gauge
        if self.drones:
            # Show timer for first active drone
            drone = self.drones[0]
            bar_width = 8  # 8 characters = 16 seconds (2 seconds per character, half-blocks for odd seconds)
            seconds_left = drone.lifetime / 30  # Convert frames to seconds (can be fractional)
            # Each character represents 2 seconds, use half-block for odd seconds
            filled_full = int(seconds_left / 2)  # Number of full blocks
            has_half = (int(seconds_left) % 2 == 1)  # Check if odd second (needs half block)
            gauge_str = '█' * filled_full
            if has_half and filled_full < bar_width:
                gauge_str += '▌'
            gauge_str = gauge_str.ljust(bar_width)
            drone_bar = f"DRONE [{gauge_str}] {int(seconds_left)}s"
            self.pad.addstr(self.height - 1, self.width - len(drone_bar) - 2,
                              drone_bar, curses.color_pair(11))

        # Draw boss health bar (using half-blocks - 15 chars for full health)
        if self.boss:
            bar_width = 15  # Half the previous size due to half-blocks
            health_pct = self.boss.health / self.boss.max_health
            # Calculate filled blocks using half-blocks for precision
            filled_chars = bar_width * health_pct  # Can be fractional
            filled_full = int(filled_chars)  # Number of full blocks
            has_half = (filled_chars - filled_full) >= 0.5  # Add half block if >= 50% of next char
            gauge_str = '█' * filled_full
            if has_half and filled_full < bar_width:
                gauge_str += '▌'
            gauge_str = gauge_str.ljust(bar_width)
            boss_bar = f"BOSS [{gauge_str}] {int(health_pct * 100)}%"
            # Position boss bar to the left of drone bar if drone is active
            if self.drones:
                self.pad.addstr(self.height - 1, self.width - len(boss_bar) - len(f"DRONE [{('█' * 8).ljust(8)}] 8s") - 4,
                                  boss_bar, curses.color_pair(9))
            else:
                self.pad.addstr(self.height - 1, self.width - len(boss_bar) - 2,
                                  boss_bar, curses.color_pair(9))

        # Draw scrolling notification text
        if self.notification_timer > 0 and self.notification_text:
            # Calculate available space in the middle of bottom row
            # Left side has weapon info, right side may have boss/drone bars
            left_offset = len(weapon_str) + 4  # After weapon string with padding

            # Calculate right boundary based on what's displayed
            if self.boss and self.drones:
                # Both boss and drone bars
                right_boundary = self.width - len(boss_bar) - len(f"DRONE [{('█' * 8).ljust(8)}] 8s") - 6
            elif self.boss:
                # Just boss bar
                right_boundary = self.width - len(boss_bar) - 4
            elif self.drones:
                # Just drone bar
                right_boundary = self.width - len(f"DRONE [{('█' * 8).ljust(8)}] 8s") - 4
            else:
                # No bars, more space available
                right_boundary = self.width - 4

            # Calculate visible window width for scrolling text
            window_width = max(10, right_boundary - left_offset)

            # Create scrolling effect by extracting visible portion of text
            # Add padding to create smooth entry and exit
            padded_text = "    " + self.notification_text + "    "
            visible_text = padded_text[self.notification_scroll_offset:self.notification_scroll_offset + window_width]

            # Draw the visible portion (bright yellow/magenta for visibility)
            try:
                self.pad.addstr(self.height - 1, left_offset, visible_text.ljust(window_width)[:window_width],
                               curses.color_pair(6) | curses.A_BOLD)  # Magenta bold
            except:
                pass

        # Draw bullets
        for bullet in self.bullets:
            try:
                self.pad.addstr(int(bullet.y), int(bullet.x),
                                 bullet.char, curses.color_pair(bullet.color))
            except:
                pass

        # Draw energy beams (drawn before player so ship appears on top)
        for energy_beam in self.energy_beams:
            try:
                # Draw full beam length starting from cannon position
                for i in range(energy_beam.length):
                    x = int(energy_beam.x) + i
                    if x < self.width - 1:
                        self.pad.addstr(int(energy_beam.y), x,
                                         energy_beam.char, curses.color_pair(energy_beam.color))
            except:
                pass

        # Draw player (with shield effect and startup flash) - drawn after beams so it's on top
        try:
            player_sprite = self.player.sprite_shield if self.player.shield else self.player.sprite
            player_color = 11 if self.player.shield else self.player.color

            # Flash ship white when taking damage (overrides other colors)
            if self.player.flash_timer > 0:
                player_color = 4  # White flash when hit
            # Flash ship at game start by alternating between cyan and white
            elif self.ship_flash_timer > 0:
                # Alternate every 3 frames between cyan (2) and white (4)
                if (self.ship_flash_timer // 3) % 2 == 0:
                    player_color = 4  # White
                else:
                    player_color = 2  # Cyan

            # Draw multi-line sprite
            for i, line in enumerate(player_sprite):
                py = int(self.player.y) + i
                if 1 <= py < self.height - 1:
                    self.pad.addstr(py, int(self.player.x), line, curses.color_pair(player_color))
        except:
            pass

        # Draw spark effect when beam is blocked
        if self.player.spark_timer > 0:
            try:
                # Spark appears in front of middle cannon (center row)
                spark_x = int(self.player.x + self.player.width)
                spark_y = int(self.player.y + 1)  # Middle row (center cannon)
                if 1 <= spark_y < self.height - 1 and spark_x < self.width - 1:
                    # Use yellow color (3) for bright spark effect
                    self.pad.addstr(spark_y, spark_x, self.player.spark_char,
                                   curses.color_pair(3) | curses.A_BOLD)
            except:
                pass

        # Draw enemies
        for enemy in self.enemies:
            try:
                # Flash white when hit
                if enemy.flash_timer > 0 and enemy.flash_timer % 2 == 0:
                    enemy_color = 4  # Flash white
                else:
                    enemy_color = enemy.color  # Normal color

                for i, line in enumerate(enemy.sprite):
                    ey = int(enemy.y) + i
                    if 1 <= ey < self.height - 1:
                        self.pad.addstr(ey, int(enemy.x),
                                         line, curses.color_pair(enemy_color))
            except:
                pass

        # Draw boss
        if self.boss:
            try:
                # Flash white when hit
                if self.boss.flash_timer > 0 and self.boss.flash_timer % 2 == 0:
                    boss_color = 4  # Flash white
                else:
                    boss_color = self.boss.color  # Normal color

                # Draw boss as larger sprite
                boss_sprite = ["╔═╗", "║◈║", "╚═╝"]
                for i, line in enumerate(boss_sprite):
                    y = int(self.boss.y) - 1 + i
                    if 1 <= y < self.height - 1:
                        self.pad.addstr(y, int(self.boss.x) - 1,
                                         line, curses.color_pair(boss_color))
            except:
                pass

        # Draw boss bullets
        for bullet in self.boss_bullets:
            try:
                self.pad.addstr(int(bullet.y), int(bullet.x),
                                 bullet.char, curses.color_pair(bullet.color))
            except:
                pass

        # Draw powerups
        for powerup in self.powerups:
            try:
                self.pad.addstr(int(powerup.y), int(powerup.x),
                                 powerup.char, curses.color_pair(powerup.color))
            except:
                pass

        # Draw drones
        for drone in self.drones:
            try:
                self.pad.addstr(int(drone.y), int(drone.x),
                                 drone.char, curses.color_pair(drone.color) | curses.A_BOLD)
            except:
                pass

        # Draw drone bullets
        for bullet in self.drone_bullets:
            try:
                self.pad.addstr(int(bullet.y), int(bullet.x),
                                 bullet.char, curses.color_pair(bullet.color))
            except:
                pass

        # Draw explosions
        for explosion in self.explosions:
            try:
                self.pad.addstr(int(explosion.y), int(explosion.x),
                                 explosion.char, curses.color_pair(explosion.color))
            except:
                pass

        # Draw nuke visual effects
        if self.nuke_effect_timer > 0:
            # Flash the border
            flash_char = "█" if self.nuke_effect_timer % 2 == 0 else "▓"
            flash_color = 1 if self.nuke_effect_timer % 4 < 2 else 3

            # Top and bottom borders
            try:
                for x in range(1, self.width - 1):
                    if self.nuke_effect_timer > 10:  # First half of effect
                        self.pad.addstr(1, x, flash_char, curses.color_pair(flash_color) | curses.A_BOLD)
                        self.pad.addstr(self.height - 2, x, flash_char, curses.color_pair(flash_color) | curses.A_BOLD)
            except:
                pass

            # Side borders
            try:
                for y in range(1, self.height - 1):
                    if self.nuke_effect_timer > 10:  # First half of effect
                        self.pad.addstr(y, 1, flash_char, curses.color_pair(flash_color) | curses.A_BOLD)
                        self.pad.addstr(y, self.width - 2, flash_char, curses.color_pair(flash_color) | curses.A_BOLD)
            except:
                pass

            # Display "BA-BAAM!" text
            if self.nuke_effect_timer > 8:
                nuke_text = [
                    "██████╗  █████╗       ██████╗  █████╗  █████╗ ███╗   ███╗██╗",
                    "██╔══██╗██╔══██╗      ██╔══██╗██╔══██╗██╔══██╗████╗ ████║██║",
                    "██████╔╝███████║█████╗██████╔╝███████║███████║██╔████╔██║██║",
                    "██╔══██╗██╔══██║╚════╝██╔══██╗██╔══██║██╔══██║██║╚██╔╝██║╚═╝",
                    "██████╔╝██║  ██║      ██████╔╝██║  ██║██║  ██║██║ ╚═╝ ██║██╗",
                    "╚═════╝ ╚═╝  ╚═╝      ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝"
                ]

                start_y = max(2, (self.height - len(nuke_text)) // 2)
                for i, line in enumerate(nuke_text):
                    y = start_y + i
                    x = max(2, (self.width - len(line)) // 2)
                    if y < self.height - 1 and x + len(line) < self.width - 1:
                        try:
                            self.pad.addstr(y, x, line, curses.color_pair(1) | curses.A_BOLD)
                        except:
                            pass

        # Draw pause indicator
        # Draw PAUSED message only if paused and not showing a dialog
        if self.paused and not self.showing_dialog:
            pause_text = [
                "╔═══════════════════════════╗",
                "║                           ║",
                "║          PAUSED           ║",
                "║                           ║",
                "║     Press P to Resume     ║",
                "║                           ║",
                "╚═══════════════════════════╝"
            ]

            start_y = max(2, (self.height - len(pause_text)) // 2)
            for i, line in enumerate(pause_text):
                y = start_y + i
                x = max(2, (self.width - len(line)) // 2)
                if y < self.height - 1 and x + len(line) < self.width - 1:
                    try:
                        self.pad.addstr(y, x, line, curses.color_pair(3) | curses.A_BOLD)
                    except:
                        pass

        # Use double buffering: refresh pad to screen in one atomic operation
        # This eliminates flicker by avoiding intermediate partial screen states
        try:
            self.pad.noutrefresh(0, 0, 0, 0, self.height - 1, self.width - 1)
            curses.doupdate()
        except curses.error:
            # Terminal size changed - just skip this frame
            pass

    def _draw_colored_line(self, y, x, line, colored_element, color_pair):
        """Helper to draw a line with a specific element colored, keeping borders yellow"""
        try:
            # All lines have format: "║ content ║"
            # Draw left border in yellow
            self.stdscr.addstr(y, x, "║ ", curses.color_pair(3))

            # Extract content (everything between "║ " and " ║")
            content_start = 2  # After "║ "
            content_end = len(line) - 2  # Before " ║"
            content = line[content_start:content_end]

            if colored_element in content:
                idx = content.index(colored_element)
                # Draw prefix in normal color
                if idx > 0:
                    self.stdscr.addstr(y, x + content_start, content[:idx], curses.color_pair(4))
                # Draw colored element
                self.stdscr.addstr(y, x + content_start + idx, colored_element, curses.color_pair(color_pair))
                # Draw suffix in normal color
                if idx + len(colored_element) < len(content):
                    self.stdscr.addstr(y, x + content_start + idx + len(colored_element),
                                      content[idx + len(colored_element):], curses.color_pair(4))
            else:
                # Element not found, draw content normally
                self.stdscr.addstr(y, x + content_start, content, curses.color_pair(4))

            # Draw right border in yellow
            self.stdscr.addstr(y, x + len(line) - 2, " ║", curses.color_pair(3))
        except:
            pass

    def show_help(self):
        """Display mission briefing / help screen with scrolling"""
        self.stdscr.clear()
        self.stdscr.bkgd(' ', curses.color_pair(4))
        self.stdscr.nodelay(0)  # Blocking input for help screen

        # Calculate box width (minimum 80 columns)
        box_width = max(80, self.width)
        content_width = box_width - 4  # Account for borders and padding

        # Helper function to create a line with proper padding
        def make_line(text, center=False):
            if center:
                return f"║ {text.center(content_width)} ║"
            else:
                # Left-aligned with padding
                return f"║ {text.ljust(content_width)} ║"

        def make_empty():
            return make_line("")

        def make_border_top():
            return f"╔{'═' * (box_width - 2)}╗"

        def make_border_bottom():
            return f"╚{'═' * (box_width - 2)}╝"

        def make_separator():
            return f"╠{'═' * (box_width - 2)}╣"

        # Build briefing content dynamically
        briefing = []
        briefing.append(make_border_top())
        briefing.append(make_line("*** CLASSIFIED - EYES ONLY ***", center=True))
        briefing.append(make_empty())
        briefing.append(make_line("[Use ↑/↓ to scroll, any other key to return]", center=True))
        briefing.append(make_empty())
        briefing.append(make_line("FROM: Admiral Vex, Galactic Defense Command"))
        briefing.append(make_line("TO: Last surviving pilot, Defense Squadron Alpha"))
        briefing.append(make_line("RE: OPERATION FINAL STAND"))
        briefing.append(make_empty())
        briefing.append(make_separator())
        briefing.append(make_empty())
        briefing.append(make_line("SITUATION:"))
        briefing.append(make_line("The freight ship GENESIS carries an artifact of immense power - one that"))
        briefing.append(make_line("could bring lasting peace to our war-torn galaxy, or become the ultimate"))
        briefing.append(make_line("weapon in the wrong hands. Your entire squadron has been eliminated."))
        briefing.append(make_line("YOU are all that remains between the cargo and enemy forces."))
        briefing.append(make_empty())
        briefing.append(make_line("The initial enemy attack wave devastated our elite squadron. You managed"))
        briefing.append(make_line("to eliminate their first assault with a tactical nuke, but intel reports"))
        briefing.append(make_line("indicate they've INTENSIFIED their response. They've deployed their most"))
        briefing.append(make_line("advanced fleet - including Capital Warships (more commonly known among our"))
        briefing.append(make_line("personnel as 'The Boss')."))
        briefing.append(make_empty())
        briefing.append(make_line("Their numbers are overwhelming and they show complete disregard for life -"))
        briefing.append(make_line("both their own and others. They'll sacrifice everything to reach the cargo."))
        briefing.append(make_line("Command has authorized EXPERIMENTAL TECH: Energy Converters that can forge"))
        briefing.append(make_line("powerful enhancements from the residual energy of destroyed enemy fighters."))
        briefing.append(make_line("Every hostile you eliminate may yield tactical advantages. This is our"))
        briefing.append(make_line("only edge against their relentless swarm tactics."))
        briefing.append(make_empty())
        briefing.append(make_line("MISSION OBJECTIVE:"))
        briefing.append(make_line("Defend the GENESIS at all costs. DO NOT let hostile fighters breach"))
        briefing.append(make_line("your defensive line. The freight ship has no armaments and cannot"))
        briefing.append(make_line("withstand a prolonged attack. This is a fight to the last."))
        briefing.append(make_empty())
        briefing.append(make_line("Remember, the GENESIS crew's morale is directly linked to your condition."))
        briefing.append(make_line("When you take damage, their resolve weakens. If you fall, they abandon"))
        briefing.append(make_line("ship. Keep yourself alive to keep them fighting."))
        briefing.append(make_empty())
        briefing.append(make_separator())
        briefing.append(make_empty())
        briefing.append(make_line("ENEMY INTELLIGENCE:"))
        briefing.append(make_empty())
        briefing.append(make_line("╔► INTERCEPTOR (10 pts) - Standard fighter. Medium speed, light armor."))
        briefing.append(make_line("╚► Numerous but manageable."))
        briefing.append(make_empty())
        briefing.append(make_line("══► SCOUT (20 pts) - Fast attack craft. High speed, light armor."))
        briefing.append(make_line("    Difficult to target. Appears at higher threat levels."))
        briefing.append(make_empty())
        briefing.append(make_line("╔▓╗ HEAVY ASSAULT (30 pts) - Armored destroyer. Slow but heavily"))
        briefing.append(make_line("╚▓╝ shielded. Requires 10 direct hits. Elite threat."))
        briefing.append(make_empty())
        briefing.append(make_line("╱► VIPER (25 pts) - Tactical zigzag fighter. Unpredictable evasive"))
        briefing.append(make_line("╲► patterns. Light armor (3 hits, 1 plasma shot). High-value target."))
        briefing.append(make_empty())
        briefing.append(make_line("╔═╗ CAPITAL WARSHIP (200+ pts) - Command vessel. Massive armor reserves,"))
        briefing.append(make_line("║◈║ heavy weaponry. Returns fire with ricocheting projectiles. Appears"))
        briefing.append(make_line("╚═╝ after 30 kills, then every 50. WARNING: If this vessel reaches the"))
        briefing.append(make_line("    cargo ship, the mission is LOST. EXTREME DANGER."))
        briefing.append(make_empty())
        briefing.append(make_separator())
        briefing.append(make_empty())
        briefing.append(make_line("YOUR ARSENAL:"))
        briefing.append(make_empty())
        briefing.append(make_line("[1] PLASMA CANNON - Standard issue. Reliable, unlimited ammunition."))
        briefing.append(make_line("    Moderate fire rate. 3 DAMAGE per hit. Concentrated firepower."))
        briefing.append(make_empty())
        briefing.append(make_line("[2] SPREAD SHOT (W) - Triple-burst system. Fires three parallel shots."))
        briefing.append(make_line("    Each shot: 1 DAMAGE. Total: 3 DAMAGE. Area coverage. Field pickup."))
        briefing.append(make_empty())
        briefing.append(make_line("[3] ENERGY BEAM (E) - Continuous energy weapon. Extended range."))
        briefing.append(make_line("    Grows when STATIONARY with rapidly accelerating charge rate. Starts"))
        briefing.append(make_line("    at 15 units, accelerates dramatically (+3/+6/+9/+12). Side cannons"))
        briefing.append(make_line("    activate at max. WARNING: At FULL POWER, beams FLICKER immediately."))
        briefing.append(make_line("    3 seconds later, OVERHEAT SHUTDOWN. Must release trigger to reset."))
        briefing.append(make_line("    Use in bursts! Field pickup."))
        briefing.append(make_empty())
        briefing.append(make_line("FIELD ENHANCEMENTS:"))
        briefing.append(make_line("(R) Rapid Fire - Dramatically increased fire rate. Doubles energy beam"))
        briefing.append(make_line("    growth rate. (10 sec)"))
        briefing.append(make_line("(S) Shield - Complete damage immunity (12 sec) [RARE with Spread Shot]"))
        briefing.append(make_line("(+) Emergency Repair - Restores 1 HP. Can exceed standard capacity."))
        briefing.append(make_line("(N) TACTICAL NUKE - Destroys ALL hostiles. COSTS 1 HP. Use with caution."))
        briefing.append(make_line("(D) COMBAT DRONES - 3 autonomous allies. 8s each. [After 2nd boss victory]"))
        briefing.append(make_empty())
        briefing.append(make_separator())
        briefing.append(make_empty())
        briefing.append(make_line("FLIGHT CONTROLS:"))
        briefing.append(make_line("Arrow Keys - Directional maneuvering    Space - Fire weapons"))
        briefing.append(make_line("1/2/3 - Weapon select                   P - Pause/Resume"))
        briefing.append(make_line("ESC - Abort mission (return to base)"))
        briefing.append(make_empty())
        briefing.append(make_separator())
        briefing.append(make_empty())
        briefing.append(make_line("MEDALS OF HONOR:"))
        briefing.append(make_empty())
        briefing.append(make_line("For exceptional performance, Command may award the following medals at"))
        briefing.append(make_line("mission completion. Each medal carries 500 bonus points and eternal glory."))
        briefing.append(make_empty())
        briefing.append(make_line("Common criteria: Complete mission (no abort) and defeat second Capital"))
        briefing.append(make_line("Warship to prove sustained excellence under pressure."))
        briefing.append(make_empty())
        briefing.append(make_line("★ PERFECT DEFENSE - Zero hostile breaches. Not one enemy reaches the"))
        briefing.append(make_line("  GENESIS. Absolute defensive mastery."))
        briefing.append(make_empty())
        briefing.append(make_line("★ PLASMA PURIST - All weapon kills using Plasma Cannon only"))
        briefing.append(make_line("  No Spread Shot or Energy Beam allowed. Pure precision firepower."))
        briefing.append(make_line("  (drones/nukes/ramming OK)"))
        briefing.append(make_empty())
        briefing.append(make_line("★ SHARPSHOOTER - Combat accuracy exceeds 18%. Every shot counts. Minimal"))
        briefing.append(make_line("  waste. Maximum efficiency. (Plasma and Spread Shot only)"))
        briefing.append(make_empty())
        briefing.append(make_separator())
        briefing.append(make_empty())
        briefing.append(make_line("Remember, pilot: You're the last line of defense. The galaxy is counting"))
        briefing.append(make_line("on you. Make every shot count."))
        briefing.append(make_empty())
        briefing.append(make_line("PERSONAL NOTE FROM ADMIRAL VEX:", center=False))
        briefing.append(make_empty())
        briefing.append(make_line("I've lost too many good people today. The freight ship crew is terrified."))
        briefing.append(make_line("Command is breathing down my neck. And those bastards just keep coming."))
        briefing.append(make_line("I'm out of options, out of backup, and frankly, out of patience."))
        briefing.append(make_empty())
        briefing.append(make_line("So here's my order, pilot: Kill them. Kill them all."))
        briefing.append(make_empty())
        briefing.append(make_line("- Admiral Vex"))
        briefing.append(make_empty())
        briefing.append(make_border_bottom())

        scroll_offset = 0
        max_scroll = max(0, len(briefing) - (self.height - 2))  # Leave 2 lines for scroll indicators

        while True:
            self.stdscr.clear()

            # Calculate visible lines
            visible_height = self.height - 2  # Reserve top and bottom lines for scroll indicators
            start_line = scroll_offset
            end_line = min(start_line + visible_height, len(briefing))

            # Draw scroll indicator at top if there's content above
            if scroll_offset > 0:
                indicator = "▲ MORE ABOVE ▲"
                try:
                    self.stdscr.addstr(0, (self.width - len(indicator)) // 2, indicator,
                                      curses.color_pair(3) | curses.A_BOLD)
                except:
                    pass

            # Draw visible portion of briefing
            for i in range(start_line, end_line):
                line = briefing[i]
                y = 1 + (i - start_line)  # Start at row 1 (below scroll indicator)
                x = max(0, (self.width - len(line)) // 2)
                try:
                    # Check for lines with special colored elements
                    if "*** CLASSIFIED - EYES ONLY ***" in line:
                        # Draw line with red classified text, yellow borders
                        self.stdscr.addstr(y, x, "║ ", curses.color_pair(3))
                        content = line[2:-2]  # Extract content between borders
                        content_start = 2
                        idx = content.index("***")
                        prefix = content[:idx]
                        classified = "*** CLASSIFIED - EYES ONLY ***"
                        suffix = content[idx + len(classified):]
                        self.stdscr.addstr(y, x + content_start, prefix, curses.color_pair(4))
                        self.stdscr.addstr(y, x + content_start + len(prefix), classified, curses.color_pair(1) | curses.A_BOLD)
                        self.stdscr.addstr(y, x + content_start + len(prefix) + len(classified), suffix, curses.color_pair(4))
                        self.stdscr.addstr(y, x + len(line) - 2, " ║", curses.color_pair(3))
                    elif "Admiral Vex out" in line:
                        # Draw line with red Admiral Vex phrase, yellow borders
                        self.stdscr.addstr(y, x, "║ ", curses.color_pair(3))
                        content = line[2:-2]  # Extract content between borders
                        content_start = 2
                        idx = content.index("Admiral Vex out")
                        prefix = content[:idx]
                        admiral = "Admiral Vex out"
                        suffix = content[idx + len(admiral):]
                        self.stdscr.addstr(y, x + content_start, prefix, curses.color_pair(4))
                        self.stdscr.addstr(y, x + content_start + len(prefix), admiral, curses.color_pair(1) | curses.A_BOLD)
                        self.stdscr.addstr(y, x + content_start + len(prefix) + len(admiral), suffix, curses.color_pair(4))
                        self.stdscr.addstr(y, x + len(line) - 2, " ║", curses.color_pair(3))
                    elif "╔► INTERCEPTOR" in line:
                        # Normal enemy - color pair 1 (dusty orange)
                        self._draw_colored_line(y, x, line, "╔►", 1)
                    elif "╚► Numerous" in line:
                        self._draw_colored_line(y, x, line, "╚►", 1)
                    elif "══► SCOUT" in line:
                        # Fast enemy - color pair 1 (dusty orange)
                        self._draw_colored_line(y, x, line, "══►", 1)
                    elif "╔▓╗ HEAVY" in line:
                        # Tank enemy - color pair 7 (slate)
                        self._draw_colored_line(y, x, line, "╔▓╗", 7)
                    elif "╚▓╝ shielded" in line:
                        self._draw_colored_line(y, x, line, "╚▓╝", 7)
                    elif "╱► VIPER" in line:
                        # Zigzag enemy - color pair 8 (amber)
                        self._draw_colored_line(y, x, line, "╱►", 8)
                    elif "╲► patterns" in line:
                        self._draw_colored_line(y, x, line, "╲►", 8)
                    elif "╔═╗ CAPITAL" in line:
                        # Boss - color pair 9 (rust)
                        self._draw_colored_line(y, x, line, "╔═╗", 9)
                    elif "║◈║ heavy" in line:
                        self._draw_colored_line(y, x, line, "║◈║", 9)
                    elif "╚═╝ after" in line:
                        self._draw_colored_line(y, x, line, "╚═╝", 9)
                    elif "(R) Rapid Fire" in line:
                        # Rapid fire powerup - color pair 10 (dusty orange)
                        self._draw_colored_line(y, x, line, "(R)", 10)
                    elif "(S) Shield" in line:
                        # Shield powerup - color pair 11 (steel blue)
                        self._draw_colored_line(y, x, line, "(S)", 11)
                    elif "(+) Emergency" in line:
                        # Health powerup - color pair 12 (moss green)
                        self._draw_colored_line(y, x, line, "(+)", 12)
                    elif "(W)" in line:
                        # Spread powerup - color pair 13 (amber)
                        self._draw_colored_line(y, x, line, "(W)", 13)
                    elif "(E)" in line:
                        # Energy beam powerup - color pair 14 (dusty purple)
                        self._draw_colored_line(y, x, line, "(E)", 14)
                    elif "(N) TACTICAL NUKE" in line:
                        # Nuke powerup - color pair 15 (salmon)
                        self._draw_colored_line(y, x, line, "(N)", 15)
                    elif "(D) COMBAT DRONE" in line:
                        # Drone powerup - color pair 16 (pale cyan)
                        self._draw_colored_line(y, x, line, "(D)", 16)
                    elif "★ PERFECT DEFENSE" in line:
                        # Medal - color pair 11 (steel blue/cyan)
                        self._draw_colored_line(y, x, line, "★", 11)
                    elif "★ PLASMA PURIST" in line:
                        # Medal - color pair 11 (steel blue/cyan)
                        self._draw_colored_line(y, x, line, "★", 11)
                    elif "★ SHARPSHOOTER" in line:
                        # Medal - color pair 11 (steel blue/cyan)
                        self._draw_colored_line(y, x, line, "★", 11)
                    elif "╔" in line or "╚" in line or "╠" in line or "═" in line[:2] or "═" in line[-2:]:
                        # Border lines (top, bottom, separators) - all yellow
                        self.stdscr.addstr(y, x, line, curses.color_pair(3))
                    elif "SITUATION:" in line or "MISSION OBJECTIVE:" in line or "ENEMY INTELLIGENCE:" in line or "YOUR ARSENAL:" in line or "FLIGHT CONTROLS:" in line or "FIELD ENHANCEMENTS:" in line or "MEDALS OF HONOR:" in line:
                        # Section headers - yellow borders, bold yellow text
                        self.stdscr.addstr(y, x, "║ ", curses.color_pair(3))
                        content = line[2:-2]
                        self.stdscr.addstr(y, x + 2, content, curses.color_pair(3) | curses.A_BOLD)
                        self.stdscr.addstr(y, x + len(line) - 2, " ║", curses.color_pair(3))
                    else:
                        # Normal text lines - yellow borders, white text
                        self.stdscr.addstr(y, x, "║ ", curses.color_pair(3))
                        content = line[2:-2]
                        self.stdscr.addstr(y, x + 2, content, curses.color_pair(4))
                        self.stdscr.addstr(y, x + len(line) - 2, " ║", curses.color_pair(3))
                except:
                    pass

            # Draw scroll indicator at bottom if there's content below
            if scroll_offset < max_scroll:
                indicator = "▼ MORE BELOW ▼"
                try:
                    self.stdscr.addstr(self.height - 1, (self.width - len(indicator)) // 2, indicator,
                                      curses.color_pair(3) | curses.A_BOLD)
                except:
                    pass

            self.stdscr.refresh()

            # Handle input
            key = self.stdscr.getch()
            if key == curses.KEY_UP:
                scroll_offset = max(0, scroll_offset - 1)
            elif key == curses.KEY_DOWN:
                scroll_offset = min(max_scroll, scroll_offset + 1)
            elif key != -1:  # Any other key exits
                break

        self.stdscr.nodelay(1)  # Return to non-blocking for menu

    def show_intro(self):
        """Show cinematic pseudo-3D intro sequence before main menu"""
        # Clear screen thoroughly to remove any pygame init messages
        self.stdscr.clear()
        self.stdscr.refresh()
        self.stdscr.erase()
        self.stdscr.refresh()
        self.stdscr.nodelay(1)
        self.stdscr.timeout(0)

        fps = 30
        frame_time = 1.0 / fps

        # GENESIS position - FAR LEFT, large boxy ship
        genesis_base_width = 24
        genesis_base_height = 16
        genesis_base_x = 3  # Moved 2 columns left (from 5 to 3)
        genesis_base_center_y = self.height // 2 + 2  # Moved up 1 row (from +3 to +2)
        genesis_wobble_x = 0.0  # X wobble offset
        genesis_wobble_y = 0.0  # Y wobble offset
        genesis_wobble_phase = 0.0  # Wobble animation phase

        # Pseudo-3D: Y position determines depth (0=close, 1=far)
        # Scale objects based on depth for perspective effect
        def get_scale(depth):
            """Get scale factor based on depth (0.0=close, 1.0=far)"""
            return 1.0 - depth * 0.6  # Objects at far end are 40% of near size

        def depth_to_screen_y(depth, base_y):
            """Convert to screen Y position (simplified - no 3D scaling)"""
            # Use GENESIS center as reference point (including wobble)
            genesis_center_y = genesis_base_center_y + genesis_wobble_y
            # Simple 2D positioning - no scaling by depth
            return int(genesis_center_y + base_y)

        # Squadron in 3D space - positioned to the RIGHT of GENESIS with movement patterns
        # NOTE: Only 4 ships here - the hero is separate!
        # GENESIS is at x=3 with width=24, so rightmost edge is at x=27
        squadron = [
            {'x': 29, 'depth': 0.5, 'base_y_origin': -4, 'base_y': -4, 'alive': True, 'fire_timer': 10,
             'move_pattern': 'vertical', 'move_phase': 1.57, 'move_speed': 0.03},  # Left-top (closest to GENESIS)
            {'x': 29, 'depth': 0.5, 'base_y_origin': 4, 'base_y': 4, 'alive': True, 'fire_timer': 5,
             'move_pattern': 'vertical', 'move_phase': 4.71, 'move_speed': 0.03},    # Left-bottom (closest to GENESIS)
            {'x': 42, 'depth': 0.2, 'base_y_origin': -4, 'base_y': -4, 'alive': True, 'fire_timer': 0,
             'move_pattern': 'circle', 'move_phase': 0, 'move_speed': 0.05},   # Right-top (moved down from -6)
            {'x': 42, 'depth': 0.2, 'base_y_origin': 6, 'base_y': 6, 'alive': True, 'fire_timer': 15,
             'move_pattern': 'circle', 'move_phase': 3.14, 'move_speed': 0.05},   # Right-bottom
        ]

        # HERO SHIP - Separate from squadron, CANNOT be destroyed
        hero_ship = {
            'x': 32,
            'depth': 0.8,
            'base_y_origin': 0,
            'base_y': 0,
            'move_pattern': 'hover',
            'move_phase': 3.14,
            'move_speed': 0.02
        }

        # Enemy waves, bullets, and debris
        enemies = []
        explosions = []
        squadron_bullets = []
        ship_debris_list = []  # Debris from destroyed squadron ships
        next_enemy_spawn = 120  # Start spawning after 4 seconds

        # Generate scrolling starfield
        intro_stars = self._generate_menu_starfield()

        # Animation phases
        phase = 0  # 0: calm, 1: light attack, 2: heavy attack, 3: final stand, 4: hero nuke
        phase_timer = 0
        frame = 0
        enemies_destroyed_by_squadron = 0
        nuke_triggered = False
        nuke_flash_timer = 0
        hero_nuke_screen_x = 0
        hero_nuke_screen_y = 0
        hero_nuke_depth = 0
        skipped = False  # Track if user skipped the intro
        fade_out = False  # Track if we're fading out
        fade_timer = 0  # Timer for fade out effect
        fade_duration = 45  # 1.5 seconds for faster fade
        blanked_positions = set()  # Positions that have been permanently blanked
        total_positions = self.width * self.height  # Total screen positions
        squadron_wiped_out = False  # Track when all squadron ships are destroyed

        # Start ominous drone
        self.synth.start_intro_drone()

        while True:
            start_time = time.time()
            frame += 1
            phase_timer += 1

            # Check for skip (SPACE only - ESC has issues with key detection)
            if not fade_out:
                try:
                    key = self.stdscr.getch()
                    if key == ord(' '):
                        skipped = True
                        fade_out = True
                        fade_timer = 0
                        # Pre-seed some black positions for instant visual feedback
                        for _ in range(500):
                            blanked_positions.add((random.randint(0, self.width - 1), random.randint(0, self.height - 1)))
                except:
                    pass

            # Update starfield
            self._update_menu_starfield(intro_stars)

            # Update GENESIS wobble to show movement
            genesis_wobble_phase += 0.02
            genesis_wobble_x = math.sin(genesis_wobble_phase * 1.3) * 0.5
            genesis_wobble_y = math.cos(genesis_wobble_phase * 0.9) * 0.3

            # Phase transitions and enemy spawning
            if phase == 0 and phase_timer > 210:  # 7 seconds calm - let player take in the scene
                phase = 1
                phase_timer = 0
            elif phase == 1 and phase_timer > 180:  # 6 seconds light attack
                phase = 2
                phase_timer = 0
            elif phase == 2 and phase_timer > 210:  # 7 seconds heavy attack
                phase = 3
                phase_timer = 0
            elif phase == 3:
                # Phase 3: Continue until all squadron ships are destroyed (only hero remains)
                alive_count = sum(1 for s in squadron if s['alive'])

                # Force kill remaining ships after 6 seconds if they're still alive
                if alive_count > 0 and phase_timer > 180:  # 6 seconds
                    any_killed = False  # Track if any ships were killed
                    for ship in squadron:
                        if ship['alive']:
                            any_killed = True
                            # Create explosions for forced deaths
                            for _ in range(5):
                                ex = ship['x'] + random.uniform(-1, 1)
                                eby = ship['base_y'] + random.uniform(-1, 1)
                                explosions.append({
                                    'x': ex,
                                    'depth': ship['depth'],
                                    'base_y': eby,
                                    'lifetime': 18
                                })

                            # Create debris spreading from ship
                            for _ in range(15):
                                angle = random.uniform(0, 2 * math.pi)
                                speed = random.uniform(0.3, 1.2)
                                vx = speed * math.cos(angle)
                                vy = speed * math.sin(angle)
                                ship_debris_list.append({
                                    'x': ship['x'],
                                    'depth': ship['depth'],
                                    'base_y': ship['base_y'],
                                    'vx': vx,
                                    'vy': vy,
                                    'char': random.choice(["█", "▓", "▒", "░", "■", "▪", "●", "◆"]),
                                    'color': random.choice([1, 3, 4, 10]),
                                    'lifetime': 45
                                })

                            ship['alive'] = False

                    # Play single explosion sound for all force-killed ships
                    if any_killed:
                        self.synth.play('squadron_explosion')

                    # Recalculate alive count after force-killing
                    alive_count = sum(1 for s in squadron if s['alive'])

                # Check if all squadron ships just died - reset timer for grace period
                if alive_count == 0 and not squadron_wiped_out:
                    squadron_wiped_out = True
                    phase_timer = 0  # Reset timer to start 2-second grace period

                # Don't transition to nuke until ALL squadron ships are destroyed
                # Wait until all are dead, then wait 60 frames (2 seconds) before nuke
                if squadron_wiped_out and phase_timer > 60:
                    phase = 4
                    phase_timer = 0
                    # Save hero position NOW (at start of phase 4) so it's frozen during arming
                    hero_nuke_screen_y = depth_to_screen_y(hero_ship['depth'], hero_ship['base_y'])
                    hero_nuke_screen_x = int(hero_ship['x'])
                    hero_nuke_depth = hero_ship['depth']
            elif phase == 4:
                # Phase 4: Hero nuke sequence
                # Wait 2 seconds (60 frames) after showing "Arming tactical nuke" message before triggering
                if not nuke_triggered and phase_timer > 60:
                    # Trigger nuke (2 seconds after arming message)
                    nuke_triggered = True
                    nuke_flash_timer = 30  # 1 second flash
                    # Force nuke sound to play on an available channel (stop other sounds if needed)
                    nuke_channel = pygame.mixer.find_channel(True)  # True = force a channel to be available
                    if nuke_channel:
                        nuke_channel.play(self.synth.sounds['nuke'])

                    # Add echoes to the nuke sound - each one octave lower
                    def play_echo(delay, sound_name, volume):
                        def play():
                            time.sleep(delay)
                            echo = self.synth.sounds[sound_name]
                            echo.set_volume(volume)
                            echo.play()
                        threading.Thread(target=play, daemon=True).start()

                    # Schedule three echoes at decreasing volumes and pitches (one octave down each)
                    play_echo(0.3, 'nuke_echo_1', 0.5)   # First echo - one octave down at 50% volume after 0.3s
                    play_echo(0.6, 'nuke_echo_2', 0.25)  # Second echo - two octaves down at 25% volume after 0.6s
                    play_echo(0.9, 'nuke_echo_3', 0.12)  # Third echo - three octaves down at 12% volume after 0.9s

                    # Hero position was already saved at start of phase 4

                    # Destroy all enemies with explosions
                    for enemy in enemies[:]:
                        explosions.append({
                            'x': enemy['x'],
                            'depth': enemy['depth'],
                            'base_y': enemy['base_y'],
                            'lifetime': 25
                        })
                    enemies.clear()

                # End scene after nuke animation - start fade out
                # Wait 3 seconds after nuke fires (nuke fires at 90, so fade at 180)
                if nuke_triggered and phase_timer > 180 and not fade_out:  # 3 seconds to see the glory
                    fade_out = True
                    fade_timer = 0
                    phase = 5  # Move to phase 5 to prevent phase 4 logic from continuing

            # Spawn enemies in waves (MANY MORE) - but stop when nuke is triggered
            if frame >= next_enemy_spawn and phase >= 1 and (phase < 4 or (phase == 4 and not nuke_triggered)):
                # Spawn multiple enemies at different depths
                if phase == 1:
                    # Light attack - 2-3 enemies
                    spawn_count = random.randint(2, 3)
                    next_enemy_spawn = frame + random.randint(45, 75)
                elif phase == 2:
                    # Heavy attack - 4-6 enemies
                    spawn_count = random.randint(4, 6)
                    next_enemy_spawn = frame + random.randint(30, 50)
                else:
                    # Final overwhelming assault - 6-10 enemies
                    spawn_count = random.randint(6, 10)
                    next_enemy_spawn = frame + random.randint(20, 35)

                for _ in range(spawn_count):
                    depth = random.uniform(0.1, 0.9)
                    base_y = random.randint(-8, 8)
                    enemies.append({
                        'x': self.width - 5,
                        'depth': depth,
                        'base_y': base_y,
                        'speed': 0.3 + random.uniform(0, 0.2),
                        'health': 1
                    })

            # Update squadron ship movements
            for ship in squadron:
                if ship['alive']:
                    # Update movement phase
                    ship['move_phase'] += ship['move_speed']

                    # Calculate position based on pattern (oscillate around origin)
                    if ship['move_pattern'] == 'circle':
                        # Circular patrol pattern
                        ship['base_y'] = ship['base_y_origin'] + math.sin(ship['move_phase']) * 3.0
                    elif ship['move_pattern'] == 'vertical':
                        # Up and down
                        ship['base_y'] = ship['base_y_origin'] + math.sin(ship['move_phase']) * 2.0
                    elif ship['move_pattern'] == 'hover':
                        # Small hovering motion
                        ship['base_y'] = ship['base_y_origin'] + math.sin(ship['move_phase']) * 1.0

            # Update HERO ship movement (always, never dies)
            # But freeze hero position during phase 4 (nuke sequence)
            if phase < 4:
                hero_ship['move_phase'] += hero_ship['move_speed']
                hero_ship['base_y'] = hero_ship['base_y_origin'] + math.sin(hero_ship['move_phase']) * 1.0  # Hover pattern

            # Squadron shoots back
            for ship in squadron:
                if ship['alive'] and phase >= 1:
                    ship['fire_timer'] -= 1
                    if ship['fire_timer'] <= 0:
                        # Fire at nearest enemy at similar depth
                        ship_y = depth_to_screen_y(ship['depth'], ship['base_y'])
                        nearest_enemy = None
                        min_dist = float('inf')

                        for enemy in enemies:
                            enemy_y = depth_to_screen_y(enemy['depth'], enemy['base_y'])
                            depth_diff = abs(ship['depth'] - enemy['depth'])
                            y_diff = abs(ship_y - enemy_y)
                            dist = depth_diff * 20 + y_diff

                            if dist < min_dist and enemy['x'] > ship['x']:
                                min_dist = dist
                                nearest_enemy = enemy

                        if nearest_enemy:
                            squadron_bullets.append({
                                'x': ship['x'] + 3,
                                'depth': ship['depth'],
                                'base_y': ship['base_y'],
                                'target': nearest_enemy
                            })
                            self.synth.play('intro_shoot')

                        ship['fire_timer'] = random.randint(10, 20)  # Faster fire rate

            # Update squadron bullets
            for bullet in squadron_bullets[:]:
                bullet['x'] += 1.5
                should_remove = False

                # Check collision with target
                if bullet['target'] in enemies:
                    target = bullet['target']
                    bullet_y = depth_to_screen_y(bullet['depth'], bullet['base_y'])
                    target_y = depth_to_screen_y(target['depth'], target['base_y'])

                    if abs(bullet['x'] - target['x']) < 2 and abs(bullet_y - target_y) < 2:
                        target['health'] -= 1
                        should_remove = True

                        if target['health'] <= 0:
                            enemies.remove(target)
                            explosions.append({
                                'x': target['x'],
                                'depth': target['depth'],
                                'base_y': target['base_y'],
                                'lifetime': 12
                            })
                            self.synth.play('intro_explosion')
                            enemies_destroyed_by_squadron += 1
                else:
                    # Target destroyed by another bullet
                    should_remove = True

                # Remove if off screen
                if bullet['x'] > self.width:
                    should_remove = True

                # Remove bullet if needed
                if should_remove and bullet in squadron_bullets:
                    squadron_bullets.remove(bullet)

            # Update enemies
            for enemy in enemies[:]:
                enemy['x'] -= enemy['speed']

                # Check collision with squadron ships
                for ship in squadron:
                    if ship['alive']:
                        enemy_y = depth_to_screen_y(enemy['depth'], enemy['base_y'])
                        ship_y = depth_to_screen_y(ship['depth'], ship['base_y'])
                        depth_match = abs(enemy['depth'] - ship['depth']) < 0.15

                        if depth_match and abs(enemy['x'] - ship['x']) < 3 and abs(enemy_y - ship_y) < 2:
                            # Destroy squadron ship with debris explosion
                            ship['alive'] = False
                            if enemy in enemies:
                                enemies.remove(enemy)

                            # Create large explosions
                            for _ in range(5):
                                ex = ship['x'] + random.uniform(-1, 1)
                                eby = ship['base_y'] + random.uniform(-1, 1)
                                explosions.append({
                                    'x': ex,
                                    'depth': ship['depth'],
                                    'base_y': eby,
                                    'lifetime': 18
                                })

                            # Create debris spreading from ship
                            for _ in range(15):
                                angle = random.uniform(0, 2 * math.pi)
                                speed = random.uniform(0.3, 1.2)
                                vx = speed * math.cos(angle)
                                vy = speed * math.sin(angle)
                                ship_debris_list.append({
                                    'x': ship['x'],
                                    'depth': ship['depth'],
                                    'base_y': ship['base_y'],
                                    'vx': vx,
                                    'vy': vy,
                                    'char': random.choice(["█", "▓", "▒", "░", "■", "▪", "●", "◆"]),
                                    'color': random.choice([1, 3, 4, 10]),
                                    'lifetime': 45
                                })

                            self.synth.play('squadron_explosion')  # Squadron ship explosion
                            break

                # Check collision with HERO ship - enemies just pass through harmlessly
                hero_enemy_y = depth_to_screen_y(enemy['depth'], enemy['base_y'])
                hero_ship_y = depth_to_screen_y(hero_ship['depth'], hero_ship['base_y'])
                hero_depth_match = abs(enemy['depth'] - hero_ship['depth']) < 0.15

                if hero_depth_match and abs(enemy['x'] - hero_ship['x']) < 3 and abs(hero_enemy_y - hero_ship_y) < 2:
                    # Enemy destroyed by hero (hero cannot be harmed!)
                    explosions.append({
                        'x': enemy['x'],
                        'depth': enemy['depth'],
                        'base_y': enemy['base_y'],
                        'lifetime': 8
                    })
                    if enemy in enemies:
                        enemies.remove(enemy)

                # Check collision with GENESIS (enemy hits the freight ship)
                genesis_x = genesis_base_x + genesis_wobble_x
                genesis_right = genesis_x + genesis_base_width

                if enemy['x'] <= genesis_right and enemy['x'] >= genesis_x:
                    # Enemy hit GENESIS - explode the enemy
                    explosions.append({
                        'x': enemy['x'],
                        'depth': enemy['depth'],
                        'base_y': enemy['base_y'],
                        'lifetime': 10
                    })
                    if enemy in enemies:
                        enemies.remove(enemy)
                    self.synth.play('intro_explosion')

                # Remove if off screen (enemy broke through)
                if enemy['x'] < 0:
                    enemies.remove(enemy)

            # Update explosions
            for explosion in explosions[:]:
                explosion['lifetime'] -= 1
                if explosion['lifetime'] <= 0:
                    explosions.remove(explosion)

            # Update nuke flash
            if nuke_flash_timer > 0:
                nuke_flash_timer -= 1

            # Update ship debris
            for debris in ship_debris_list[:]:
                debris['x'] += debris['vx']
                debris['base_y'] += debris['vy']
                debris['vy'] += 0.03  # Gravity
                debris['lifetime'] -= 1

                # Remove if lifetime expired or off screen
                screen_y = depth_to_screen_y(debris['depth'], debris['base_y'])
                if debris['lifetime'] <= 0 or debris['x'] < 0 or debris['x'] >= self.width or screen_y < 0 or screen_y >= self.height:
                    ship_debris_list.remove(debris)

            # Draw
            self.stdscr.erase()

            # Draw starfield
            for star in intro_stars:
                try:
                    x = int(star['x'])
                    y = int(star['y'])
                    if 0 <= x < self.width and 0 <= y < self.height:
                        attr = curses.color_pair(star['color'])
                        if star['bold']:
                            attr |= curses.A_BOLD
                        self.stdscr.addstr(y, x, star['char'], attr)
                except:
                    pass

            # Draw GENESIS freight ship - FAR LEFT, large boxy container with wobble
            try:
                # Apply wobble to position
                genesis_x = int(genesis_base_x + genesis_wobble_x)
                genesis_center_y = int(genesis_base_center_y + genesis_wobble_y)

                wall_patterns = ["▓", "▒", "░", "█"]

                # Top and bottom borders
                top_border = "╔" + "═" * (genesis_base_width - 2) + "╗"
                bottom_border = "╚" + "═" * (genesis_base_width - 2) + "╝"

                y_start = genesis_center_y - genesis_base_height // 2
                self.stdscr.addstr(y_start, genesis_x, top_border, curses.color_pair(5))
                self.stdscr.addstr(y_start + genesis_base_height - 1, genesis_x, bottom_border, curses.color_pair(5))

                # Walls with texture (SAME as in-game wall)
                for row in range(1, genesis_base_height - 1):
                    y = y_start + row
                    pattern_idx = (row % 4)
                    if row % 3 == 0:
                        char = "║"
                        color = 5
                    elif row % 7 == 0:
                        char = "●"
                        color = 4
                    else:
                        char = wall_patterns[pattern_idx]
                        color = 7

                    # Left and right walls
                    self.stdscr.addstr(y, genesis_x, char, curses.color_pair(color))
                    self.stdscr.addstr(y, genesis_x + genesis_base_width - 1, char, curses.color_pair(color))

                    # Interior
                    interior = "░" * (genesis_base_width - 2)
                    self.stdscr.addstr(y, genesis_x + 1, interior, curses.color_pair(7))

                # Large "G" logo with "CARGO" text below
                # Large "G" (5 rows high, 8 chars wide)
                large_g = [
                    " █████ ",
                    "███    ",
                    "███ ███",
                    "███ ███",
                    " █████ "
                ]

                # Draw large G centered
                g_start_y = genesis_center_y - 3
                g_start_x = genesis_x + (genesis_base_width - 8) // 2

                for i, line in enumerate(large_g):
                    self.stdscr.addstr(g_start_y + i, g_start_x, line, curses.color_pair(1) | curses.A_BOLD)

                # Draw "CARGO" text below the G
                cargo_text = "CARGO"
                cargo_y = g_start_y + 5
                cargo_x = genesis_x + (genesis_base_width - len(cargo_text)) // 2
                self.stdscr.addstr(cargo_y, cargo_x, cargo_text, curses.color_pair(1) | curses.A_BOLD)
            except:
                pass

            # Draw squadron ships (always full size)
            ship_sprite = ["╱█►", "██►", "╲█►"]

            # Sort squadron by depth (far to near) for proper z-ordering
            squadron_sorted = sorted(squadron, key=lambda s: s['depth'], reverse=True)

            for ship in squadron_sorted:
                if ship['alive']:
                    try:
                        screen_y = depth_to_screen_y(ship['depth'], ship['base_y'])

                        # Ensure squadron ships stay on screen (don't go too low - moved up 2 rows)
                        screen_y = max(1, min(screen_y, self.height - 6))

                        # Normal squadron ships are cyan
                        attr = curses.color_pair(2)

                        for j, line in enumerate(ship_sprite):
                            self.stdscr.addstr(screen_y + j, int(ship['x']), line, attr)
                    except:
                        pass

            # Draw squadron bullets (always full size)
            for bullet in squadron_bullets:
                try:
                    screen_y = depth_to_screen_y(bullet['depth'], bullet['base_y'])
                    self.stdscr.addstr(screen_y, int(bullet['x']), "─", curses.color_pair(3))
                except:
                    pass

            # Draw enemies (always full size)
            enemy_sprite = ["╔►", "╚►"]

            # Sort by depth
            enemies_sorted = sorted(enemies, key=lambda e: e['depth'], reverse=True)

            for enemy in enemies_sorted:
                try:
                    screen_y = depth_to_screen_y(enemy['depth'], enemy['base_y'])

                    for j, line in enumerate(enemy_sprite):
                        self.stdscr.addstr(screen_y + j, int(enemy['x']), line, curses.color_pair(1))
                except:
                    pass

            # Draw explosions (always full size)
            explosion_chars = ["*", "✦", "✧", "○"]
            explosions_sorted = sorted(explosions, key=lambda e: e['depth'], reverse=True)
            for explosion in explosions_sorted:
                try:
                    screen_y = depth_to_screen_y(explosion['depth'], explosion['base_y'])
                    char = random.choice(explosion_chars)
                    self.stdscr.addstr(screen_y, int(explosion['x']), char, curses.color_pair(4))
                except:
                    pass

            # Nuke flash effect - draw red flashes across screen (BEFORE hero ship so it doesn't cover it)
            if nuke_flash_timer > 0 and nuke_flash_timer % 4 < 2:
                # Draw random red characters for flash effect (reduced density to not cover hero ship)
                for _ in range(int(self.width * self.height * 0.05)):  # Reduced from 0.15 to 0.05
                    try:
                        fx = random.randint(0, self.width - 1)
                        fy = random.randint(0, self.height - 1)
                        # Don't draw flash near hero ship position
                        hero_y = depth_to_screen_y(hero_ship['depth'], hero_ship['base_y'])
                        if not (abs(fx - hero_ship['x']) < 5 and abs(fy - hero_y) < 4):
                            self.stdscr.addstr(fy, fx, "█", curses.color_pair(1) | curses.A_BOLD)
                    except:
                        pass

            # Draw ship debris (always full size)
            debris_sorted = sorted(ship_debris_list, key=lambda d: d['depth'], reverse=True)
            for debris in debris_sorted:
                try:
                    screen_y = depth_to_screen_y(debris['depth'], debris['base_y'])

                    # Fade debris in final frames
                    attr = curses.color_pair(debris['color'])
                    if debris['lifetime'] > 15:
                        attr |= curses.A_BOLD

                    self.stdscr.addstr(screen_y, int(debris['x']), debris['char'], attr)
                except:
                    pass

            # Draw HERO ship ON TOP (ALWAYS rendered, CANNOT be destroyed, always full size)
            # Drawn last so nothing can cover it!
            hero_sprite = ["╱█►", "██►", "╲█►"]

            # During phase 4 (nuke), use frozen SCREEN position from moment of nuke
            if phase >= 4:
                # Use saved screen coordinates (already calculated at moment of nuke)
                hero_screen_y = hero_nuke_screen_y
                hero_x = hero_nuke_screen_x

                # Ensure position is on screen (bounds check - moved up 2 rows)
                hero_screen_y = max(1, min(hero_screen_y, self.height - 6))
                hero_x = max(1, min(hero_x, self.width - 5))

                # Red during flash, cyan (blue) after
                if nuke_flash_timer > 0:
                    hero_attr = curses.color_pair(1) | curses.A_BOLD  # Red during flash
                else:
                    hero_attr = curses.color_pair(2) | curses.A_BOLD  # Cyan (blue) after flash
            else:
                hero_screen_y = depth_to_screen_y(hero_ship['depth'], hero_ship['base_y'])

                # Ensure hero ship stays on screen (moved up 2 rows)
                hero_screen_y = max(1, min(hero_screen_y, self.height - 6))
                hero_x = max(1, min(int(hero_ship['x']), self.width - 5))

                # Hero ship always cyan (blue) - never changes color
                hero_attr = curses.color_pair(2)

            # ALWAYS draw hero ship - NO exceptions allowed!
            for j, line in enumerate(hero_sprite):
                self.stdscr.addstr(hero_screen_y + j, hero_x, line, hero_attr)

            # Draw text overlays
            try:
                squadron_alive = sum(1 for s in squadron if s['alive'])
                total_alive = squadron_alive + 1  # +1 for hero ship (always alive)

                if phase == 0:
                    text = "Freight Ship GENESIS - Deep Space Transit"
                    self.stdscr.addstr(2, (self.width - len(text)) // 2, text, curses.color_pair(3))
                    text2 = "Defense Squadron Alpha - Standard Patrol"
                    self.stdscr.addstr(4, (self.width - len(text2)) // 2, text2, curses.color_pair(5))
                elif phase == 1:
                    text = "CONTACT - Hostiles Inbound"
                    self.stdscr.addstr(2, (self.width - len(text)) // 2, text, curses.color_pair(3) | curses.A_BOLD)
                elif phase == 2:
                    text = "UNDER HEAVY ATTACK!"
                    self.stdscr.addstr(2, (self.width - len(text)) // 2, text, curses.color_pair(1) | curses.A_BOLD)
                    text2 = f"Squadron Status: {total_alive}/5 fighters operational"
                    self.stdscr.addstr(4, (self.width - len(text2)) // 2, text2, curses.color_pair(4))
                elif phase == 3:
                    if squadron_alive == 0:
                        text = "LAST PILOT STANDING"
                        self.stdscr.addstr(2, (self.width - len(text)) // 2, text, curses.color_pair(3) | curses.A_BOLD)
                        text2 = "Arming tactical nuke... This is the only way..."
                        self.stdscr.addstr(4, (self.width - len(text2)) // 2, text2, curses.color_pair(4))
                    else:
                        text = "THEY'RE OVERWHELMING US!"
                        self.stdscr.addstr(2, (self.width - len(text)) // 2, text, curses.color_pair(1) | curses.A_BOLD)
                        text2 = f"Squadron Status: {total_alive}/5 fighters operational"
                        self.stdscr.addstr(4, (self.width - len(text2)) // 2, text2, curses.color_pair(4))
                elif phase == 4:
                    if nuke_triggered:
                        # After nuke fires - show BA-BAAM!
                        text = "TACTICAL NUKE DEPLOYED!"
                        self.stdscr.addstr(2, (self.width - len(text)) // 2, text, curses.color_pair(1) | curses.A_BOLD)
                        text2 = "BA-BAAM!"
                        self.stdscr.addstr(4, (self.width - len(text2)) // 2, text2, curses.color_pair(3) | curses.A_BOLD)
                    else:
                        # Before nuke fires - show arming message
                        text = "ALL FIGHTERS DOWN!"
                        self.stdscr.addstr(2, (self.width - len(text)) // 2, text, curses.color_pair(1) | curses.A_BOLD)
                        text2 = "Arming tactical nuke... This is the only way..."
                        self.stdscr.addstr(4, (self.width - len(text2)) // 2, text2, curses.color_pair(4))

                # Skip hint
                skip_text = "[SPACE to skip]"
                self.stdscr.addstr(self.height - 2, (self.width - len(skip_text)) // 2, skip_text, curses.color_pair(4))
            except:
                pass

            # Handle fade out effect - draw black curtain sweeping down
            if fade_out:
                fade_timer += 1
                # Calculate fade progress (0.0 to 1.0)
                fade_progress = min(1.0, fade_timer / fade_duration)

                # Fade out intro drone volume
                if self.synth.intro_drone_channel:
                    self.synth.intro_drone_channel.set_volume(0.4 * (1.0 - fade_progress))

                # Accumulating fade: add more black positions each frame
                # Use accelerated curve for faster fade
                visual_progress = fade_progress ** 0.5  # More aggressive acceleration
                target_blanked = int(visual_progress * total_positions)

                # Add new random positions to the blanked set
                positions_to_add = target_blanked - len(blanked_positions)
                if positions_to_add > 0:
                    # Generate random positions - much faster approach
                    # Try to add requested amount, but don't loop forever
                    for _ in range(min(positions_to_add * 3, 1000)):  # Cap attempts
                        x = random.randint(0, self.width - 1)
                        y = random.randint(0, self.height - 1)
                        pos = (x, y)
                        if pos not in blanked_positions:
                            blanked_positions.add(pos)
                            if len(blanked_positions) >= target_blanked:
                                break

                # Draw ALL blanked positions to prevent flicker from animation
                for x, y in blanked_positions:
                    try:
                        self.stdscr.addstr(y, x, " ", curses.color_pair(4))
                    except:
                        pass

                # Stop all sounds and exit when fade complete
                if fade_timer >= fade_duration:
                    # Final cleanup: ensure entire screen is black
                    self.stdscr.erase()
                    self.stdscr.refresh()
                    self.synth.stop_intro_drone()
                    pygame.mixer.stop()  # Stop all intro sounds
                    break

            self.stdscr.refresh()

            # Maintain frame rate
            elapsed = time.time() - start_time
            sleep_time = frame_time - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        # Ensure intro drone is stopped (may have already stopped during fade)
        self.synth.stop_intro_drone()
        pygame.mixer.stop()  # Stop all sounds

        # Brief transition pause
        time.sleep(0.5)

    def show_main_menu(self) -> bool:
        """Display animated main menu with scrolling starfield. Returns True to start game, False to quit."""
        # Reload high scores to get latest
        self.high_scores = self.load_high_scores()

        self.stdscr.clear()
        self.stdscr.bkgd(' ', curses.color_pair(4))  # Set white on black for menu
        self.stdscr.nodelay(1)  # Non-blocking input
        self.stdscr.timeout(0)

        # Start background music
        self.synth.start_menu_music()

        # Generate menu starfield
        menu_stars = self._generate_menu_starfield()

        # Animation state
        frame_count = 0
        fps = 30
        frame_time = 1.0 / fps

        # Title
        title = [
            "██████╗  █████╗       ██████╗  █████╗  █████╗ ███╗   ███╗██╗",
            "██╔══██╗██╔══██╗      ██╔══██╗██╔══██╗██╔══██╗████╗ ████║██║",
            "██████╔╝███████║█████╗██████╔╝███████║███████║██╔████╔██║██║",
            "██╔══██╗██╔══██║╚════╝██╔══██╗██╔══██║██╔══██║██║╚██╔╝██║╚═╝",
            "██████╔╝██║  ██║      ██████╔╝██║  ██║██║  ██║██║ ╚═╝ ██║██╗",
            "╚═════╝ ╚═╝  ╚═╝      ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝"
        ]

        # Animation loop
        while True:
            start_time = time.time()

            # Clear screen
            self.stdscr.erase()

            # Update starfield
            self._update_menu_starfield(menu_stars)

            # Draw starfield
            for star in menu_stars:
                try:
                    x = int(star['x'])
                    y = int(star['y'])
                    if 1 <= x < self.width - 1 and 1 <= y < self.height - 1:
                        attr = curses.color_pair(star['color'])
                        if star['bold']:
                            attr |= curses.A_BOLD
                        self.stdscr.addstr(y, x, star['char'], attr)
                except:
                    pass

            # Draw title with periodic golden shimmer effect (35-degree diagonal)
            title_y = 3
            shimmer_width = 15  # Width of the shimmer wave

            # Shimmer cycle: 4 seconds pause, 6 seconds active = 10 second total cycle
            # At 30 FPS: 120 frames pause, 180 frames active, 300 frames total
            cycle_length = 300  # 10 seconds
            pause_duration = 120  # 4 seconds
            shimmer_duration = 180  # 6 seconds
            cycle_position = frame_count % cycle_length

            # Only show shimmer after pause period (starts with solid red)
            shimmer_active = cycle_position >= pause_duration

            for i, line in enumerate(title):
                y = title_y + i
                x_start = max(1, (self.width - len(line)) // 2)
                if y < self.height - 1 and x_start + len(line) < self.width - 1:
                    try:
                        if shimmer_active:
                            # Shimmer is active - calculate shimmer position
                            # Use time within shimmer period (cycle_position - pause_duration)
                            shimmer_time = cycle_position - pause_duration
                            shimmer_base_pos = (shimmer_time * 0.5) % (len(title[0]) + shimmer_width * 2)

                            # Apply diagonal offset for 35-degree rotation
                            diagonal_offset = i * 4  # 4 chars per row for visible diagonal effect
                            shimmer_pos = shimmer_base_pos + diagonal_offset

                            # Draw each character individually with shimmer effect
                            for char_idx, char in enumerate(line):
                                x = x_start + char_idx
                                # Calculate distance from shimmer center
                                distance_from_shimmer = abs(char_idx - (shimmer_pos - shimmer_width))

                                # Determine color based on position in shimmer wave
                                if distance_from_shimmer < shimmer_width:
                                    # Inside shimmer wave - use gradient from red to yellow to red
                                    intensity = 1.0 - (distance_from_shimmer / shimmer_width)
                                    if intensity > 0.7:
                                        # Center of shimmer - bright yellow/gold
                                        attr = curses.color_pair(3) | curses.A_BOLD  # Yellow
                                    elif intensity > 0.3:
                                        # Mid shimmer - yellow
                                        attr = curses.color_pair(3)  # Yellow, not bold
                                    else:
                                        # Edge of shimmer - red bold
                                        attr = curses.color_pair(1) | curses.A_BOLD  # Red
                                else:
                                    # Outside shimmer - normal red
                                    attr = curses.color_pair(1) | curses.A_BOLD  # Red

                                self.stdscr.addstr(y, x, char, attr)
                        else:
                            # Shimmer is paused - draw title in normal red
                            self.stdscr.addstr(y, x_start, line, curses.color_pair(1) | curses.A_BOLD)
                    except:
                        pass

            # Positioning relative to logo and terminal height
            # Logo is 6 lines tall, starts at title_y (3), so ends at row 8
            logo_bottom_y = title_y + len(title) - 1  # Row 8

            # Tagline: immediately below logo (no empty row)
            tagline_y = logo_bottom_y + 1  # Row 9
            tagline = "Kill them. Kill them all."

            # High scores: positioned below tagline (3 rows below for spacing)
            header_y = tagline_y + 3

            # Menu options: 2 rows above bottom (so visible)
            bottom_y = self.height - 3  # At height 24, this is row 21 (rows 22-23 are empty)

            # Draw tagline with independent shimmer effect
            # Separate cycle: 2.5 seconds pause, 3 seconds shimmer = 5.5 second cycle
            tagline_cycle_length = 165  # 5.5 seconds at 30 FPS
            tagline_pause = 75  # 2.5 seconds
            tagline_shimmer_duration = 90  # 3 seconds
            tagline_cycle_pos = frame_count % tagline_cycle_length
            tagline_shimmer_active = tagline_cycle_pos >= tagline_pause

            try:
                tagline_x_start = (self.width - len(tagline)) // 2

                if tagline_shimmer_active:
                    # Calculate shimmer position within the tagline
                    tagline_shimmer_time = tagline_cycle_pos - tagline_pause
                    # Slower movement (0.3 instead of 0.5) to ensure full coverage
                    tagline_shimmer_pos = (tagline_shimmer_time * 0.3)

                    # Draw each character with shimmer - no diagonal, just horizontal sweep
                    for char_idx, char in enumerate(tagline):
                        x = tagline_x_start + char_idx
                        # Calculate distance from shimmer center
                        distance_from_shimmer = abs(char_idx - tagline_shimmer_pos)

                        if distance_from_shimmer < shimmer_width:
                            intensity = 1.0 - (distance_from_shimmer / shimmer_width)
                            if intensity > 0.7:
                                # Center - bright white
                                attr = curses.color_pair(4) | curses.A_BOLD  # White bold
                            elif intensity > 0.3:
                                # Mid - bright blue
                                attr = curses.color_pair(11) | curses.A_BOLD  # Blue bold
                            else:
                                # Edge - blue
                                attr = curses.color_pair(11)  # Blue
                        else:
                            # Outside shimmer - solid blue
                            attr = curses.color_pair(11) | curses.A_BOLD  # Blue bold

                        self.stdscr.addstr(tagline_y, x, char, attr)
                else:
                    # No shimmer - draw in solid blue
                    self.stdscr.addstr(tagline_y, tagline_x_start, tagline, curses.color_pair(11) | curses.A_BOLD)
            except:
                pass

            # Display top 5 high scores with shimmer effect
            # High score shimmer cycle: 3 seconds pause, 5 seconds shimmer = 8 second cycle
            # Offset from other shimmers for visual variety
            highscore_cycle_length = 240  # 8 seconds at 30 FPS
            highscore_pause = 90  # 3 seconds
            highscore_shimmer_duration = 150  # 5 seconds
            highscore_cycle_pos = frame_count % highscore_cycle_length
            highscore_shimmer_active = highscore_cycle_pos >= highscore_pause

            try:
                # Header - dimension-specific title (e.g., "OUR 80x24 HEROES")
                dimension = self._get_dimension_key()
                header_text = f"═══ OUR {dimension} HEROES ═══"
                header_x_start = (self.width - len(header_text)) // 2

                # Shimmer the header
                if highscore_shimmer_active:
                    highscore_shimmer_time = highscore_cycle_pos - highscore_pause
                    highscore_shimmer_pos = (highscore_shimmer_time * 0.4)

                    for char_idx, char in enumerate(header_text):
                        x = header_x_start + char_idx
                        distance_from_shimmer = abs(char_idx - highscore_shimmer_pos)

                        if distance_from_shimmer < shimmer_width:
                            intensity = 1.0 - (distance_from_shimmer / shimmer_width)
                            if intensity > 0.7:
                                # Center - bright white
                                attr = curses.color_pair(4) | curses.A_BOLD
                            elif intensity > 0.3:
                                # Mid - bright yellow
                                attr = curses.color_pair(3) | curses.A_BOLD
                            else:
                                # Edge - yellow
                                attr = curses.color_pair(3)
                        else:
                            # Outside shimmer - solid yellow
                            attr = curses.color_pair(3) | curses.A_BOLD

                        self.stdscr.addstr(header_y, x, char, attr)
                else:
                    # No shimmer - solid yellow
                    self.stdscr.addstr(header_y, header_x_start, header_text,
                                      curses.color_pair(3) | curses.A_BOLD)

                # Display scores with shimmer
                for i, entry in enumerate(self.high_scores[:5]):
                    rank = i + 1
                    initials = entry['initials']
                    score = entry['score']
                    score_line = f"{rank}. {initials:<3}       {score:>6}"
                    score_y = header_y + 1 + i
                    score_x_start = (self.width - len(score_line)) // 2 - 1  # Shifted 1 char left

                    # Base colors for each rank
                    if rank == 1:
                        base_color = 3  # Yellow/Gold
                        base_bold = True
                    elif rank == 2:
                        base_color = 4  # White/Silver
                        base_bold = True
                    elif rank == 3:
                        base_color = 10  # Red/Bronze
                        base_bold = False
                    else:
                        base_color = 5  # Green
                        base_bold = False

                    # Apply shimmer effect
                    if highscore_shimmer_active:
                        # Offset shimmer position for each line for cascading effect
                        line_shimmer_pos = highscore_shimmer_pos + (i * 3)

                        for char_idx, char in enumerate(score_line):
                            x = score_x_start + char_idx
                            distance_from_shimmer = abs(char_idx - line_shimmer_pos)

                            if distance_from_shimmer < shimmer_width:
                                intensity = 1.0 - (distance_from_shimmer / shimmer_width)
                                if intensity > 0.7:
                                    # Center - brightest white
                                    attr = curses.color_pair(4) | curses.A_BOLD
                                elif intensity > 0.3:
                                    # Mid - base color bright
                                    attr = curses.color_pair(base_color) | curses.A_BOLD
                                else:
                                    # Edge - base color
                                    attr = curses.color_pair(base_color)
                                    if base_bold:
                                        attr |= curses.A_BOLD
                            else:
                                # Outside shimmer - base color
                                attr = curses.color_pair(base_color)
                                if base_bold:
                                    attr |= curses.A_BOLD

                            self.stdscr.addstr(score_y, x, char, attr)
                    else:
                        # No shimmer - solid base color
                        attr = curses.color_pair(base_color)
                        if base_bold:
                            attr |= curses.A_BOLD
                        self.stdscr.addstr(score_y, score_x_start, score_line, attr)
            except:
                pass

            menu_text = "[N] New Game    [I] Intro    [B] Briefing    [ESC] Quit"
            try:
                self.stdscr.addstr(bottom_y, (self.width - len(menu_text)) // 2, menu_text, curses.color_pair(3) | curses.A_BOLD)
            except:
                pass

            self.stdscr.refresh()

            # Check for input (non-blocking)
            try:
                key = self.stdscr.getch()
                if key == ord('n') or key == ord('N'):
                    self.synth.stop_menu_music()
                    return True
                elif key == ord('i') or key == ord('I'):
                    self.synth.stop_menu_music()
                    self.show_intro()
                    self.synth.start_menu_music()
                elif key == ord('b') or key == ord('B'):
                    self.show_help()
                elif key == 27:  # ESC key
                    self.synth.stop_menu_music()
                    return False
            except:
                pass

            # Increment frame counter
            frame_count += 1

            # Maintain frame rate
            elapsed = time.time() - start_time
            sleep_time = frame_time - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def animate_ship_destruction(self):
        """Animate ship exploding into debris"""
        # Create debris particles spreading from ship center
        debris_list = []
        ship_center_x = self.player.x + self.player.width / 2
        ship_center_y = self.player.y + self.player.height / 2

        # Create 30 debris pieces spreading in all directions
        for _ in range(30):
            # Random velocity in all directions
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(0.5, 2.5)
            vx = speed * math.cos(angle)
            vy = speed * math.sin(angle)
            debris_list.append(ShipDebris(ship_center_x, ship_center_y, vx, vy))

        # Create large explosions at ship position
        for _ in range(8):
            ex = ship_center_x + random.uniform(-2, 2)
            ey = ship_center_y + random.uniform(-2, 2)
            self.explosions.append(Explosion(ex, ey, True))

        # Play massive explosion sound with extra noise
        nuke_sound = self.synth.sounds['nuke']
        nuke_sound.set_volume(1.2)  # Extra loud for ship destruction
        nuke_sound.play()

        # Animate debris for 2 seconds (60 frames at 30 FPS)
        fps = 30
        frame_time = 1.0 / fps

        for frame in range(60):
            start_time = time.time()

            # Update GENESIS wobble animation
            self.genesis_wobble_phase += 0.02
            self.genesis_wobble_x = math.sin(self.genesis_wobble_phase * 1.3) * 0.5
            self.genesis_wobble_y = math.cos(self.genesis_wobble_phase * 0.9) * 0.3

            # Update debris positions with physics
            for debris in debris_list[:]:
                debris.x += debris.vx
                debris.y += debris.vy
                debris.vy += debris.gravity  # Apply gravity
                debris.lifetime -= 1

                # Remove if off screen or lifetime expired
                if (debris.x < 1 or debris.x >= self.width - 1 or
                    debris.y < 1 or debris.y >= self.height - 1 or
                    debris.lifetime <= 0):
                    debris_list.remove(debris)

            # Update regular explosions
            for explosion in self.explosions[:]:
                explosion.lifetime -= 1
                if explosion.lifetime <= 0:
                    self.explosions.remove(explosion)

            # Draw the destruction scene
            self.pad.erase()

            # Draw border
            self.pad.attron(curses.color_pair(4))
            self.pad.border()
            self.pad.attroff(curses.color_pair(4))

            # Draw starfield
            self._update_starfield()
            for star in self.starfield:
                try:
                    if star['layer'] == 1:
                        self.pad.addstr(int(star['y']), int(star['x']), star['char'], curses.color_pair(4))
                    elif star['layer'] == 2:
                        self.pad.addstr(int(star['y']), int(star['x']), star['char'], curses.color_pair(5))
                    else:
                        self.pad.addstr(int(star['y']), int(star['x']), star['char'], curses.color_pair(5) | curses.A_BOLD)
                except:
                    pass

            # Draw GENESIS freight ship (same as in main game loop)
            try:
                genesis_x = int(self.genesis_x + self.genesis_wobble_x)
                genesis_center_y = (self.height // 2) + int(self.genesis_wobble_y)

                # Use normal colors during death animation (no flash)
                border_color = 5  # Green
                rivet_color = 4   # White
                texture_color = 7  # Gray

                y_start = genesis_center_y - self.genesis_height // 2
                wall_patterns = ["▓", "▒", "░", "█"]

                # Draw only the visible right portion of GENESIS (matching intro exactly)
                for row in range(self.genesis_height):
                    y = y_start + row
                    if 0 < y < self.height - 1:
                        right_wall_x = genesis_x + self.genesis_width - 1

                        # Determine what character to use based on row position
                        if row == 0:
                            wall_char = "╗"
                            wall_color = border_color
                        elif row == self.genesis_height - 1:
                            wall_char = "╝"
                            wall_color = border_color
                        else:
                            if row % 3 == 0:
                                wall_char = "║"
                                wall_color = border_color
                            elif row % 7 == 0:
                                wall_char = "●"
                                wall_color = rivet_color
                            else:
                                wall_char = wall_patterns[row % 4]
                                wall_color = texture_color

                        # Draw rightmost column (the right wall)
                        if right_wall_x >= 0 and right_wall_x < self.width:
                            self.pad.addstr(y, right_wall_x, wall_char, curses.color_pair(wall_color))

                        # Also draw column to the left if wobble pushes GENESIS right
                        if right_wall_x == 1:
                            if row == 0:
                                self.pad.addstr(y, 0, "═", curses.color_pair(border_color))
                            elif row == self.genesis_height - 1:
                                self.pad.addstr(y, 0, "═", curses.color_pair(border_color))
                            else:
                                self.pad.addstr(y, 0, "░", curses.color_pair(texture_color))
            except:
                pass

            # Draw explosions
            for explosion in self.explosions:
                try:
                    self.pad.addstr(int(explosion.y), int(explosion.x),
                                   explosion.char, curses.color_pair(explosion.color))
                except:
                    pass

            # Draw debris
            for debris in debris_list:
                try:
                    # Fade debris color as lifetime decreases
                    if debris.lifetime < 20:
                        # Fade to darker color in final 2/3 second
                        self.pad.addstr(int(debris.y), int(debris.x),
                                       debris.char, curses.color_pair(4))
                    else:
                        self.pad.addstr(int(debris.y), int(debris.x),
                                       debris.char, curses.color_pair(debris.color) | curses.A_BOLD)
                except:
                    pass

            # Refresh screen
            self.pad.noutrefresh(0, 0, 0, 0, self.height - 1, self.width - 1)
            curses.doupdate()

            # Maintain frame rate
            elapsed = time.time() - start_time
            sleep_time = frame_time - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def show_game_over(self):
        """Display game over screen, prompt for initials if high score, then return to main menu."""
        self.stdscr.clear()
        self.stdscr.bkgd(' ', curses.color_pair(4))  # Set white on black
        self.stdscr.nodelay(0)

        # Play game over tune
        self.synth.play('gameover')

        # Pause before game over screen (unless ship was destroyed - already had 3-second explosion)
        if self.game_over_reason != 'player_died':
            time.sleep(1.5)

        # Helper function to create properly formatted box lines
        def format_box_line(text, width=35):
            """Format a line to fit exactly in the box with proper padding"""
            return f"║{text.center(width)}║"

        # Different messages based on how the game ended
        if self.game_over_reason == 'cargo_captured':
            # Cargo ship was captured - randomly select failure message
            failure_messages = [
                ["The GENESIS has been captured."],
                ["The artifact is in enemy hands."],
                ["All is lost. They won."],
                ["Mission failed. GENESIS lost."],
                ["The enemy has seized the cargo."],
            ]
            failure_lines = random.choice(failure_messages)

            game_over_lines = [
                "╔═══════════════════════════════════╗",
                format_box_line(""),
                format_box_line("M I S S I O N   L O S T"),
                format_box_line(""),
                "╠═══════════════════════════════════╣",
            ]
            for line in failure_lines:
                game_over_lines.append(format_box_line(""))
                game_over_lines.append(format_box_line(line))
            game_over_lines.append(format_box_line(""))
            game_over_lines.append("╚═══════════════════════════════════╝")
        elif self.game_over_reason == 'aborted':
            # Player aborted mission - randomly select motivational/challenging message
            abort_messages = [
                ["We can't all be heroes."],
                ["Maybe next time, \"pilot\"..."],
                ["The galaxy needed you, pilot."],
                ["Giving up already?"],
                ["Heroes are made, not born."],
            ]
            abort_lines = random.choice(abort_messages)

            game_over_lines = [
                "╔═══════════════════════════════════╗",
                format_box_line(""),
                format_box_line("M I S S I O N   A B O R T E D"),
                format_box_line(""),
                "╠═══════════════════════════════════╣",
            ]
            for line in abort_lines:
                game_over_lines.append(format_box_line(""))
                game_over_lines.append(format_box_line(line))
            game_over_lines.append(format_box_line(""))
            game_over_lines.append("╚═══════════════════════════════════╝")
        elif self.game_over_reason == 'nuke_sacrifice':
            # Player sacrificed themselves with a nuke - special heroic messages
            sacrifice_messages = [
                ["Thank you for your sacrifice."],
                ["Your sacrifice saved the GENESIS."],
                ["A hero's sacrifice. We salute you."],
                ["You gave everything for the", "mission. Thank you."],
                ["Greater love has no one than", "this. Thank you, pilot."],
            ]
            sacrifice_lines = random.choice(sacrifice_messages)

            game_over_lines = [
                "╔═══════════════════════════════════╗",
                format_box_line(""),
                format_box_line("H E R O I C   S A C R I F I C E"),
                format_box_line(""),
                "╠═══════════════════════════════════╣",
            ]
            for line in sacrifice_lines:
                game_over_lines.append(format_box_line(""))
                game_over_lines.append(format_box_line(line))
            game_over_lines.append(format_box_line(""))
            game_over_lines.append("╚═══════════════════════════════════╝")
        else:
            # Player died - randomly select memorial message
            memorial_messages = [
                ["Your efforts will be remembered."],
                ["Your sacrifice echoes through", "eternity."],
                ["You fought with honor."],
                ["Your name lives on."],
                ["The galaxy will not forget."],
            ]
            memorial_lines = random.choice(memorial_messages)

            game_over_lines = [
                "╔═══════════════════════════════════╗",
                format_box_line(""),
                format_box_line("P I L O T   D O W N"),
                format_box_line(""),
                "╠═══════════════════════════════════╣",
            ]
            for line in memorial_lines:
                game_over_lines.append(format_box_line(""))
                game_over_lines.append(format_box_line(line))
            game_over_lines.append(format_box_line(""))
            game_over_lines.append("╚═══════════════════════════════════╝")

        start_y = max(2, (self.height - len(game_over_lines) - 2) // 2)

        # Draw game over message
        for i, line in enumerate(game_over_lines):
            y = start_y + i
            if y < self.height - 1:
                x = max(1, (self.width - len(line)) // 2)
                try:
                    # Check if this is a title line (has MISSION, PILOT, or HEROIC)
                    if "MISSION" in line or "PILOT" in line or "HEROIC" in line:
                        # Draw borders in yellow, title text in red
                        self.stdscr.addstr(y, x, "║ ", curses.color_pair(3))
                        # Extract content between borders
                        content = line[2:-2]
                        self.stdscr.addstr(y, x + 2, content, curses.color_pair(1) | curses.A_BOLD)
                        self.stdscr.addstr(y, x + len(line) - 2, " ║", curses.color_pair(3))
                    elif "═" in line:
                        # Border lines - all yellow
                        self.stdscr.addstr(y, x, line, curses.color_pair(3))
                    else:
                        # Content lines - yellow borders, white content
                        self.stdscr.addstr(y, x, "║ ", curses.color_pair(3))
                        content = line[2:-2]
                        self.stdscr.addstr(y, x + 2, content, curses.color_pair(4))
                        self.stdscr.addstr(y, x + len(line) - 2, " ║", curses.color_pair(3))
                except:
                    pass

        # Show score info (without high score indicator yet - that comes after achievements)
        msg2 = f"Final Score: {self.player.score}"

        info_y = start_y + len(game_over_lines) + 1

        try:
            self.stdscr.addstr(info_y, (self.width - len(msg2)) // 2, msg2,
                              curses.color_pair(5) | curses.A_BOLD)
        except:
            pass

        # Show statistics
        stats_y = info_y + 2
        try:
            # Calculate accuracy
            if self.total_shots_fired > 0:
                accuracy = (self.total_hits / self.total_shots_fired) * 100
                accuracy_str = f"{accuracy:.1f}%"
            else:
                accuracy_str = "N/A"

            # Create statistics lines
            stats_lines = [
                f"Enemies Killed: {self.enemies_killed}",
                f"Nukes Used: {self.nukes_used}",
                f"Accuracy: {accuracy_str}"
            ]

            # Draw statistics
            for i, stat in enumerate(stats_lines):
                self.stdscr.addstr(stats_y + i, (self.width - len(stat)) // 2, stat,
                                  curses.color_pair(4))
        except:
            pass

        self.stdscr.refresh()

        # Wait 4 seconds to show game over message
        time.sleep(4)

        # Check for achievements
        achievements = self.check_achievements()

        # If there are achievements, display them and add bonus points
        if achievements:
            self.stdscr.clear()
            self.stdscr.bkgd(' ', curses.color_pair(4))

            # Build achievement display (same width as game over dialog: 37 chars)
            achievement_lines = [
                "╔═══════════════════════════════════╗",
                "║                                   ║",
                "║    A C H I E V E M E N T S !      ║",
                "║                                   ║",
                "╠═══════════════════════════════════╣",
                "║                                   ║",
            ]

            for achievement in achievements:
                # Content width is 35 chars (37 total - 2 for borders)
                # Format: "║ ★ NAME║" where " ★ NAME" = 35 chars (1 space + star + space + name padded to 32)
                ach_line = f"║ ★ {achievement:<32}║"
                achievement_lines.append(ach_line)
                achievement_lines.append("║   +500 points                     ║")

            achievement_lines.append("║                                   ║")
            achievement_lines.append("╚═══════════════════════════════════╝")

            # Display achievement dialog
            ach_start_y = max(2, (self.height - len(achievement_lines)) // 2)
            for i, line in enumerate(achievement_lines):
                y = ach_start_y + i
                if y < self.height - 1:
                    x = max(1, (self.width - len(line)) // 2)
                    try:
                        if "ACHIEVEMENTS" in line:
                            # Draw borders in yellow, title text in gold
                            self.stdscr.addstr(y, x, "║ ", curses.color_pair(3))
                            content = line[2:-2]
                            self.stdscr.addstr(y, x + 2, content, curses.color_pair(3) | curses.A_BOLD)
                            self.stdscr.addstr(y, x + len(line) - 2, " ║", curses.color_pair(3))
                        elif "═" in line:
                            # Border lines - yellow
                            self.stdscr.addstr(y, x, line, curses.color_pair(3))
                        elif "★" in line:
                            # Achievement name line: "║ ★ NAME║"
                            # Draw left border
                            self.stdscr.addstr(y, x, "║ ", curses.color_pair(3))
                            # Draw star + space + name in cyan bold
                            content = line[2:-1]  # Extract " ★ NAME" (everything between ║ and ║)
                            self.stdscr.addstr(y, x + 2, content, curses.color_pair(11) | curses.A_BOLD)
                            # Draw right border
                            self.stdscr.addstr(y, x + len(line) - 1, "║", curses.color_pair(3))
                        elif "+500" in line:
                            # Points line - green
                            self.stdscr.addstr(y, x, "║ ", curses.color_pair(3))
                            content = line[2:-2]
                            self.stdscr.addstr(y, x + 2, content, curses.color_pair(5) | curses.A_BOLD)
                            self.stdscr.addstr(y, x + len(line) - 2, " ║", curses.color_pair(3))
                        else:
                            # Empty lines - yellow borders
                            self.stdscr.addstr(y, x, line, curses.color_pair(3))
                    except:
                        pass

            self.stdscr.refresh()

            # Add points incrementally for each achievement
            total_bonus = len(achievements) * 500
            points_added = 0

            # Display current score below achievements
            score_y = ach_start_y + len(achievement_lines) + 2

            while points_added < total_bonus:
                # Add 20 points at a time
                increment = min(20, total_bonus - points_added)
                self.player.score += increment
                points_added += increment

                # Play ding sound
                self.synth.play('ding')

                # Update score display
                score_msg = f"Score: {self.player.score - points_added + increment} → {self.player.score}"
                try:
                    # Clear previous score line
                    self.stdscr.addstr(score_y, 0, " " * self.width)
                    # Draw new score
                    self.stdscr.addstr(score_y, (self.width - len(score_msg)) // 2, score_msg,
                                      curses.color_pair(5) | curses.A_BOLD)
                    self.stdscr.refresh()
                except:
                    pass

                # Wait a bit between increments
                time.sleep(0.05)

            # Final display with just the final score
            final_msg = f"Final Score: {self.player.score}"
            try:
                self.stdscr.addstr(score_y, 0, " " * self.width)
                self.stdscr.addstr(score_y, (self.width - len(final_msg)) // 2, final_msg,
                                  curses.color_pair(5) | curses.A_BOLD)
                self.stdscr.refresh()
            except:
                pass

            # Wait 4 seconds to show final score
            time.sleep(4)

        # Now check if player made high score with the UPDATED score (including achievement bonuses)
        made_high_score = self.check_high_score(self.player.score) >= 0 and self.player.score > 0

        # If made high score, show the high score message
        if made_high_score:
            self.stdscr.clear()
            self.stdscr.bkgd(' ', curses.color_pair(4))

            # Show final score with high score indicator
            high_score_msg = f"Final Score: {self.player.score}"
            high_score_indicator = "★ HIGH SCORE! ★"

            msg_y = (self.height - 4) // 2

            try:
                self.stdscr.addstr(msg_y, (self.width - len(high_score_msg)) // 2, high_score_msg,
                                  curses.color_pair(5) | curses.A_BOLD)
                self.stdscr.addstr(msg_y + 2, (self.width - len(high_score_indicator)) // 2, high_score_indicator,
                                  curses.color_pair(10) | curses.A_BOLD)
            except:
                pass

            self.stdscr.refresh()

            # Wait 2 seconds before prompting for initials
            time.sleep(2)

        # If made high score, prompt for initials
        if made_high_score:
            initials = self.prompt_for_initials()
            self.add_high_score(self.player.score, initials)

        # Clear any buffered input
        curses.flushinp()

    def reset_game(self):
        """Reset game state for a new game"""
        # Start player at center of horizontally allowed area (vertically centered accounting for 3-row sprite)
        right_limit = (self.width // 3) + 8
        ship_width = 3  # Player ship is 3 characters wide
        # Center between left limit (x=2) and rightmost position (right_limit - ship_width)
        player_x = (2 + (right_limit - ship_width)) / 2
        self.player = Player(player_x, (self.height // 2) - 1)
        self.bullets = []
        self.energy_beams = []
        self.enemies = []
        self.boss = None
        self.boss_bullets = []
        self.powerups = []
        self.explosions = []
        self.drones = []
        self.drone_bullets = []
        self.game_over = False
        self.game_over_reason = None
        self.frame_count = 0
        self.enemy_spawn_rate = 30
        self.boss_level = 1
        self.enemies_killed = 0
        self.next_boss_kills = 30  # First boss after 30 enemies, then every 50
        self.nuke_effect_timer = 0  # Reset nuke effect
        self.paused = False  # Reset pause state
        self.ship_flash_timer = 30  # Flash ship for 1 second at start of new game
        self.starfield = self._generate_starfield()  # Reset starfield

        # Reset notification system
        self.notification_text = ""
        self.notification_timer = 0
        self.notification_scroll_offset = 0
        self.energy_beam_tip_shown = False  # Reset energy beam tip for new game

        # Reset achievement tracking
        self.achievement_cheats = {
            'PERFECT DEFENSE': False,
            'PLASMA PURIST': False,
            'SHARPSHOOTER': False
        }
        self.enemies_breached = 0
        self.total_shots_fired = 0
        self.total_hits = 0
        self.plasma_only_kills = True
        self.nukes_used = 0

        # Reset engine sound tracking
        if self.engine_sound_channel:
            self.engine_sound_channel.stop()
            self.engine_sound_channel = None
        self.prev_vx = 0.0
        self.prev_vy = 0.0

        # Reset arrow key states
        for key in self.arrow_keys_state:
            self.arrow_keys_state[key] = False

        # Re-enable non-blocking input for gameplay
        self.stdscr.nodelay(1)
        self.stdscr.timeout(0)

    def run(self):
        """Main game loop"""
        fps = 30
        frame_time = 1.0 / fps

        # Play game start fanfare at reduced volume
        fanfare_sound = self.synth.sounds['game_start']
        fanfare_sound.set_volume(0.7)
        fanfare_sound.play()

        # Start engine sound (ship is always moving through space)
        self.engine_sound_channel = self.synth.sounds['engine_idle'].play(loops=-1)

        # Don't start game music automatically - it will start when player gets power-ups

        while not self.game_over:
            start_time = time.time()

            # Check terminal size
            terminal_ok = self._check_terminal_size()

            if terminal_ok:
                # Normal game loop
                self.handle_input()
                self.update()
                self.draw()
            else:
                # Terminal is too small - game is already paused, just show resize message
                try:
                    # Clear the screen first to prevent residue
                    self.stdscr.clear()

                    current_height, current_width = self.stdscr.getmaxyx()
                    msg1 = "Terminal too small!"
                    msg2 = f"Current: {current_width}x{current_height}"
                    msg3 = f"Required: {self.initial_width}x{self.initial_height}"
                    msg4 = "Please resize your terminal or restart"
                    msg5 = "(Game is paused)"

                    # Try to center the messages if possible
                    if current_height >= 5 and current_width >= len(msg1):
                        y_start = max(0, current_height // 2 - 2)
                        if y_start + 0 < current_height and len(msg1) < current_width:
                            x = max(0, (current_width - len(msg1)) // 2)
                            self.stdscr.addstr(y_start + 0, x, msg1, curses.color_pair(1) | curses.A_BOLD)
                        if y_start + 1 < current_height and len(msg2) < current_width:
                            x = max(0, (current_width - len(msg2)) // 2)
                            self.stdscr.addstr(y_start + 1, x, msg2, curses.color_pair(4))
                        if y_start + 2 < current_height and len(msg3) < current_width:
                            x = max(0, (current_width - len(msg3)) // 2)
                            self.stdscr.addstr(y_start + 2, x, msg3, curses.color_pair(4))
                        if y_start + 3 < current_height and len(msg4) < current_width:
                            x = max(0, (current_width - len(msg4)) // 2)
                            self.stdscr.addstr(y_start + 3, x, msg4, curses.color_pair(3))
                        if y_start + 4 < current_height and len(msg5) < current_width:
                            x = max(0, (current_width - len(msg5)) // 2)
                            self.stdscr.addstr(y_start + 4, x, msg5, curses.color_pair(7))

                    self.stdscr.refresh()
                except:
                    pass  # If we can't draw the message, that's ok

            # Maintain frame rate
            elapsed = time.time() - start_time
            sleep_time = frame_time - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        # Game over - stop engine sound and game music
        if self.engine_sound_channel:
            self.engine_sound_channel.stop()
            self.engine_sound_channel = None
        self.synth.stop_game_music()

        # If player was destroyed, show dramatic explosion animation
        if self.game_over_reason == 'player_died':
            self.animate_ship_destruction()
        else:
            # For other game over reasons (cargo captured, aborted), just freeze
            self.draw()  # Draw final frame to show frozen state
            time.sleep(1.0)

        # Show game over screen for 3 seconds then return to main menu
        self.show_game_over()


def main(stdscr):
    """Entry point for curses wrapper"""
    # Clear any pre-existing terminal output before curses takes over
    stdscr.clear()
    stdscr.refresh()

    # Check minimum terminal size requirement
    height, width = stdscr.getmaxyx()
    if height < 24 or width < 80:
        # Exit curses mode temporarily to print error
        curses.endwin()
        print("Error: Terminal size must be at least 80x24.")
        print(f"Current size: {width}x{height}")
        print("Please resize your terminal and try again.")
        sys.exit(1)

    game = Game(stdscr)

    try:
        # Show intro sequence first time only
        game.show_intro()

        # Main loop - show menu, play game, repeat
        while True:
            # Show main menu
            if not game.show_main_menu():
                break  # User chose to quit

            # Play game
            game.reset_game()
            game.run()

            # After game over, loop back to main menu
    finally:
        # Clean up keyboard listener
        game.keyboard_listener.stop()


if __name__ == "__main__":
    curses.wrapper(main)
