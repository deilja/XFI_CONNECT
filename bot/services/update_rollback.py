"""Compatibility façade for the XFI CONNECT update engine.

The old YadrenoVPN updater implementation has been removed.  This module is
kept temporarily because existing handlers import its public names.  All
runtime logic lives in :mod:`bot.services.xfi_update`.
"""
from bot.services.xfi_update import *  # noqa: F401,F403
