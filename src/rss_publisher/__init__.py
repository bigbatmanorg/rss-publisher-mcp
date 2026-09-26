"""RSS Publisher core package."""

from .models import FeedConfig, FeedEntry
from .service import PublisherService

__all__ = ["FeedConfig", "FeedEntry", "PublisherService"]
__version__ = "0.1.0"
