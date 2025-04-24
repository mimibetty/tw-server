from flask import Blueprint, abort, request

from app.schemas.things_to_do import ThingToDoSchema
from app.utils.response import APIResponse

bp = Blueprint('things_to_do', __name__, url_prefix='/things-to-do')


@bp.post('')
def create_things_to_do():
    try:
        schema = ThingToDoSchema()
        inputs = schema.load(request.json)
        return APIResponse.success(payload=inputs, status=201)
    except Exception as e:
        abort(500, str(e))
