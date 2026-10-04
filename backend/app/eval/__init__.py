"""Offline evaluation harness.

Measures grading quality against a hand-labelled golden set, so a change to the
pipeline can be defended with a number rather than an impression. Nothing here
runs in the request path or the worker; it is driven from `app.cli`.
"""
