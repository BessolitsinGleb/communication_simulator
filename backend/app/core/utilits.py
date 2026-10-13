from redis import Redis
from .config import s

r = Redis.from_url(url=s.REDIS_URL)