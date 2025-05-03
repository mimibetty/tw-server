from app.extensions import ma
from app.postgres import UserModel


class UserProfileSchema(ma.SQLAlchemyAutoSchema):
    class Meta:
        model = UserModel
        load_instance = True
        exclude = ('password',)
