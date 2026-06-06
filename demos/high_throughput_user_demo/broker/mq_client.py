import redis
import json
from config.settings import settings

class RedisBroker:
    """
    Message Broker wrapper using Redis List as a simple Queue.
    In a bigger system, this could be swapped with RabbitMQ (Pika) or Kafka.
    """
    def __init__(self):
        # We use a connection pool even for Redis
        pool = redis.ConnectionPool(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            decode_responses=True # Auto decode to strings
        )
        self.client = redis.Redis(connection_pool=pool)
        self.queue_name = settings.REDIS_QUEUE_NAME

    def push_message(self, message: dict):
        """Producer uses this to quickly push a message."""
        # Using RPUSH to append to right
        self.client.rpush(self.queue_name, json.dumps(message))

    def pop_message(self, timeout: int = 1) -> dict | None:
        """Consumer uses this to block-wait for messages safely."""
        # BLPOP blocks until a message is available or timeout hits
        result = self.client.blpop(self.queue_name, timeout=timeout)
        if result:
            _queue, data = result
            return json.loads(data)
        return None
        
    def queue_size(self) -> int:
        """Get the current backlog count."""
        return self.client.llen(self.queue_name)

# Expose a singleton instance
broker_instance = RedisBroker()
