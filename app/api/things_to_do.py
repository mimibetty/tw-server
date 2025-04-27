from flask import Blueprint, request

from app.schemas.things_to_do import ThingToDoSchema
from app.utils.response import APIResponse

bp = Blueprint('things_to_do', __name__, url_prefix='/things-to-do')


@bp.post('')
def create_things_to_do():
    schema = ThingToDoSchema()
    inputs = schema.load(request.json)
    return APIResponse.success(data=inputs, status=201)
