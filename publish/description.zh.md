# Oculus 自定义 uniform 修复（Oculus Custom-Uniform Fix）

> **一句话简介（Summary，可直接填 Modrinth / CurseForge 的简介栏）**
> 让 Oculus 1.16.5 支持 OptiFine 自定义 uniform：Complementary 的雨水坑、EuphoriaPatches 的雨天效果一次修好，且**不需要改光影包**。
>
> **One-liner (EN)**: Restores OptiFine custom uniforms on Oculus 1.16.5 — Complementary rain puddles and EuphoriaPatches rain effects work out of the box, with no shaderpack edits.

**支持**：Minecraft 1.16.5 · Forge 36.x · 仅客户端 · 需要 [Oculus](https://www.curseforge.com/minecraft/mc-mods/oculus)

---

## 你遇到的是这个问题吗？

装了 Oculus、用 Complementary Unbound（或 EuphoriaPatches 版），下雨天**地面永远是干的**，
雨天天空/光照也怪怪的，但游戏不报错、光影也显示已启用。翻 `logs/latest.log` 能找到这样一行：

```
[gbuffers_terrain] Unsupported uniform: float inRainy
[gbuffers_deferred] Unsupported uniform: float inDry
[composite1] Unsupported uniform: float rainFactorUniform
```

这行是**警告**，不是错误 —— 所以光影看起来"正常加载"，但那些 uniform 全都读成了 `0.0`。

## 原因

OptiFine 允许光影在 `shaders.properties` 里自己声明 uniform：

```properties
uniform.float.inRainy = smooth(102, if(in(biome_precipitation, 1), 1, 0), 20, 10)
```

而 Complementary 的整个雨水坑系统就挂在这个值上：

```glsl
puddleMixer = puddleLightFactor * inRainy * puddleNormalFactor;   // inRainy == 0 时永远没有水坑
```

Oculus 1.16.5（1.4.8，基于 Iris 1.6.x）**没有实现这个表达式语法**：它只上传一张硬编码的自定义 uniform 表，
而表里用的是**另一套名字**（`isDry` / `isRainy` / `isSnowy`）。光影声明的 `inDry` / `inRainy` / `inSnowy`
因此永远不会被赋值 —— 加载器不提供的 uniform 在 GLSL 里就是 `0.0`。

EuphoriaPatches 同理：它把雨强度声明成 `rainFactorUniform`，一旦拿不到，整个 `rainFactor`（雨的大小、
雨天染色、水的表现）都按"没下雨"处理。

## 本模组做了什么

用 Mixin 在 Oculus 自己的 `HardcodedCustomUniforms#addHardcodedCustomUniforms` 末尾**补上缺失的名字**，
取值直接调用 Oculus 自己的辅助方法（反射），因此数值与 OptiFine 的语义完全一致：

| 补上的名字 | 取值来源 | 对应的 OptiFine 定义 |
| --- | --- | --- |
| `inDry` / `inRainy` / `inSnowy` | `getRawPrecipitation()`，包在 `SmoothedFloat(20, 10, …)` 里 | `smooth(id, if(in(biome_precipitation, n), 1, 0), 20, 10)`，与 Oculus 自带的 `isDry` / `isRainy` / `isSnowy` 逐项一致 |
| `eyeBrightnessM2` | `getEyeSkyBrightness() > 239`，包在 `SmoothedFloat(2, 2, …)` 里 | `smooth(4, if(eyeBrightness.y > 239.0, 1, 0), 2, 2)` |
| `maxBlindnessDarkness` | `CommonUniforms.getBlindness()`（1.16.5 没有 1.19+ 的黑暗效果，`darknessFactor` 恒为 0） | `max(blindness, darknessFactor)` |
| `rainFactorUniform` | `CommonUniforms.getRainStrength()`，包在 `SmoothedFloat(3, 3, …)` 里 | EuphoriaPatches 的雨强度（`smooth(1, rainStrength, 3, 3)`） |

因为取值全部走 Oculus 自己的 API，本模组**不引用任何 Minecraft 类**，所以与 MC 映射、混淆、补丁版本无关。

## 安装

1. Minecraft **1.16.5** + **Forge 36.x** + **Oculus**；
2. 把 `oculuscufix-1.0.0-mc1.16.5.jar` 丢进 `mods` 文件夹。

**不需要**改光影包，也**不需要**删除你现有的光影设置（`config/oculus.properties` 里的选择会被保留）。

## 怎么确认生效

**看日志（推荐，不用满地找水坑）** —— `logs/latest.log` 里应出现：

```
[oculuscufix] provided the missing OptiFine custom uniforms: inDry/inRainy/inSnowy, eyeBrightnessM2, maxBlindnessDarkness, rainFactorUniform
```

同时下面这些行应当**全部消失**：`Unsupported uniform: float inRainy` / `inDry` / `inSnowy` /
`rainFactorUniform`。

**看画面** —— Complementary Unbound 里把 *Rain Puddles* 调成 `Puddles Always`，找一块露天、朝上的地面，
水坑会立刻出现（不必等下雨）。注意水坑只在**朝上且见天光**的面上出现（室内、屋檐下、垂直墙面本来就没有）。

## 兼容性

* **纯客户端**，不会在服务端注册任何东西；
* 与**原版**光影包配合使用；也**不会**和手工打过补丁的光影包冲突；
* 只补上表那四个名字，不碰其它任何 uniform，所以不可能改变别家光影的表现；
* **安全降级**：注入器非必需、mixin 配置 `required: false`、整体 `try/catch`。即使 Oculus 以后改动导致注入失败，
  也只是日志里多一条警告，游戏照常运行；
* 卸载 = 删掉 jar，不留任何配置文件或存档数据。

## 已知限制（有意不做的部分）

| 名字 | 为什么不做 |
| --- | --- |
| `thunderFactor` | 需要 CPU 侧的雷雨强度，Oculus 没有暴露；影响仅为雷雨高光，很小 |
| `lightningFlashOptifine` | 需要 skyColor（渲染期数据），无法在 uniform 注册阶段取到 |
| `waterAltitude` | 依赖 EuphoriaPatches 自己的 CPU 变量 |
| `inNetherWastes` / `inCrimsonForest` / `inLushCave` / `inPaleGarden` 等 | 生物群系类；1.16.5 上 OptiFine 同样是 0 或（`inLushCave` / `inPaleGarden`）根本不存在 |

## 常见问题

**Q：为什么不直接改光影包？**
A：也可以（把 `inRainy` 改名的补丁），但那样每次 Complementary / EuphoriaPatches 更新都要重打一次，
而且每个光影包都要各自处理。装在加载器侧则一劳永逸。

**Q：会不会和别的 Oculus 修复类模组冲突？**
A：本模组只**新增** uniform 名字，不替换、不删除 Oculus 已有的任何行为；重复注册同名 uniform 也只是最后一次生效。

**Q：支持 1.16.5 以外的版本吗？**
A：不支持。1.17+ 的 Iris/Oculus 已经自己实现了自定义 uniform，这个模组没有意义。

**Q：会掉帧吗？**
A：不会。每个 uniform 每帧只多一次反射调用（`Method` 已缓存），且只在光影程序创建时注册一次。

## 构建 / 许可

* 源码与离线构建脚本见仓库 `mod/`（只用 `javac` + 你 Minecraft 安装里已有的 jar，不需要 Gradle、不需要联网）；
* 作者 **norohime**，许可 **LGPL-3.0-only**（与 Oculus 自身一致）；
* 背景 issue：[Oculus #453](https://github.com/Asek3/Oculus/issues/453)。
