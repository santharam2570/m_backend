"""Seed countries and states reference data for the lead address dropdowns."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import initialize_db
from models import Countries, States

COUNTRIES = [
    {'name': 'India', 'code': 'IN'},
    {'name': 'United States', 'code': 'US'},
    {'name': 'United Kingdom', 'code': 'GB'},
    {'name': 'Canada', 'code': 'CA'},
    {'name': 'Australia', 'code': 'AU'},
    {'name': 'United Arab Emirates', 'code': 'AE'},
    {'name': 'Singapore', 'code': 'SG'},
]

INDIA_STATES = [
    'Andhra Pradesh',
    'Arunachal Pradesh',
    'Assam',
    'Bihar',
    'Chhattisgarh',
    'Goa',
    'Gujarat',
    'Haryana',
    'Himachal Pradesh',
    'Jharkhand',
    'Karnataka',
    'Kerala',
    'Madhya Pradesh',
    'Maharashtra',
    'Manipur',
    'Meghalaya',
    'Mizoram',
    'Nagaland',
    'Odisha',
    'Punjab',
    'Rajasthan',
    'Sikkim',
    'Tamil Nadu',
    'Telangana',
    'Tripura',
    'Uttar Pradesh',
    'Uttarakhand',
    'West Bengal',
    'Andaman and Nicobar Islands',
    'Chandigarh',
    'Dadra and Nagar Haveli and Daman and Diu',
    'Delhi',
    'Jammu and Kashmir',
    'Ladakh',
    'Lakshadweep',
    'Puducherry',
]

US_STATES = [
    'Alabama', 'Alaska', 'Arizona', 'Arkansas', 'California', 'Colorado',
    'Connecticut', 'Delaware', 'Florida', 'Georgia', 'Hawaii', 'Idaho',
    'Illinois', 'Indiana', 'Iowa', 'Kansas', 'Kentucky', 'Louisiana',
    'Maine', 'Maryland', 'Massachusetts', 'Michigan', 'Minnesota',
    'Mississippi', 'Missouri', 'Montana', 'Nebraska', 'Nevada',
    'New Hampshire', 'New Jersey', 'New Mexico', 'New York',
    'North Carolina', 'North Dakota', 'Ohio', 'Oklahoma', 'Oregon',
    'Pennsylvania', 'Rhode Island', 'South Carolina', 'South Dakota',
    'Tennessee', 'Texas', 'Utah', 'Vermont', 'Virginia', 'Washington',
    'West Virginia', 'Wisconsin', 'Wyoming',
]

STATES_BY_COUNTRY = {
    'India': INDIA_STATES,
    'United States': US_STATES,
}


def seed_countries():
    created = 0
    for country in COUNTRIES:
        if Countries.objects(name=country['name']).first():
            continue
        Countries(name=country['name'], code=country['code']).save()
        created += 1
    return created


def seed_states():
    created = 0
    for country_name, state_names in STATES_BY_COUNTRY.items():
        for state_name in state_names:
            if States.objects(name=state_name, country=country_name).first():
                continue
            States(name=state_name, country=country_name).save()
            created += 1
    return created


if __name__ == '__main__':
    initialize_db()
    countries_added = seed_countries()
    states_added = seed_states()
    print(f'Seeded {countries_added} countries and {states_added} states.')
