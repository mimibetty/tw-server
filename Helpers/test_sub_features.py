import os
import sys

# Add the project root to the Python path to allow for imports from the 'app' module
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Now that the path is correctly set, we can import the utility functions
from app.utils import get_all_subcategories, get_all_subtypes


def main():
    """
    Main function to test fetching all subtypes and subcategories.
    """
    print('--- Testing get_all_subtypes() ---')
    try:
        subtypes = get_all_subtypes()
        if subtypes:
            print(f'Successfully fetched {len(subtypes)} subtypes.')
            # Print a sample of the results
            print('Sample:', subtypes)
        else:
            print('No subtypes were found.')

    except Exception as e:
        print(f'An error occurred while fetching subtypes: {e}')

    print('\\n' + '=' * 50 + '\\n')

    print('--- Testing get_all_subcategories() ---')
    try:
        subcategories = get_all_subcategories()
        if subcategories:
            print(f'Successfully fetched {len(subcategories)} subcategories.')
            # Print a sample of the results
            print('Sample:', subcategories)
        else:
            print('No subcategories were found.')

    except Exception as e:
        print(f'An error occurred while fetching subcategories: {e}')


if __name__ == '__main__':
    main()
