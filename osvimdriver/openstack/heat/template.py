
import re
import yaml
from ignition.utils.propvaluemap import PropValueMap

PUBLIC_KEY_SUFFIX = '_public'
PRIVATE_KEY_SUFFIX = '_private'

class HeatInputUtil:

    def filter_used_properties(self, heat_template_str, original_properties):
        heat_tpl = yaml.safe_load(heat_template_str)
        used_properties = {}
        if 'parameters' in heat_tpl:
            parameters = heat_tpl['parameters']
            if isinstance(original_properties, PropValueMap):
                return self.__filter_from_propvaluemap(parameters, original_properties)
            else:
                return self.__filter_from_dictionary(parameters, original_properties)
        return used_properties

    def __filter_from_dictionary(self, parameters, properties_dict):
        used_properties = {}
        for k, v in parameters.items():
            if k in properties_dict:
                used_properties[k] = properties_dict[k]
        return used_properties
    
    def filter_password_from_dictionary(self, heat_template_str):
        heat_tpl = yaml.safe_load(heat_template_str)
        if 'resources' in heat_tpl:
            resources = heat_tpl['resources'] 
            user_data = resources['apache_server']['properties']['user_data']
            regex = re.compile('{0}(.*?){1}'.format('password:', '\\n'), flags=re.DOTALL | re.IGNORECASE)
            data_list = re.findall(regex, user_data)
            if len(data_list) > 0:
                for data in data_list:
                    rep = '*' * len(data)
                    masked_value = 'password:' + rep + '\\n'
                    heat_template_str = re.sub(regex, masked_value, heat_template_str)
        return heat_template_str

    def __filter_from_propvaluemap(self, parameters, prop_value_map):
        used_properties = {}
        for param_name, param_def in parameters.items():
            if param_name in prop_value_map:
                used_properties[param_name] = self.__extract_property_from_value_map(prop_value_map, param_name)
            elif param_name.endswith(PUBLIC_KEY_SUFFIX):
                key_name = param_name[:len(param_name)-len(PUBLIC_KEY_SUFFIX)]
                if key_name in prop_value_map:
                    full_value = prop_value_map.get_value_and_type(key_name)
                    if full_value.get('type') == 'key' and 'publicKey' in full_value:
                        used_properties[param_name] = full_value.get('publicKey')
            elif param_name.endswith(PRIVATE_KEY_SUFFIX):
                key_name = param_name[:len(param_name)-len(PRIVATE_KEY_SUFFIX)]
                if key_name in prop_value_map:
                    full_value = prop_value_map.get_value_and_type(key_name)
                    if full_value.get('type') == 'key' and 'privateKey' in full_value:
                        used_properties[param_name] = full_value.get('privateKey')
        return used_properties

    def __extract_property_from_value_map(self, prop_value_map, property_name):
        full_value = prop_value_map.get_value_and_type(property_name)
        if full_value.get('type') == 'key':
            return full_value.get('keyName')
        else:
            return prop_value_map[property_name]

