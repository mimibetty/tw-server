class APIResponse:
    @staticmethod
    def success(data, message: str = 'Success', status: int = 200):
        """Return a success response."""
        import json

        from flask import Response

        response = json.dumps(
            {'data': data, 'message': message, 'status': status},
            sort_keys=True,
        )
        return Response(
            response=response, status=status, mimetype='application/json'
        )

    @staticmethod
    def error(error: str, status: int, same_with_response: bool = False):
        """Return an error response."""
        import json

        from flask import Response

        response = json.dumps(
            {'error': error, 'status': status}, sort_keys=True
        )
        if not same_with_response:
            return Response(
                response=response, status=200, mimetype='application/json'
            )

        return Response(
            response=response, status=status, mimetype='application/json'
        )
