TEMP_CONFIG = {
    "Caliente": {"color": "#ef4444", "emoji": "🔴", "badge": "🔴 Caliente"},
    "Tibio":    {"color": "#f97316", "emoji": "🟡", "badge": "🟡 Tibio"},
    "Frio":     {"color": "#3b82f6", "emoji": "🔵", "badge": "🔵 Frío"},
}

CANAL_EMOJI = {
    "WhatsApp":       "💬",
    "Meta Ads":       "📱",
    "Formulario Web": "🌐",
}


def badge_temperatura(temperatura: str | None) -> str:
    if not temperatura:
        return "⚪ Sin score"
    return TEMP_CONFIG.get(temperatura, {}).get("badge", temperatura)


def color_temperatura(temperatura: str | None) -> str:
    if not temperatura:
        return "#6b7280"
    return TEMP_CONFIG.get(temperatura, {}).get("color", "#6b7280")


def badge_canal(canal: str) -> str:
    emoji = CANAL_EMOJI.get(canal, "📋")
    return f"{emoji} {canal}"


def fmt_score(score) -> str:
    if score is None:
        return "—"
    return f"{float(score):.1f}"


def fmt_horas_sin_contacto(fecha_registro: str | None, fecha_primer_contacto: str | None) -> str:
    if fecha_primer_contacto:
        return "✅ Contactado"
    if not fecha_registro:
        return "—"
    from datetime import datetime, timezone
    try:
        reg = datetime.fromisoformat(fecha_registro.replace("Z", "+00:00"))
        horas = (datetime.now(timezone.utc) - reg).total_seconds() / 3600
        if horas < 24:
            return f"🕐 {horas:.0f}h"
        return f"⚠️ {horas:.0f}h sin contacto"
    except Exception:
        return "—"