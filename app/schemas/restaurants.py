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
    open = fields.String()
    close = fields.String()


class HoursSchema(ma.Schema):
    monday = fields.Nested(SimplifiedHourSchema, allow_none=True)
    tuesday = fields.Nested(SimplifiedHourSchema, allow_none=True)
    wednesday = fields.Nested(SimplifiedHourSchema, allow_none=True)
    thursday = fields.Nested(SimplifiedHourSchema, allow_none=True)
    friday = fields.Nested(SimplifiedHourSchema, allow_none=True)
    saturday = fields.Nested(SimplifiedHourSchema, allow_none=True)
    sunday = fields.Nested(SimplifiedHourSchema, allow_none=True)
    timezone = fields.String(allow_none=True)


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

    # Place type identifier
    type = fields.String(dump_only=True, default="RESTAURANT")

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

        # Process hours from weekRanges format to day-based format
        if 'hours' in data and data['hours'] and 'weekRanges' in data['hours']:
            weekRanges = data['hours']['weekRanges']
            timezone = data['hours'].get('timezone')
            
            # Create new hours structure
            new_hours = {
                'timezone': timezone
            }
            
            # Map index to day name
            day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
            
            # Convert each day's hours
            for i, day_ranges in enumerate(weekRanges):
                if i < len(day_names) and day_ranges:
                    # Take the first time slot for each day (most restaurants have just one slot per day)
                    time_slot = day_ranges[0] if day_ranges else None
                    if time_slot:
                        new_hours[day_names[i]] = {
                            'open': time_slot.get('openHours', ''),
                            'close': time_slot.get('closeHours', '')
                        }
            
            # Replace the old hours structure with our new one
            data['hours'] = new_hours

        # Convert travelerChoiceAward to boolean
        if 'travelerChoiceAward' in data:
            data['travelerChoiceAward'] = bool(data['travelerChoiceAward'])

        return data
