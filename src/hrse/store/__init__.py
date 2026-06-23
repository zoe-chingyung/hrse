"""Event store package.

The rest of the application depends only on ``EventStore`` (the Protocol).
Import the concrete ``S3EventStore`` only in factories / DI wiring.
"""
