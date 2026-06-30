import json

from bson import json_util
from uuid import uuid1


class Uid:
    @staticmethod
    def generateUUID():
        return str(uuid1())

    @staticmethod
    def fix_array_role(info):
        if not info:
            return {}
        if isinstance(info, dict) and 'id' in info:
            return info
        settings = {}
        for key, value in info.items():
            if isinstance(value, dict) and '$oid' in value:
                settings[key] = str(value['$oid'])
            elif key == '_id' and value is not None:
                settings['id'] = str(value)
            else:
                settings[key] = value
        if 'id' not in settings and '_id' in settings:
            settings['id'] = settings['_id']
        return settings

    @staticmethod
    def fix_array(info):
        item1 = []
        for item in info:
            for key, value in item.items():
                if not isinstance(value, dict) or len(value) != 1:
                    continue
                (subkey, subvalue), = value.items()
                if not subkey.startswith('$'):
                    continue
                elif key != 'password':
                    item[key] = subvalue
            item1.append(item)
        return item1

    @staticmethod
    def fix_array3(info):
        if not info:
            return {}
        if not isinstance(info, dict):
            return info
        result = json.loads(json_util.dumps(info))
        if '_id' in result:
            oid = result['_id']
            if isinstance(oid, dict) and '$oid' in oid:
                result['_id'] = oid['$oid']
            else:
                result['_id'] = str(oid)
        return result

    @staticmethod
    def fix_array_multiple(info):
        if not info:
            return {}
        if not isinstance(info, dict):
            return info

        def normalize(value):
            if isinstance(value, dict):
                if set(value.keys()) == {'$oid'}:
                    return value['$oid']
                if set(value.keys()) == {'$date'}:
                    return value['$date']
                return {key: normalize(item) for key, item in value.items()}
            if isinstance(value, list):
                return [normalize(item) for item in value]
            return value

        return normalize(json.loads(json_util.dumps(info)))

    @staticmethod
    def fix_array5(info):
        if not info:
            return {}
        if not isinstance(info, dict):
            return info
        result = dict(info)
        if 'user_id' not in result:
            if 'id' in result:
                result['user_id'] = result['id']
            elif '_id' in result:
                result['user_id'] = str(result['_id'])
        return result
