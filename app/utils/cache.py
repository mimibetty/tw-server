class Cache:
    @staticmethod
    def set(key: str, data: dict, expire_in_minutes: int = 60):
        import json

        from app import AppContext

        try:
            redis = AppContext().get_redis()
            redis.set(key, json.dumps(data, sort_keys=True))
            redis.expire(key, expire_in_minutes * 60)
        except Exception as e:
            raise e

    @staticmethod
    def get(key: str) -> dict:
        import json

        from app import AppContext

        try:
            redis = AppContext().get_redis()
            data = redis.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            raise e

    @staticmethod
    def delete(key: str):
        from app import AppContext

        try:
            redis = AppContext().get_redis()
            redis.delete(key)
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
