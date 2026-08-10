"""Typed failures for the optional conversation boundary."""


class ConversationError(Exception):
    pass


class ConfigurationError(ConversationError):
    pass


class BudgetExhausted(ConversationError):
    pass


class ProposalInFlight(ConversationError):
    pass


class ConversationTimeout(ConversationError):
    pass


class RemoteError(ConversationError):
    pass


class InvalidModelResponse(ConversationError):
    pass
