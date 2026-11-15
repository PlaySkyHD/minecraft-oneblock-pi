package de.werkbank.endlock;

import java.util.Map;
import java.util.WeakHashMap;
import net.minecraft.commands.Commands;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.level.Level;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.fml.ModContainer;
import net.neoforged.fml.common.Mod;
import net.neoforged.fml.common.EventBusSubscriber;
import net.neoforged.fml.config.ModConfig;
import net.neoforged.neoforge.common.ModConfigSpec;
import net.neoforged.neoforge.event.RegisterCommandsEvent;
import net.neoforged.neoforge.event.entity.EntityTravelToDimensionEvent;

@Mod(EndAccessLock.ID)
public final class EndAccessLock {
    public static final String ID = "endaccesslock";
    private static final ModConfigSpec SPEC;
    private static final ModConfigSpec.BooleanValue LOCKED;
    private static final ModConfigSpec.ConfigValue<String> MESSAGE;
    static {
        var builder = new ModConfigSpec.Builder();
        LOCKED = builder.comment("Block travel into the End for everyone, including operators.")
            .define("locked", true);
        MESSAGE = builder.comment("Shown in chat and action bar when a player is denied entry.")
            .define("message", "Das End ist aktuell noch gesperrt. Wir öffnen es später gemeinsam!");
        SPEC = builder.build();
    }

    public EndAccessLock(ModContainer container) {
        container.registerConfig(ModConfig.Type.COMMON, SPEC, "end-access-lock.toml");
    }

    @EventBusSubscriber(modid = ID)
    public static final class Events {
        // Travel events run on the server thread. Weak keys do not retain logged-out players.
        private static final Map<ServerPlayer, Long> LAST_NOTICE = new WeakHashMap<>();
        private static final Map<ServerPlayer, Long> LAST_CHAT = new WeakHashMap<>();

        @SubscribeEvent
        public static void onTravel(EntityTravelToDimensionEvent event) {
            if (event.getEntity().getServer() == null || !Level.END.equals(event.getDimension()) || !LOCKED.get()) return;
            event.setCanceled(true);
            if (event.getEntity() instanceof ServerPlayer player) {
                long now = System.nanoTime();
                Component message = Component.literal(MESSAGE.get()).withStyle(net.minecraft.ChatFormatting.GOLD);
                if (now - LAST_NOTICE.getOrDefault(player, now - 2_000_000_000L) >= 2_000_000_000L) {
                    player.displayClientMessage(message, true);
                    LAST_NOTICE.put(player, now);
                }
                if (now - LAST_CHAT.getOrDefault(player, now - 30_000_000_000L) >= 30_000_000_000L) {
                    player.sendSystemMessage(message);
                    LAST_CHAT.put(player, now);
                }
            }
        }

        @SubscribeEvent
        public static void onCommands(RegisterCommandsEvent event) {
            event.getDispatcher().register(Commands.literal("endlock")
                .requires(source -> source.hasPermission(2))
                .then(Commands.literal("status").executes(context -> {
                    context.getSource().sendSuccess(() -> Component.literal(
                        "End-Zugang: " + (LOCKED.get() ? "GESPERRT" : "OFFEN") + ". Nachricht: " + MESSAGE.get()), false);
                    return LOCKED.get() ? 1 : 0;
                }))
                .then(Commands.literal("open").executes(context -> {
                    LOCKED.set(false); LOCKED.save();
                    context.getSource().sendSuccess(() -> Component.literal("Das End ist jetzt freigegeben."), true);
                    return 1;
                }))
                .then(Commands.literal("close").executes(context -> {
                    LOCKED.set(true); LOCKED.save();
                    context.getSource().sendSuccess(() -> Component.literal("Der Zugang zum End ist jetzt gesperrt."), true);
                    return 1;
                })));
        }
    }
}
