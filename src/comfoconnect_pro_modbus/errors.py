"""The errors the library raises itself."""

from __future__ import annotations


class ComfoConnectProError(Exception):
    """The base of every error this library raises itself."""


class InvalidValueError(ComfoConnectProError, ValueError):
    """A value is outside what the gateway accepts; nothing was sent."""
