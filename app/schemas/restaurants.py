from marshmallow import fields, pre_load

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


class SimplifiedHourSchema(ma.Schema):
    openHours = fields.String()
    closeHours = fields.String()


class HoursSchema(ma.Schema):
    weekRanges = fields.List(fields.List(fields.Nested(SimplifiedHourSchema)))
    timezone = fields.String()


class CitySchema(ma.Schema):
    """Schema for city information"""
    name = fields.String()
    postalCode = fields.String()


class AddressSchema(ma.Schema):
    """Schema for structured address"""
    street = fields.String()
    city = fields.Nested(CitySchema)


class RestaurantSchema(ma.Schema):
    # Core required fields
    name = fields.String(required=True)
    longitude = fields.Float(required=True)
    latitude = fields.Float(required=True)

    # Basic information
    description = fields.String(allow_none=True, default='')
    phone = fields.String(allow_none=True, default='')
    address = fields.Nested(AddressSchema, allow_none=True)
    email = fields.String(allow_none=True, default='')

    # Web details
    website = fields.String(allow_none=True, default='')
    menuWebUrl = fields.String(allow_none=True, default='')

    # Main features
    dishes = fields.List(fields.String(), default=list)
    features = fields.List(
        fields.String(), default=list
    )  # Used as amenities in the graph
    dietaryRestrictions = fields.List(fields.String(), default=list)

    # Relationship data stored as separate nodes
    mealTypes = fields.List(fields.String(), default=list)
    cuisines = fields.List(fields.String(), default=list)
    priceLevel = fields.String(allow_none=True, default='')

    # Media
    image = fields.String(allow_none=True, default='')
    photos = fields.List(fields.String(), default=list)

    # Nested data
    hours = fields.Nested(HoursSchema, allow_none=True)

    # Ratings and awards
    ratingHistogram = fields.List(fields.Integer(), default=list)
    newRatingHistogram = fields.List(fields.Integer(), allow_none=True)
    rawRanking = RoundedFloat(decimals=5, allow_none=True)
    travelerChoiceAward = fields.Boolean(default=False)

    # These fields will be added by the GET API from relationship data
    priceLevels = fields.List(fields.String(), dump_only=True)
    amenities = fields.List(fields.String(), dump_only=True)

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

        # Process hours to only include openHours and closeHours
        if 'hours' in data and data['hours'] and 'weekRanges' in data['hours']:
            weekRanges = data['hours']['weekRanges']
            simplified_weekRanges = []

            for day_ranges in weekRanges:
                simplified_day_ranges = []
                for time_range in day_ranges:
                    simplified_time_range = {
                        'openHours': time_range.get('openHours', ''),
                        'closeHours': time_range.get('closeHours', ''),
                    }
                    simplified_day_ranges.append(simplified_time_range)
                simplified_weekRanges.append(simplified_day_ranges)

            data['hours']['weekRanges'] = simplified_weekRanges

        # Convert travelerChoiceAward to boolean
        if 'travelerChoiceAward' in data:
            data['travelerChoiceAward'] = bool(data['travelerChoiceAward'])

        return data
