"""Build the Oculus side fix: oculuscufix (a Mixin into Oculus' HardcodedCustomUniforms).

No Gradle, no MixinGradle, no network: everything needed (the Oculus jar, Mixin, log4j-api and the
Forge universal jar) already exists inside a Minecraft installation that has Forge + Oculus.

    python build_mod.py                      # build + validate -> dist/oculuscufix-<ver>-mc1.16.5.jar
    python build_mod.py --install            # also copy it into <game>/versions/<mc>/mods/
    python build_mod.py --uninstall          # remove it from the mods folder again
    python build_mod.py --game-dir "D:\\mc\\.minecraft"

Where is the game? Resolved in this order:
  1. --game-dir / --version-dir / --mods-dir
  2. the MC_GAME_DIR environment variable
  3. a `.mc-game-dir` text file next to this script (git-ignored, handy for local work)
  4. auto-detection: walk up from this script looking for a folder that has both `libraries` and
     `versions`, then %APPDATA%\\.minecraft

Why no refmap / no annotation processor: the injected method
(`HardcodedCustomUniforms#addHardcodedCustomUniforms`) is Oculus' own static method whose parameters
are all Oculus types, so it does not override anything from Minecraft and its name is never remapped
in production. `remap = false` with the readable name is therefore correct, no refmap is needed, and
`-proc:none` skips the Mixin annotation processor (which would require Gson/Guava/ASM and mappings).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))

MOD_ID = "oculuscufix"
MOD_VERSION = "1.0.0"
# the package carries the author namespace; the modId itself must stay [a-z0-9_] (Forge rule)
MIXIN_PACKAGE = "norohime.oculuscufix.mixin"
MIXIN_CLASS = "norohime/oculuscufix/mixin/MixinHardcodedCustomUniforms.class"
ENTRY_CLASS = "norohime/oculuscufix/OculusCUFix.class"
TARGET_CLASS = "net.coderbot.iris.uniforms.HardcodedCustomUniforms"
TARGET_METHOD = ("addHardcodedCustomUniforms(net.coderbot.iris.gl.uniform.UniformHolder, "
                 "net.coderbot.iris.uniforms.FrameUpdateNotifier)")

MANIFEST = ("Manifest-Version: 1.0\r\n"
            "MixinConfigs: %s.mixins.json\r\n"
            "\r\n" % MOD_ID)

PACK_MCMETA = ('{\n'
               '  "pack": {\n'
               '    "description": "Oculus custom-uniform fix (mixin only)",\n'
               '    "pack_format": 6\n'
               '  }\n'
               '}\n')

# filled in by configure()
GAME_DIR = ""
VERSION_DIR = ""
MC_VERSION = ""
LIBRARIES = ""
MODS_DIR = ""
OCULUS_JAR = ""
MIXIN_JAR = ""
LOG4J_JAR = ""
FORGE_JAR = ""
JAR_NAME = ""


def _looks_like_game_dir(path):
    return bool(path) and os.path.isdir(os.path.join(path, "libraries")) \
        and os.path.isdir(os.path.join(path, "versions"))


def detect_game_dir(explicit=None):
    if explicit:
        if not _looks_like_game_dir(explicit):
            raise SystemExit("error: --game-dir %r does not contain both 'libraries' and 'versions'"
                             % explicit)
        return os.path.abspath(explicit)
    from_env = os.environ.get("MC_GAME_DIR")
    if _looks_like_game_dir(from_env):
        return os.path.abspath(from_env)
    marker = os.path.join(HERE, ".mc-game-dir")
    if os.path.isfile(marker):
        with open(marker, "r", encoding="utf-8") as fh:
            candidate = fh.read().strip().strip('"')
        if _looks_like_game_dir(candidate):
            return os.path.abspath(candidate)
    # walk up: maybe this checkout lives inside the game directory (e.g. <game>/mods/src/...)
    current = HERE
    for _ in range(8):
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
        for candidate in (current, os.path.join(current, ".minecraft")):
            if _looks_like_game_dir(candidate):
                return os.path.abspath(candidate)
    appdata = os.environ.get("APPDATA")
    if appdata and _looks_like_game_dir(os.path.join(appdata, ".minecraft")):
        return os.path.join(appdata, ".minecraft")
    raise SystemExit(
        "error: could not find a Minecraft installation.\n"
        "  Pass --game-dir <path to .minecraft>, set MC_GAME_DIR, or write the path into\n"
        "  %s" % os.path.join(HERE, ".mc-game-dir"))


def _library_version(profile, coordinate):
    """Read the exact library version Forge/the launcher uses (e.g. org.spongepowered:mixin)."""
    try:
        with open(profile, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError:
        return None
    for lib in data.get("libraries", []):
        if lib.get("name", "").startswith(coordinate + ":"):
            return lib["name"].split(":")[2]
    return None


def discover(args):
    global GAME_DIR, VERSION_DIR, MC_VERSION, LIBRARIES, MODS_DIR, JAR_NAME
    global OCULUS_JAR, MIXIN_JAR, LOG4J_JAR, FORGE_JAR

    GAME_DIR = detect_game_dir(args.game_dir)
    LIBRARIES = os.path.join(GAME_DIR, "libraries")
    versions_root = os.path.join(GAME_DIR, "versions")
    VERSION_DIR = os.path.abspath(args.version_dir) if args.version_dir else \
        os.path.join(versions_root, args.mc_version)
    if not os.path.isdir(VERSION_DIR):
        available = sorted(d for d in os.listdir(versions_root)
                           if os.path.isdir(os.path.join(versions_root, d)))
        raise SystemExit("error: %s does not exist. Available versions: %s"
                         % (VERSION_DIR, ", ".join(available)))
    MC_VERSION = os.path.basename(VERSION_DIR)
    MODS_DIR = os.path.abspath(args.mods_dir) if args.mods_dir else os.path.join(VERSION_DIR, "mods")
    JAR_NAME = "%s-%s-mc%s.jar" % (MOD_ID, MOD_VERSION, MC_VERSION)

    profile = os.path.join(VERSION_DIR, MC_VERSION + ".json")
    mixin_ver = _library_version(profile, "org.spongepowered:mixin")
    mixin_jars = sorted(glob.glob(os.path.join(LIBRARIES, "org", "spongepowered", "mixin", "*",
                                               "mixin-*.jar")))
    if mixin_ver:
        candidate = os.path.join(LIBRARIES, "org", "spongepowered", "mixin", mixin_ver,
                                 "mixin-%s.jar" % mixin_ver)
        MIXIN_JAR = candidate if os.path.isfile(candidate) else ""
    if not MIXIN_JAR:
        MIXIN_JAR = mixin_jars[-1] if mixin_jars else ""
    log4j_ver = _library_version(profile, "org.apache.logging.log4j:log4j-api")
    if log4j_ver:
        candidate = os.path.join(LIBRARIES, "org", "apache", "logging", "log4j", "log4j-api",
                                 log4j_ver, "log4j-api-%s.jar" % log4j_ver)
        LOG4J_JAR = candidate if os.path.isfile(candidate) else ""
    if not LOG4J_JAR:
        LOG4J_JAR = args.log4j_jar or (sorted(glob.glob(os.path.join(
            LIBRARIES, "org", "apache", "logging", "log4j", "log4j-api", "*",
            "log4j-api-*.jar"))) or [""])[-1]
    forge_jars = sorted(glob.glob(os.path.join(LIBRARIES, "net", "minecraftforge", "forge", "*",
                                               "forge-*-universal.jar")))
    forge_ver = _library_version(profile, "net.minecraftforge:forge")
    if forge_ver:
        candidate = os.path.join(LIBRARIES, "net", "minecraftforge", "forge", forge_ver,
                                 "forge-%s-universal.jar" % forge_ver)
        FORGE_JAR = candidate if os.path.isfile(candidate) else ""
    if not FORGE_JAR:
        FORGE_JAR = forge_jars[-1] if forge_jars else ""
    oculus = []
    for folder in (MODS_DIR, os.path.join(VERSION_DIR, "shaderpacks")):
        oculus += sorted(glob.glob(os.path.join(folder, "oculus*.jar")))
    OCULUS_JAR = args.oculus_jar or (oculus[0] if oculus else "")

    print("  game dir   : %s" % GAME_DIR)
    print("  version dir : %s  (MC %s)" % (VERSION_DIR, MC_VERSION))
    print("  mods dir   : %s" % MODS_DIR)
    for label, path in (("oculus", OCULUS_JAR), ("mixin", MIXIN_JAR), ("log4j-api", LOG4J_JAR),
                        ("forge", FORGE_JAR)):
        print("  %-11s: %s" % (label, path or "(NOT FOUND)"))
    missing = [n for n, p in (("--oculus-jar", OCULUS_JAR), ("Mixin", MIXIN_JAR),
                              ("log4j-api", LOG4J_JAR), ("Forge universal", FORGE_JAR)) if not p]
    if missing:
        raise SystemExit("error: missing build inputs: %s\n"
                         "  hint: is Oculus installed in this version? for the others, check that the\n"
                         "  launcher profile has been used at least once (libraries must be present)."
                         % ", ".join(missing))


def find_tool(name, fallback):
    found = shutil.which(name)
    if found:
        return found
    if os.path.isfile(fallback):
        return fallback
    raise SystemExit("error: %s not found on PATH (looked for %r too)" % (name, fallback))


def verify_target():
    """The mixin must be able to find the method it injects into."""
    javap = find_tool("javap", r"B:\util\jdk-21\bin\javap.exe")
    res = subprocess.run([javap, "-p", "-classpath", OCULUS_JAR, TARGET_CLASS],
                         capture_output=True, text=True)
    ok = res.returncode == 0 and TARGET_METHOD in res.stdout
    print("  mixin target present: %s" % ok)
    if not ok:
        for line in (res.stdout + res.stderr).splitlines()[:12]:
            print("     " + line)
        raise SystemExit("error: the Oculus jar does not expose the expected mixin target")
    for helper in ("getRawPrecipitation", "getEyeSkyBrightness"):
        if helper not in res.stdout:
            print("  warning: helper %s() not found - that uniform will be skipped at runtime" % helper)


def compile_java():
    javac = find_tool("javac", r"B:\util\jdk-21\bin\javac.exe")
    build_dir = os.path.join(HERE, "build")
    if os.path.isdir(build_dir):
        shutil.rmtree(build_dir)
    classes = os.path.join(build_dir, "classes")
    os.makedirs(classes, exist_ok=True)
    sources = []
    for dirpath, _dirs, files in os.walk(os.path.join(HERE, "src")):
        sources += [os.path.join(dirpath, f) for f in files if f.endswith(".java")]
    if not sources:
        raise SystemExit("error: no .java files under %s" % os.path.join(HERE, "src"))
    classpath = os.pathsep.join([OCULUS_JAR, MIXIN_JAR, LOG4J_JAR, FORGE_JAR])
    # -proc:none: the Mixin annotation processor wants Gson/Guava/ASM and a refmap; we need neither.
    cmd = [javac, "--release", "8", "-nowarn", "-proc:none",
           "-classpath", classpath, "-d", classes] + sources
    print("  javac: %d source file(s), target Java 8" % len(sources))
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(res.stdout)
        print(res.stderr)
        raise SystemExit("error: compilation failed")
    for line in res.stdout.splitlines():
        print("     " + line)
    return classes


def package_jar(classes):
    dist = os.path.join(HERE, "dist")
    os.makedirs(dist, exist_ok=True)
    out = os.path.join(dist, JAR_NAME)
    resources = os.path.join(HERE, "resources")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.writestr("META-INF/MANIFEST.MF", MANIFEST)
        zf.writestr("pack.mcmeta", PACK_MCMETA)
        for dirpath, _dirs, files in os.walk(resources):
            for fn in sorted(files):
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, resources).replace("\\", "/")
                if rel == "META-INF/MANIFEST.MF":
                    continue
                zf.write(full, rel)
        for dirpath, _dirs, files in os.walk(classes):
            for fn in sorted(files):
                if fn.endswith(".class"):
                    full = os.path.join(dirpath, fn)
                    zf.write(full, os.path.relpath(full, classes).replace("\\", "/"))
    print("  wrote %s (%d bytes)" % (out, os.path.getsize(out)))
    return out


def validate(jar):
    ok = True
    with zipfile.ZipFile(jar) as zf:
        names = zf.namelist()
        manifest = zf.read("META-INF/MANIFEST.MF").decode("utf-8")
        print("  entries: %s" % ", ".join(sorted(names)))
        if "MixinConfigs: %s.mixins.json" % MOD_ID not in manifest:
            print("  FAIL: MixinConfigs missing from the manifest")
            ok = False
        try:
            cfg = json.loads(zf.read("%s.mixins.json" % MOD_ID).decode("utf-8"))
            print("  mixin config: package=%s client=%s defaultRequire=%s"
                  % (cfg.get("package"), cfg.get("client"), cfg.get("injectors")))
            if cfg.get("package") != MIXIN_PACKAGE:
                print("  FAIL: mixin config package must be %s" % MIXIN_PACKAGE)
                ok = False
            if cfg.get("required") is not False or "defaultRequire" not in cfg.get("injectors", {}):
                print("  FAIL: keep the mixin non-fatal (required=false + injectors.defaultRequire)")
                ok = False
        except Exception as exc:  # noqa: BLE001
            print("  FAIL: bad mixin config: %s" % exc)
            ok = False
        if MIXIN_CLASS not in names:
            print("  FAIL: %s missing" % MIXIN_CLASS)
            ok = False
        else:
            data = zf.read(MIXIN_CLASS)
            major = int.from_bytes(data[6:8], "big")
            print("  class file major version: %d (52 = Java 8)" % major)
            if major > 52:
                print("  FAIL: class targets a newer Java than 8")
                ok = False
            for needle in (b"Lorg/spongepowered/asm/mixin/injection/Inject;",
                           b"addHardcodedCustomUniforms"):
                if needle not in data:
                    print("  FAIL: %s missing from the compiled mixin" % needle.decode())
                    ok = False
        if ENTRY_CLASS not in names:
            print("  FAIL: @Mod entry point missing (%s)" % ENTRY_CLASS)
            ok = False
    if not ok:
        raise SystemExit("error: validation failed")
    print("  validation: OK")


def install(jar):
    os.makedirs(MODS_DIR, exist_ok=True)
    dest = os.path.join(MODS_DIR, JAR_NAME)
    for old in os.listdir(MODS_DIR):
        if old.endswith(".jar") and old != JAR_NAME and (
                old.startswith(MOD_ID + "-") or old.startswith("oculus-cufix-")):
            os.remove(os.path.join(MODS_DIR, old))
            print("  removed stale %s" % old)
    shutil.copyfile(jar, dest)
    print("  installed -> %s" % dest)


def uninstall():
    removed = []
    if os.path.isdir(MODS_DIR):
        for fn in os.listdir(MODS_DIR):
            if fn.endswith(".jar") and (fn.startswith(MOD_ID + "-") or fn.startswith("oculus-cufix-")):
                os.remove(os.path.join(MODS_DIR, fn))
                removed.append(fn)
    print("  removed: %s" % (removed or "nothing"))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--game-dir", help="path to the .minecraft folder")
    ap.add_argument("--version-dir", help="path to <game>/versions/<mc version>")
    ap.add_argument("--mods-dir", help="override the mods folder (used by --install/--uninstall)")
    ap.add_argument("--mc-version", default="1.16.5", help="Minecraft version folder (default 1.16.5)")
    ap.add_argument("--oculus-jar", help="override the Oculus jar path")
    ap.add_argument("--log4j-jar", help="override the log4j-api jar path")
    ap.add_argument("--install", action="store_true", help="copy the jar into the mods folder")
    ap.add_argument("--uninstall", action="store_true", help="remove the jar from the mods folder")
    ap.add_argument("--no-verify", action="store_true", help="skip the javap target check")
    args = ap.parse_args()

    print("=== environment")
    discover(args)
    if args.uninstall:
        uninstall()
        return 0
    if not args.no_verify:
        print("=== mixin target check")
        verify_target()
    print("=== compile")
    classes = compile_java()
    print("=== package")
    jar = package_jar(classes)
    print("=== validate")
    validate(jar)
    if args.install:
        print("=== install")
        install(jar)
        print("\nStart the game; logs/latest.log should contain '[%s] provided the missing OptiFine\n"
              "custom uniforms: ...' and the line '[<program>] Unsupported uniform: float inRainy'\n"
              "must be gone. Delete the jar from mods/ (or run --uninstall) to remove it." % MOD_ID)
    else:
        print("\njar ready: %s   (use --install to copy it into %s)" % (jar, MODS_DIR))
    return 0


if __name__ == "__main__":
    sys.exit(main())
