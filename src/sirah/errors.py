"""Errores propios de la aplicación SIRAH."""


class SirahApplicationError(Exception):
    """Error base controlado por SIRAH."""


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

