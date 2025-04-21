from typing import Optional


class Cache:
    @staticmethod
    def set(
        prefix: str,
        key: Optional[str],
        data: dict,
        expire_in_minutes: int = 60,
    ):
        import json

        from app import AppContext

        try:
            redis = AppContext().get_redis()
            name = prefix + '_' + key if key else prefix

            redis.set(name, json.dumps(data, sort_keys=True))
            redis.expire(name, expire_in_minutes * 60)
        except Exception as e:
            raise e

    @staticmethod
    def get(prefix: str, key: Optional[str]) -> dict:
        import json

        from app import AppContext

        try:
            redis = AppContext().get_redis()
            name = prefix + '_' + key if key else prefix

            data = redis.get(name)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            raise e

    @staticmethod
    def delete(prefix: str, key: Optional[str]):
        from app import AppContext

        try:
            redis = AppContext().get_redis()
            name = prefix + '_' + key if key else prefix
            redis.delete(name)
        except Exception as e:
            raise e

    @staticmethod
    def delete_by_prefix(prefix: str):
        from app import AppContext

        try:
            redis = AppContext().get_redis()
            keys = redis.keys(f'{prefix}*')
            if keys:
                redis.delete(*keys)
        except Exception as e:
            raise e
