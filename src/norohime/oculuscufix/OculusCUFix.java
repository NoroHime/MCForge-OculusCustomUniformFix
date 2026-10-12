package norohime.oculuscufix;

import net.minecraftforge.fml.common.Mod;

/**
 * FML entry point. The mod adds no behaviour of its own: the work happens in
 * {@code norohime.oculuscufix.mixin.MixinHardcodedCustomUniforms}, which is registered through the
 * {@code MixinConfigs} attribute in this jar's manifest (the same mechanism Oculus itself uses).
 */
@Mod("oculuscufix")
public class OculusCUFix {

    public OculusCUFix() {
        // nothing to do; the mixin is applied by Mixin at class-load time
    }
}
