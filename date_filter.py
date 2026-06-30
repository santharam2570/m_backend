import calendar
import datetime
from datetime import date, timedelta

from pytz import timezone

DATE_FORMAT1 = '%d/%m/%Y'
DATE_FORMAT2 = '%H:%M %p'
DATE_FORMAT3 = '%Y-%m-%d %H:%M:%S'
DATE_FORMAT = '%Y-%m-%d %H:%M:%S.%f'
DATE_FORMAT4 = '%Y-%m-%d %H:%M:%S'


class DateFilter:
    @staticmethod
    def get_offset_date(offset):
        today_utc = datetime.datetime.now(timezone('UTC')).date()
        return today_utc + timedelta(hours=offset)

    @staticmethod
    def date_range_filter(option_id, user_id, org_id, custom_start=None, custom_end=None):
        from mongodb import MongoAPI

        offset = MongoAPI.commontimeset(user_id, org_id)
        today = DateFilter.get_offset_date(offset)

        if option_id == 'today':
            start_date = today
            end_date = today
        elif option_id == 'yesterday':
            start_date = today - timedelta(days=1)
            end_date = today - timedelta(days=1)
        elif option_id == 'this_week':
            start_date = today - timedelta(days=today.weekday())
            end_date = today
        elif option_id == 'last_week':
            end_date = today - timedelta(days=(today.weekday() + 1) % 7)
            start_date = end_date - timedelta(days=6)
        elif option_id == 'this_month':
            start_date = today.replace(day=1)
            _, last_day = calendar.monthrange(today.year, today.month)
            end_date = today.replace(day=last_day)
        elif option_id == 'last_month':
            last_month_end = today.replace(day=1) - timedelta(days=1)
            start_date = last_month_end.replace(day=1)
            end_date = last_month_end
        elif option_id == 'last_7_days':
            start_date = today - timedelta(days=6)
            end_date = today
        elif option_id == 'last_30_days':
            start_date = today - timedelta(days=29)
            end_date = today
        elif option_id == 'last_90_days':
            start_date = today - timedelta(days=89)
            end_date = today
        elif option_id == 'this_quarter':
            quarter = (today.month - 1) // 3 + 1
            start_month = 3 * (quarter - 1) + 1
            start_date = today.replace(month=start_month, day=1)
            if start_month + 3 > 12:
                end_date = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                end_date = today.replace(month=start_month + 3, day=1) - timedelta(days=1)
        elif option_id == 'last_quarter':
            quarter = (today.month - 1) // 3 + 1
            if quarter == 1:
                year = today.year - 1
                start_month = 10
            else:
                year = today.year
                start_month = 3 * (quarter - 2) + 1
            start_date = today.replace(year=year, month=start_month, day=1)
            if start_month + 3 > 12:
                end_date = start_date.replace(year=year + 1, month=1, day=1) - timedelta(days=1)
            else:
                end_date = start_date.replace(month=start_month + 3, day=1) - timedelta(days=1)
        elif option_id == 'this_year':
            start_date = today.replace(month=1, day=1)
            end_date = today.replace(month=12, day=31)
        elif option_id == 'custom' and custom_start and custom_end:
            if isinstance(custom_start, str):
                start_date = datetime.datetime.strptime(custom_start, '%Y-%m-%d').date()
            else:
                start_date = custom_start
            if isinstance(custom_end, str):
                end_date = datetime.datetime.strptime(custom_end, '%Y-%m-%d').date()
            else:
                end_date = custom_end
        else:
            return None, None

        date_from = datetime.datetime.combine(start_date, datetime.time.min)
        date_to = datetime.datetime.combine(end_date, datetime.time.max)
        return date_from, date_to


def calculate_age(born):
    born_date = datetime.datetime.strptime(born, DATE_FORMAT1).date()
    today = date.today()
    days1 = (today - born_date).days
    if days1 == 0:
        return 'Today'
    if days1 == 1:
        return '1 Day'
    return f'{days1} Days'
