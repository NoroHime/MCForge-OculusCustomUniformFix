# Oculus Custom-Uniform Fix

> **Summary (paste into the Modrinth / CurseForge summary field)**
> Restores OptiFine custom uniforms on Oculus 1.16.5 — Complementary rain puddles and EuphoriaPatches rain effects work out of the box, with no shaderpack edits.
>
> **一句话简介（中文）**：让 Oculus 1.16.5 支持 OptiFine 自定义 uniform，Complementary 的雨水坑、EuphoriaPatches 的雨天效果一次修好，且不需要改光影包。

**Requires**: Minecraft 1.16.5 · Forge 36.x · client side · [Oculus](https://www.curseforge.com/minecraft/mc-mods/oculus)

---

## Is this your problem?

You run Oculus with Complementary Unbound (or its EuphoriaPatches build). It rains, but **the ground
stays dry**; the sky/light tinting in rain also looks off. No error is shown, the shaderpack appears
to be enabled, and `logs/latest.log` has lines like:

```
[gbuffers_terrain] Unsupported uniform: float inRainy
[gbuffers_deferred] Unsupported uniform: float inDry
[composite1] Unsupported uniform: float rainFactorUniform
```

Those are **warnings**, not errors — which is why everything looks "loaded fine" while those uniforms
silently read back as `0.0`.

## Why it happens

OptiFine lets a shaderpack declare its own uniforms in `shaders.properties`:

```properties
uniform.float.inRainy = smooth(102, if(in(biome_precipitation, 1), 1, 0), 20, 10)
```

and Complementary hangs its entire rain-puddle system on that value:

```glsl
puddleMixer = puddleLightFactor * inRainy * puddleNormalFactor;   // inRainy == 0 -> never any puddles
```

Oculus 1.16.5 (1.4.8, Iris 1.6.x base) **does not implement that expression syntax**. It only
uploads a hardcoded list of custom uniforms that uses *different names* (`isDry` / `isRainy` /
`isSnowy`), so the `inDry` / `inRainy` / `inSnowy` a shaderpack declares are never assigned — and an
unprovided uniform is simply `0.0` in GLSL.

EuphoriaPatches is the same story: it declares its rain strength as `rainFactorUniform`, and without
it the whole pack-wide `rainFactor` (rain look, tinting, water behaviour) behaves as "no rain".

## What this mod does

A Mixin appends the missing names at the end of Oculus' own
`HardcodedCustomUniforms#addHardcodedCustomUniforms`, reading the values from Oculus' own helpers via
reflection, so they are numerically identical to OptiFine's semantics:

| Name added | Value source | OptiFine definition it matches |
| --- | --- | --- |
| `inDry` / `inRainy` / `inSnowy` | `getRawPrecipitation()` wrapped in `SmoothedFloat(20, 10, …)` | `smooth(id, if(in(biome_precipitation, n), 1, 0), 20, 10)` — identical to Oculus' own `isDry` / `isRainy` / `isSnowy` |
| `eyeBrightnessM2` | `getEyeSkyBrightness() > 239` wrapped in `SmoothedFloat(2, 2, …)` | `smooth(4, if(eyeBrightness.y > 239.0, 1, 0), 2, 2)` |
| `maxBlindnessDarkness` | `CommonUniforms.getBlindness()` (the 1.19+ darkness effect does not exist on 1.16.5, so `darknessFactor` is always 0) | `max(blindness, darknessFactor)` |
| `rainFactorUniform` | `CommonUniforms.getRainStrength()` wrapped in `SmoothedFloat(3, 3, …)` | EuphoriaPatches' rain factor (`smooth(1, rainStrength, 3, 3)`) |

Because every value comes from Oculus' own API, **this mod references no Minecraft class at all** —
it does not care about mappings, obfuscation or MC patch versions.

## Install

1. Minecraft **1.16.5** + **Forge 36.x** + **Oculus**.
2. Drop `oculuscufix-1.0.0-mc1.16.5.jar` into your `mods` folder.

No shaderpack edits, and you do not need to reset your existing shader settings
(the selection in `config/oculus.properties` is kept).

## Verify it works

**From the log (recommended — no need to hunt for puddles)**: `logs/latest.log` should contain

```
[oculuscufix] provided the missing OptiFine custom uniforms: inDry/inRainy/inSnowy, eyeBrightnessM2, maxBlindnessDarkness, rainFactorUniform
```

and these lines must be **gone**: `Unsupported uniform: float inRainy` / `inDry` / `inSnowy` /
`rainFactorUniform`.

**Visually**: in Complementary Unbound set *Rain Puddles* to `Puddles Always` and look at an outdoor,
upward-facing surface — puddles appear immediately, no rain needed. Note that puddles only form on
upward faces that see the sky (never indoors, under eaves, or on vertical walls).

## Compatibility

* **Client side only** — nothing is registered on a dedicated server.
* Works with **stock** shaderpacks, and does **not** conflict with hand-patched ones.
* It only *adds* the four names above; it never replaces or removes existing Oculus behaviour, so it
  cannot change how other shaderpacks look.
* **Fail-safe**: the injector is non-required, the mixin config is `required: false` and everything is
  wrapped in `try/catch`. If a future Oculus change breaks the injection, you get one log warning and
  the game keeps running.
* Uninstall by deleting the jar — no config files, no world data.

## Known limits (intentionally not implemented)

| Name | Why not |
| --- | --- |
| `thunderFactor` | Needs CPU-side thunder strength, which Oculus does not expose; only affects thunderstorm highlights |
| `lightningFlashOptifine` | Needs skyColor, which is only available during rendering, not at uniform registration |
| `waterAltitude` | Depends on a EuphoriaPatches CPU-side variable |
| `inNetherWastes` / `inCrimsonForest` / `inLushCave` / `inPaleGarden` / … | Biome-based; on 1.16.5 OptiFine is 0 as well, and `inLushCave` / `inPaleGarden` do not exist at all |

## FAQ

**Why not just patch the shaderpack?**
You can (rename `inRainy` and friends), but then every Complementary / EuphoriaPatches update needs to
be re-patched, and every shaderpack needs its own treatment. Fixing it on the loader side is
one-and-done.

**Will it conflict with other Oculus fix mods?**
It only *adds* uniform names. It never replaces or deletes existing behaviour, and registering the
same uniform twice simply means the last registration wins.

**Does it support versions other than 1.16.5?**
No. Iris/Oculus on 1.17+ already implements custom uniforms, so this mod has no purpose there.

**Does it cost performance?**
No. Each uniform adds one cached reflective call per frame, and registration happens once per shader
program creation.

## Build & license

* Source and an offline build script live in `mod/` of the repository — it only needs `javac` plus the
  jars already present in your Minecraft installation (no Gradle, no network).
* By **norohime**, licensed **LGPL-3.0-only** (the same license Oculus itself uses).
* Background: [Oculus #453](https://github.com/Asek3/Oculus/issues/453).
