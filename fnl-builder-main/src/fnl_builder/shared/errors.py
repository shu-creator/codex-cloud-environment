from __future__ import annotations


class FnlError(Exception):
    pass


class InputError(FnlError):
    pass


class ParseError(FnlError):
    pass


class LLMError(FnlError):
    pass
