"""Errores propios de la aplicación SIRAH."""


class SirahApplicationError(Exception):
    """Error base controlado por SIRAH."""


class SituationalError(SirahApplicationError):
    """Error controlado del circuito situado."""


class SpeechError(SituationalError):
    """Error controlado del contrato de voz."""


class SpeechBusyError(SpeechError):
    """El proveedor de voz ya tiene una operación activa."""


class SpeechUnavailableError(SpeechError):
    """El proveedor de voz no acepta operaciones."""


class AudioTurnBusyError(SpeechBusyError):
    """La otra dirección posee el turno local de audio."""


class SpeechStartError(SpeechError):
    """Una operación de voz no pudo completar su inicio atómico."""


class SpeechInputError(SpeechError):
    """Error seguro del runtime de entrada de voz."""


class CapabilityRejectedError(SirahApplicationError):
    """La política local rechazó una solicitud de capacidad."""


class CapabilityExecutionError(SirahApplicationError):
    """Cortex o el adaptador no pudo ejecutar una capacidad autorizada."""


class IntelligenceError(SirahApplicationError):
    """Error base del proveedor o de su respuesta."""


class IntelligenceUnavailableError(IntelligenceError):
    """El proveedor, modelo o configuración no está disponible."""


class IntelligenceTimeoutError(IntelligenceError):
    """El proveedor excedió el tiempo permitido."""


class IntelligenceRateLimitError(IntelligenceError):
    """El proveedor rechazó la solicitud por cuota o frecuencia."""


class InvalidIntelligenceResponseError(IntelligenceError):
    """La respuesta del proveedor no satisface el contrato de SIRAH."""
