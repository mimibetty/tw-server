from flask import Blueprint, request
from app.schemas.restaurants import RestaurantSchema
from app.utils.response import APIResponse

bp = Blueprint('restaurants', __name__, url_prefix='/restaurants')

@bp.post('')
def create_restaurant():
    schema = RestaurantSchema()
    inputs = schema.load(request.json)
    return APIResponse.success(data=inputs, status=201)
