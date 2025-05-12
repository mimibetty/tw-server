from marshmallow import fields, validate, pre_load, post_load
from app.extensions import ma


class RoundedFloat(fields.Float):
    """Custom field that rounds float values to a specified number of decimal places"""

    def __init__(self, decimals=5, **kwargs):
        self.decimals = decimals
        super().__init__(**kwargs)

    def _serialize(self, value, attr, obj, **kwargs):
        if value is None:
            return None
        return round(float(value), self.decimals)

    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        if value is None:
            return None
        return round(float(value), self.decimals)


class CitySchema(ma.Schema):
    """Schema for city information"""
    name = fields.String()
    postalCode = fields.String()


class AddressSchema(ma.Schema):
    """Schema for structured address"""
    street = fields.String()
    city = fields.Nested(CitySchema)


class HotelSchema(ma.Schema):
    # Core required fields
    name = fields.String(required=True)
    longitude = fields.Float(required=True)
    latitude = fields.Float(required=True)

    # Important information fields
    address = fields.Nested(AddressSchema, allow_none=True)
    description = fields.String(allow_none=True, default='')
    phone = fields.String(allow_none=True, default='')
    website = fields.String(allow_none=True, default='')
    email = fields.String(allow_none=True, default='')

    # Hotel specific fields
    hotelClass = fields.Float(
        allow_none=True
    )  # Kept for schema compatibility but stored as relationship
    priceRange = fields.String(allow_none=True)
    priceLevel = fields.String(
        allow_none=True
    )  # Kept for schema compatibility but stored as relationship
    numberOfRooms = fields.Integer(allow_none=True)
    aiReviewsSummary = fields.String(allow_none=True)
    rawRanking = RoundedFloat(allow_none=True, decimals=5)

    # Media fields
    image = fields.String(allow_none=True, default='')
    photos = fields.List(fields.String(), allow_none=True, default=list)

    # Special features
    travelerChoiceAward = fields.Boolean(default=False)

    # Relationship fields (stored as separate nodes)
    amenities = fields.List(fields.String(), allow_none=True, default=list)

    # These fields will be added by the GET API from relationship data
    priceLevels = fields.List(
        fields.String(), load_only=False, dump_only=True
    )
    hotelClasses = fields.List(
        fields.String(), load_only=False, dump_only=True
    )

    # Rating data
    ratingHistogram = fields.List(
        fields.Integer(), allow_none=True, default=list
    )

    # Fields we're keeping for backwards compatibility
    # webUrl = fields.String(allow_none=True)
    # localName = fields.String(allow_none=True)
    # whatsAppRedirectUrl = fields.String(allow_none=True)
    newRatingHistogram = fields.List(fields.Integer(), allow_none=True)

    @pre_load
    def process_input(self, data, **kwargs):
        """Pre-process input data before validation"""
        # Handle rating histogram conversion if needed
        if 'ratingHistogram' in data:
            if isinstance(data['ratingHistogram'], dict):
                # If it's a dictionary format like {count1: 10, count2: 20, ...}
                rh = data['ratingHistogram']
                data['ratingHistogram'] = [
                    rh.get('count1', 0),
                    rh.get('count2', 0),
                    rh.get('count3', 0),
                    rh.get('count4', 0),
                    rh.get('count5', 0),
                ]
            elif not isinstance(data['ratingHistogram'], list):
                # If it's not a list or dict, set to empty list
                data['ratingHistogram'] = []
        
        # For backward compatibility with rating_histogram
        if 'rating_histogram' in data and 'ratingHistogram' not in data:
            if isinstance(data['rating_histogram'], list):
                data['ratingHistogram'] = data.pop('rating_histogram')
            else:
                # If rating_histogram is not a list, initialize empty list
                data.pop('rating_histogram')
                data['ratingHistogram'] = []

        # Handle address conversion to structured format
        if 'address' in data and isinstance(data['address'], str):
            street = data['address']
            # Extract city information
            city_name = "Da Nang"
            postal_code = "550000"
            
            # Clean up the address by removing city/postal code suffixes
            suffixes = [
                f', {city_name} {postal_code} Vietnam',
                f', {city_name} Vietnam',
                f'{city_name} {postal_code} Vietnam',
                f'{city_name} Vietnam',
            ]
            for suffix in suffixes:
                if street.endswith(suffix):
                    street = street[: -len(suffix)].strip()
                    break

            # Create structured address
            data['address'] = {
                'street': street,
                'city': {
                    'name': city_name,
                    'postalCode': postal_code
                }
            }

        # Convert travelerChoiceAward to boolean
        if 'travelerChoiceAward' in data:
            data['travelerChoiceAward'] = bool(data['travelerChoiceAward'])

        # Convert hotelClass to float if it's a string
        if 'hotelClass' in data and data['hotelClass'] is not None:
            try:
                data['hotelClass'] = float(data['hotelClass'])
            except (ValueError, TypeError):
                # If conversion fails, set to None
                data['hotelClass'] = None

        return data
