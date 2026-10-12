# Oculus Custom-Uniform Fix

**English** | [中文](#中文说明)

A tiny (≈5 KB) client-side Forge mod for **Minecraft 1.16.5 + Oculus** that restores the OptiFine
custom uniforms Oculus never implements — most visibly, **Complementary Unbound rain puddles**.

* No shaderpack editing: install the jar and stock shaderpacks work as intended.
* Fail-safe by design: a non-required injector, a `required: false` mixin config and full
  `try/catch`. If Oculus ever changes, you get one log warning instead of a crash.
* Uninstall = delete the jar. No config files, no world data, no permanent changes.

---

## 中文说明

一个约 5 KB 的**客户端** Forge 小模组（**Minecraft 1.16.5 + Oculus**），用来补上 Oculus 从未实现的
OptiFine 自定义 uniform —— 最直观的效果就是**让 Complementary Unbound 的雨水坑重新出现**。

* **不需要改光影包**：装上这个 jar，原版光影包就能按设计工作。
* **默认安全降级**：注入器非必需、mixin 配置 `required: false`、整体 `try/catch`。
  万一 Oculus 以后变了，最多是一条日志警告，不会崩游戏。
* **卸载 = 删掉 jar**：不写配置文件、不动存档、没有任何持久更改。

---

## The problem / 问题所在

OptiFine lets a shaderpack declare its own uniforms in `shaders.properties`:

```properties
uniform.float.inRainy = smooth(102, if(in(biome_precipitation, 1), 1, 0), 20, 10)
```

Complementary Unbound gates its entire rain-puddle system on that value:

```glsl
puddleMixer = puddleLightFactor * inRainy * puddleNormalFactor;
```

Oculus 1.16.5 (1.4.8, Iris 1.6.x base) **does not implement that expression syntax at all**. It only
uploads a hardcoded list of custom uniforms that uses *different names* (`isDry` / `isRainy` /
`isSnowy` instead of `inDry` / `inRainy` / `inSnowy`). A uniform the loader never provides reads back
as `0.0`, and the only hint is a non-fatal log line:

```
[gbuffers_terrain] Unsupported uniform: float inRainy
```

Result: rain puddles never appear, rain sky/light tinting is missing, and EuphoriaPatches' whole rain
factor (`rainFactorUniform`) is dead — with no error message.

OptiFine 用 `shaders.properties` 里的 `uniform.float.*` 让光影自定义 uniform；Oculus 1.16.5 **完全不实现**
这个语法，只上传一张硬编码表，而表里的名字和光影声明的不一样（`isDry/isRainy/isSnowy` vs
`inDry/inRainy/inSnowy`）。加载器没提供的 uniform 会静默读到 `0.0`，唯一线索是一行非致命日志
`Unsupported uniform: float inRainy`。于是雨水坑不出现、雨天天空/光照染色失效、EuphoriaPatches 的
`rainFactorUniform` 整个变成 0。

## What this mod does / 本模组做了什么

It appends the missing names to Oculus' own hardcoded table via a Mixin on
`net.coderbot.iris.uniforms.HardcodedCustomUniforms#addHardcodedCustomUniforms`, using Oculus' own
helper methods (through reflection) so the values are numerically identical to OptiFine's semantics.

| Name | Value source | OptiFine definition it matches |
| --- | --- | --- |
| `inDry` / `inRainy` / `inSnowy` | `getRawPrecipitation()` wrapped in `SmoothedFloat(20, 10, …)` | `smooth(<id>, if(in(biome_precipitation, <n>), 1, 0), 20, 10)` — identical to Oculus' own `isDry` / `isRainy` / `isSnowy` |
| `eyeBrightnessM2` | `getEyeSkyBrightness() > 239` wrapped in `SmoothedFloat(2, 2, …)` | `smooth(4, if(eyeBrightness.y > 239.0, 1, 0), 2, 2)` |
| `maxBlindnessDarkness` | `CommonUniforms.getBlindness()` (the darkness effect is 1.19+, so `darknessFactor` is always 0 on 1.16.5) | `max(blindness, darknessFactor)` |
| `rainFactorUniform` | `CommonUniforms.getRainStrength()` wrapped in `SmoothedFloat(3, 3, …)` | EuphoriaPatches' rain factor (`smooth(1, rainStrength, 3, 3)`) |

本模组通过 Mixin 注入 Oculus 自己的 `HardcodedCustomUniforms#addHardcodedCustomUniforms`，用**反射**调用
Oculus 自己的辅助方法（`getRawPrecipitation()` / `getEyeSkyBrightness()` /
`CommonUniforms.getRainStrength()` / `getBlindness()`），把上表的取值补进硬编码表 —— 数值语义与 OptiFine 一致。

Because every value is read through Oculus' own API, **this mod references no Minecraft class at all**
and therefore does not care about mappings, obfuscation or MC patch versions.

因为全部取值都走 Oculus 自己的 API，本模组**不引用任何 Minecraft 类**，因此与 MC 映射、混淆、补丁版本无关。

## Install / 安装

1. Minecraft **1.16.5** + **Forge 36.x** + **[Oculus](https://www.curseforge.com/minecraft/mc-mods/oculus)**.
2. Drop `oculuscufix-1.0.0-mc1.16.5.jar` into your `mods` folder. That's all.

1. 需要 Minecraft **1.16.5** + **Forge 36.x** + **[Oculus](https://www.curseforge.com/minecraft/mc-mods/oculus)**。
2. 把 `oculuscufix-1.0.0-mc1.16.5.jar` 放进 `mods` 文件夹即可。

## Verify it works / 如何确认生效

**From the log** (recommended, no need to hunt for puddles): `logs/latest.log` should contain

```
[oculuscufix] provided the missing OptiFine custom uniforms: inDry/inRainy/inSnowy, eyeBrightnessM2, maxBlindnessDarkness, rainFactorUniform
```

and the line `Unsupported uniform: float inRainy` (also `inDry`, `inSnowy`, `rainFactorUniform`) must be
**gone**.

**Visually**: with Complementary Unbound, set *Rain Puddles* to `Puddles Always` and look at an
outdoor, upward-facing surface — puddles appear immediately, no rain required.

**看日志（推荐）**：`logs/latest.log` 里应出现上面那行 `[oculuscufix] ...`，同时
`Unsupported uniform: float inRainy`（以及 `inDry`/`inSnowy`/`rainFactorUniform`）应当**消失**。
**看画面**：Complementary Unbound 里把 *Rain Puddles* 设成 `Puddles Always`，找一块露天、朝上的地面，
水坑会立刻出现（不用等下雨）。

## Compatibility / 兼容性

* **Client side only.** Nothing is registered on a dedicated server.
* Works with **stock** shaderpacks. It is also *not* in conflict with shaderpacks that were patched by
  hand (`#define inRainyValue max(inRainy, isRainy)` still evaluates correctly).
* Only the four names above are provided. `thunderFactor`, `lightningFlashOptifine`, `waterAltitude`
  and the biome-based names (`inNetherWastes`, `inLushCave`, …) are intentionally left alone: on
  1.16.5 they are either always 0 or need CPU-side data Oculus does not expose.
* Uninstall by deleting the jar.

* **纯客户端**，服务端不会注册任何东西。
* 与**原版**光影包配合使用；也**不会**和手工打过补丁的光影包冲突
  （`#define inRainyValue max(inRainy, isRainy)` 两边都成立）。
* 只补上表那四个名字。`thunderFactor`、`lightningFlashOptifine`、`waterAltitude` 以及生物群系类
  （`inNetherWastes`、`inLushCave` 等）**故意不动**：在 1.16.5 上它们要么恒为 0，要么需要 Oculus 没有暴露的
  CPU 侧数据。
* 卸载就是删掉 jar。

## Repository layout / 仓库结构

```
build_mod.py                  offline build script (javac + Python, no Gradle, no network)
src/norohime/oculuscufix/     @Mod entry point + the Mixin
resources/                    mods.toml / oculuscufix.mixins.json / pack.mcmeta
publish/                      description.zh.md + description.en.md (mod page texts, both languages)
LICENSE                       LGPL-3.0-only
```

## Build from source / 从源码构建

No Gradle, no MixinGradle, no network: the build script only needs `javac` plus the jars that already
exist inside your Minecraft installation (Oculus, Mixin, log4j-api, Forge universal).

```powershell
python build_mod.py                                     # -> dist\oculuscufix-1.0.0-mc1.16.5.jar
python build_mod.py --install                           # also copy it into <game>\versions\1.16.5\mods\
python build_mod.py --uninstall                         # remove it again
python build_mod.py --game-dir "D:\mc\.minecraft"       # if the game folder is not auto-detected
```

The game folder is resolved from `--game-dir`, then `MC_GAME_DIR`, then a git-ignored `.mc-game-dir`
file next to the script, then auto-detection (walking up looking for `libraries` + `versions`, finally
`%APPDATA%\.minecraft`).

Before compiling, the script verifies that the Oculus jar really exposes
`HardcodedCustomUniforms#addHardcodedCustomUniforms`; after packaging it asserts the jar structure, the
`MixinConfigs` manifest entry, the mixin config package, the Java 8 class version, the presence of the
`@Inject` annotation and the non-fatal mixin settings. That assertion is not decoration — it caught a
stale `package` field in `oculuscufix.mixins.json` during the rename to `norohime.oculuscufix`, an
error that would otherwise have failed silently in production.

不需要 Gradle、不需要 MixinGradle、不需要联网：`build_mod.py` 只用 `javac` 和你 Minecraft 安装里已有的 jar
（Oculus、Mixin、log4j-api、Forge universal）编译打包，并在打包前后做静态验收
（注入目标是否存在、注解是否进了 class、类版本是否 52、jar 结构 / `MixinConfigs` / mixin 包名 /
`mods.toml` 与 `mixins.json` 是否合法、是否保持非致命配置）。

## Credits & license / 致谢与许可

* Written by **norohime**. Licensed **LGPL-3.0-only** (the same license Oculus itself uses).
* Oculus / Iris are the work of their respective authors; this mod contains none of their code — it
  only injects into a public static method and reuses values through reflection.
* Background: [Oculus issue #453](https://github.com/Asek3/Oculus/issues/453) tracks OptiFine custom
  uniforms on 1.16.5.
