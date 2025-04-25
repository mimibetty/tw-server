class APIResponse:
    @staticmethod
    def success(data=None, status: int = 200):
        """Return a success response."""
        import json

        from flask import Response

        response = json.dumps({'data': data, 'success': True}, sort_keys=True)
        return Response(
            response=response, status=status, mimetype='application/json'
        )

    @staticmethod
    def error(error, status: int):
        """Return an error response."""
        import json

        from flask import Response

        response = json.dumps(
            {'error': error, 'success': False}, sort_keys=True
        )
        return Response(
            response=response, status=status, mimetype='application/json'
        )

    @staticmethod
    def paginate(data: list, page: int, per_page: int, total_records: int):
        """Return a paginated response."""
        import json

        from flask import Response

        total_pages = (total_records + per_page - 1) // per_page
        next_page = page + 1 if page < total_pages else None
        prev_page = page - 1 if page > 1 else None
        response = json.dumps(
            {
                'data': data,
                'pagination': {
                    'total_records': total_records,
                    'current_page': page,
                    'total_pages': total_pages,
                    'per_page': per_page,
                    'next_page': next_page,
                    'prev_page': prev_page,
                },
                'success': True,
            },
            sort_keys=True,
        )
        return Response(
            response=response, status=200, mimetype='application/json'
        )
