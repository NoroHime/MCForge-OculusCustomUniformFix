package norohime.oculuscufix.mixin;

import java.lang.reflect.Method;

import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

import net.coderbot.iris.gl.uniform.FloatSupplier;
import net.coderbot.iris.gl.uniform.UniformHolder;
import net.coderbot.iris.gl.uniform.UniformUpdateFrequency;
import net.coderbot.iris.uniforms.FrameUpdateNotifier;
import net.coderbot.iris.uniforms.transforms.SmoothedFloat;

/**
 * Oculus 1.16.5 (1.4.8, Iris 1.6.x base) does not implement OptiFine's custom-uniform expression
 * syntax (shaders.properties: {@code uniform.float.<name> = <expression>}). It only uploads the
 * hardcoded table in {@code HardcodedCustomUniforms}, whose names differ from what several popular
 * packs declare, so those uniforms silently read back as 0.0.
 *
 * <p>Concrete effect: Complementary Unbound gates its rain puddles on {@code inRainy}
 * ({@code puddleMixer = ... * inRainy * ...}) and EuphoriaPatches gates its whole rain factor on
 * {@code rainFactorUniform}. On Oculus both stay 0.0, so rain puddles never appear and the EP rain
 * factor is dead - with no error, only a {@code [program] Unsupported uniform: float inRainy}
 * warning in the log.
 *
 * <p>This mixin appends the missing names to that hardcoded table, so <b>every</b> OptiFine pack
 * that declares them works without touching the shaderpack.
 *
 * <p>{@code addHardcodedCustomUniforms} is Oculus' own static method taking Oculus' own types, so
 * its name is never remapped in production: {@code remap = false} with the readable name is correct
 * here and no refmap is needed. Values are read through Oculus' own helpers via reflection (they are
 * private / package-private), so this class references no Minecraft class at all.
 *
 * <p>Everything is wrapped in try/catch and the injector is declared non-required: if Oculus ever
 * changes, this mod logs and the game keeps running with stock behaviour.
 */
@Mixin(targets = "net.coderbot.iris.uniforms.HardcodedCustomUniforms")
public class MixinHardcodedCustomUniforms {

    private static final Logger LOG = LogManager.getLogger("oculuscufix");

    private static Method mPrecipitation;
    private static Method mEyeSkyBrightness;
    private static Method mRainStrength;
    private static Method mBlindness;
    private static boolean resolved;

    private static void resolve() {
        if (resolved) {
            return;
        }
        resolved = true;
        try {
            Class<?> hardcoded = Class.forName("net.coderbot.iris.uniforms.HardcodedCustomUniforms");
            mPrecipitation = hardcoded.getDeclaredMethod("getRawPrecipitation");
            mEyeSkyBrightness = hardcoded.getDeclaredMethod("getEyeSkyBrightness");
            mPrecipitation.setAccessible(true);
            mEyeSkyBrightness.setAccessible(true);
        } catch (Throwable t) {
            LOG.warn("[oculuscufix] getRawPrecipitation/getEyeSkyBrightness unavailable, "
                    + "in* and eyeBrightnessM2 will not be provided", t);
        }
        try {
            Class<?> common = Class.forName("net.coderbot.iris.uniforms.CommonUniforms");
            mRainStrength = common.getDeclaredMethod("getRainStrength");
            mBlindness = common.getDeclaredMethod("getBlindness");
            mRainStrength.setAccessible(true);
            mBlindness.setAccessible(true);
        } catch (Throwable t) {
            LOG.warn("[oculuscufix] CommonUniforms.getRainStrength/getBlindness unavailable, "
                    + "rainFactorUniform and maxBlindnessDarkness will not be provided", t);
        }
    }

    private static float call(Method method, float fallback) {
        if (method == null) {
            return fallback;
        }
        try {
            Object value = method.invoke(null);
            return value instanceof Number ? ((Number) value).floatValue() : fallback;
        } catch (Throwable t) {
            return fallback;
        }
    }

    private static float precipitation() {
        return call(mPrecipitation, 0.0F);
    }

    private static float eyeSkyBrightness() {
        return call(mEyeSkyBrightness, 0.0F);
    }

    private static float rainStrength() {
        return call(mRainStrength, 0.0F);
    }

    private static float blindness() {
        return call(mBlindness, 0.0F);
    }

    @Inject(method = "addHardcodedCustomUniforms", at = @At("TAIL"), remap = false)
    private static void oculuscufix$addOptiFineNames(UniformHolder holder,
                                                     FrameUpdateNotifier notifier,
                                                     CallbackInfo ci) {
        try {
            resolve();

            // inDry / inRainy / inSnowy: the exact definitions Complementary declares in
            // shaders.properties, and identical to Oculus' own isDry / isRainy / isSnowy
            // (smooth(20 ticks up, 10 ticks down) of "biome precipitation == NONE/RAIN/SNOW").
            holder.uniform1f(UniformUpdateFrequency.PER_FRAME, "inDry",
                    new SmoothedFloat(20.0F, 10.0F, () -> precipitation() == 0.0F ? 1.0F : 0.0F, notifier));
            holder.uniform1f(UniformUpdateFrequency.PER_FRAME, "inRainy",
                    new SmoothedFloat(20.0F, 10.0F, () -> precipitation() == 1.0F ? 1.0F : 0.0F, notifier));
            holder.uniform1f(UniformUpdateFrequency.PER_FRAME, "inSnowy",
                    new SmoothedFloat(20.0F, 10.0F, () -> precipitation() == 2.0F ? 1.0F : 0.0F, notifier));

            // eyeBrightnessM2 = smooth(4, if(eyeBrightness.y > 239.0, 1, 0), 2, 2)
            holder.uniform1f(UniformUpdateFrequency.PER_FRAME, "eyeBrightnessM2",
                    new SmoothedFloat(2.0F, 2.0F, () -> eyeSkyBrightness() > 239.0F ? 1.0F : 0.0F, notifier));

            // maxBlindnessDarkness = max(blindness, darknessFactor); the darkness effect is 1.19+,
            // so on 1.16.5 darknessFactor is always 0 and this equals the OptiFine expression.
            FloatSupplier blindnessSupplier = new FloatSupplier() {
                @Override
                public float getAsFloat() {
                    return blindness();
                }
            };
            holder.uniform1f(UniformUpdateFrequency.PER_FRAME, "maxBlindnessDarkness", blindnessSupplier);

            // EuphoriaPatches declares its rain factor as its own custom uniform
            // (smooth(1, rainStrength, 3, 3) when IRIS_VERSION is unavailable) and derives the
            // pack-wide "rainFactor" from it. Iris serves the same quantity as rainStrengthS.
            holder.uniform1f(UniformUpdateFrequency.PER_FRAME, "rainFactorUniform",
                    new SmoothedFloat(3.0F, 3.0F, () -> rainStrength(), notifier));

            LOG.info("[oculuscufix] provided the missing OptiFine custom uniforms: "
                    + "inDry/inRainy/inSnowy, eyeBrightnessM2, maxBlindnessDarkness, rainFactorUniform");
        } catch (Throwable t) {
            LOG.warn("[oculuscufix] could not register the extra custom uniforms; "
                    + "shaders keep working with stock behaviour", t);
        }
    }
}
