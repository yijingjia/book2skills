import os

# Provide the minimum env vars required for Settings() validation so tests
# that import app modules (extractor, retriever, etc.) can load without a
# running Docker environment.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
