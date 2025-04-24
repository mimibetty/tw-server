class APIResponse:
    @staticmethod
    def success(payload=None, message: str = 'Success', status: int = 200):
        """Return a success response."""
        import json

        from flask import Response

        response = json.dumps(
            {'payload': payload, 'message': message, 'status': status},
            sort_keys=True,
        )
        return Response(
            response=response, status=status, mimetype='application/json'
        )

    @staticmethod
    def error(error: str, status: int):
        """Return an error response."""
        import json

        from flask import Response

        response = json.dumps(
            {'error': error, 'status': status}, sort_keys=True
        )
        return Response(
            response=response, status=status, mimetype='application/json'
        )
